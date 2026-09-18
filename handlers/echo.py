"""Echo handler - simple text echo."""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.nav import NavState
from bot.texts import Messages

router = Router()


@router.message(Command("echo"))
async def cmd_echo(message: Message, bot: Bot) -> None:
    """Handle /echo command - prompt for text to echo."""
    await message.answer(
        "✍️ Kirim teks yang ingin Anda echo setelah perintah ini.", reply_markup=make_home_keyboard()
    )
    try:
        await message.bot.current_state().set_state(NavState.echo)
    except Exception:
        pass


@router.message(StateFilter(NavState.echo))
async def handle_echo_text(message: Message, bot: Bot) -> None:
    """Handle text while waiting for echo input."""
    if message.text in [Messages.BTN_HOME, Messages.BTN_BACK, Messages.BTN_CANCEL]:
        await message.answer(Messages.WELCOME_ID, reply_markup=make_home_keyboard())
        try:
            await message.bot.current_state().set_state(NavState.home)
        except Exception:
            pass
        return

    await message.answer(
        f"{Messages.ECHO_PREFIX} <code>{message.text}</code>", reply_markup=make_home_keyboard()
    )
    try:
        await message.bot.current_state().set_state(NavState.home)
    except Exception:
        pass
