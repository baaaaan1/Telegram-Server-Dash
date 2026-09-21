"""Common handlers: /start, /help, /cancel.

Authentication, lockout, and rate limiting are enforced by
:class:`bot.middleware.AccessMiddleware`, so handlers only deal with UX.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.services import Services
from bot.texts import Messages

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, services: Services) -> None:
    """Handle /start command - greet and show main menu."""
    await state.clear()
    await message.answer(Messages.WELCOME_ID, reply_markup=make_home_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message, services: Services) -> None:
    """Handle /help command - show help text."""
    help_text = (
        Messages.HELP_TEXT_ID
        if services.settings.environment != "production"
        else Messages.HELP_TEXT_EN
    )
    await message.answer(help_text, reply_markup=make_home_keyboard())


@router.message(F.text == Messages.MENU_HELP)
async def btn_help(message: Message, services: Services) -> None:
    """Handle the Help menu button."""
    await cmd_help(message, services)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Handle Cancel - clear state and return to home."""
    await state.clear()
    await message.answer(Messages.ACTION_CANCELLED, reply_markup=make_home_keyboard())
