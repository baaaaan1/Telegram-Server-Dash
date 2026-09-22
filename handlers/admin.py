"""Admin utilities: lockout recovery, user registry, and audit inspection."""

from __future__ import annotations

import html

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.keyboards import make_home_keyboard
from bot.services import Services, log_user_action
from bot.texts import Messages
from core.auth import Permission, Role, has_permission

router = Router()

MAX_USER_LIST = 50
DEFAULT_AUDIT_LIMIT = 10
MAX_AUDIT_LIMIT = 25


async def _deny_permission(services: Services, message: Message, command: str) -> None:
    """Report a denied admin command and record it in the audit trail."""
    await log_user_action(
        services,
        message,
        command=command,
        action="auth.denied.permission",
        result="denied",
    )
    await message.answer(Messages.PERMISSION_DENIED)


@router.message(Command("unlock"))
async def cmd_unlock(
    message: Message, command: CommandObject, services: Services, role: Role | None
) -> None:
    """Admin recovery: clear the lockout timer for a registered user."""
    if not has_permission(role, Permission.MANAGE_USERS):
        await _deny_permission(services, message, "/unlock")
        return

    raw = (command.args or "").strip()
    if not raw.isdigit():
        await message.answer(Messages.UNLOCK_USAGE)
        return

    target = int(raw)
    unlocked = services.auth.unlock(target)
    await log_user_action(
        services,
        message,
        command=f"/unlock {target}",
        action="admin.unlock",
        result="ok" if unlocked else "not_found",
    )
    template = Messages.UNLOCK_OK if unlocked else Messages.UNLOCK_UNKNOWN
    await message.answer(
        template.format(user_id=target),
        reply_markup=make_home_keyboard(),
    )


@router.message(Command("users"))
async def cmd_users(message: Message, services: Services, role: Role | None) -> None:
    """List registered users and their roles."""
    if not has_permission(role, Permission.MANAGE_USERS):
        await _deny_permission(services, message, "/users")
        return

    users = services.auth.list_users()
    if not users:
        await message.answer(Messages.USERS_EMPTY, reply_markup=make_home_keyboard())
        return

    bindings = services.settings.username_bindings
    lines = [Messages.USERS_HEADER]
    for user in users[:MAX_USER_LIST]:
        username = f"@{html.escape(user.username)}" if user.username else "-"
        state = "aktif" if user.is_active else "nonaktif"
        binding = bindings.get(user.user_id)
        bound_to = f" | terikat: @{html.escape(binding)}" if binding else ""
        lines.append(
            f"• <code>{user.user_id}</code> | {username} | {user.role.value} | {state}{bound_to}"
        )
    if len(users) > MAX_USER_LIST:
        lines.append(f"… dan {len(users) - MAX_USER_LIST} user lainnya")

    await message.answer("\n".join(lines), reply_markup=make_home_keyboard())


@router.message(Command("audit"))
async def cmd_audit(
    message: Message, command: CommandObject, services: Services, role: Role | None
) -> None:
    """Show the most recent audit trail entries."""
    if not has_permission(role, Permission.VIEW_AUDIT):
        await _deny_permission(services, message, "/audit")
        return

    raw = (command.args or "").strip()
    limit = int(raw) if raw.isdigit() else DEFAULT_AUDIT_LIMIT
    limit = max(1, min(limit, MAX_AUDIT_LIMIT))

    entries = services.audit.fetch_recent(limit)
    if not entries:
        await message.answer(Messages.AUDIT_EMPTY, reply_markup=make_home_keyboard())
        return

    lines = [Messages.AUDIT_HEADER]
    for row in entries:
        who = f"@{html.escape(row['username'])}" if row["username"] else str(row["user_id"])
        lines.append(
            Messages.AUDIT_LINE.format(
                id=row["id"],
                timestamp=html.escape(str(row["timestamp"])),
                user=html.escape(who),
                action=html.escape(str(row["action"])),
                result=html.escape(str(row["result"] or "-")),
            )
        )

    await message.answer("\n".join(lines), reply_markup=make_home_keyboard())
