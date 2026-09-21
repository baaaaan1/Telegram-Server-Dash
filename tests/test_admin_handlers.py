"""Tests for admin utilities: /unlock, /users, and /audit."""

from __future__ import annotations

import pytest
from aiogram.filters import CommandObject

from bot.services import build_services, log_user_action
from bot.texts import Messages
from config.settings import BotSettings
from core.audit import AuditEntry
from core.auth import Role
from handlers.admin import cmd_audit, cmd_unlock, cmd_users
from tests.conftest import ADMIN_ID, OPERATOR_ID, VIEWER_ID


def answers(message) -> list[str]:
    """All texts answered to a message double."""
    return [call.args[0] for call in message.answer.await_args_list]


def command(name: str, args: str | None = None) -> CommandObject:
    """Build an aiogram CommandObject for direct handler calls."""
    return CommandObject(prefix="/", command=name, args=args)


class TestUnlockCommand:
    """Tests for admin lockout recovery."""

    @pytest.mark.asyncio
    async def test_admin_unlocks_locked_user(self, services, make_message, settings):
        services.auth.set_pin(OPERATOR_ID, "1234")
        for _ in range(settings.auth_max_attempts):
            services.auth.verify_pin(OPERATOR_ID, "0000")

        message = make_message()
        await cmd_unlock(message, command("unlock", str(OPERATOR_ID)), services, Role.ADMIN)

        assert f"{OPERATOR_ID}" in answers(message)[0]
        assert services.auth.authenticate(OPERATOR_ID).status.value == "ok"

    @pytest.mark.asyncio
    async def test_non_admin_is_denied(self, services, make_message):
        message = make_message(user_id=VIEWER_ID)
        await cmd_unlock(message, command("unlock", str(ADMIN_ID)), services, Role.VIEWER)

        assert Messages.PERMISSION_DENIED in answers(message)

    @pytest.mark.asyncio
    async def test_usage_hint_without_argument(self, services, make_message):
        message = make_message()
        await cmd_unlock(message, command("unlock"), services, Role.ADMIN)

        assert Messages.UNLOCK_USAGE in answers(message)

    @pytest.mark.asyncio
    async def test_unknown_user_reports_missing(self, services, make_message):
        message = make_message()
        await cmd_unlock(message, command("unlock", "424242"), services, Role.ADMIN)

        assert "424242" in answers(message)[0]


class TestUsersCommand:
    """Tests for the registered user listing."""

    @pytest.mark.asyncio
    async def test_lists_registered_users_with_roles(self, services, make_message):
        message = make_message()
        await cmd_users(message, services, Role.ADMIN)

        response = answers(message)[0]
        assert str(ADMIN_ID) in response
        assert "admin" in response
        assert "operator" in response

    @pytest.mark.asyncio
    async def test_lists_username_bindings(self, db, make_message):
        """Bound accounts show their required username."""
        settings = BotSettings(
            _env_file=None, bot_token="1:test-token", admin_user_ids=f"{ADMIN_ID}:alice"
        )
        services = build_services(settings, db)
        message = make_message()
        await cmd_users(message, services, Role.ADMIN)

        assert "terikat: @alice" in answers(message)[0]

    @pytest.mark.asyncio
    async def test_empty_registry_shows_hint(self, db, make_message):
        settings = BotSettings(_env_file=None, bot_token="1:test-token")
        services = build_services(settings, db)
        message = make_message()
        await cmd_users(message, services, Role.ADMIN)

        assert Messages.USERS_EMPTY in answers(message)

    @pytest.mark.asyncio
    async def test_viewer_is_denied(self, services, make_message):
        message = make_message(user_id=VIEWER_ID)
        await cmd_users(message, services, Role.VIEWER)

        assert Messages.PERMISSION_DENIED in answers(message)

    @pytest.mark.asyncio
    async def test_permission_denial_is_audited(self, services, make_message, db):
        message = make_message(user_id=VIEWER_ID)
        await cmd_users(message, services, Role.VIEWER)

        row = db.fetchone("SELECT * FROM audit_log WHERE action = ?", ("auth.denied.permission",))
        assert row is not None
        assert row["user_id"] == VIEWER_ID
        assert row["command"] == "/users"


class TestAuditCommand:
    """Tests for the audit trail viewer."""

    @pytest.mark.asyncio
    async def test_shows_recent_entries(self, services, make_message):
        message = make_message(username="admin")
        await log_user_action(services, message, command="/status", action="monitor.status")

        reply = make_message()
        await cmd_audit(reply, command("audit", "5"), services, Role.ADMIN)

        response = answers(reply)[0]
        assert "monitor.status" in response
        assert "@admin" in response

    @pytest.mark.asyncio
    async def test_empty_trail_shows_hint(self, services, make_message):
        message = make_message()
        await cmd_audit(message, command("audit"), services, Role.ADMIN)

        assert Messages.AUDIT_EMPTY in answers(message)

    @pytest.mark.asyncio
    async def test_operator_is_denied(self, services, make_message):
        message = make_message(user_id=OPERATOR_ID)
        await cmd_audit(message, command("audit"), services, Role.OPERATOR)

        assert Messages.PERMISSION_DENIED in answers(message)

    @pytest.mark.asyncio
    async def test_limit_is_clamped(self, services, make_message, db):
        logger = services.audit
        for index in range(30):
            await logger.log(
                AuditEntry(
                    user_id=ADMIN_ID,
                    username="tester",
                    command=f"/cmd{index}",
                    action="monitor.test",
                )
            )

        message = make_message()
        await cmd_audit(message, command("audit", "999"), services, Role.ADMIN)

        response = answers(message)[0]
        assert response.count("monitor.test") == 25
