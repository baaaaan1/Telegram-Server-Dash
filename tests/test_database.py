"""Tests for database package."""

from unittest.mock import patch

from db.database import Database, get_db, init_database
from db.schema import SCHEMA_SQL


class TestDatabase:
    """Tests for Database class."""

    def test_init_creates_directory(self, tmp_path):
        """Test that init creates parent directories."""
        db_path = tmp_path / "nested" / "deep" / "test.db"
        db = Database(db_path)
        db.init()
        assert db_path.exists()

    def test_init_creates_tables(self, tmp_path):
        """Test that init creates expected tables."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.init()

        import sqlite3

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            assert "audit_log" in tables
            assert "metric_samples" in tables

    def test_schema_not_empty(self):
        """Test that schema SQL is defined."""
        assert SCHEMA_SQL
        assert "audit_log" in SCHEMA_SQL


class TestDatabaseSingleton:
    """Tests for database singleton functions."""

    def test_init_database_creates_instance(self, tmp_path):
        """Test init_database returns Database instance."""
        db_path = tmp_path / "db.sqlite"
        db = init_database(db_path)
        assert isinstance(db, Database)
        assert db._path == db_path

    def test_get_db_returns_same_instance(self):
        """Test get_db returns same instance."""
        with patch.dict("os.environ", {"DATABASE_PATH": "/tmp/test.db"}):
            db1 = get_db()
            db2 = get_db()
            assert db1 is db2
