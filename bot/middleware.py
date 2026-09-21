"""Access middleware enforcing whitelist, lockout, RBAC, and rate limits."""

from __future__ import annotations

import html
import logging
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.services import Services, log_user_action
from bot.texts import Messages
from config.settings import normalize_pin
from core.auth import AccessStatus

__all__ = ["AccessMiddleware", "redact_message_text"]

logger = logging.getLogger(__name__)

ADMIN_NOTIFY_COOLDOWN_SECONDS = 600
MAX_COMMAND_LABEL_LENGTH = 64


def redact_message_text(text: str | None) -> str:
    """Return a loggable command label; PIN-shaped message bodies are masked."""
    stripped = (text or "").strip()
    if not stripped:
        return "<non-text>"
    if normalize_pin(stripped) is not None:
        return "<pin>"
    return stripped[:MAX_COMMAND_LABEL_LENGTH]


class AccessMiddleware(BaseMiddleware):
    """Outer middleware that authenticates every private message before routing."""

    NAV_TEXTS = frozenset({Messages.BTN_HOME, Messages.BTN_BACK, Messages.BTN_CANCEL})

    def __init__(
        self,
        services: Services,
        clock: Callable[[], float] = time.monotonic,
        notify_cooldown_seconds: int = ADMIN_NOTIFY_COOLDOWN_SECONDS,
    ):
        self._services = services
        self._clock = clock
        self._notify_cooldown = notify_cooldown_seconds
        self._last_notified: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or getattr(user, "is_bot", False):
            return None

        chat = getattr(event, "chat", None)
        if chat is not None and getattr(chat, "type", "private") != "private":
            return None

        text = (getattr(event, "text", None) or "").strip()
        limit = self._services.rate_limiter.check(user.id)

        result = self._services.auth.authenticate(user.id, user.username)
        if result.status is not AccessStatus.OK:
            # Denied senders are answered only while under quota so that an
            # unauthenticated flood cannot amplify replies or audit rows.
            if limit.allowed:
                await self._deny(event, result, user.id, user.username)
            return None

        if text not in self.NAV_TEXTS and not limit.allowed:
            await event.answer(Messages.RATE_LIMITED.format(seconds=limit.retry_after))
            await log_user_action(
                self._services,
                event,
                command=redact_message_text(text),
                action="rate_limit.denied",
                result="limited",
            )
            return None

        data["services"] = self._services
        data["auth_user"] = result.user
        data["role"] = result.user.role if result.user else None
        return await handler(event, data)

    async def _deny(
        self,
        event: Message,
        result,
        user_id: int,
        username: str | None,
    ) -> None:
        status = result.status
        if status is AccessStatus.LOCKED:
            minutes = max(1, math.ceil(result.retry_after / 60))
            await event.answer(Messages.ACCESS_LOCKED.format(minutes=minutes))
        elif status is AccessStatus.USERNAME_MISMATCH:
            await event.answer(Messages.ACCESS_USERNAME_MISMATCH)
        elif status is AccessStatus.INACTIVE:
            await event.answer(Messages.ACCESS_INACTIVE)
        else:
            await event.answer(Messages.ACCESS_DENIED)

        command_label = redact_message_text(getattr(event, "text", None))
        await log_user_action(
            self._services,
            event,
            command=command_label,
            action=f"auth.denied.{status.value}",
            result="denied",
        )
        await self._notify_admins(event, user_id, username, status.value, command_label)

    async def _notify_admins(
        self,
        event: Message,
        user_id: int,
        username: str | None,
        status: str,
        command_label: str,
    ) -> None:
        now = self._clock()
        stale = [
            uid
            for uid, notified_at in self._last_notified.items()
            if now - notified_at >= self._notify_cooldown
        ]
        for uid in stale:
            del self._last_notified[uid]

        last = self._last_notified.get(user_id)
        if last is not None and now - last < self._notify_cooldown:
            return
        self._last_notified[user_id] = now

        bot = getattr(event, "bot", None)
        if bot is None:
            return

        who = f"@{html.escape(username)}" if username else "tanpa username"
        text = Messages.ADMIN_ACCESS_ALERT.format(
            user_id=user_id,
            who=who,
            status=status,
            command=html.escape(command_label),
        )

        targets = set(self._services.settings.admin_user_ids)
        if self._services.settings.log_chat_id is not None:
            targets.add(self._services.settings.log_chat_id)

        for chat_id in targets:
            try:
                await bot.send_message(chat_id, text)
            except Exception:
                logger.warning("Failed to notify admin %s about denied access", chat_id)
