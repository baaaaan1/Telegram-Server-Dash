"""Shared fixtures for TSD Bot tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.services import Services, build_services
from config.settings import BotSettings
from db.database import Database

ADMIN_ID = 1001
OPERATOR_ID = 1002
VIEWER_ID = 1003


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
