"""Status handler - server status overview."""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.nav import NavState
from bot.texts import Messages
from config import AppSettings, load_server_registry, load_settings

router = Router()


def _is_allowed(user_id: int, settings: AppSettings) -> bool:
    """Check if user ID is in allowed admin list."""
    return bool(settings.admin_user_ids) and user_id in settings.admin_user_ids


@router.message(Command("status"))
async def cmd_status(message: Message, bot: Bot) -> None:
    """Handle /status command - show server status summary."""
    settings, config_path = load_settings()

    if settings.admin_user_ids and not _is_allowed(message.from_user.id, settings):
        await message.answer(Messages.ACCESS_DENIED)
        return

    registry = load_server_registry(config_path)
    enabled = registry.get_enabled_servers()

    if not enabled:
        await message.answer(
            "ℹ️ Tidak ada server yang dikonfigurasi.", reply_markup=make_home_keyboard()
        )
        return

    lines = [Messages.STATUS_HEADER]
    for name, server in enabled.items():
        lines.append(f"📍 <b>{name}</b> ({server.group})")
        lines.append(f"   Host: {server.host}:{server.port}")

    lines.append("\nGunakan tombol di bawah untuk detail.")
    await message.answer("\n".join(lines), reply_markup=make_home_keyboard())

    try:
        await message.bot.current_state().set_state(NavState.status)
    except Exception:
        pass
