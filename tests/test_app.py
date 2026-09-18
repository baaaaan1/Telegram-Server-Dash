"""Tests for application bootstrap."""

from unittest.mock import patch

import pytest

from bot.app import build_app


def test_build_app_initializes_configured_database(tmp_path, monkeypatch):
    """Startup initializes SQLite at DATABASE_PATH before polling."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("servers: []\n")
    database_path = tmp_path / "data" / "bot.db"

    monkeypatch.setenv("BOT_TOKEN", "123:test-token")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("TSD_CONFIG", str(config_path))

    with (
        patch("bot.app.create_bot", return_value=object()),
        patch("bot.app.build_dispatcher", return_value=object()),
    ):
        _, _, settings = build_app()

    assert settings.database_path == database_path
    assert database_path.is_file()


def test_build_app_rejects_missing_config(tmp_path, monkeypatch):
    """An explicitly configured missing registry must not use a fallback file."""
    config_path = tmp_path / "missing.yaml"
    monkeypatch.setenv("BOT_TOKEN", "123:test-token")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "bot.db"))
    monkeypatch.setenv("TSD_CONFIG", str(config_path))

    with pytest.raises(FileNotFoundError, match="Server configuration file not found"):
        build_app()
