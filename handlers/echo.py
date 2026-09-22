"""Echo handler - replies with the user's own text, entity-escaped."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.formatting import code, expandable_blockquote, italic
from bot.keyboards import make_home_keyboard
from bot.nav import NavState
from bot.texts import Messages

router = Router()

MAX_ECHO_LENGTH = 3000
ECHO_EXAMPLE = "Contoh: /echo halo *dunia*\nMarkup apa pun diperlakukan sebagai teks biasa."


@router.message(Command("echo"))
async def cmd_echo(message: Message, state: FSMContext) -> None:
    """Handle /echo command - prompt for text to echo."""
    await state.set_state(NavState.echo)
    await message.answer(
        f"{Messages.SCREEN_ECHO}\n"
        f"{italic('Kirim teks yang ingin Anda lihat kembali; teks akan di-escape.')}\n"
        f"{expandable_blockquote(ECHO_EXAMPLE)}",
        reply_markup=make_home_keyboard(),
    )


@router.message(StateFilter(NavState.echo))
async def handle_echo_text(message: Message, state: FSMContext) -> None:
    """Handle text while waiting for echo input."""
    await state.clear()
    raw = (message.text or "")[:MAX_ECHO_LENGTH]
    await message.answer(
        f"{Messages.ECHO_PREFIX} {code(raw)}",
        reply_markup=make_home_keyboard(),
    )
