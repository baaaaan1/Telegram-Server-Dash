"""Tests for server status and ping responses."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from config.servers import ServerConfig, Transport
from core.probe import ServerMetrics
from handlers.status import _send_ping, _send_status


@pytest.mark.asyncio
async def test_status_button_sends_collected_metrics():
    """The status action sends data instead of a loading placeholder."""
    message = SimpleNamespace(answer=AsyncMock())
    connection = SimpleNamespace(close=AsyncMock())
    enabled = {"local-vps": ServerConfig(name="local-vps", transport=Transport.LOCAL)}
    metrics = ServerMetrics(
        online=True,
        hostname="vps-01",
        uptime="up 2 days",
        load="0.10 0.20 0.30",
        memory="128/1024 MiB (13%)",
        disk="4G/20G (20%)",
        latency_ms=0.25,
    )

    with (
        patch("handlers.status._load_enabled_servers", AsyncMock(return_value=enabled)),
        patch("handlers.status.create_ssh_pool", return_value={"local-vps": connection}),
        patch("handlers.status.collect_server_metrics", AsyncMock(return_value=metrics)),
    ):
        await _send_status(message)

    response = message.answer.await_args.args[0]
    assert "vps-01" in response
    assert "128/1024 MiB" in response
    assert "4G/20G" in response


@pytest.mark.asyncio
async def test_ping_button_sends_connectivity_result():
    """The ping action reports connectivity for configured servers."""
    message = SimpleNamespace(answer=AsyncMock())
    connection = SimpleNamespace(close=AsyncMock())
    enabled = {"local-vps": ServerConfig(name="local-vps", transport=Transport.LOCAL)}

    with (
        patch("handlers.status._load_enabled_servers", AsyncMock(return_value=enabled)),
        patch("handlers.status.create_ssh_pool", return_value={"local-vps": connection}),
        patch("handlers.status.connectivity_test", AsyncMock(return_value=True)),
        patch("handlers.status.latency_test", AsyncMock(return_value=0.25)),
    ):
        await _send_ping(message)

    response = message.answer.await_args.args[0]
    assert "local-vps" in response
    assert "0.25 ms" in response
