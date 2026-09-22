"""Tests for the audit trail writer and log channel mirror."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.audit import AuditEntry, AuditLogger


def make_entry(**overrides) -> AuditEntry:
    data = {
        "user_id": 1001,
        "username": "tester",
        "command": "/status",
        "action": "monitor.status",
        "result": "ok",
        "server_name": None,
    }
    data.update(overrides)
    return AuditEntry(**data)


@pytest.mark.asyncio
async def test_log_persists_entry(db):
    """Entries are written to the audit_log table."""
    logger = AuditLogger(db)
    await logger.log(make_entry(server_name="local-vps"))

    rows = logger.fetch_recent(limit=5)
    assert len(rows) == 1
    assert rows[0]["user_id"] == 1001
    assert rows[0]["action"] == "monitor.status"
    assert rows[0]["server_name"] == "local-vps"


@pytest.mark.asyncio
async def test_recent_entries_are_newest_first(db):
    """fetch_recent returns the newest entry first."""
    logger = AuditLogger(db)
    await logger.log(make_entry(action="first"))
    await logger.log(make_entry(action="second"))

    rows = logger.fetch_recent(limit=5)
    assert [row["action"] for row in rows] == ["second", "first"]


@pytest.mark.asyncio
async def test_log_mirrors_to_log_channel(db):
    """A configured log chat receives a copy of every entry."""
    bot = SimpleNamespace(send_message=AsyncMock())
    logger = AuditLogger(db, log_chat_id=-100123)
    logger.attach_bot(bot)

    await logger.log(make_entry())

    bot.send_message.assert_awaited_once()
    chat_id, text = bot.send_message.await_args.args
    assert chat_id == -100123
    assert "monitor.status" in text


@pytest.mark.asyncio
async def test_log_without_bot_or_channel_is_safe(db):
    """Mirroring is skipped when no bot or log chat is configured."""
    logger = AuditLogger(db)
    await logger.log(make_entry())
    assert len(logger.fetch_recent(limit=5)) == 1


@pytest.mark.asyncio
async def test_mirror_failure_does_not_raise(db):
    """A failing Telegram send must not break the audited action."""
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("boom")))
    logger = AuditLogger(db, log_chat_id=-100123)
    logger.attach_bot(bot)

    await logger.log(make_entry())
    assert len(logger.fetch_recent(limit=5)) == 1


def test_format_line_escapes_html():
    """HTML in username and command is escaped for ParseMode.HTML."""
    entry = make_entry(username="<b>x</b>", command="<script>")
    line = entry.format_line()
    assert "<b>x</b>" not in line
    assert "&lt;script&gt;" in line
