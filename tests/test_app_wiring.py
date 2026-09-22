"""End-to-end wiring tests: Dispatcher + AccessMiddleware + handlers.

aiogram routers are process-wide singletons, so the dispatcher is built once
per module with a module-scoped database.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User

from bot.app import build_dispatcher
from bot.services import build_services
from config.settings import BotSettings
from db.database import Database
from tests.conftest import ADMIN_ID, OPERATOR_ID, VIEWER_ID

ALLOWED_HANDLER_KWARGS = {
    "auth_user",
    "bot",
    "command",
    "dispatcher",
    "event_from_user",
    "message",
    "role",
    "services",
    "state",
}


class StubSession(BaseSession):
    """Captures outgoing SendMessage calls instead of hitting the network."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[SendMessage] = []

    async def close(self) -> None:
        return None

    async def make_request(self, bot: Bot, method: Any, timeout: float | None = None) -> Any:
        if isinstance(method, SendMessage):
            self.sent.append(method)
            return Message(
                message_id=len(self.sent),
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text or "",
            )
        return None

    async def stream_content(self, *args: Any, **kwargs: Any):
        yield b""


@pytest.fixture(scope="module")
def wiring(tmp_path_factory):
    """Dispatcher, services, and database shared by the module's tests."""
    db_path = tmp_path_factory.mktemp("wiring") / "bot.db"
    settings = BotSettings(
        _env_file=None,
        bot_token="1:test-token",
        admin_user_ids=[ADMIN_ID],
        operator_user_ids=[OPERATOR_ID],
        viewer_user_ids=[VIEWER_ID],
    )
    db = Database(db_path)
    db.init()
    services = build_services(settings, db)
    dispatcher = build_dispatcher(settings, services)
    return SimpleNamespace(settings=settings, db=db, services=services, dispatcher=dispatcher)


def make_update(user_id: int, text: str) -> Update:
    """Build a private-chat text update."""
    return Update(
        update_id=user_id,
        message=Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="Tester"),
            text=text,
        ),
    )


def build_bot(session: StubSession) -> Bot:
    """Bot bound to the stub session."""
    return Bot(
        token="1:test-token",
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def test_all_handlers_only_request_injected_kwargs(wiring):
    """Every handler param must be provided by middleware or aiogram context."""
    dp: Dispatcher = wiring.dispatcher

    for router in dp.sub_routers:
        for handler in router.message.handlers:
            params = set(inspect.signature(handler.callback).parameters)
            unexpected = params - ALLOWED_HANDLER_KWARGS
            assert not unexpected, f"{handler.callback.__name__} expects {unexpected}"


def test_access_middleware_is_registered(wiring):
    """The access middleware wraps every incoming message."""
    assert len(wiring.dispatcher.message.outer_middleware._middlewares) == 1


@pytest.mark.asyncio
async def test_whoami_reaches_handler_for_whitelisted_user(wiring):
    """A whitelisted admin gets their account summary end to end."""
    session = StubSession()
    bot = build_bot(session)

    await wiring.dispatcher.feed_update(bot, make_update(ADMIN_ID, "/whoami"))

    assert len(session.sent) == 1
    text = session.sent[0].text or ""
    assert "admin" in text
    assert "manage_users" in text


@pytest.mark.asyncio
async def test_unknown_user_is_blocked_end_to_end(wiring):
    """Unknown users never reach handlers and trigger an admin alert."""
    session = StubSession()
    bot = build_bot(session)

    await wiring.dispatcher.feed_update(bot, make_update(4242, "/start"))

    assert len(session.sent) == 2
    assert session.sent[0].chat_id == 4242
    assert "Akses ditolak" in (session.sent[0].text or "")
    assert session.sent[1].chat_id == ADMIN_ID
    assert "Percobaan akses ditolak" in (session.sent[1].text or "")

    row = wiring.db.fetchone("SELECT * FROM audit_log WHERE user_id = ?", (4242,))
    assert row is not None
    assert row["action"] == "auth.denied.unknown"
