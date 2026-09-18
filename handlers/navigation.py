"""Navigation handler - Home/Back/Cancel button routing."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.nav import NavContext
from bot.texts import Messages

router = Router()


@router.message(F.text == Messages.BTN_HOME)
async def btn_home(message: Message) -> None:
    """Handle Home button - go to home screen."""
    try:
        state: FSMContext = message.bot.current_state()
        nav_ctx = NavContext()
        nav_ctx.go_home()
        await nav_ctx.save_to_fsm(state)
    except Exception:
        pass

    await message.answer(Messages.WELCOME_ID, reply_markup=make_home_keyboard())


@router.message(F.text == Messages.BTN_BACK)
async def btn_back(message: Message) -> None:
    """Handle Back button - navigate to previous screen."""
    try:
        state: FSMContext = message.bot.current_state()
        nav_ctx = NavContext.from_fsm(state)
        prev = nav_ctx.go_back()
        if prev:
            await message.answer(f"← Kembali ke {prev}", reply_markup=make_home_keyboard())
        else:
            await message.answer("Anda sudah di halaman utama.", reply_markup=make_home_keyboard())
    except Exception:
        await message.answer(Messages.WELCOME_ID, reply_markup=make_home_keyboard())


@router.message(F.text == Messages.BTN_CANCEL)
async def btn_cancel(message: Message) -> None:
    """Handle Cancel button - clear state and go home."""
    await message.answer("✅ Dibatalkan", reply_markup=make_home_keyboard())
    try:
        await message.bot.current_state().clear()
    except Exception:
        pass


@router.message(F.text == Messages.MENU_STATUS)
async def btn_status(message: Message) -> None:
    """Handle Status menu button."""
    await message.answer("📊 Mendapatkan status server...", reply_markup=make_home_keyboard())
