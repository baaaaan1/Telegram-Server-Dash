"""Status handler - server status overview."""

from __future__ import annotations

import asyncio
import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.texts import Messages
from config import AppSettings, load_server_registry, load_settings
from core.probe import collect_server_metrics, connectivity_test, latency_test
from core.ssh import create_ssh_pool

router = Router()
logger = logging.getLogger(__name__)


def _is_allowed(user_id: int, settings: AppSettings) -> bool:
    """Check if user ID is in allowed admin list."""
    return bool(settings.admin_user_ids) and user_id in settings.admin_user_ids


async def _load_enabled_servers(message: Message):
    """Load authorized settings and enabled servers for a message."""
    settings, config_path = load_settings()

    if not message.from_user or (
        settings.admin_user_ids and not _is_allowed(message.from_user.id, settings)
    ):
        await message.answer(Messages.ACCESS_DENIED)
        return None

    registry = load_server_registry(config_path)
    enabled = registry.get_enabled_servers()
    if not enabled:
        await message.answer(
            "ℹ️ Tidak ada server yang dikonfigurasi.", reply_markup=make_home_keyboard()
        )
        return None
    return enabled


async def _send_status(message: Message) -> None:
    """Collect and send status metrics for all enabled servers."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    pool = create_ssh_pool(enabled)
    lines = [Messages.STATUS_HEADER]
    try:
        for name, server in enabled.items():
            connection = pool[name]
            try:
                metrics = await collect_server_metrics(connection)
            except Exception:
                logger.exception("Failed to collect metrics for server %s", name)
                metrics = None

            safe_name = html.escape(name)
            safe_group = html.escape(server.group)
            if not metrics or not metrics.online:
                lines.append(f"🔴 <b>{safe_name}</b> ({safe_group})")
                lines.append("   Status: tidak dapat dijangkau")
                continue

            latency = f"{metrics.latency_ms:.2f} ms" if metrics.latency_ms >= 0 else "n/a"
            lines.extend(
                [
                    f"🟢 <b>{safe_name}</b> ({safe_group})",
                    f"   Hostname: <code>{html.escape(metrics.hostname)}</code>",
                    f"   Uptime: {html.escape(metrics.uptime)}",
                    f"   Load 1/5/15m: {html.escape(metrics.load)}",
                    f"   RAM: {html.escape(metrics.memory)}",
                    f"   Disk /: {html.escape(metrics.disk)}",
                    f"   Latensi: {latency}",
                ]
            )
    finally:
        await asyncio.gather(
            *(connection.close() for connection in pool.values()), return_exceptions=True
        )

    await message.answer("\n".join(lines), reply_markup=make_home_keyboard())


async def _send_ping(message: Message) -> None:
    """Test connectivity for all enabled servers."""
    enabled = await _load_enabled_servers(message)
    if not enabled:
        return

    pool = create_ssh_pool(enabled)
    lines = ["🟢 <b>Ping Server</b>\n"]
    try:
        for name in enabled:
            connection = pool[name]
            try:
                online = await connectivity_test(connection)
                latency = await latency_test(connection) if online else -1
            except Exception:
                logger.exception("Failed to ping server %s", name)
                online = False
                latency = -1

            safe_name = html.escape(name)
            if online:
                latency_text = f"{latency:.2f} ms" if latency >= 0 else "aktif"
                lines.append(f"🟢 <b>{safe_name}</b>: {latency_text}")
            else:
                lines.append(f"🔴 <b>{safe_name}</b>: koneksi gagal")
    finally:
        await asyncio.gather(
            *(connection.close() for connection in pool.values()), return_exceptions=True
        )

    await message.answer("\n".join(lines), reply_markup=make_home_keyboard())


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Handle /status command."""
    await _send_status(message)


@router.message(F.text == Messages.MENU_STATUS)
async def btn_status(message: Message) -> None:
    """Handle the Status Server menu button."""
    await _send_status(message)


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    """Handle /ping command."""
    await _send_ping(message)


@router.message(F.text == Messages.MENU_PING)
async def btn_ping(message: Message) -> None:
    """Handle the Ping Server menu button."""
    await _send_ping(message)
