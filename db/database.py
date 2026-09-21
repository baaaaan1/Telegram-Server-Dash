"""Database package for TSD Bot - audit log and metric storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from db.schema import SCHEMA_SQL

__all__ = ["Database", "init_database", "get_db"]

BUSY_TIMEOUT_MS = 5000


class Database:
    """SQLite database wrapper for audit log, users, and metrics.

    A single shared connection is reused for every statement. The bot runs on
    one asyncio thread, so avoiding a connect/close cycle (and its fsync cost)
    per query keeps the per-message auth/rate-limit/audit path cheap.
    """

    def __init__(self, db_path: Path | str):
        self._path = Path(db_path)
        self._connection: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._connection is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            conn.execute("PRAGMA foreign_keys=ON")
            self._connection = conn
        return self._connection

    def init(self) -> None:
        """Initialize database schema."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    def close(self) -> None:
        """Close the shared connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield the shared connection with row access by column name."""
        yield self._connect()

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        """Execute a write statement and return the last inserted row id."""
        conn = self._connect()
        cursor = conn.execute(sql, tuple(params or ()))
        conn.commit()
        return cursor.lastrowid or 0

    def fetchone(self, sql: str, params: Sequence[Any] | None = None) -> sqlite3.Row | None:
        """Fetch a single row."""
        return self._connect().execute(sql, tuple(params or ())).fetchone()

    def fetchall(self, sql: str, params: Sequence[Any] | None = None) -> list[sqlite3.Row]:
        """Fetch all matching rows."""
        return list(self._connect().execute(sql, tuple(params or ())).fetchall())


_db_instance: Database | None = None


def init_database(db_path: Path | str) -> Database:
    """Initialize and return database instance."""
    global _db_instance
    if _db_instance is not None:
        _db_instance.close()
    _db_instance = Database(db_path)
    _db_instance.init()
    return _db_instance


def get_db() -> Database:
    """Get current database instance, initializing if needed."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(Path("data/bot.db"))
        _db_instance.init()
    return _db_instance
