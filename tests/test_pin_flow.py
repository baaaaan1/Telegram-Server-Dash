"""Tests for the critical action confirmation and PIN FSM flows."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.services import build_services
from bot.texts import Messages
from config.settings import BotSettings
from core.auth import Role
from handlers.critical import (
    CriticalActionSpec,
    CriticalRequest,
    PinFlow,
    cmd_pin,
    cmd_whoami,
    confirm_guard,
    confirm_no,
    confirm_yes,
    enter_pin,
    pin_setup_confirm,
    pin_setup_current,
    pin_setup_new,
    register_critical_action,
    request_critical_action,
    unregister_critical_action,
)
from handlers.navigation import btn_back, btn_cancel
from tests.conftest import ADMIN_ID, VIEWER_ID


def answers(message) -> list[str]:
    """All texts answered to a message double."""
    return [call.args[0] for call in message.answer.await_args_list]


@pytest.fixture
def reboot_action():
    """Registered critical action with a mock executor."""
    executor = AsyncMock()
    register_critical_action(CriticalActionSpec(key="reboot", title="Reboot Server"), executor)
    yield executor
    unregister_critical_action("reboot")


class TestPinSetup:
    """Tests for /pin setup and change flows."""

    @pytest.mark.asyncio
    async def test_first_time_setup_stores_pin(self, services, make_message, make_state):
        state = make_state()

        await cmd_pin(make_message(text="/pin"), state, services)
        assert await state.get_state() == PinFlow.set_new.state

        await pin_setup_new(make_message(text="1234"), state)
        assert await state.get_state() == PinFlow.set_confirm.state

        await pin_setup_confirm(make_message(text="1234"), state, services)

        assert await state.get_state() is None
        assert services.auth.get_user(ADMIN_ID).has_pin is True

    @pytest.mark.asyncio
    async def test_confirm_mismatch_returns_to_new_pin(self, services, make_message, make_state):
        state = make_state()
        await cmd_pin(make_message(text="/pin"), state, services)
        await pin_setup_new(make_message(text="1234"), state)

        confirm = make_message(text="9999")
        await pin_setup_confirm(confirm, state, services)

        assert await state.get_state() == PinFlow.set_new.state
        assert Messages.PIN_SETUP_MISMATCH in answers(confirm)
        assert services.auth.get_user(ADMIN_ID).has_pin is False

    @pytest.mark.asyncio
    async def test_invalid_pin_format_is_rejected(self, services, make_message, make_state):
        state = make_state()
        await cmd_pin(make_message(text="/pin"), state, services)

        invalid = make_message(text="12ab")
        await pin_setup_new(invalid, state)

        assert Messages.PIN_SETUP_INVALID in answers(invalid)
        assert await state.get_state() == PinFlow.set_new.state

    @pytest.mark.asyncio
    async def test_change_pin_requires_current_pin(self, services, make_message, make_state):
        services.auth.set_pin(ADMIN_ID, "1234")
        state = make_state()

        await cmd_pin(make_message(text="/pin"), state, services)
        assert await state.get_state() == PinFlow.set_current.state

        wrong = make_message(text="0000")
        await pin_setup_current(wrong, state, services)
        assert any("PIN salah" in text for text in answers(wrong))
        assert await state.get_state() == PinFlow.set_current.state

        await pin_setup_current(make_message(text="1234"), state, services)
        assert await state.get_state() == PinFlow.set_new.state


class TestCriticalActionFlow:
    """Tests for confirmation + PIN gating of critical actions."""

    @pytest.mark.asyncio
    async def test_action_requires_confirmation_and_pin(
        self, services, make_message, make_state, reboot_action
    ):
        services.auth.set_pin(ADMIN_ID, "1234")
        state = make_state()

        request = make_message(text="reboot")
        started = await request_critical_action(
            request, state, services, CriticalRequest(key="reboot", role=Role.ADMIN)
        )
        assert started is True
        assert await state.get_state() == PinFlow.confirm_action.state

        confirm = make_message(text=Messages.BTN_YES)
        await confirm_yes(confirm, state, services)
        assert await state.get_state() == PinFlow.enter_pin.state
        assert Messages.PIN_PROMPT in answers(confirm)

        pin_message = make_message(text="1234")
        await enter_pin(pin_message, state, services)

        reboot_action.assert_awaited_once()
        assert await state.get_state() is None
        assert any("Reboot Server" in text for text in answers(pin_message))

    @pytest.mark.asyncio
    async def test_wrong_pin_keeps_state_and_reports_attempts(
        self, services, make_message, make_state, reboot_action
    ):
        services.auth.set_pin(ADMIN_ID, "1234")
        state = make_state()
        await request_critical_action(
            make_message(text="reboot"),
            state,
            services,
            CriticalRequest(key="reboot", role=Role.ADMIN),
        )
        await confirm_yes(make_message(text=Messages.BTN_YES), state, services)

        wrong = make_message(text="0000")
        await enter_pin(wrong, state, services)

        assert any("PIN salah" in text for text in answers(wrong))
        assert await state.get_state() == PinFlow.enter_pin.state
        reboot_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_recent_pin_skips_prompt(self, services, make_message, make_state, reboot_action):
        services.auth.set_pin(ADMIN_ID, "1234")
        services.auth.verify_pin(ADMIN_ID, "1234")
        state = make_state()

        await request_critical_action(
            make_message(text="reboot"),
            state,
            services,
            CriticalRequest(key="reboot", role=Role.ADMIN),
        )
        await confirm_yes(make_message(text=Messages.BTN_YES), state, services)

        reboot_action.assert_awaited_once()
        assert await state.get_state() is None

    @pytest.mark.asyncio
    async def test_cancel_does_not_execute(self, services, make_message, make_state, reboot_action):
        state = make_state()
        await request_critical_action(
            make_message(text="reboot"),
            state,
            services,
            CriticalRequest(key="reboot", role=Role.ADMIN),
        )

        cancel = make_message(text=Messages.BTN_NO)
        await confirm_no(cancel, state, services)

        assert await state.get_state() is None
        assert Messages.ACTION_CANCELLED in answers(cancel)
        reboot_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_viewer_cannot_start_critical_action(
        self, services, make_message, make_state, reboot_action, db
    ):
        state = make_state()
        denied = make_message(user_id=VIEWER_ID, text="reboot")

        started = await request_critical_action(
            denied, state, services, CriticalRequest(key="reboot", role=Role.VIEWER)
        )

        assert started is False
        assert Messages.PERMISSION_DENIED in answers(denied)
        assert await state.get_state() is None
        row = db.fetchone("SELECT * FROM audit_log WHERE action = ?", ("auth.denied.permission",))
        assert row is not None
        assert row["user_id"] == VIEWER_ID

    @pytest.mark.asyncio
    async def test_unknown_action_is_rejected(self, services, make_message, make_state):
        state = make_state()
        message = make_message(text="ghost")

        started = await request_critical_action(
            message, state, services, CriticalRequest(key="ghost", role=Role.ADMIN)
        )

        assert started is False
        assert Messages.ERROR_UNKNOWN in answers(message)

    @pytest.mark.asyncio
    async def test_confirm_state_guardrail(self, make_message, make_state):
        state = make_state()
        await state.set_state(PinFlow.confirm_action)

        message = make_message(text="apapun")
        await confirm_guard(message)

        assert Messages.CONFIRM_CHOICE_ONLY in answers(message)


class TestCancelNavigation:
    """Tests that Cancel and Back always abort the running FSM flow."""

    @pytest.mark.asyncio
    async def test_cancel_clears_pin_state(self, services, make_message, make_state):
        state = make_state()
        await state.set_state(PinFlow.enter_pin)

        message = make_message(text=Messages.BTN_CANCEL)
        await btn_cancel(message, state, services)

        assert await state.get_state() is None
        assert Messages.ACTION_CANCELLED in answers(message)

    @pytest.mark.asyncio
    async def test_back_cancels_pending_confirmation(
        self, services, make_message, make_state, reboot_action
    ):
        """Back must not leave a critical confirmation armed in the background."""
        state = make_state()
        await request_critical_action(
            make_message(text="reboot"),
            state,
            services,
            CriticalRequest(key="reboot", role=Role.ADMIN),
        )
        assert await state.get_state() == PinFlow.confirm_action.state

        message = make_message(text=Messages.BTN_BACK)
        await btn_back(message, state, services)

        assert await state.get_state() is None
        assert Messages.ACTION_CANCELLED in answers(message)
        reboot_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_back_cancels_pin_setup(self, services, make_message, make_state):
        state = make_state()
        await cmd_pin(make_message(text="/pin"), state, services)
        assert await state.get_state() == PinFlow.set_new.state

        message = make_message(text=Messages.BTN_BACK)
        await btn_back(message, state, services)

        assert await state.get_state() is None
        assert Messages.ACTION_CANCELLED in answers(message)


class TestWhoami:
    """Tests for the /whoami account summary."""

    @pytest.mark.asyncio
    async def test_whoami_lists_role_and_permissions(self, services, make_message):
        message = make_message()
        await cmd_whoami(message, services, Role.ADMIN)

        text = answers(message)[0]
        assert "admin" in text
        assert "manage_users" in text
        assert str(ADMIN_ID) in text
        assert "tidak terikat" in text

    @pytest.mark.asyncio
    async def test_whoami_shows_username_binding(self, db, make_message):
        settings = BotSettings(
            _env_file=None, bot_token="1:test-token", admin_user_ids=f"{ADMIN_ID}:alice"
        )
        services = build_services(settings, db)
        message = make_message(user_id=ADMIN_ID, username="alice")
        await cmd_whoami(message, services, Role.ADMIN)

        assert "terikat @alice" in answers(message)[0]
