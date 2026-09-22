"""Tests for authentication, RBAC, lockout, and PIN verification."""

from __future__ import annotations

import logging

import pytest

from config.settings import BotSettings
from core.auth import (
    AccessStatus,
    AuthService,
    Permission,
    PinResult,
    Role,
    has_permission,
    hash_pin,
    verify_pin_hash,
)

ADMIN_ID = 1001
OPERATOR_ID = 1002
VIEWER_ID = 1003


class FakeClock:
    """Deterministic clock for lockout and TTL assertions."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_service(db, settings, clock=None) -> AuthService:
    service = AuthService(db, settings, clock=clock or FakeClock())
    service.sync_users_from_settings()
    return service


class TestRolePermissions:
    """Tests for the RBAC permission matrix."""

    def test_viewer_can_only_view(self):
        assert has_permission(Role.VIEWER, Permission.VIEW_STATUS) is True
        assert has_permission(Role.VIEWER, Permission.MANAGE_SERVICE) is False
        assert has_permission(Role.VIEWER, Permission.CRITICAL_ACTION) is False

    def test_operator_can_manage_services_and_exec(self):
        assert has_permission(Role.OPERATOR, Permission.MANAGE_SERVICE) is True
        assert has_permission(Role.OPERATOR, Permission.EXEC_COMMAND) is True
        assert has_permission(Role.OPERATOR, Permission.MANAGE_USERS) is False

    def test_admin_has_every_permission(self):
        for permission in Permission:
            assert has_permission(Role.ADMIN, permission) is True

    def test_unknown_role_is_denied(self):
        assert has_permission("superuser", Permission.VIEW_STATUS) is False


class TestUserSync:
    """Tests for whitelist seeding from settings."""

    def test_sync_creates_all_roles(self, db, settings):
        service = make_service(db, settings)
        assert service.get_user(ADMIN_ID).role is Role.ADMIN
        assert service.get_user(OPERATOR_ID).role is Role.OPERATOR
        assert service.get_user(VIEWER_ID).role is Role.VIEWER
        assert len(service.list_users()) == 3

    def test_admin_wins_duplicate_role(self, db):
        settings = BotSettings(
            _env_file=None,
            bot_token="1:test-token",
            admin_user_ids=[1001],
            operator_user_ids=[1001],
        )
        service = make_service(db, settings)
        assert service.get_user(1001).role is Role.ADMIN

    def test_sync_keeps_pin_and_reactivates(self, db, settings):
        service = make_service(db, settings)
        service.set_pin(ADMIN_ID, "1234")
        service.set_active(ADMIN_ID, False)

        service.sync_users_from_settings()

        user = service.get_user(ADMIN_ID)
        assert user.has_pin is True
        assert user.is_active is True

    def test_sync_disables_users_removed_from_whitelist(self, db, settings):
        """Removing an ID from the env whitelist revokes access on the next sync."""
        make_service(db, settings)
        reduced = BotSettings(_env_file=None, bot_token="1:test-token", admin_user_ids=[ADMIN_ID])
        service = AuthService(db, reduced, clock=FakeClock())
        service.sync_users_from_settings()

        assert service.authenticate(OPERATOR_ID).status is AccessStatus.INACTIVE
        assert service.authenticate(VIEWER_ID).status is AccessStatus.INACTIVE
        assert service.get_user(VIEWER_ID).role is Role.VIEWER
        assert service.authenticate(ADMIN_ID).status is AccessStatus.OK

    def test_sync_reactivates_restored_user(self, db, settings):
        """Re-adding an ID to the whitelist restores access."""
        make_service(db, settings)
        reduced = BotSettings(_env_file=None, bot_token="1:test-token", admin_user_ids=[ADMIN_ID])
        AuthService(db, reduced, clock=FakeClock()).sync_users_from_settings()

        service = AuthService(db, settings, clock=FakeClock())
        service.sync_users_from_settings()

        assert service.authenticate(VIEWER_ID).status is AccessStatus.OK

    def test_sync_without_whitelist_deactivates_all(self, db, settings):
        """An empty configuration deactivates every registered user."""
        make_service(db, settings)
        empty = BotSettings(_env_file=None, bot_token="1:test-token")

        service = AuthService(db, empty, clock=FakeClock())
        service.sync_users_from_settings()

        assert all(not user.is_active for user in service.list_users())


class TestAuthenticate:
    """Tests for the authenticate() decision table."""

    def test_unknown_user_is_rejected(self, db, settings):
        service = make_service(db, settings)
        result = service.authenticate(9999)
        assert result.status is AccessStatus.UNKNOWN
        assert result.user is None

    def test_inactive_user_is_rejected(self, db, settings):
        service = make_service(db, settings)
        service.set_active(VIEWER_ID, False)
        result = service.authenticate(VIEWER_ID)
        assert result.status is AccessStatus.INACTIVE

    def test_active_user_is_allowed(self, db, settings):
        service = make_service(db, settings)
        result = service.authenticate(OPERATOR_ID, "op")
        assert result.status is AccessStatus.OK
        assert result.user.role is Role.OPERATOR

    def test_last_seen_is_touched_once(self, db, settings):
        service = make_service(db, settings)
        service.authenticate(VIEWER_ID, "viewer")
        first = db.fetchone("SELECT last_seen FROM users WHERE user_id = ?", (VIEWER_ID,))
        assert first["last_seen"] is not None

        service.authenticate(VIEWER_ID, "viewer")
        second = db.fetchone("SELECT last_seen FROM users WHERE user_id = ?", (VIEWER_ID,))
        assert second["last_seen"] == first["last_seen"]


class TestUsernameBinding:
    """Tests for ID + username verification."""

    def bound_service(self, db, clock=None):
        settings = BotSettings(
            _env_file=None, bot_token="1:test-token", admin_user_ids="1001:Alice"
        )
        return make_service(db, settings, clock)

    def test_matching_username_is_allowed(self, db):
        """Username comparison ignores case and a leading @."""
        service = self.bound_service(db)
        assert service.authenticate(ADMIN_ID, "alice").status is AccessStatus.OK
        assert service.authenticate(ADMIN_ID, "@Alice").status is AccessStatus.OK
        assert service.expected_username(ADMIN_ID) == "alice"

    def test_wrong_username_is_rejected(self, db):
        """A different username on the same ID is denied."""
        service = self.bound_service(db)
        result = service.authenticate(ADMIN_ID, "mallory")
        assert result.status is AccessStatus.USERNAME_MISMATCH
        assert result.user is not None

    def test_missing_username_is_rejected_when_bound(self, db):
        """An account without a username cannot satisfy a binding."""
        service = self.bound_service(db)
        assert service.authenticate(ADMIN_ID, None).status is AccessStatus.USERNAME_MISMATCH

    def test_unbound_id_is_allowed_when_not_strict(self, db, settings):
        """Without a binding and without strict mode, only the ID is checked."""
        service = make_service(db, settings)
        assert service.authenticate(ADMIN_ID, "anybody").status is AccessStatus.OK
        assert service.expected_username(ADMIN_ID) is None

    def test_strict_mode_rejects_unbound_ids(self, db):
        """Strict mode denies whitelisted IDs that have no username binding."""
        settings = BotSettings(
            _env_file=None,
            bot_token="1:test-token",
            admin_user_ids=[ADMIN_ID],
            strict_username_match=True,
        )
        service = AuthService(db, settings, clock=FakeClock())
        with pytest.raises(ValueError, match="STRICT_USERNAME_MATCH"):
            service.sync_users_from_settings()

        # A row seeded earlier still cannot authenticate in strict mode.
        AuthService(
            db,
            BotSettings(_env_file=None, bot_token="1:test-token", admin_user_ids=[ADMIN_ID]),
            clock=FakeClock(),
        ).sync_users_from_settings()
        strict_service = AuthService(db, settings, clock=FakeClock())
        assert (
            strict_service.authenticate(ADMIN_ID, "alice").status is AccessStatus.USERNAME_MISMATCH
        )

    def test_strict_mode_allows_bound_users(self, db):
        """Strict mode works when every whitelisted ID is bound."""
        settings = BotSettings(
            _env_file=None,
            bot_token="1:test-token",
            admin_user_ids="1001:alice",
            strict_username_match=True,
        )
        service = AuthService(db, settings, clock=FakeClock())
        service.sync_users_from_settings()
        assert service.authenticate(ADMIN_ID, "alice").status is AccessStatus.OK
        assert service.authenticate(ADMIN_ID, "mallory").status is AccessStatus.USERNAME_MISMATCH

    def test_unbound_admin_logs_warning(self, db, caplog):
        """Non-strict mode still nudges the operator to bind admins."""
        settings = BotSettings(_env_file=None, bot_token="1:test-token", admin_user_ids=[ADMIN_ID])
        with caplog.at_level(logging.WARNING):
            AuthService(db, settings, clock=FakeClock()).sync_users_from_settings()
        assert "without a username binding" in caplog.text


class TestLockout:
    """Tests for failed-attempt lockout behaviour."""

    def test_lockout_after_max_failed_pin(self, db, settings):
        clock = FakeClock()
        service = make_service(db, settings, clock)
        service.set_pin(ADMIN_ID, "1234")

        for _ in range(settings.auth_max_attempts - 1):
            assert service.verify_pin(ADMIN_ID, "0000") is PinResult.MISMATCH

        assert service.verify_pin(ADMIN_ID, "0000") is PinResult.LOCKED
        assert service.authenticate(ADMIN_ID).status is AccessStatus.LOCKED
        assert service.lockout_remaining(ADMIN_ID) == settings.auth_lockout_seconds

    def test_lockout_expires(self, db, settings):
        clock = FakeClock()
        service = make_service(db, settings, clock)
        service.set_pin(ADMIN_ID, "1234")
        for _ in range(settings.auth_max_attempts):
            service.verify_pin(ADMIN_ID, "0000")

        assert service.authenticate(ADMIN_ID).status is AccessStatus.LOCKED
        clock.advance(settings.auth_lockout_seconds + 1)
        assert service.authenticate(ADMIN_ID).status is AccessStatus.OK

    def test_expired_lockout_restores_full_attempt_quota(self, db, settings):
        """After a lockout expires the user gets a fresh set of attempts."""
        clock = FakeClock()
        service = make_service(db, settings, clock)
        service.set_pin(ADMIN_ID, "1234")
        for _ in range(settings.auth_max_attempts):
            service.verify_pin(ADMIN_ID, "0000")

        clock.advance(settings.auth_lockout_seconds + 1)

        assert service.authenticate(ADMIN_ID).status is AccessStatus.OK
        assert service.remaining_attempts(ADMIN_ID) == settings.auth_max_attempts
        assert service.verify_pin(ADMIN_ID, "0000") is PinResult.MISMATCH
        assert service.verify_pin(ADMIN_ID, "1234") is PinResult.OK

    def test_verify_pin_after_expired_lockout_does_not_relock(self, db, settings):
        """A stale counter must not re-lock a user who never called authenticate."""
        clock = FakeClock()
        service = make_service(db, settings, clock)
        service.set_pin(ADMIN_ID, "1234")
        for _ in range(settings.auth_max_attempts):
            service.verify_pin(ADMIN_ID, "0000")

        clock.advance(settings.auth_lockout_seconds + 1)

        assert service.verify_pin(ADMIN_ID, "0000") is PinResult.MISMATCH

    def test_successful_pin_resets_attempts(self, db, settings):
        service = make_service(db, settings)
        service.set_pin(ADMIN_ID, "1234")
        service.verify_pin(ADMIN_ID, "0000")

        assert service.verify_pin(ADMIN_ID, "1234") is PinResult.OK
        assert service.remaining_attempts(ADMIN_ID) == settings.auth_max_attempts

    def test_admin_unlock_clears_lockout(self, db, settings):
        service = make_service(db, settings)
        service.set_pin(ADMIN_ID, "1234")
        for _ in range(settings.auth_max_attempts):
            service.verify_pin(ADMIN_ID, "0000")

        assert service.unlock(ADMIN_ID) is True
        assert service.authenticate(ADMIN_ID).status is AccessStatus.OK
        assert service.unlock(9999) is False


class TestPin:
    """Tests for PIN storage and verification."""

    def test_pin_hash_round_trip(self):
        stored = hash_pin("1234")
        assert stored.startswith("pbkdf2_sha256$")
        assert verify_pin_hash("1234", stored) is True
        assert verify_pin_hash("4321", stored) is False
        assert verify_pin_hash("1234", "garbage") is False

    def test_set_pin_rejects_invalid_format(self, db, settings):
        service = make_service(db, settings)
        assert service.set_pin(ADMIN_ID, "abc") is False
        assert service.set_pin(ADMIN_ID, "12") is False
        assert service.get_user(ADMIN_ID).has_pin is False

    def test_set_pin_rejects_unknown_user(self, db, settings):
        service = make_service(db, settings)
        assert service.set_pin(9999, "1234") is False

    def test_verify_without_pin_reports_not_set(self, db, settings):
        service = make_service(db, settings)
        assert service.verify_pin(ADMIN_ID, "1234") is PinResult.NOT_SET

    def test_env_pin_is_used_as_fallback(self, db):
        settings = BotSettings(
            _env_file=None, bot_token="1:test-token", admin_user_ids=[ADMIN_ID], pin="4321"
        )
        service = make_service(db, settings)
        assert service.verify_pin(ADMIN_ID, "0000") is PinResult.MISMATCH
        assert service.verify_pin(ADMIN_ID, "4321") is PinResult.OK

    def test_clear_pin_removes_hash(self, db, settings):
        service = make_service(db, settings)
        service.set_pin(ADMIN_ID, "1234")
        service.clear_pin(ADMIN_ID)
        assert service.get_user(ADMIN_ID).has_pin is False


class TestCriticalWindow:
    """Tests for the PIN TTL that unlocks critical actions."""

    def test_verification_unlocks_critical_actions(self, db, settings):
        clock = FakeClock()
        service = make_service(db, settings, clock)
        service.set_pin(ADMIN_ID, "1234")

        assert service.is_critical_unlocked(ADMIN_ID) is False
        service.verify_pin(ADMIN_ID, "1234")
        assert service.is_critical_unlocked(ADMIN_ID) is True

        clock.advance(settings.pin_ttl_seconds + 1)
        assert service.is_critical_unlocked(ADMIN_ID) is False

    def test_zero_ttl_never_reuses_pin(self, db):
        settings = BotSettings(
            _env_file=None, bot_token="1:test-token", admin_user_ids=[ADMIN_ID], pin_ttl_seconds=0
        )
        service = make_service(db, settings)
        service.set_pin(ADMIN_ID, "1234")
        assert service.verify_pin(ADMIN_ID, "1234") is PinResult.OK
        assert service.is_critical_unlocked(ADMIN_ID) is False


class TestRoleManagement:
    """Tests for role and activity changes."""

    def test_set_role_and_activate(self, db, settings):
        service = make_service(db, settings)
        assert service.set_role(VIEWER_ID, Role.OPERATOR) is True
        assert service.get_user(VIEWER_ID).role is Role.OPERATOR
        assert service.set_role(9999, Role.ADMIN) is False

        assert service.set_active(VIEWER_ID, False) is True
        assert service.get_user(VIEWER_ID).is_active is False
