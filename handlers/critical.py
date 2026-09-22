"""Critical action confirmation flow with PIN verification.

Reboot, kill process, file deletion, and firewall changes must go through
:func:`request_critical_action`: confirmation (Ya/Batal) followed by a PIN
check for the acting user. The flow is Reply Keyboard only.
"""

from __future__ import annotations

import html
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.keyboards import make_cancel_only_keyboard, make_confirm_keyboard, make_home_keyboard
from bot.services import Services, log_user_action
from bot.texts import Messages
from config.settings import normalize_pin
from core.auth import ROLE_PERMISSIONS, Permission, PinResult, Role, has_permission

__all__ = [
    "CriticalActionSpec",
    "CriticalRequest",
    "PinFlow",
    "get_critical_action",
    "register_critical_action",
    "request_critical_action",
    "unregister_critical_action",
]

router = Router()
logger = logging.getLogger(__name__)

DATA_ACTION_KEY = "critical_key"
DATA_ACTION_SERVER = "critical_server"
DATA_ACTION_PAYLOAD = "critical_payload"
DATA_PENDING_PIN = "pin_pending"


class PinFlow(StatesGroup):
    """FSM states for PIN setup and critical action confirmation."""

    set_current = State()
    set_new = State()
    set_confirm = State()
    confirm_action = State()
    enter_pin = State()


@dataclass(frozen=True, slots=True)
class CriticalActionSpec:
    """Metadata for a critical action that requires confirmation + PIN."""

    key: str
    title: str
    permission: Permission = Permission.CRITICAL_ACTION


@dataclass(frozen=True, slots=True)
class CriticalRequest:
    """Confirmation request for a registered critical action."""

    key: str
    role: Role | str | None
    server_name: str = "local"
    payload: dict | None = None


CriticalActionExecutor = Callable[[Message, FSMContext, Services, dict], Awaitable[None]]

_registry: dict[str, tuple[CriticalActionSpec, CriticalActionExecutor]] = {}


def register_critical_action(spec: CriticalActionSpec, executor: CriticalActionExecutor) -> None:
    """Register an executor for a critical action key."""
    _registry[spec.key] = (spec, executor)


def unregister_critical_action(key: str) -> None:
    """Remove a critical action executor."""
    _registry.pop(key, None)


def get_critical_action(key: str) -> tuple[CriticalActionSpec, CriticalActionExecutor] | None:
    """Look up a registered critical action."""
    return _registry.get(key)


async def request_critical_action(
    message: Message,
    state: FSMContext,
    services: Services,
    request: CriticalRequest,
) -> bool:
    """Start the confirmation flow for a registered critical action."""
    entry = _registry.get(request.key)
    if entry is None:
        logger.error("Unknown critical action requested: %s", request.key)
        await message.answer(Messages.ERROR_UNKNOWN, reply_markup=make_home_keyboard())
        return False

    spec, _executor = entry
    if not has_permission(request.role, spec.permission):
        await log_user_action(
            services,
            message,
            command=request.key,
            action="auth.denied.permission",
            result="denied",
            server_name=request.server_name,
        )
        await message.answer(Messages.PERMISSION_DENIED)
        return False

    await state.set_state(PinFlow.confirm_action)
    await state.update_data(
        {
            DATA_ACTION_KEY: request.key,
            DATA_ACTION_SERVER: request.server_name,
            DATA_ACTION_PAYLOAD: request.payload or {},
        }
    )
    await message.answer(
        Messages.CONFIRM_ACTION.format(
            title=html.escape(spec.title), server=html.escape(request.server_name)
        ),
        reply_markup=make_confirm_keyboard(),
    )
    await log_user_action(
        services,
        message,
        command=request.key,
        action="critical.requested",
        server_name=request.server_name,
    )
    return True


@router.message(StateFilter(PinFlow.confirm_action), F.text == Messages.BTN_YES)
async def confirm_yes(message: Message, state: FSMContext, services: Services) -> None:
    """User confirmed; require PIN unless it is still valid in the TTL window."""
    user = message.from_user
    if user is None:
        return

    if services.auth.is_critical_unlocked(user.id):
        await _execute(message, state, services)
        return

    await state.set_state(PinFlow.enter_pin)
    await message.answer(Messages.PIN_PROMPT, reply_markup=make_cancel_only_keyboard())


@router.message(StateFilter(PinFlow.confirm_action), F.text == Messages.BTN_NO)
async def confirm_no(message: Message, state: FSMContext, services: Services) -> None:
    """User cancelled the critical action."""
    data = await state.get_data()
    entry = _registry.get(data.get(DATA_ACTION_KEY, ""))
    title = entry[0].title if entry else "aksi"
    await state.clear()
    await log_user_action(
        services,
        message,
        command=title,
        action="critical.cancelled",
        result="cancelled",
        server_name=data.get(DATA_ACTION_SERVER),
    )
    await message.answer(Messages.ACTION_CANCELLED, reply_markup=make_home_keyboard())


@router.message(StateFilter(PinFlow.confirm_action))
async def confirm_guard(message: Message) -> None:
    """Guardrail: only the Ya/Batal buttons are valid during confirmation."""
    await message.answer(Messages.CONFIRM_CHOICE_ONLY, reply_markup=make_confirm_keyboard())


@router.message(StateFilter(PinFlow.enter_pin))
async def enter_pin(message: Message, state: FSMContext, services: Services) -> None:
    """Verify the PIN typed by the user, then execute the critical action."""
    user = message.from_user
    if user is None:
        return

    pin = normalize_pin(message.text)
    if pin is None:
        await message.answer(Messages.PIN_SETUP_INVALID, reply_markup=make_cancel_only_keyboard())
        return

    result = services.auth.verify_pin(user.id, pin)
    if result is PinResult.OK:
        await message.answer(Messages.PIN_VERIFIED)
        await _execute(message, state, services)
        return

    if result is PinResult.LOCKED:
        await state.clear()
        await log_user_action(
            services, message, command="<pin>", action="auth.pin.locked", result="locked"
        )
        await message.answer(
            Messages.ACCESS_LOCKED.format(minutes=_lockout_minutes(services, user.id)),
            reply_markup=make_home_keyboard(),
        )
        return

    if result is PinResult.NOT_SET:
        await state.clear()
        await message.answer(Messages.PIN_NOT_SET, reply_markup=make_home_keyboard())
        return

    remaining = services.auth.remaining_attempts(user.id)
    await log_user_action(
        services, message, command="<pin>", action="auth.pin.failed", result="mismatch"
    )
    await message.answer(Messages.PIN_WRONG.format(remaining=remaining))


def _lockout_minutes(services: Services, user_id: int) -> int:
    """Minutes remaining in a lockout, rounded up for the user-facing message."""
    remaining = services.auth.lockout_remaining(user_id)
    return max(1, math.ceil(remaining / 60))


async def _execute(message: Message, state: FSMContext, services: Services) -> None:
    """Run the registered executor for the pending critical action."""
    data = await state.get_data()
    key = data.get(DATA_ACTION_KEY, "")
    await state.clear()

    entry = _registry.get(key)
    if entry is None:
        await message.answer(Messages.ERROR_UNKNOWN, reply_markup=make_home_keyboard())
        return

    spec, executor = entry
    payload = data.get(DATA_ACTION_PAYLOAD) or {}
    server_name = data.get(DATA_ACTION_SERVER)

    try:
        await executor(message, state, services, payload)
    except Exception:
        logger.exception("Critical action %s failed", spec.key)
        await log_user_action(
            services,
            message,
            command=spec.key,
            action=f"critical.{spec.key}",
            result="error",
            server_name=server_name,
        )
        await message.answer(Messages.ERROR_UNKNOWN, reply_markup=make_home_keyboard())
        return

    await log_user_action(
        services,
        message,
        command=spec.key,
        action=f"critical.{spec.key}",
        result="ok",
        server_name=server_name,
    )
    await message.answer(
        Messages.ACTION_DONE.format(title=html.escape(spec.title)),
        reply_markup=make_home_keyboard(),
    )


@router.message(Command("pin"))
async def cmd_pin(message: Message, state: FSMContext, services: Services) -> None:
    """Start PIN setup: verify the current PIN first when one exists."""
    user = message.from_user
    if user is None:
        return

    existing = services.auth.get_user(user.id)
    has_env_pin = bool(services.settings.pin)

    if (existing is not None and existing.has_pin) or has_env_pin:
        await state.set_state(PinFlow.set_current)
        prompt = Messages.PIN_SETUP_CURRENT
        if has_env_pin and (existing is None or not existing.has_pin):
            prompt = f"{Messages.PIN_ENV_HINT}\n\n{Messages.PIN_SETUP_CURRENT}"
        await message.answer(prompt, reply_markup=make_cancel_only_keyboard())
        return

    await state.set_state(PinFlow.set_new)
    await message.answer(Messages.PIN_SETUP_NEW, reply_markup=make_cancel_only_keyboard())


@router.message(StateFilter(PinFlow.set_current))
async def pin_setup_current(message: Message, state: FSMContext, services: Services) -> None:
    """Verify the current PIN before allowing a change."""
    user = message.from_user
    if user is None:
        return

    pin = normalize_pin(message.text)
    if pin is None:
        await message.answer(Messages.PIN_SETUP_INVALID, reply_markup=make_cancel_only_keyboard())
        return

    result = services.auth.verify_pin(user.id, pin)
    if result is PinResult.OK:
        await state.set_state(PinFlow.set_new)
        await message.answer(Messages.PIN_SETUP_NEW, reply_markup=make_cancel_only_keyboard())
        return

    if result is PinResult.LOCKED:
        await state.clear()
        await log_user_action(
            services, message, command="<pin>", action="auth.pin.locked", result="locked"
        )
        await message.answer(
            Messages.ACCESS_LOCKED.format(minutes=_lockout_minutes(services, user.id)),
            reply_markup=make_home_keyboard(),
        )
        return

    if result is PinResult.NOT_SET:
        await state.set_state(PinFlow.set_new)
        await message.answer(Messages.PIN_SETUP_NEW, reply_markup=make_cancel_only_keyboard())
        return

    remaining = services.auth.remaining_attempts(user.id)
    await log_user_action(
        services, message, command="<pin>", action="auth.pin.failed", result="mismatch"
    )
    await message.answer(Messages.PIN_WRONG.format(remaining=remaining))


@router.message(StateFilter(PinFlow.set_new))
async def pin_setup_new(message: Message, state: FSMContext) -> None:
    """Store the new PIN temporarily and ask for confirmation."""
    pin = normalize_pin(message.text)
    if pin is None:
        await message.answer(Messages.PIN_SETUP_INVALID, reply_markup=make_cancel_only_keyboard())
        return

    await state.update_data({DATA_PENDING_PIN: pin})
    await state.set_state(PinFlow.set_confirm)
    await message.answer(Messages.PIN_SETUP_CONFIRM, reply_markup=make_cancel_only_keyboard())


@router.message(StateFilter(PinFlow.set_confirm))
async def pin_setup_confirm(message: Message, state: FSMContext, services: Services) -> None:
    """Confirm the repeated PIN and persist its hash."""
    user = message.from_user
    if user is None:
        return

    data = await state.get_data()
    pending = data.get(DATA_PENDING_PIN)
    typed = normalize_pin(message.text)

    if typed is None or pending is None or typed != pending:
        await state.set_state(PinFlow.set_new)
        await message.answer(Messages.PIN_SETUP_MISMATCH, reply_markup=make_cancel_only_keyboard())
        return

    services.auth.set_pin(user.id, typed)
    await state.clear()
    await log_user_action(services, message, command="/pin", action="auth.pin.set", result="ok")
    await message.answer(Messages.PIN_SETUP_DONE, reply_markup=make_home_keyboard())


@router.message(Command("whoami"))
async def cmd_whoami(message: Message, services: Services, role: Role) -> None:
    """Show the caller's account, role, permissions, and PIN status."""
    user = message.from_user
    if user is None:
        return

    role = role or Role.VIEWER
    account = services.auth.get_user(user.id)
    lock_status = "aktif" if account is None or account.locked_until is None else "terkunci"
    if account is not None and account.locked_until is not None:
        lock_status = f"terkunci ({services.auth.lockout_remaining(user.id)}s)"

    if account is not None and account.has_pin:
        pin_status = "diatur"
    elif services.settings.pin:
        pin_status = "diatur via TSD_PIN"
    else:
        pin_status = "belum diatur"

    expected_username = services.auth.expected_username(user.id)
    if expected_username is None:
        binding = "tidak terikat (ID saja)"
        if services.settings.strict_username_match:
            binding = "tidak terikat (ditolak: STRICT_USERNAME_MATCH aktif)"
    else:
        binding = f"terikat @{html.escape(expected_username)}"

    permissions = ", ".join(sorted(p.value for p in ROLE_PERMISSIONS[role]))
    await message.answer(
        Messages.WHOAMI.format(
            user_id=user.id,
            username=html.escape(user.username) if user.username else "-",
            binding=binding,
            role=role.value,
            pin_status=pin_status,
            lock_status=lock_status,
            permissions=permissions,
        ),
        reply_markup=make_home_keyboard(),
    )
