"""Tests for the per-user fixed-window rate limiter."""

from __future__ import annotations

from core.rate_limit import RateLimiter


class FakeClock:
    """Deterministic clock for window assertions."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_allows_until_limit(db):
    """Requests within the limit pass and report remaining quota."""
    clock = FakeClock()
    limiter = RateLimiter(db, limit_per_minute=3, clock=clock)

    first = limiter.check(1)
    assert first.allowed is True
    assert first.remaining == 2

    limiter.check(1)
    last = limiter.check(1)
    assert last.allowed is True
    assert last.remaining == 0

    denied = limiter.check(1)
    assert denied.allowed is False
    assert denied.retry_after > 0


def test_window_resets_after_minute(db):
    """A new window restores the quota."""
    clock = FakeClock()
    limiter = RateLimiter(db, limit_per_minute=2, clock=clock)
    limiter.check(1)
    limiter.check(1)
    assert limiter.check(1).allowed is False

    clock.advance(61)
    assert limiter.check(1).allowed is True


def test_limits_are_per_user(db):
    """One user exhausting the quota does not affect another."""
    limiter = RateLimiter(db, limit_per_minute=1)
    assert limiter.check(1).allowed is True
    assert limiter.check(1).allowed is False
    assert limiter.check(2).allowed is True


def test_limit_property(db):
    """The configured limit is exposed for messaging."""
    limiter = RateLimiter(db, limit_per_minute=7)
    assert limiter.limit == 7
