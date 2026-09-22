"""Runtime service container shared by middleware and handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.audit import AuditEntry, AuditLogger
from core.auth import AuthService
from core.rate_limit import RateLimiter

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message

    from config.settings import AppSettings
    from db.database import Database

__all__ = ["Services", "build_services", "log_user_action"]


@dataclass(slots=True)
class Services:
    """Composition root passed to middleware and handlers."""

    settings: AppSettings
    db: Database
    auth: AuthService
    rate_limiter: RateLimiter
    audit: AuditLogger


def build_services(settings: AppSettings, db: Database) -> Services:
    """Create services and sync the whitelist from settings."""
    auth = AuthService(db, settings)
    auth.sync_users_from_settings()
    return Services(
        settings=settings,
        db=db,
        auth=auth,
        rate_limiter=RateLimiter(db, limit_per_minute=settings.rate_limit_per_minute),
        audit=AuditLogger(db, log_chat_id=settings.log_chat_id),
    )


async def log_user_action(  # noqa: PLR0913 - explicit fields keep call sites readable
    services: Services,
    event: Message | CallbackQuery,
    *,
    command: str,
    action: str,
    result: str = "ok",
    server_name: str | None = None,
) -> None:
    """Record a user action in the audit trail (messages and inline callbacks)."""
    user = event.from_user
    if user is None:
        return
    await services.audit.log(
        AuditEntry(
            user_id=user.id,
            username=user.username,
            command=command,
            action=action,
            result=result,
            server_name=server_name,
        )
    )
