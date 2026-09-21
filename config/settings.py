"""Pydantic-settings based application configuration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode

PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 8
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{5,32}$")

WHITELIST_FIELDS = (
    ("admin_user_ids", "admin_usernames", "ADMIN_USER_IDS"),
    ("operator_user_ids", "operator_usernames", "OPERATOR_USER_IDS"),
    ("viewer_user_ids", "viewer_usernames", "VIEWER_USER_IDS"),
)


def normalize_username(raw: str | None) -> str | None:
    """Normalize a Telegram @username for comparison (no @, lowercase)."""
    if raw is None:
        return None
    username = raw.strip().lstrip("@").lower()
    return username or None


def split_user_entries(raw: Any) -> list[str]:
    """Split raw whitelist input into ``ID`` or ``ID:username`` entries."""
    if raw is None or isinstance(raw, bool):
        return []
    if isinstance(raw, int | float):
        return [str(int(raw))]
    if isinstance(raw, str):
        cleaned = raw.strip().removeprefix("[").removesuffix("]").replace(" ", "")
        if not cleaned:
            return []
        return [entry for entry in cleaned.split(",") if entry]
    if isinstance(raw, list | tuple | set):
        return [str(entry).strip() for entry in raw if str(entry).strip()]
    return []


def parse_whitelist(raw: Any) -> tuple[list[int], dict[int, str]]:
    """Parse whitelist entries into user IDs and optional username bindings.

    Each entry is ``ID`` or ``ID:username`` (a leading ``@`` is allowed).
    """
    user_ids: list[int] = []
    usernames: dict[int, str] = {}
    for entry in split_user_entries(raw):
        id_part, separator, username_part = entry.partition(":")
        try:
            user_id = int(id_part)
        except ValueError:
            msg = f"Whitelist entry {entry!r} must start with a numeric user ID"
            raise ValueError(msg) from None

        if separator:
            username = normalize_username(username_part)
            if username is None or not USERNAME_PATTERN.match(username):
                msg = (
                    f"Whitelist entry {entry!r} has an invalid username; "
                    "use ID:username with 5-32 letters, digits, or underscores"
                )
                raise ValueError(msg)
            usernames[user_id] = username

        user_ids.append(user_id)
    return user_ids, usernames


def parse_user_ids(raw: str | float | list[int] | list[str] | None) -> list[int]:
    """Parse a Telegram user ID list from env, config, or code input.

    Accepts comma-separated strings (``1,2`` or ``1:alice,2``), JSON-like lists
    (``[1, 2]``), plain numbers, and actual lists. ``NoDecode`` on the settings
    fields keeps pydantic-settings from JSON-decoding the raw env value first.
    """
    user_ids, _usernames = parse_whitelist(raw)
    return user_ids


def normalize_pin(raw: str | None) -> str | None:
    """Return a valid numeric PIN or None when the input is not valid."""
    if raw is None:
        return None
    pin = raw.strip()
    if pin.isdigit() and PIN_MIN_LENGTH <= len(pin) <= PIN_MAX_LENGTH:
        return pin
    return None


class BotSettings(BaseSettings):
    """Telegram bot runtime configuration from environment."""

    bot_token: Annotated[str, Field(alias="BOT_TOKEN", validation_alias="BOT_TOKEN")]
    admin_user_ids: Annotated[
        list[int], NoDecode, Field(default_factory=list, alias="ADMIN_USER_IDS")
    ]
    operator_user_ids: Annotated[
        list[int], NoDecode, Field(default_factory=list, alias="OPERATOR_USER_IDS")
    ]
    viewer_user_ids: Annotated[
        list[int], NoDecode, Field(default_factory=list, alias="VIEWER_USER_IDS")
    ]
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
    admin_usernames: dict[int, str] = Field(default_factory=dict)
    operator_usernames: dict[int, str] = Field(default_factory=dict)
    viewer_usernames: dict[int, str] = Field(default_factory=dict)
    strict_username_match: bool = Field(default=False, alias="STRICT_USERNAME_MATCH")
    pin: str | None = Field(default=None, alias="TSD_PIN")
    pin_ttl_seconds: int = Field(default=300, alias="PIN_TTL_SECONDS", ge=0)
    auth_max_attempts: int = Field(default=5, alias="AUTH_MAX_ATTEMPTS", ge=1)
    auth_lockout_seconds: int = Field(default=900, alias="AUTH_LOCKOUT_SECONDS", ge=1)
    rate_limit_per_minute: int = Field(default=30, alias="RATE_LIMIT_PER_MINUTE", ge=1)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_ignore_empty": True,
        "extra": "ignore",
        "case_sensitive": False,
        "populate_by_name": True,
    }

    @model_validator(mode="before")
    @classmethod
    def _split_username_bindings(cls, data: Any) -> Any:
        """Derive ``*_usernames`` bindings from ``ID:username`` whitelist entries."""
        if not isinstance(data, dict):
            return data
        for ids_field, usernames_field, alias in WHITELIST_FIELDS:
            raw = data.pop(alias, None)
            if raw is None:
                raw = data.get(ids_field)
            user_ids, usernames = parse_whitelist(raw)
            data[ids_field] = user_ids
            data[usernames_field] = usernames
        return data

    @property
    def username_bindings(self) -> dict[int, str]:
        """Merged ``user_id -> username`` bindings for every role."""
        bindings: dict[int, str] = {}
        bindings.update(self.viewer_usernames)
        bindings.update(self.operator_usernames)
        bindings.update(self.admin_usernames)
        return bindings

    @field_validator("pin", mode="before")
    @classmethod
    def _validate_pin(cls, v: str | None) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        pin = normalize_pin(str(v))
        if pin is None:
            msg = f"TSD_PIN must be {PIN_MIN_LENGTH}-{PIN_MAX_LENGTH} digits"
            raise ValueError(msg)
        return pin


def load_settings() -> tuple[BotSettings, Path]:
    """Load bot settings from environment, return (settings, config_path)."""
    settings = BotSettings()
    return settings, settings.config_path


AppSettings = BotSettings
