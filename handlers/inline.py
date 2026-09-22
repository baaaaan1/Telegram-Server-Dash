"""Inline panel router: refresh, density, reveal, pagination, and shortcuts.

Every action edits the message the button lives on (``edit_text``), so a panel
never adds chat messages and never replaces the Reply Keyboard. Authentication,
role checks, rate limiting, and audit logging are handled by
:class:`bot.middleware.AccessMiddleware` for callback updates too.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.formatting import to_plain_text
from bot.inline import CALLBACK_PREFIX, OverlayAction, OverlayCallback
from bot.render import EditOutcome, ScreenReport, edit_report
from bot.services import Services, log_user_action
from bot.texts import Messages
from handlers.monitor import MONITOR_SCREENS, render_screen_report
from handlers.status import render_ping_report, render_status_report

router = Router()
logger = logging.getLogger(__name__)

CALLBACK_FILTER = F.data.startswith(f"{CALLBACK_PREFIX}:")


def _toast_text(payload: OverlayCallback, outcome: EditOutcome) -> str:
    """User-facing callback answer for the action that was just served."""
    if outcome is not EditOutcome.EDITED:
        return (
            Messages.TOAST_UNCHANGED if outcome is EditOutcome.UNCHANGED else Messages.TOAST_STALE
        )
    if payload.action is OverlayAction.SHOW and payload.screen == "help" and payload.page > 1:
        return Messages.TOAST_HELP_ALL
    toggles = {
        OverlayAction.DETAIL: (
            Messages.TOAST_DETAIL_ON if payload.detail else Messages.TOAST_DETAIL_OFF
        ),
        OverlayAction.REVEAL: (
            Messages.TOAST_REVEAL_ON if payload.reveal else Messages.TOAST_REVEAL_OFF
        ),
        OverlayAction.PAGE: Messages.TOAST_PAGE.format(page=payload.page),
    }
    return toggles.get(payload.action, Messages.TOAST_REFRESHED)


async def _answer(callback: CallbackQuery, text: str, *, alert: bool = False) -> None:
    """Answer a callback query so the client spinner always stops."""
    try:
        await callback.answer(text, show_alert=alert)
    except Exception:
        logger.warning("Failed to answer callback query", exc_info=True)


def _owns_panel(callback: CallbackQuery) -> bool:
    """Secondary guard: the panel may only be driven by the chat owner."""
    message = callback.message
    chat = getattr(message, "chat", None)
    user = callback.from_user
    return chat is not None and user is not None and getattr(chat, "id", None) == user.id


def _is_expired(report: ScreenReport) -> bool:
    """A report without a renderable body means the screen could not be rebuilt."""
    return not report.text.strip()


async def _render(services: Services, payload: OverlayCallback) -> ScreenReport:
    """Rebuild the screen requested by an inline action."""
    if payload.screen == "home":
        return ScreenReport(screen="home", text=Messages.INLINE_HOME_PANEL)
    if payload.screen == "help":
        return _render_help(services, payload)
    if payload.screen in MONITOR_SCREENS:
        return await render_screen_report(
            payload.screen,
            detail=payload.detail,
            reveal=payload.reveal,
            page=payload.page,
        )
    if payload.screen == "ping":
        return await render_ping_report(reveal=payload.reveal, page=payload.page)
    return await render_status_report(
        detail=payload.detail,
        reveal=payload.reveal,
        page=payload.page,
    )


def _render_help(services: Services, payload: OverlayCallback) -> ScreenReport:
    """Paged help: one topic per page, plus the combined view as the last page."""
    indonesian = services.settings.environment != "production"
    pages = Messages.HELP_PAGES_ID if indonesian else Messages.HELP_PAGES_EN
    combined = Messages.HELP_TEXT_ID if indonesian else Messages.HELP_TEXT_EN

    if payload.page > len(pages):
        return ScreenReport(
            screen="help",
            text=combined,
            page=payload.page,
            pages=len(pages),
            copy_text=to_plain_text(combined),
        )

    index = min(max(payload.page, 1), len(pages)) - 1
    page = pages[index]
    text = f"{Messages.SCREEN_HELP}\n{page.title}\n\n<blockquote>{page.body}</blockquote>"
    return ScreenReport(
        screen="help",
        text=text,
        page=index + 1,
        pages=len(pages),
        copy_text=to_plain_text(text),
    )


@router.callback_query(CALLBACK_FILTER)
async def handle_panel(callback: CallbackQuery, services: Services) -> None:
    """Serve every inline panel action by editing the panel message in place."""
    if not _owns_panel(callback):
        await _answer(callback, Messages.TOAST_FOREIGN, alert=True)
        await log_user_action(
            services,
            callback,
            command=callback.data or "<callback>",
            action="panel.denied.foreign",
            result="denied",
        )
        return

    payload = OverlayCallback.parse(callback.data)
    if payload is None:
        await _answer(callback, Messages.TOAST_UNKNOWN, alert=True)
        await log_user_action(
            services,
            callback,
            command=callback.data or "<callback>",
            action="panel.denied.unknown",
            result="denied",
        )
        return

    if payload.action is OverlayAction.INFO:
        await _answer(callback, Messages.TOAST_PAGE.format(page=payload.page))
        return

    report = await _render(services, payload)
    if _is_expired(report):
        await _answer(callback, Messages.TOAST_STALE, alert=True)
        return

    outcome = await edit_report(callback, report, catalog=services.settings.custom_emoji_ids)
    await _answer(callback, _toast_text(payload, outcome))
    await log_user_action(
        services,
        callback,
        command=callback.data or "<callback>",
        action=f"panel.{payload.action.value}",
        result=str(outcome),
    )


__all__ = ["handle_panel", "router"]
