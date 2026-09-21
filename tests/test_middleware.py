"""Tests for the AccessMiddleware whitelist, lockout, and rate limiting."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.middleware import ADMIN_NOTIFY_COOLDOWN_SECONDS, AccessMiddleware
from bot.services import build_services
from bot.texts import Messages
from config.settings import BotSettings
from core.auth import Role
from tests.conftest import ADMIN_ID, OPERATOR_ID, VIEWER_ID


class FakeClock:
    """Deterministic monotonic clock for notification cooldown."""

    def __init__(self, start: float = 100.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def build(services, clock=None) -> AccessMiddleware:
    return AccessMiddleware(services, clock=clock or FakeClock())


@pytest.mark.asyncio
async def test_allowed_user_injects_context(services, make_message):
    """Whitelisted users reach the handler with role and services injected."""
    handler = AsyncMock(return_value="handled")
    data: dict = {}

    result = await build(services)(handler, make_message(user_id=OPERATOR_ID), data)

    assert result == "handled"
    handler.assert_awaited_once()
    assert data["role"] is Role.OPERATOR
    assert data["services"] is services
    assert data["auth_user"].user_id == OPERATOR_ID


@pytest.mark.asyncio
async def test_unknown_user_is_denied_and_admins_notified(services, make_message):
    """Unknown users are blocked and every admin is notified."""
    message = make_message(user_id=42, username="stranger", text="/start")
    handler = AsyncMock()

    result = await build(services)(handler, message, {})

    assert result is None
    handler.assert_not_awaited()
    assert message.answer.await_args.args[0] == Messages.ACCESS_DENIED
    message.bot.send_message.assert_awaited_once()
    assert message.bot.send_message.await_args.args[0] == ADMIN_ID


@pytest.mark.asyncio
async def test_denied_attempts_are_audited(services, make_message, db):
    """Denied attempts land in the audit trail."""
    await build(services)(AsyncMock(), make_message(user_id=42), {})

    row = db.fetchone("SELECT * FROM audit_log WHERE user_id = ?", (42,))
    assert row is not None
    assert row["action"] == "auth.denied.unknown"
    assert row["result"] == "denied"


@pytest.mark.asyncio
async def test_admin_notification_is_throttled(services, make_message):
    """Repeated denials from the same user do not spam admins."""
    clock = FakeClock()
    middleware = build(services, clock)
    first = make_message(user_id=42)
    await middleware(AsyncMock(), first, {})

    clock.advance(5)
    second = make_message(user_id=42)
    await middleware(AsyncMock(), second, {})

    assert first.bot.send_message.await_count == 1
    assert second.bot.send_message.await_count == 0

    clock.advance(ADMIN_NOTIFY_COOLDOWN_SECONDS)
    third = make_message(user_id=42)
    await middleware(AsyncMock(), third, {})
    assert third.bot.send_message.await_count == 1


@pytest.mark.asyncio
async def test_username_mismatch_is_denied_and_audited(db, make_message):
    """A whitelisted ID with the wrong username must not reach handlers."""
    settings = BotSettings(
        _env_file=None, bot_token="1:test-token", admin_user_ids=f"{ADMIN_ID}:alice"
    )
    services = build_services(settings, db)
    message = make_message(user_id=ADMIN_ID, username="mallory", text="/status")
    handler = AsyncMock()

    assert await build(services)(handler, message, {}) is None
    handler.assert_not_awaited()
    assert message.answer.await_args.args[0] == Messages.ACCESS_USERNAME_MISMATCH

    row = db.fetchone(
        "SELECT * FROM audit_log WHERE action = ?", ("auth.denied.username_mismatch",)
    )
    assert row is not None
    assert row["result"] == "denied"


@pytest.mark.asyncio
async def test_bound_username_is_allowed(db, make_message):
    """The matching username reaches the handler."""
    settings = BotSettings(
        _env_file=None, bot_token="1:test-token", admin_user_ids=f"{ADMIN_ID}:alice"
    )
    services = build_services(settings, db)
    handler = AsyncMock(return_value="ok")

    result = await build(services)(handler, make_message(user_id=ADMIN_ID, username="Alice"), {})

    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_group_chat_is_ignored(services, make_message):
    """Only private chats are served."""
    handler = AsyncMock()
    message = make_message(user_id=ADMIN_ID, chat_type="group")

    assert await build(services)(handler, message, {}) is None
    handler.assert_not_awaited()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_inactive_user_is_denied(services, make_message):
    """Users disabled by an admin cannot reach handlers."""
    services.auth.set_active(VIEWER_ID, False)
    message = make_message(user_id=VIEWER_ID)
    handler = AsyncMock()

    assert await build(services)(handler, message, {}) is None
    handler.assert_not_awaited()
    assert message.answer.await_args.args[0] == Messages.ACCESS_INACTIVE


@pytest.mark.asyncio
async def test_locked_user_sees_retry_hint(services, make_message, settings):
    """Locked users get a retry hint instead of handler execution."""
    services.auth.set_pin(ADMIN_ID, "1234")
    for _ in range(settings.auth_max_attempts):
        services.auth.verify_pin(ADMIN_ID, "0000")

    message = make_message(user_id=ADMIN_ID)
    handler = AsyncMock()

    assert await build(services)(handler, message, {}) is None
    handler.assert_not_awaited()
    assert messages_contains(message, "dikunci")


def messages_contains(message, needle: str) -> bool:
    """Helper: whether any answered message contains the needle."""
    return any(needle in call.args[0] for call in message.answer.await_args_list)


@pytest.mark.asyncio
async def test_rate_limit_blocks_and_audits(db, make_message):
    """Exceeding the per-minute quota rejects the message and audits it."""
    settings = BotSettings(
        _env_file=None,
        bot_token="1:test-token",
        admin_user_ids=[ADMIN_ID],
        rate_limit_per_minute=2,
    )
    services = build_services(settings, db)
    middleware = build(services)
    handler = AsyncMock(return_value="ok")

    assert await middleware(handler, make_message(user_id=ADMIN_ID), {}) == "ok"
    assert await middleware(handler, make_message(user_id=ADMIN_ID), {}) == "ok"

    blocked = make_message(user_id=ADMIN_ID)
    assert await middleware(handler, blocked, {}) is None
    assert "Terlalu banyak permintaan" in blocked.answer.await_args.args[0]

    row = db.fetchone("SELECT * FROM audit_log WHERE action = ?", ("rate_limit.denied",))
    assert row is not None

    nav = make_message(user_id=ADMIN_ID, text=Messages.BTN_HOME)
    assert await middleware(handler, nav, {}) == "ok"


@pytest.mark.asyncio
async def test_denied_message_does_not_leak_pin(services, make_message, db, settings):
    """A locked user retyping a PIN must not have it stored or broadcast."""
    services.auth.set_pin(ADMIN_ID, "1234")
    for _ in range(settings.auth_max_attempts):
        services.auth.verify_pin(ADMIN_ID, "0000")

    message = make_message(user_id=ADMIN_ID, text="9876")
    await build(services)(AsyncMock(), message, {})

    row = db.fetchone("SELECT command FROM audit_log WHERE action = ?", ("auth.denied.locked",))
    assert row is not None
    assert row["command"] == "<pin>"

    alert = message.bot.send_message.await_args.args[1]
    assert "9876" not in alert


@pytest.mark.asyncio
async def test_rate_limited_pin_is_redacted(db, make_message):
    """PIN-shaped bodies rejected by the rate limiter are masked everywhere."""
    settings = BotSettings(
        _env_file=None,
        bot_token="1:test-token",
        admin_user_ids=[ADMIN_ID],
        rate_limit_per_minute=1,
    )
    services = build_services(settings, db)
    middleware = build(services)
    handler = AsyncMock()

    await middleware(handler, make_message(user_id=ADMIN_ID, text="1234"), {})

    blocked = make_message(user_id=ADMIN_ID, text="1234")
    assert await middleware(handler, blocked, {}) is None

    row = db.fetchone("SELECT command FROM audit_log WHERE action = ?", ("rate_limit.denied",))
    assert row is not None
    assert row["command"] == "<pin>"
    assert "1234" not in blocked.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_unknown_user_flood_is_dropped_silently(db, make_message):
    """Unauthenticated senders stop being answered once over quota."""
    settings = BotSettings(
        _env_file=None,
        bot_token="1:test-token",
        admin_user_ids=[ADMIN_ID],
        rate_limit_per_minute=1,
    )
    services = build_services(settings, db)
    middleware = build(services)
    handler = AsyncMock()

    first = make_message(user_id=4242, text="/start")
    await middleware(handler, first, {})
    assert first.answer.await_count == 1
    assert first.bot.send_message.await_count == 1

    flood = make_message(user_id=4242, text="/start")
    await middleware(handler, flood, {})
    assert flood.answer.await_count == 0
    assert flood.bot.send_message.await_count == 0

    rows = db.fetchall("SELECT id FROM audit_log WHERE user_id = ?", (4242,))
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_bot_sender_is_ignored(services, make_message):
    """Messages from other bots are dropped."""
    message = make_message()
    message.from_user.is_bot = True
    handler = AsyncMock()

    assert await build(services)(handler, message, {}) is None
    handler.assert_not_awaited()
