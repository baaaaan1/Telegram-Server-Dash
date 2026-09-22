"""Entity-contract tests for complete rendered reports.

Handlers assemble reports from live host data, so these tests feed hostile
values (markup, quotes, long commands) through every screen and both view modes
and assert that the output is still valid Telegram HTML inside the documented
length and entity limits.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot import formatting as fmt
from bot.inline import DEFAULT_VIEW, DETAIL_VIEW, OverlayCallback, build_overlay
from bot.render import ScreenReport, build_markup, paginate
from config.servers import ServerConfig, Transport
from core.probe import (
    CpuDetails,
    DiskDetails,
    MemoryDetails,
    NetworkDetails,
    ServerMetrics,
)
from core.ssh import CommandResult
from handlers.monitor import MONITOR_SCREENS, render_screen_report
from handlers.status import render_ping_report, render_status_report

INJECTION = "<b>evil</b> & <script>alert('x')</script>"
HOSTILE_SERVERS = {
    f"vps-{index:02d}": ServerConfig(
        name=f"vps-{index:02d}",
        group=INJECTION,
        transport=Transport.LOCAL,
    )
    for index in range(1, 8)
}
ONLINE_METRICS = ServerMetrics(
    online=True,
    hostname=INJECTION,
    uptime="up 5 days",
    load="0.10 0.20 0.30",
    memory="128/1024 MiB (13%)",
    disk="4G/20G (20%)",
    latency_ms=12.5,
)


@pytest.fixture
def fake_connections():
    """Connection doubles accepted by both the status and monitor renderers."""
    connection = SimpleNamespace(
        close=AsyncMock(),
        run=AsyncMock(
            return_value=CommandResult(stdout="42", stderr="", exit_code=0, duration=0.01)
        ),
    )
    return {"close": connection.close, "connection": connection}


def connection_pool(connections, names):
    """Pool mapping for the requested server names."""
    return dict.fromkeys(names, connections["connection"])


def assert_telegram_safe(report: ScreenReport):
    """Every report must respect the Bot API text limits and grammar."""
    assert report.text
    assert fmt.validate_html(report.text) == []
    assert fmt.tag_count(report.text) <= fmt.MAX_MESSAGE_ENTITIES
    assert len(report.text) <= fmt.MAX_MESSAGE_LENGTH
    assert report.copy_text
    assert fmt.validate_html(report.text) == []


class TestStatusReports:
    """Status and ping dashboards."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("detail", [False, True])
    @pytest.mark.parametrize("reveal", [False, True])
    async def test_status_report_is_safe_and_paginated(self, fake_connections, detail, reveal):
        with (
            patch(
                "handlers.status.create_ssh_pool",
                lambda servers: connection_pool(fake_connections, servers),
            ),
            patch("handlers.status.collect_server_metrics", AsyncMock(return_value=ONLINE_METRICS)),
        ):
            report = await render_status_report(
                servers=HOSTILE_SERVERS,
                detail=detail,
                reveal=reveal,
            )

        assert_telegram_safe(report)
        assert report.pages == 3
        assert report.page == 1
        assert report.attention is False
        assert report.text.count("🟢 <b>vps-") == 3
        assert report.text.count("<i>Hostname</i>") == 3
        assert INJECTION not in report.text

    @pytest.mark.asyncio
    async def test_status_pagination_walks_pages(self, fake_connections):
        servers = HOSTILE_SERVERS

        with (
            patch(
                "handlers.status.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.status.collect_server_metrics", AsyncMock(return_value=ONLINE_METRICS)),
        ):
            pages = [await render_status_report(servers=servers, page=page) for page in range(1, 4)]

        assert [report.page for report in pages] == [1, 2, 3]
        assert {report.pages for report in pages} == {3}
        for report in pages:
            assert_telegram_safe(report)

    @pytest.mark.asyncio
    async def test_offline_server_flags_attention(self, fake_connections):
        offline = ServerMetrics(online=False, latency_ms=-1)
        markup_report = ScreenReport(screen="status", text="x")

        with (
            patch(
                "handlers.status.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.status.collect_server_metrics", AsyncMock(return_value=offline)),
        ):
            report = await render_status_report(servers=HOSTILE_SERVERS)

        assert report.attention is True
        overlay = build_overlay(report.payload(), attention=True)
        assert overlay.inline_keyboard[0][0].style == "danger"
        assert markup_report.payload().screen == "status"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("reveal", [False, True])
    async def test_ping_report_is_safe(self, fake_connections, reveal):
        with (
            patch(
                "handlers.status.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.status.connectivity_test", AsyncMock(return_value=True)),
            patch("handlers.status.latency_test", AsyncMock(return_value=0.25)),
        ):
            report = await render_ping_report(servers=HOSTILE_SERVERS, reveal=reveal)

        assert_telegram_safe(report)
        assert "0.25 ms" in report.text
        assert report.screen == "ping"

    @pytest.mark.asyncio
    async def test_ping_failure_is_reported_without_leaking(self, fake_connections):
        with (
            patch(
                "handlers.status.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.status.connectivity_test", AsyncMock(return_value=False)),
            patch("handlers.status.latency_test", AsyncMock(side_effect=AssertionError)),
        ):
            report = await render_ping_report(servers=HOSTILE_SERVERS)

        assert_telegram_safe(report)
        assert report.attention is True
        assert "koneksi gagal" in report.text

    @pytest.mark.asyncio
    async def test_collection_errors_degrade_to_offline_blocks(self, fake_connections):
        with (
            patch(
                "handlers.status.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.status.collect_server_metrics", AsyncMock(side_effect=OSError("boom"))),
        ):
            report = await render_status_report(servers=HOSTILE_SERVERS)

        assert_telegram_safe(report)
        assert report.attention is True
        assert "tidak dapat dijangkau" in report.text


class TestMonitorReports:
    """CPU, memory, network, disk, and process dashboards."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("screen", sorted(MONITOR_SCREENS))
    @pytest.mark.parametrize("detail", [False, True])
    async def test_monitor_report_is_safe(self, fake_connections, screen, detail):
        cpu = CpuDetails(
            model=INJECTION,
            cores=8,
            usage_per_core=[10.5, 99.9, 55.0],
            overall_usage=42.0,
            top_processes=[{"pid": 1, "cpu": 99.9, "command": INJECTION}],
            temperature=INJECTION,
        )
        memory = MemoryDetails(
            total_mb=1024,
            used_mb=512,
            free_mb=256,
            available_mb=600,
            cached_mb=100,
            buffers_mb=50,
            swap_total_mb=2048,
            swap_used_mb=512,
            swap_free_mb=1536,
            top_processes=[{"pid": 2, "mem": 45.5, "command": INJECTION}],
        )
        network = NetworkDetails(
            interfaces=[
                {"name": INJECTION, "rx_bytes": 1024, "tx_bytes": 2048},
                {"name": "lo", "rx_bytes": 1, "tx_bytes": 1},
            ],
            total_rx_bytes=1024,
            total_tx_bytes=2048,
            active_connections=7,
            established_connections=3,
            listening_ports=[{"port": 22, "process": INJECTION}],
        )
        disk = DiskDetails(
            partitions=[
                {
                    "mount": INJECTION,
                    "use_percent": "42%",
                    "used": "4G",
                    "size": "20G",
                    "avail": "16G",
                    "device": INJECTION,
                }
            ],
            total_inodes=1000,
            used_inodes=250,
            io_stats=[{"device": INJECTION, "reads": 1, "writes": 2}],
        )

        with (
            patch(
                "handlers.monitor.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.monitor.collect_cpu_details", AsyncMock(return_value=cpu)),
            patch("handlers.monitor.collect_memory_details", AsyncMock(return_value=memory)),
            patch("handlers.monitor.collect_network_details", AsyncMock(return_value=network)),
            patch("handlers.monitor.collect_disk_details", AsyncMock(return_value=disk)),
        ):
            report = await render_screen_report(
                screen,
                servers=HOSTILE_SERVERS,
                detail=detail,
                reveal=True,
            )

        assert_telegram_safe(report)
        assert report.screen == screen
        assert INJECTION not in report.text
        assert report.detail is detail

    @pytest.mark.asyncio
    async def test_network_ports_are_hidden_until_revealed(self, fake_connections):
        network = NetworkDetails(
            interfaces=[],
            total_rx_bytes=0,
            total_tx_bytes=0,
            active_connections=0,
            established_connections=0,
            listening_ports=[{"port": 22, "process": "sshd"}],
        )

        with (
            patch(
                "handlers.monitor.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.monitor.collect_network_details", AsyncMock(return_value=network)),
        ):
            hidden = await render_screen_report("network", servers=HOSTILE_SERVERS, detail=True)
            shown = await render_screen_report(
                "network", servers=HOSTILE_SERVERS, detail=True, reveal=True
            )

        assert fmt.spoiler("sshd") in hidden.text
        assert fmt.spoiler("sshd") not in shown.text
        assert "sshd" in shown.text

    @pytest.mark.asyncio
    async def test_monitor_errors_are_isolated_per_server(self, fake_connections):
        with (
            patch(
                "handlers.monitor.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.monitor.collect_cpu_details", AsyncMock(side_effect=OSError("boom"))),
        ):
            report = await render_screen_report("cpu", servers=HOSTILE_SERVERS)

        assert_telegram_safe(report)
        assert report.attention is True


class TestReportMarkup:
    """The markup that ships with a report matches its state."""

    @pytest.mark.asyncio
    async def test_detail_markup_reflects_expanded_state(self, fake_connections):
        with (
            patch(
                "handlers.status.create_ssh_pool",
                lambda pool: connection_pool(fake_connections, pool),
            ),
            patch("handlers.status.collect_server_metrics", AsyncMock(return_value=ONLINE_METRICS)),
        ):
            compact = await render_status_report(servers=HOSTILE_SERVERS)
            detailed = await render_status_report(servers=HOSTILE_SERVERS, detail=True)

        compact_markup = build_markup(compact)
        detailed_markup = build_markup(detailed)

        compact_toggle = compact_markup.inline_keyboard[0][1]
        detailed_toggle = detailed_markup.inline_keyboard[0][1]
        assert compact_toggle.style == "primary"
        assert detailed_toggle.style == "success"
        assert OverlayCallback.parse(compact_toggle.callback_data).view == DETAIL_VIEW
        assert OverlayCallback.parse(detailed_toggle.callback_data).view == DEFAULT_VIEW

    def test_pagination_clamps_and_counts(self):
        names = [f"vps-{index}" for index in range(7)]
        first, page, pages = paginate(names, 1)
        last, last_page, _ = paginate(names, 99)

        assert (page, pages) == (1, 3)
        assert last_page == 3
        assert len(first) == 3
        assert len(last) == 1

    def test_help_reports_use_the_paged_overlay(self):
        from bot.render import help_report

        report = help_report(1)
        markup = build_markup(report)
        labels = [button.text for row in markup.inline_keyboard for button in row]

        assert "📚 Semua bagian" in labels
        assert report.pages == len(
            __import__("bot.texts", fromlist=["Messages"]).Messages.HELP_PAGES_ID
        )
