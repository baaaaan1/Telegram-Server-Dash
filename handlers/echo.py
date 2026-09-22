"""Echo handler - simple text echo."""

from __future__ import annotations

import html

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.nav import NavState
from bot.texts import Messages

router = Router()


@router.message(Command("echo"))
async def cmd_echo(message: Message, state: FSMContext) -> None:
    """Handle /echo command - prompt for text to echo."""
    await state.set_state(NavState.echo)
    await message.answer(
        "✍️ Kirim teks yang ingin Anda echo setelah perintah ini.",
        reply_markup=make_home_keyboard(),
    )


@router.message(StateFilter(NavState.echo))
async def handle_echo_text(message: Message, state: FSMContext) -> None:
    """Handle text while waiting for echo input."""
    await state.clear()
    await message.answer(
        f"{Messages.ECHO_PREFIX} <code>{html.escape(message.text or '')}</code>",
        reply_markup=make_home_keyboard(),
    )
