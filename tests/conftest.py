"""Shared fixtures for TSD Bot tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, User

from bot.services import Services, build_services
from config.settings import BotSettings
from db.database import Database

ADMIN_ID = 1001
OPERATOR_ID = 1002
VIEWER_ID = 1003


class StubSession(BaseSession):
    """Captures outgoing API calls instead of hitting the Telegram network."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[SendMessage] = []
        self.edits: list[EditMessageText] = []
        self.answers: list[str] = []

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
        if isinstance(method, EditMessageText):
            self.edits.append(method)
            return Message(
                message_id=method.message_id,
                date=datetime.now(UTC),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text or "",
            )
        if isinstance(method, AnswerCallbackQuery):
            self.answers.append(method.text or "")
            return True
        return None

    async def stream_content(self, *args: Any, **kwargs: Any):
        yield b""


@pytest.fixture
def stub_bot() -> Bot:
    """Bot bound to a capturing stub session."""
    return Bot(
        token="1:test-token",
        session=StubSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


@pytest.fixture
def settings() -> BotSettings:
    """Runtime settings with one user per RBAC role."""
    return BotSettings(
        _env_file=None,
        bot_token="1:test-token",
        admin_user_ids=[ADMIN_ID],
        operator_user_ids=[OPERATOR_ID],
        viewer_user_ids=[VIEWER_ID],
        rate_limit_per_minute=30,
    )


@pytest.fixture
def db(tmp_path) -> Database:
    """Initialized SQLite database in a temporary directory."""
    database = Database(tmp_path / "bot.db")
    database.init()
    return database


@pytest.fixture
def services(settings: BotSettings, db: Database) -> Services:
    """Service container with users synced from settings."""
    return build_services(settings, db)


@pytest.fixture
def make_message():
    """Factory for lightweight Telegram message doubles."""

    def _make(
        user_id: int = ADMIN_ID,
        text: str = "/status",
        chat_type: str = "private",
        username: str | None = "tester",
        bot: SimpleNamespace | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            from_user=SimpleNamespace(id=user_id, username=username, is_bot=False),
            chat=SimpleNamespace(type=chat_type),
            text=text,
            bot=bot or SimpleNamespace(send_message=AsyncMock()),
            answer=AsyncMock(),
        )

    return _make


@pytest.fixture
def make_state():
    """Factory for aiogram FSM contexts backed by MemoryStorage."""
    storage = MemoryStorage()
    counter = {"n": 0}

    def _make(user_id: int = ADMIN_ID) -> FSMContext:
        counter["n"] += 1
        key = StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
        return FSMContext(storage=storage, key=key)

    return _make


@pytest.fixture
def make_panel_callback():
    """Factory for inline-panel callback doubles used by handler tests."""

    def _make(
        user_id: int = ADMIN_ID,
        data: str = "tsd:i:help:c:0:1",
        chat_id: int | None = None,
        username: str | None = "tester",
        message: SimpleNamespace | None = None,
    ) -> SimpleNamespace:
        panel = message or SimpleNamespace(
            chat=SimpleNamespace(id=chat_id if chat_id is not None else user_id, type="private"),
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        return SimpleNamespace(
            from_user=SimpleNamespace(id=user_id, username=username, is_bot=False),
            message=panel,
            data=data,
            answer=AsyncMock(),
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

    return _make


@pytest.fixture
def make_callback_query(stub_bot):
    """Factory for real aiogram ``CallbackQuery`` updates bound to the stub bot."""

    def _make(  # noqa: PLR0913 - mirrors the CallbackQuery fields under test
        user_id: int = ADMIN_ID,
        data: str = "tsd:i:help:c:0:1",
        chat_id: int | None = None,
        username: str | None = "tester",
        *,
        with_message: bool = True,
        is_bot: bool = False,
    ) -> CallbackQuery:
        message = None
        if with_message:
            message = Message(
                message_id=10,
                date=datetime.now(UTC),
                chat=Chat(id=chat_id if chat_id is not None else user_id, type="private"),
                text="panel",
            )
        query = CallbackQuery(
            id=f"cb-{user_id}-{data}",
            from_user=User(id=user_id, is_bot=is_bot, first_name="Tester", username=username),
            chat_instance="chat-instance",
            data=data,
            message=message,
        )
        return query.as_(stub_bot)

    return _make
