"""Common handlers: /start, /help, access control middleware."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.nav import NavState
from bot.texts import Messages
from config import AppSettings, load_settings

router = Router()


def _is_allowed(user_id: int, settings: AppSettings) -> bool:
    """Check if user ID is in allowed admin list."""
    return bool(settings.admin_user_ids) and user_id in settings.admin_user_ids


@router.message(F.text == Messages.BTN_HOME)
async def cmd_home(message: Message, bot: Bot) -> None:
    """Handle Home button - reset to main menu."""
    await message.answer(Messages.WELCOME_ID, reply_markup=make_home_keyboard())
    await message.answer(Messages.MENU_STATUS, reply_markup=make_home_keyboard())
    if hasattr(message, "bot") and hasattr(message.bot, "current_state"):
        try:
            await message.bot.current_state().clear()
        except Exception:
            pass


@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot) -> None:
    """Handle /start command - greet and show main menu."""
    settings, _ = load_settings()

    if settings.admin_user_ids and not _is_allowed(message.from_user.id, settings):
        await message.answer(Messages.ACCESS_DENIED)
        return

    await message.answer(Messages.WELCOME_ID, reply_markup=make_home_keyboard())
    if hasattr(message, "bot") and hasattr(message.bot, "current_state"):
        try:
            await message.bot.current_state().set_state(NavState.home)
        except Exception:
            pass


@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot) -> None:
    """Handle /help command - show help text."""
    settings, _ = load_settings()

    if settings.admin_user_ids and not _is_allowed(message.from_user.id, settings):
        await message.answer(Messages.ACCESS_DENIED)
        return

    help_text = (
        Messages.HELP_TEXT_ID if settings.environment != "production" else Messages.HELP_TEXT_EN
    )
    await message.answer(help_text, reply_markup=make_home_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot: Bot) -> None:
    """Handle Cancel - clear state and return to home."""
    await message.answer("✅ Dibatalkan", reply_markup=make_home_keyboard())
    try:
        await message.bot.current_state().clear()
    except Exception:
        pass


@router.message(F.text == Messages.BTN_CANCEL)
async def btn_cancel(message: Message, bot: Bot) -> None:
    """Handle Cancel button."""
    await cmd_cancel(message, bot)
