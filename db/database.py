"""Database package for TSD Bot - audit log and metric storage."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from db.schema import SCHEMA_SQL

__all__ = ["Database", "init_database", "get_db"]


class Database:
    """SQLite database wrapper for audit log and metrics."""

    def __init__(self, db_path: Path | str):
        self._path = Path(db_path)
        self._lock = None

    def init(self) -> None:
        """Initialize database schema."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection."""
        conn = sqlite3.connect(self._path)
        try:
            yield conn
        finally:
            conn.close()


_db_instance: Database | None = None


def init_database(db_path: Path | str) -> Database:
    """Initialize and return database instance."""
    global _db_instance
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
