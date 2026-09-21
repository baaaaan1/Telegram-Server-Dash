"""Per-user command rate limiting with fixed windows."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db.database import Database

__all__ = ["RateLimitResult", "RateLimiter"]

DEFAULT_WINDOW_SECONDS = 60
STALE_WINDOW_MULTIPLIER = 2


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """Outcome of a rate limit check."""

    allowed: bool
    remaining: int
    retry_after: int = 0
    limit: int = 0


class RateLimiter:
    """Fixed-window rate limiter persisted in SQLite (one row per user window)."""

    def __init__(
        self,
        db: Database,
        limit_per_minute: int = 30,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.time,
    ):
        self._db = db
        self._limit = limit_per_minute
        self._window_seconds = window_seconds
        self._clock = clock

    @property
    def limit(self) -> int:
        """Configured number of allowed messages per window."""
        return self._limit

    def check(self, user_id: int) -> RateLimitResult:
        """Register one message from the user and report whether it is allowed."""
        now = int(self._clock())
        window_start = now - (now % self._window_seconds)
        stale_before = window_start - self._window_seconds * STALE_WINDOW_MULTIPLIER

        with self._db.get_connection() as conn:
            conn.execute("DELETE FROM rate_limit_counters WHERE window_start < ?", (stale_before,))
            conn.execute(
                """
                INSERT INTO rate_limit_counters (user_id, window_start, count)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, window_start) DO UPDATE SET count = count + 1
                """,
                (user_id, window_start),
            )
            row = conn.execute(
                "SELECT count FROM rate_limit_counters WHERE user_id = ? AND window_start = ?",
                (user_id, window_start),
            ).fetchone()
            conn.commit()

        count = int(row["count"]) if row is not None else 1
        allowed = count <= self._limit
        remaining = max(0, self._limit - count)
        retry_after = 0 if allowed else window_start + self._window_seconds - now
        return RateLimitResult(
            allowed=allowed, remaining=remaining, retry_after=retry_after, limit=self._limit
        )
