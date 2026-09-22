"""Access middleware enforcing whitelist, lockout, RBAC, and rate limits.

It guards both entry points: private text messages and the inline-overlay
``callback_query`` updates, so the hybrid panel can never become a bypass around
authentication, role checks, or the audit trail.
"""

from __future__ import annotations

import html
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from bot.services import Services, log_user_action
from bot.texts import Messages
from config.settings import normalize_pin
from core.auth import AccessStatus

__all__ = ["AccessMiddleware", "redact_callback_data", "redact_message_text"]

logger = logging.getLogger(__name__)

ADMIN_NOTIFY_COOLDOWN_SECONDS = 600
MAX_COMMAND_LABEL_LENGTH = 64
MAX_CALLBACK_LABEL_LENGTH = 64

BotEvent = Message | CallbackQuery
BotHandler = Callable[[BotEvent, dict[str, Any]], Awaitable[Any]]


def redact_message_text(text: str | None) -> str:
    """Return a loggable command label; PIN-shaped message bodies are masked."""
    stripped = (text or "").strip()
    if not stripped:
        return "<non-text>"
    if normalize_pin(stripped) is not None:
        return "<pin>"
    return stripped[:MAX_COMMAND_LABEL_LENGTH]


def redact_callback_data(data: str | None) -> str:
    """Return a loggable label for an inline callback payload."""
    stripped = (data or "").strip()
    if not stripped:
        return "<callback>"
    return stripped[:MAX_CALLBACK_LABEL_LENGTH]


@dataclass(frozen=True, slots=True)
class EventView:
    """Normalised view over a message or callback update."""

    user_id: int
    username: str | None
    label: str
    nav: bool
    reply: Callable[[str], Awaitable[Any]]
    bot: Any


def describe_event(event: BotEvent, nav_texts: frozenset[str]) -> EventView | None:
    """Extract the fields the middleware needs; ``None`` when the update is ignored."""
    user = getattr(event, "from_user", None)
    if user is None or getattr(user, "is_bot", False):
        return None

    if isinstance(event, CallbackQuery):
        panel = event.message
        chat = getattr(panel, "chat", None)
        if panel is None or chat is None or getattr(chat, "type", "private") != "private":
            return None
        if getattr(chat, "id", None) != user.id:
            return None
        bot = getattr(event, "bot", None) or getattr(panel, "bot", None)
        return EventView(
            user_id=user.id,
            username=user.username,
            label=redact_callback_data(event.data),
            nav=False,
            reply=_callback_reply(event),
            bot=bot,
        )

    chat = getattr(event, "chat", None)
    if chat is not None and getattr(chat, "type", "private") != "private":
        return None
    text = redact_message_text(getattr(event, "text", None))
    view = EventView(
        user_id=user.id,
        username=user.username,
        label=text,
        nav=text in nav_texts,
        reply=_message_reply(event),
        bot=getattr(event, "bot", None),
    )
    return view


def _message_reply(event: Message) -> Callable[[str], Awaitable[Any]]:
    async def reply(text: str) -> Any:
        return await event.answer(text)

    return reply


def _callback_reply(event: CallbackQuery) -> Callable[[str], Awaitable[Any]]:
    async def reply(text: str) -> Any:
        try:
            return await event.answer(text, show_alert=True)
        except Exception:
            logger.warning("Failed to answer callback query", exc_info=True)
            return None

    return reply


class AccessMiddleware(BaseMiddleware):
    """Outer middleware that authenticates every private update before routing."""

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
        handler: BotHandler,
        event: BotEvent,
        data: dict[str, Any],
    ) -> Any:
        view = describe_event(event, self.NAV_TEXTS)
        if view is None:
            return None

        limit = self._services.rate_limiter.check(view.user_id)
        result = self._services.auth.authenticate(view.user_id, view.username)
        if result.status is not AccessStatus.OK:
            # Denied senders are answered only while under quota so that an
            # unauthenticated flood cannot amplify replies or audit rows.
            if limit.allowed:
                await self._deny(event, view, result)
            return None

        if not view.nav and not limit.allowed:
            await view.reply(Messages.RATE_LIMITED.format(seconds=limit.retry_after))
            await log_user_action(
                self._services,
                event,
                command=view.label,
                action="rate_limit.denied",
                result="limited",
            )
            return None

        data["services"] = self._services
        data["auth_user"] = result.user
        data["role"] = result.user.role if result.user else None
        return await handler(event, data)

    async def _deny(self, event: BotEvent, view: EventView, result) -> None:
        status = result.status
        if status is AccessStatus.LOCKED:
            minutes = max(1, math.ceil(result.retry_after / 60))
            await view.reply(Messages.ACCESS_LOCKED.format(minutes=minutes))
        elif status is AccessStatus.USERNAME_MISMATCH:
            await view.reply(Messages.ACCESS_USERNAME_MISMATCH)
        elif status is AccessStatus.INACTIVE:
            await view.reply(Messages.ACCESS_INACTIVE)
        else:
            await view.reply(Messages.ACCESS_DENIED)

        await log_user_action(
            self._services,
            event,
            command=view.label,
            action=f"auth.denied.{status.value}",
            result="denied",
        )
        await self._notify_admins(view, status.value)

    async def _notify_admins(self, view: EventView, status: str) -> None:
        now = self._clock()
        stale = [
            uid
            for uid, notified_at in self._last_notified.items()
            if now - notified_at >= self._notify_cooldown
        ]
        for uid in stale:
            del self._last_notified[uid]

        last = self._last_notified.get(view.user_id)
        if last is not None and now - last < self._notify_cooldown:
            return
        self._last_notified[view.user_id] = now

        if view.bot is None:
            return

        who = f"@{html.escape(view.username)}" if view.username else "tanpa username"
        text = Messages.ADMIN_ACCESS_ALERT.format(
            user_id=view.user_id,
            who=who,
            status=status,
            command=html.escape(view.label),
        )

        targets = set(self._services.settings.admin_user_ids)
        if self._services.settings.log_chat_id is not None:
            targets.add(self._services.settings.log_chat_id)

        for chat_id in targets:
            try:
                await view.bot.send_message(chat_id, text)
            except Exception:
                logger.warning("Failed to notify admin %s about denied access", chat_id)
