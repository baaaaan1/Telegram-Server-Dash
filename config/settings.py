"""Pydantic-settings based application configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class BotSettings(BaseSettings):
    """Telegram bot runtime configuration from environment."""

    bot_token: Annotated[str, Field(alias="BOT_TOKEN", validation_alias="BOT_TOKEN")]
    admin_user_ids: Annotated[list[int], Field(default_factory=list, alias="ADMIN_USER_IDS")]
    log_chat_id: int | None = Field(default=None, alias="LOG_CHAT_ID")
    environment: str = Field(default="dev", alias="ENV")
    database_path: Path = Field(
        default_factory=lambda: Path("data/bot.db"),
        alias="DATABASE_PATH",
    )
    config_path: Path = Field(
        default_factory=lambda: Path("config/config.yaml"),
        alias="TSD_CONFIG",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "case_sensitive": False,
        "populate_by_name": True,
    }

    @field_validator("admin_user_ids", mode="before")
    @classmethod
    def _parse_admin_user_ids(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, str):
            v = v.replace(" ", "")
            if not v:
                return []
            return [int(x) for x in v.split(",")]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []


def load_settings() -> tuple[BotSettings, Path]:
    """Load bot settings from environment, return (settings, config_path)."""
    settings = BotSettings()
    return settings, settings.config_path


AppSettings = BotSettings
