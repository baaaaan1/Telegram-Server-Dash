"""Audit trail: persist every user action and mirror it to the log channel."""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3

    from aiogram import Bot

    from db.database import Database

__all__ = ["AuditEntry", "AuditLogger"]

logger = logging.getLogger(__name__)

INSERT_SQL = """
INSERT INTO audit_log (user_id, username, command, server_name, action, result)
VALUES (?, ?, ?, ?, ?, ?)
"""


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One auditable action performed by a Telegram user."""

    user_id: int
    username: str | None
    command: str
    action: str
    result: str = "ok"
    server_name: str | None = None

    def format_line(self) -> str:
        """Render a compact HTML line for the log channel."""
        who = f"@{html.escape(self.username)}" if self.username else str(self.user_id)
        parts = [
            f"🧾 <b>{html.escape(self.action)}</b>",
            f"User: {who} (<code>{self.user_id}</code>)",
            f"Command: <code>{html.escape(self.command)}</code>",
            f"Result: {html.escape(self.result)}",
        ]
        if self.server_name:
            parts.append(f"Server: {html.escape(self.server_name)}")
        return "\n".join(parts)


class AuditLogger:
    """Writes audit entries to SQLite and optionally mirrors them to a log chat."""

    def __init__(self, db: Database, log_chat_id: int | None = None):
        self._db = db
        self._log_chat_id = log_chat_id
        self._bot: Bot | None = None

    def attach_bot(self, bot: Bot) -> None:
        """Attach the bot used to mirror entries to the log channel."""
        self._bot = bot

    async def log(self, entry: AuditEntry) -> None:
        """Persist an entry and mirror it to the log channel when configured."""
        self._store(entry)
        await self._mirror(entry)

    def _store(self, entry: AuditEntry) -> None:
        try:
            self._db.execute(
                INSERT_SQL,
                (
                    entry.user_id,
                    entry.username,
                    entry.command,
                    entry.server_name,
                    entry.action,
                    entry.result,
                ),
            )
        except Exception:
            logger.exception("Failed to persist audit entry for user %s", entry.user_id)

    async def _mirror(self, entry: AuditEntry) -> None:
        if self._bot is None or self._log_chat_id is None:
            return
        try:
            await self._bot.send_message(self._log_chat_id, entry.format_line())
        except Exception:
            logger.exception("Failed to mirror audit entry to log channel")

    def fetch_recent(self, limit: int = 10) -> list[sqlite3.Row]:
        """Return the most recent audit entries."""
        return self._db.fetchall(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?",
            (max(1, limit),),
        )
