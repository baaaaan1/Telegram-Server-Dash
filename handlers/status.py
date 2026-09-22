"""Status handlers - server status and connectivity dashboards.

Each command sends one navigation header (Reply Keyboard) plus one report message
carrying the inline panel; the same ``render_*`` coroutines back the panel's
refresh/detail/reveal/pagination actions, so the message is re-rendered in place.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.formatting import (
    Entity,
    blockquote,
    entity,
    expandable_blockquote,
    italic,
    to_plain_text,
)
from bot.keyboards import make_home_keyboard
from bot.nav import push_screen
from bot.render import ScreenReport, paginate, send_report
from bot.services import Services, log_user_action
from bot.texts import Messages
from config import load_server_registry, load_settings
from config.servers import ServerConfig
from core.probe import collect_server_metrics, connectivity_test, latency_test
from core.ssh import create_ssh_pool

router = Router()
logger = logging.getLogger(__name__)

LATENCY_ATTENTION_MS = 300.0


def _enabled_servers() -> dict[str, ServerConfig]:
    """Load every enabled server from the registry (no message side effects)."""
    _settings, config_path = load_settings()
    return load_server_registry(config_path).get_enabled_servers()


async def _load_enabled_servers(message: Message) -> dict[str, ServerConfig] | None:
    """Load enabled servers, answering with the home keyboard when the list is empty."""
    enabled = _enabled_servers()
    if not enabled:
        await message.answer(Messages.REPORT_NO_SERVERS, reply_markup=make_home_keyboard())
        return None
    return enabled


async def _collect_status(
    servers: dict[str, ServerConfig],
    *,
    detail: bool = False,
    reveal: bool = False,
) -> tuple[list[Entity], bool]:
    """Collect status metrics; returns rendered blocks plus a degraded-host flag."""
    pool = create_ssh_pool(servers)
    blocks: list[Entity] = []
    attention = False
    try:
        for name, server in servers.items():
            connection = pool[name]
            try:
                metrics = await collect_server_metrics(connection)
            except Exception:
                logger.exception("Failed to collect metrics for server %s", name)
                metrics = None

            online = bool(metrics and metrics.online)
            lines = [Messages.server_line(name, online=online, group=server.group)]
            if not metrics or not metrics.online:
                attention = True
                lines.append(f"└ {Messages.REPORT_UNREACHABLE}")
                blocks.append(entity(*lines))
                continue

            lines.append(
                Messages.server_details(
                    metrics.hostname,
                    metrics.uptime,
                    metrics.load,
                    metrics.memory,
                    metrics.disk,
                    reveal=reveal,
                )
            )
            if metrics.latency_ms > LATENCY_ATTENTION_MS:
                attention = True
            if detail:
                lines.append(Messages.detail_row("Latensi", f"{metrics.latency_ms:.2f} ms"))
                lines.append(Messages.detail_row("Grup", server.group, icon="🗂️"))
            blocks.append(entity(*lines))
    finally:
        await asyncio.gather(
            *(connection.close() for connection in pool.values()), return_exceptions=True
        )
    return blocks, attention


async def render_status_report(
    *,
    servers: dict[str, ServerConfig] | None = None,
    detail: bool = False,
    reveal: bool = False,
    page: int = 1,
) -> ScreenReport:
    """Render the server status dashboard for one page of the registry."""
    available = _enabled_servers() if servers is None else servers
    if not available:
        return ScreenReport(screen="status", text=Messages.REPORT_NO_SERVERS)

    names, current, pages = paginate(list(available), page)
    subset = {name: available[name] for name in names}
    blocks, attention = await _collect_status(subset, detail=detail, reveal=reveal)

    lines = [Messages.report_heading("status", Messages.METHOD_STATUS_LINE)]
    if pages > 1:
        lines.append(Messages.REPORT_PAGE.format(page=current, pages=pages, total=len(available)))
    lines.extend(expandable_blockquote(block) if detail else blockquote(block) for block in blocks)

    text = "\n\n".join(lines)
    return ScreenReport(
        screen="status",
        text=text,
        page=current,
        pages=pages,
        detail=detail,
        reveal=reveal,
        attention=attention,
        copy_text=to_plain_text(text),
    )


async def _collect_ping(servers: dict[str, ServerConfig]) -> tuple[list[Entity], bool]:
    """Probe connectivity and latency; returns rendered blocks plus a failure flag."""
    pool = create_ssh_pool(servers)
    blocks: list[Entity] = []
    attention = False
    try:
        for name in servers:
            connection = pool[name]
            try:
                online = await connectivity_test(connection)
                latency = await latency_test(connection) if online else -1
            except Exception:
                logger.exception("Failed to ping server %s", name)
                online = False
                latency = -1

            head = Messages.server_line(name, online=online)
            if not online:
                attention = True
                blocks.append(entity(head, f"└ {italic('koneksi gagal')}"))
                continue
            if latency > LATENCY_ATTENTION_MS:
                attention = True
            blocks.append(entity(head, Messages.latency_row(latency, online=online)))
    finally:
        await asyncio.gather(
            *(connection.close() for connection in pool.values()), return_exceptions=True
        )
    return blocks, attention


async def render_ping_report(
    *,
    servers: dict[str, ServerConfig] | None = None,
    reveal: bool = False,
    page: int = 1,
) -> ScreenReport:
    """Render the connectivity dashboard for one page of the registry."""
    available = _enabled_servers() if servers is None else servers
    if not available:
        return ScreenReport(screen="ping", text=Messages.REPORT_NO_SERVERS)

    names, current, pages = paginate(list(available), page)
    subset = {name: available[name] for name in names}
    blocks, attention = await _collect_ping(subset)

    lines = [Messages.report_heading("ping", Messages.METHOD_PING_LINE)]
    if pages > 1:
        lines.append(Messages.REPORT_PAGE.format(page=current, pages=pages, total=len(available)))
    lines.extend(blockquote(block) for block in blocks)

    text = "\n\n".join(lines)
    return ScreenReport(
        screen="ping",
        text=text,
        page=current,
        pages=pages,
        detail=False,
        reveal=reveal,
        attention=attention,
        copy_text=to_plain_text(text),
    )


async def _send_status(message: Message) -> None:
    """Collect and send the status dashboard for the first page of servers."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return
    report = await render_status_report(servers=enabled)
    await send_report(message, report, reply_markup=make_home_keyboard())


async def _send_ping(message: Message) -> None:
    """Probe connectivity and send the ping dashboard for the first page."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return
    report = await render_ping_report(servers=enabled)
    await send_report(message, report, reply_markup=make_home_keyboard())


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext, services: Services) -> None:
    """Handle /status command."""
    await push_screen(state, "status")
    await _send_status(message)
    await log_user_action(services, message, command="/status", action="monitor.status")


@router.message(F.text == Messages.MENU_STATUS)
async def btn_status(message: Message, state: FSMContext, services: Services) -> None:
    """Handle the Status Server menu button."""
    await push_screen(state, "status")
    await _send_status(message)
    await log_user_action(services, message, command=Messages.MENU_STATUS, action="monitor.status")


@router.message(Command("ping"))
async def cmd_ping(message: Message, state: FSMContext, services: Services) -> None:
    """Handle /ping command."""
    await push_screen(state, "ping")
    await _send_ping(message)
    await log_user_action(services, message, command="/ping", action="monitor.ping")


@router.message(F.text == Messages.MENU_PING)
async def btn_ping(message: Message, state: FSMContext, services: Services) -> None:
    """Handle the Ping Server menu button."""
    await push_screen(state, "ping")
    await _send_ping(message)
    await log_user_action(services, message, command=Messages.MENU_PING, action="monitor.ping")
