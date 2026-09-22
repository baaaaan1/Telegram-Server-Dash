"""Tests for the inline panel router: in-place edits, toasts, and guardrails.

The panel is the optional half of the hybrid UX, so these tests focus on the two
properties that keep it safe: it must never post new chat messages, and it must
never serve a payload it cannot validate.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest

from bot.inline import MAX_PAGE, OverlayAction, OverlayCallback
from bot.render import EditOutcome, ScreenReport
from bot.texts import Messages
from handlers.inline import handle_panel

HELP_PAGE_TWO = OverlayCallback(
    action=OverlayAction.PAGE, screen="help", view="c", reveal=False, page=2
)
INFO_PAGE_TWO = OverlayCallback(
    action=OverlayAction.INFO, screen="status", view="c", reveal=False, page=2
)


def edited_text(callback) -> str:
    """Text passed to the panel message edit."""
    return callback.message.edit_text.await_args.args[0]


class TestPanelEditing:
    """Every request re-renders the existing message instead of sending a new one."""

    @pytest.mark.asyncio
    async def test_help_pagination_edits_in_place(self, services, make_panel_callback):
        callback = make_panel_callback(data=HELP_PAGE_TWO.encode())

        await handle_panel(callback, services)

        callback.message.edit_text.assert_awaited_once()
        callback.message.answer.assert_not_awaited()
        assert "Keamanan" in edited_text(callback)
        assert callback.answer.await_args.args[0] == Messages.TOAST_PAGE.format(page=2)

    @pytest.mark.asyncio
    async def test_help_combined_view_is_a_normal_page(self, services, make_panel_callback):
        payload = HELP_PAGE_TWO.with_action(OverlayAction.SHOW, page=MAX_PAGE)
        callback = make_panel_callback(data=payload.encode())

        await handle_panel(callback, services)

        text = edited_text(callback)
        assert Messages.SCREEN_HELP in text
        assert "📊 Monitoring" in text
        assert "🛡️ Admin" in text
        assert callback.answer.await_args.args[0] == Messages.TOAST_HELP_ALL

    @pytest.mark.asyncio
    async def test_home_shortcut_renders_the_quick_panel(self, services, make_panel_callback):
        payload = OverlayCallback(
            action=OverlayAction.SHOW, screen="home", view="c", reveal=False, page=1
        )
        callback = make_panel_callback(data=payload.encode())

        await handle_panel(callback, services)

        assert edited_text(callback) == Messages.INLINE_HOME_PANEL

    @pytest.mark.asyncio
    async def test_refresh_routes_to_the_screen_renderer(self, services, make_panel_callback):
        payload = OverlayCallback(
            action=OverlayAction.REFRESH, screen="status", view="f", reveal=True, page=1
        )
        callback = make_panel_callback(data=payload.encode())
        report = ScreenReport(screen="status", text="<b>fresh</b>", detail=True, reveal=True)

        with patch(
            "handlers.inline.render_status_report", AsyncMock(return_value=report)
        ) as renderer:
            await handle_panel(callback, services)

        renderer.assert_awaited_once_with(detail=True, reveal=True, page=1)
        assert edited_text(callback) == "<b>fresh</b>"
        assert callback.answer.await_args.args[0] == Messages.TOAST_REFRESHED

    @pytest.mark.asyncio
    async def test_detail_toggle_toasts_the_new_mode(self, services, make_panel_callback):
        payload = OverlayCallback(
            action=OverlayAction.DETAIL, screen="help", view="c", reveal=False, page=1
        )
        callback = make_panel_callback(data=payload.encode())

        await handle_panel(callback, services)

        assert callback.answer.await_args.args[0] == Messages.TOAST_DETAIL_OFF

    @pytest.mark.asyncio
    async def test_edit_is_audited(self, services, make_panel_callback, db):
        callback = make_panel_callback(data=HELP_PAGE_TWO.encode())

        await handle_panel(callback, services)

        row = db.fetchone("SELECT * FROM audit_log WHERE action = ?", ("panel.p",))
        assert row is not None
        assert row["result"] == EditOutcome.EDITED

    @pytest.mark.asyncio
    async def test_callback_payload_is_audited_verbatim(self, services, make_panel_callback, db):
        payload = HELP_PAGE_TWO.encode()
        callback = make_panel_callback(data=payload)

        await handle_panel(callback, services)

        row = db.fetchone("SELECT command FROM audit_log WHERE action = ?", ("panel.p",))
        assert row["command"] == payload


class TestPanelOutcomes:
    """Unchanged and stale panels get their own feedback instead of an error."""

    @pytest.mark.asyncio
    async def test_unchanged_message_reports_no_change(self, services, make_panel_callback):
        callback = make_panel_callback(data=HELP_PAGE_TWO.encode())
        callback.message.edit_text.side_effect = TelegramBadRequest(
            method=None, message="Bad Request: message is not modified"
        )

        await handle_panel(callback, services)

        assert callback.answer.await_args.args[0] == Messages.TOAST_UNCHANGED

    @pytest.mark.asyncio
    async def test_older_message_reports_stale_panel(self, services, make_panel_callback):
        callback = make_panel_callback(data=HELP_PAGE_TWO.encode())
        callback.message.edit_text.side_effect = TelegramBadRequest(
            method=None, message="Bad Request: message to edit not found"
        )

        await handle_panel(callback, services)

        assert callback.answer.await_args.args[0] == Messages.TOAST_STALE

    @pytest.mark.asyncio
    async def test_inaccessible_panel_message_is_refused(self, services, make_panel_callback, db):
        callback = make_panel_callback(data=HELP_PAGE_TWO.encode())
        callback.message = None

        await handle_panel(callback, services)

        assert callback.answer.await_args.args[0] == Messages.TOAST_FOREIGN
        row = db.fetchone("SELECT * FROM audit_log WHERE action = ?", ("panel.denied.foreign",))
        assert row is not None


class TestPanelGuardrails:
    """Malformed payloads and foreign panels must be refused and audited."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "data",
        [
            "tsd:zz:status:c:0:1",
            "tsd:r:unknown:c:0:1",
            "foreign:r:status:c:0:1",
            "tsd",
        ],
    )
    async def test_malformed_payloads_are_refused(self, services, make_panel_callback, db, data):
        callback = make_panel_callback(data=data)

        await handle_panel(callback, services)

        callback.message.edit_text.assert_not_awaited()
        assert callback.answer.await_args.args[0] == Messages.TOAST_UNKNOWN
        assert callback.answer.await_args.kwargs["show_alert"] is True
        row = db.fetchone("SELECT * FROM audit_log WHERE action = ?", ("panel.denied.unknown",))
        assert row is not None
        assert row["result"] == "denied"

    @pytest.mark.asyncio
    async def test_foreign_panel_owner_is_refused(self, services, make_panel_callback, db):
        callback = make_panel_callback(
            user_id=1003,
            data=HELP_PAGE_TWO.encode(),
            chat_id=1001,
        )

        await handle_panel(callback, services)

        callback.message.edit_text.assert_not_awaited()
        assert callback.answer.await_args.args[0] == Messages.TOAST_FOREIGN
        row = db.fetchone("SELECT * FROM audit_log WHERE action = ?", ("panel.denied.foreign",))
        assert row is not None

    @pytest.mark.asyncio
    async def test_info_action_answers_without_editing(self, services, make_panel_callback):
        callback = make_panel_callback(data=INFO_PAGE_TWO.encode())

        await handle_panel(callback, services)

        callback.message.edit_text.assert_not_awaited()
        assert callback.answer.await_args.args[0] == Messages.TOAST_PAGE.format(page=2)

    @pytest.mark.asyncio
    async def test_dead_panel_message_is_not_edited(self, services, make_panel_callback):
        callback = make_panel_callback(data=HELP_PAGE_TWO.encode())
        callback.message.answer = AsyncMock()

        with patch("handlers.inline.edit_report", AsyncMock(return_value=EditOutcome.FAILED)):
            await handle_panel(callback, services)

        callback.message.answer.assert_not_awaited()
        assert callback.answer.await_args.args[0] == Messages.TOAST_STALE
