"""End-to-end wiring tests: Dispatcher + AccessMiddleware + handlers.

aiogram routers are process-wide singletons, so the dispatcher is built once
per module with a module-scoped database.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User

from bot.app import build_dispatcher
from bot.services import build_services
from config.settings import BotSettings
from db.database import Database
from tests.conftest import ADMIN_ID, OPERATOR_ID, VIEWER_ID, StubSession

ALLOWED_HANDLER_KWARGS = {
    "auth_user",
    "bot",
    "callback",
    "callback_query",
    "command",
    "dispatcher",
    "event_from_user",
    "message",
    "role",
    "services",
    "state",
}

HELP_PAGE_TWO = "tsd:p:help:c:0:2"


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


def make_callback_update(user_id: int, data: str) -> Update:
    """Build a private-chat callback update carrying an inline panel payload."""
    return Update(
        update_id=user_id + 10_000,
        callback_query={
            "id": f"cb-{user_id}-{data}",
            "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
            "chat_instance": "chat-instance",
            "data": data,
            "message": {
                "message_id": 10,
                "date": int(datetime.now(UTC).timestamp()),
                "chat": {"id": user_id, "type": "private"},
                "text": "panel",
            },
        },
    )


def build_bot(session: StubSession | None = None) -> Bot:
    """Bot bound to the capturing stub session."""
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    return Bot(
        token="1:test-token",
        session=session or StubSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


@pytest.mark.parametrize("event_kind", ["message", "callback_query"])
def test_all_handlers_only_request_injected_kwargs(wiring, event_kind: str):
    """Every handler param must be provided by middleware or aiogram context."""
    dp: Dispatcher = wiring.dispatcher

    for router in dp.sub_routers:
        observer = getattr(router, event_kind)
        for handler in observer.handlers:
            params = set(inspect.signature(handler.callback).parameters)
            unexpected = params - ALLOWED_HANDLER_KWARGS
            assert not unexpected, f"{handler.callback.__name__} expects {unexpected}"


def test_access_middleware_guards_both_entry_points(wiring):
    """Text messages and inline callbacks are both authenticated."""
    assert len(wiring.dispatcher.message.outer_middleware._middlewares) == 1
    assert len(wiring.dispatcher.callback_query.outer_middleware._middlewares) == 1


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


@pytest.mark.asyncio
async def test_start_sends_reply_keyboard_and_inline_panel(wiring):
    """The hybrid entry point: Reply Keyboard header plus the quick inline panel."""
    session = StubSession()
    bot = build_bot(session)

    await wiring.dispatcher.feed_update(bot, make_update(ADMIN_ID, "/start"))

    assert len(session.sent) == 2
    keyboard = session.sent[0].reply_markup
    assert keyboard.keyboard[-1][0].text == "✖ Cancel"
    panel = session.sent[1]
    assert panel.reply_markup is not None
    assert panel.reply_markup.inline_keyboard


@pytest.mark.asyncio
async def test_help_panel_page_is_edited_in_place(wiring):
    """A panel page change updates the existing message instead of sending one."""
    session = StubSession()
    bot = build_bot(session)

    await wiring.dispatcher.feed_update(bot, make_callback_update(ADMIN_ID, HELP_PAGE_TWO))

    assert session.sent == []
    assert len(session.edits) == 1
    assert "Keamanan" in (session.edits[0].text or "")
    assert session.answers == ["Halaman 2"]


@pytest.mark.asyncio
async def test_unknown_user_callback_is_blocked_end_to_end(wiring):
    """A callback from an unregistered user is refused before the router."""
    session = StubSession()
    bot = build_bot(session)

    await wiring.dispatcher.feed_update(bot, make_callback_update(4243, HELP_PAGE_TWO))

    assert session.edits == []
    assert "Akses ditolak" in session.answers[0]
    assert session.sent[-1].chat_id == ADMIN_ID
