"""Common handlers: /start, /help, /cancel.

Authentication, lockout, and rate limiting are enforced by
:class:`bot.middleware.AccessMiddleware`, so handlers only deal with UX: the
welcome screen, the paged help panel, and the always-available escape hatch.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.render import help_report, home_panel, send_panel, send_report
from bot.services import Services, log_user_action
from bot.texts import Messages

router = Router()


def _use_indonesian(services: Services) -> bool:
    """Development and staging deployments default to the Indonesian copy."""
    return services.settings.environment != "production"


async def send_home(message: Message, state: FSMContext, services: Services) -> None:
    """Send the welcome screen: Reply Keyboard message plus the quick inline panel."""
    await state.clear()
    catalog = services.settings.custom_emoji_ids
    await message.answer(
        Messages.WELCOME_ID if _use_indonesian(services) else Messages.WELCOME_EN,
        reply_markup=make_home_keyboard(catalog),
    )
    await send_panel(message, home_panel(), catalog=catalog)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, services: Services) -> None:
    """Handle /start command - greet and show the main menu."""
    await send_home(message, state, services)


@router.message(Command("help"))
async def cmd_help(message: Message, services: Services) -> None:
    """Handle /help command - show the paged help panel."""
    catalog = services.settings.custom_emoji_ids
    report = help_report(1, indonesian=_use_indonesian(services))
    await send_report(message, report, reply_markup=make_home_keyboard(catalog), catalog=catalog)
    await log_user_action(services, message, command="/help", action="help.view")


@router.message(F.text == Messages.MENU_HELP)
async def btn_help(message: Message, services: Services) -> None:
    """Handle the Help menu button."""
    await cmd_help(message, services)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, services: Services) -> None:
    """Handle Cancel - clear state and return to home."""
    await state.clear()
    await message.answer(Messages.ACTION_CANCELLED, reply_markup=make_home_keyboard())
    await log_user_action(services, message, command="/cancel", action="nav.cancel")
