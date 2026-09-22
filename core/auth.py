"""Authentication, RBAC roles, and PIN verification."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from config.settings import normalize_pin, normalize_username

if TYPE_CHECKING:
    import sqlite3

    from config.settings import AppSettings
    from db.database import Database

__all__ = [
    "AccessResult",
    "AccessStatus",
    "AuthService",
    "AuthUser",
    "Permission",
    "PinResult",
    "Role",
    "ROLE_PERMISSIONS",
    "hash_pin",
    "has_permission",
    "verify_pin_hash",
]

PBKDF2_ITERATIONS = 120_000
PBKDF2_PREFIX = "pbkdf2_sha256"
LAST_SEEN_THROTTLE_SECONDS = 60

logger = logging.getLogger(__name__)


class Role(StrEnum):
    """RBAC role attached to a Telegram user."""

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Permission(StrEnum):
    """Fine-grained capability checked by handlers."""

    VIEW_STATUS = "view_status"
    MANAGE_SERVICE = "manage_service"
    EXEC_COMMAND = "exec_command"
    CRITICAL_ACTION = "critical_action"
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT = "view_audit"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.VIEW_STATUS}),
    Role.OPERATOR: frozenset(
        {Permission.VIEW_STATUS, Permission.MANAGE_SERVICE, Permission.EXEC_COMMAND}
    ),
    Role.ADMIN: frozenset(Permission),
}


def has_permission(role: Role | str, permission: Permission | str) -> bool:
    """Check whether a role grants the requested permission."""
    try:
        resolved_role = Role(role)
    except ValueError:
        return False
    return Permission(permission) in ROLE_PERMISSIONS[resolved_role]


class AccessStatus(StrEnum):
    """Result of an authentication attempt."""

    OK = "ok"
    UNKNOWN = "unknown"
    INACTIVE = "inactive"
    LOCKED = "locked"
    USERNAME_MISMATCH = "username_mismatch"


class PinResult(StrEnum):
    """Result of a PIN verification attempt."""

    OK = "ok"
    MISMATCH = "mismatch"
    NOT_SET = "not_set"
    LOCKED = "locked"


@dataclass(frozen=True, slots=True)
class AuthUser:
    """Registered bot user loaded from the database."""

    user_id: int
    username: str | None
    role: Role
    pin_hash: str | None
    is_active: bool
    failed_attempts: int
    locked_until: int | None
    pin_verified_until: int | None

    @property
    def has_pin(self) -> bool:
        """Whether a PIN hash is stored for this user."""
        return bool(self.pin_hash)


@dataclass(frozen=True, slots=True)
class AccessResult:
    """Outcome of an authentication attempt."""

    status: AccessStatus
    user: AuthUser | None = None
    retry_after: int = 0


def hash_pin(pin: str) -> str:
    """Hash a PIN with PBKDF2-HMAC-SHA256 and a random salt."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"{PBKDF2_PREFIX}${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_pin_hash(pin: str, stored_hash: str) -> bool:
    """Constant-time check of a PIN against a stored PBKDF2 hash."""
    try:
        prefix, iterations, salt, digest = stored_hash.split("$")
        if prefix != PBKDF2_PREFIX:
            return False
        expected = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(expected.hex(), digest)
    except (ValueError, TypeError, AttributeError):
        return False


def _coerce_role(value: str | Role) -> Role:
    """Convert a stored role value, falling back to viewer."""
    try:
        return Role(value)
    except ValueError:
        return Role.VIEWER


class AuthService:
    """Database-backed user registry with roles, lockout, and PIN checks."""

    def __init__(
        self,
        db: Database,
        settings: AppSettings,
        clock: Callable[[], float] = time.time,
    ):
        self._db = db
        self._settings = settings
        self._clock = clock

    def sync_users_from_settings(self) -> None:
        """Seed and reconcile the whitelist from settings.

        The environment whitelists are authoritative: listed users are created
        or reactivated with the configured role, and every other row is
        deactivated so removing an ID from the environment revokes access on
        the next start. PIN hash, lockout state, and last_seen are preserved.
        """
        assignments: dict[int, Role] = {}
        for user_id in self._settings.viewer_user_ids:
            assignments[user_id] = Role.VIEWER
        for user_id in self._settings.operator_user_ids:
            assignments[user_id] = Role.OPERATOR
        for user_id in self._settings.admin_user_ids:
            assignments[user_id] = Role.ADMIN

        self._check_username_bindings(assignments)

        for user_id, role in assignments.items():
            self._db.execute(
                """
                INSERT INTO users (user_id, role, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET role = excluded.role, is_active = 1
                """,
                (user_id, role.value),
            )

        if assignments:
            placeholders = ",".join("?" for _ in assignments)
            self._db.execute(
                f"UPDATE users SET is_active = 0 WHERE user_id NOT IN ({placeholders})",
                tuple(assignments),
            )
        else:
            self._db.execute("UPDATE users SET is_active = 0 WHERE is_active = 1")

    def _check_username_bindings(self, assignments: dict[int, Role]) -> None:
        """Fail fast in strict mode; warn about unbound admins otherwise."""
        bindings = self._settings.username_bindings
        if self._settings.strict_username_match:
            missing = sorted(user_id for user_id in assignments if user_id not in bindings)
            if missing:
                listed = ", ".join(str(user_id) for user_id in missing)
                msg = (
                    "STRICT_USERNAME_MATCH is enabled but no username binding exists for: "
                    f"{listed}. Use ID:username entries, for example "
                    "ADMIN_USER_IDS=123456789:myusername"
                )
                raise ValueError(msg)
            return

        unbound_admins = sorted(
            user_id for user_id in self._settings.admin_user_ids if user_id not in bindings
        )
        if unbound_admins:
            listed = ", ".join(str(user_id) for user_id in unbound_admins)
            logger.warning(
                "Admin IDs without a username binding: %s. Bind them as ID:username "
                "(or set STRICT_USERNAME_MATCH=1) to require both ID and username.",
                listed,
            )

    def expected_username(self, user_id: int) -> str | None:
        """Username bound to a whitelisted user, if any."""
        return self._settings.username_bindings.get(user_id)

    def _username_matches(self, user_id: int, username: str | None) -> bool:
        expected = self.expected_username(user_id)
        if expected is None:
            return not self._settings.strict_username_match
        return normalize_username(username) == expected

    def get_user(self, user_id: int) -> AuthUser | None:
        """Load a registered user by Telegram ID."""
        row = self._db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self._row_to_user(row) if row is not None else None

    def list_users(self) -> list[AuthUser]:
        """List all registered users ordered by role strength."""
        rows = self._db.fetchall("SELECT * FROM users ORDER BY user_id")
        return [self._row_to_user(row) for row in rows]

    def authenticate(self, user_id: int, username: str | None = None) -> AccessResult:
        """Check whitelist, active flag, and lockout for a user."""
        user = self.get_user(user_id)
        if user is None:
            return AccessResult(AccessStatus.UNKNOWN)

        if not user.is_active:
            return AccessResult(AccessStatus.INACTIVE, user=user)

        if not self._username_matches(user_id, username):
            return AccessResult(AccessStatus.USERNAME_MISMATCH, user=user)

        now = int(self._clock())
        if user.locked_until is not None:
            if user.locked_until > now:
                return AccessResult(
                    AccessStatus.LOCKED, user=user, retry_after=user.locked_until - now
                )
            # An expired lockout grants a fresh attempt quota.
            self.reset_failed_attempts(user_id)

        self._touch_last_seen(user, username, now)
        return AccessResult(AccessStatus.OK, user=user)

    def _touch_last_seen(self, user: AuthUser, username: str | None, now: int) -> None:
        row = self._db.fetchone(
            "SELECT last_seen, username FROM users WHERE user_id = ?", (user.user_id,)
        )
        if row is None:
            return
        last_seen = row["last_seen"]
        if (
            username == row["username"]
            and last_seen is not None
            and now - int(last_seen) < LAST_SEEN_THROTTLE_SECONDS
        ):
            return
        self._db.execute(
            "UPDATE users SET username = ?, last_seen = ? WHERE user_id = ?",
            (username, now, user.user_id),
        )

    def register_failed_attempt(self, user_id: int) -> tuple[int, int | None]:
        """Record a failed authentication attempt; returns (attempts, locked_until)."""
        row = self._db.fetchone(
            "SELECT failed_attempts, locked_until FROM users WHERE user_id = ?", (user_id,)
        )
        if row is None:
            return 0, None

        now = int(self._clock())
        previous = int(row["failed_attempts"])
        if row["locked_until"] is not None and int(row["locked_until"]) <= now:
            # An expired lockout must not leave the user with zero attempts.
            previous = 0

        attempts = previous + 1
        locked_until: int | None = None
        if attempts >= self._settings.auth_max_attempts:
            locked_until = now + self._settings.auth_lockout_seconds

        self._db.execute(
            "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE user_id = ?",
            (attempts, locked_until, user_id),
        )
        return attempts, locked_until

    def remaining_attempts(self, user_id: int) -> int:
        """Number of attempts left before the account is locked."""
        user = self.get_user(user_id)
        if user is None:
            return 0
        return max(0, self._settings.auth_max_attempts - user.failed_attempts)

    def reset_failed_attempts(self, user_id: int) -> None:
        """Clear failed attempts and any active lockout."""
        self._db.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE user_id = ?",
            (user_id,),
        )

    def unlock(self, user_id: int) -> bool:
        """Admin recovery: clear lockout for a user."""
        user = self.get_user(user_id)
        if user is None:
            return False
        self.reset_failed_attempts(user_id)
        return True

    def set_role(self, user_id: int, role: Role | str) -> bool:
        """Change the role of a registered user."""
        if self.get_user(user_id) is None:
            return False
        self._db.execute(
            "UPDATE users SET role = ? WHERE user_id = ?", (_coerce_role(role).value, user_id)
        )
        return True

    def set_active(self, user_id: int, is_active: bool) -> bool:
        """Enable or disable a registered user."""
        if self.get_user(user_id) is None:
            return False
        self._db.execute(
            "UPDATE users SET is_active = ? WHERE user_id = ?", (1 if is_active else 0, user_id)
        )
        return True

    def set_pin(self, user_id: int, pin: str) -> bool:
        """Store a new PIN hash for a registered user."""
        normalized = normalize_pin(pin)
        if normalized is None or self.get_user(user_id) is None:
            return False
        self._db.execute(
            "UPDATE users SET pin_hash = ? WHERE user_id = ?", (hash_pin(normalized), user_id)
        )
        return True

    def clear_pin(self, user_id: int) -> None:
        """Remove the stored PIN hash for a user."""
        self._db.execute(
            "UPDATE users SET pin_hash = NULL, pin_verified_until = NULL WHERE user_id = ?",
            (user_id,),
        )

    def verify_pin(self, user_id: int, pin: str) -> PinResult:
        """Verify a PIN and unlock critical actions on success."""
        user = self.get_user(user_id)
        if user is None or not user.is_active:
            return PinResult.NOT_SET

        now = int(self._clock())
        if user.locked_until is not None and user.locked_until > now:
            return PinResult.LOCKED

        if user.pin_hash is not None:
            matches = verify_pin_hash(pin, user.pin_hash)
        elif self._settings.pin:
            matches = hmac.compare_digest(pin, self._settings.pin)
        else:
            return PinResult.NOT_SET

        if not matches:
            attempts, locked_until = self.register_failed_attempt(user_id)
            if locked_until is not None:
                return PinResult.LOCKED
            return PinResult.MISMATCH

        self.reset_failed_attempts(user_id)
        self._mark_pin_verified(user_id, now)
        return PinResult.OK

    def _mark_pin_verified(self, user_id: int, now: int) -> None:
        ttl = self._settings.pin_ttl_seconds
        verified_until = now + ttl if ttl > 0 else None
        self._db.execute(
            "UPDATE users SET pin_verified_until = ? WHERE user_id = ?",
            (verified_until, user_id),
        )

    def is_critical_unlocked(self, user_id: int) -> bool:
        """Whether the user recently verified a PIN (within the TTL window)."""
        user = self.get_user(user_id)
        if user is None or user.pin_verified_until is None:
            return False
        return user.pin_verified_until > int(self._clock())

    def lockout_remaining(self, user_id: int) -> int:
        """Seconds remaining before a locked account is released."""
        user = self.get_user(user_id)
        if user is None or user.locked_until is None:
            return 0
        return max(0, user.locked_until - int(self._clock()))

    def _row_to_user(self, row: sqlite3.Row) -> AuthUser:
        return AuthUser(
            user_id=int(row["user_id"]),
            username=row["username"],
            role=_coerce_role(row["role"]),
            pin_hash=row["pin_hash"],
            is_active=bool(row["is_active"]),
            failed_attempts=int(row["failed_attempts"]),
            locked_until=row["locked_until"],
            pin_verified_until=row["pin_verified_until"],
        )
