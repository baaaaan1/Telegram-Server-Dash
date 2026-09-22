"""Navigation handler - Home/Back/Cancel button routing."""

from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.nav import NavContext
from bot.services import Services, log_user_action
from bot.texts import Messages
from handlers.critical import PinFlow

router = Router()

MODAL_FLOW_STATES = frozenset(state.state for state in PinFlow.__states__)


@router.message(F.text == Messages.BTN_HOME)
async def btn_home(message: Message, state: FSMContext) -> None:
    """Handle Home button - reset context and go to the main menu."""
    await state.clear()
    await message.answer(Messages.WELCOME_ID, reply_markup=make_home_keyboard())


@router.message(F.text == Messages.BTN_BACK)
async def btn_back(message: Message, state: FSMContext, services: Services) -> None:
    """Handle Back button - abort a modal flow or pop the navigation stack."""
    if await state.get_state() in MODAL_FLOW_STATES:
        await state.clear()
        await log_user_action(
            services, message, command="/back", action="nav.back", result="cancelled"
        )
        await message.answer(Messages.ACTION_CANCELLED, reply_markup=make_home_keyboard())
        return

    data = await state.get_data()
    nav_ctx = NavContext(stack=list(data.get("nav_stack") or ["home"]))
    previous = nav_ctx.go_back()
    await state.update_data(nav_stack=nav_ctx.stack)

    if previous:
        await message.answer(
            f"← Kembali ke <b>{html.escape(previous)}</b>", reply_markup=make_home_keyboard()
        )
    else:
        await message.answer("ℹ️ Anda sudah di halaman utama.", reply_markup=make_home_keyboard())


@router.message(F.text == Messages.BTN_CANCEL)
async def btn_cancel(message: Message, state: FSMContext, services: Services) -> None:
    """Handle Cancel button - abort the running flow and return to a safe state."""
    await state.clear()
    await log_user_action(services, message, command="/cancel", action="nav.cancel")
    await message.answer(Messages.ACTION_CANCELLED, reply_markup=make_home_keyboard())
