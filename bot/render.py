"""Report rendering pipeline: Reply Keyboard header plus inline panel message.

Each screen sends exactly one navigation header (carrying the mandatory Reply
Keyboard) and one report message (carrying the inline overlay). Inline actions
re-render the report in place with ``edit_text``; the header is never touched, so
``Cancel``/``Back``/``Home`` stay on screen for the whole interaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LinkPreviewOptions, Message
from aiogram.types import ReplyKeyboardMarkup as ReplyMarkup

from bot.formatting import bold, to_plain_text
from bot.inline import (
    DEFAULT_VIEW,
    DETAIL_VIEW,
    OverlayAction,
    OverlayCallback,
    build_help_overlay,
    build_overlay,
)
from bot.texts import Messages

__all__ = [
    "EditOutcome",
    "ScreenReport",
    "build_markup",
    "edit_report",
    "help_report",
    "paginate",
    "send_panel",
    "send_report",
]

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE: Final = 3
LINK_PREVIEW_DISABLED: Final = LinkPreviewOptions(is_disabled=True)
NOT_MODIFIED_MARKER: Final = "not modified"


class EditOutcome(StrEnum):
    """Result of re-rendering an existing panel message."""

    EDITED = "edited"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ScreenReport:
    """One renderable report: rich body text plus its panel state."""

    screen: str
    text: str
    page: int = 1
    pages: int = 1
    detail: bool = False
    reveal: bool = False
    attention: bool = False
    copy_text: str | None = None

    def payload(self) -> OverlayCallback:
        """Callback payload describing this report's current state."""
        return OverlayCallback(
            action=OverlayAction.INFO,
            screen=self.screen,
            view=DETAIL_VIEW if self.detail else DEFAULT_VIEW,
            reveal=self.reveal,
            page=self.page,
        )


def build_markup(
    report: ScreenReport, catalog: dict[str, str] | None = None
) -> InlineKeyboardMarkup:
    """Inline overlay markup matching the report's state."""
    payload = report.payload()
    if report.screen == "help":
        return build_help_overlay(payload, catalog=catalog)
    return build_overlay(
        payload,
        pages=report.pages,
        attention=report.attention,
        copy_content=report.copy_text,
        catalog=catalog,
    )


async def send_panel(
    message: Message,
    report: ScreenReport,
    *,
    catalog: dict[str, str] | None = None,
) -> Message:
    """Send only the report message with its inline panel."""
    return await message.answer(
        report.text,
        reply_markup=build_markup(report, catalog),
        link_preview_options=LINK_PREVIEW_DISABLED,
    )


async def send_report(
    message: Message,
    report: ScreenReport,
    *,
    reply_markup: ReplyMarkup,
    catalog: dict[str, str] | None = None,
    hint: str | None = None,
) -> Message | None:
    """Send the navigation header then the report with its inline panel."""
    await message.answer(
        Messages.nav_header(report.screen, hint or Messages.NAV_HINT_REPLY_KEYBOARD),
        reply_markup=reply_markup,
    )
    return await send_panel(message, report, catalog=catalog)


async def edit_report(
    callback: CallbackQuery,
    report: ScreenReport,
    *,
    catalog: dict[str, str] | None = None,
) -> EditOutcome:
    """Re-render the callback's own message in place (no new chat messages)."""
    message = callback.message
    if message is None or getattr(message, "edit_text", None) is None:
        return EditOutcome.FAILED
    try:
        await message.edit_text(
            report.text,
            reply_markup=build_markup(report, catalog),
            link_preview_options=LINK_PREVIEW_DISABLED,
        )
    except TelegramBadRequest as error:
        if NOT_MODIFIED_MARKER in str(error).lower():
            return EditOutcome.UNCHANGED
        logger.warning("Rejected panel edit for screen %s: %s", report.screen, error)
        return EditOutcome.FAILED
    except Exception:
        logger.warning("Failed to edit panel message for screen %s", report.screen, exc_info=True)
        return EditOutcome.FAILED
    return EditOutcome.EDITED


def paginate(
    items: list[str], page: int, per_page: int = DEFAULT_PAGE_SIZE
) -> tuple[list[str], int, int]:
    """Clamp ``page`` to the available range and return the slice, page, and count."""
    if per_page < 1:
        per_page = DEFAULT_PAGE_SIZE
    pages = max(1, -(-len(items) // per_page))
    current = min(max(page, 1), pages)
    start = (current - 1) * per_page
    return items[start : start + per_page], current, pages


def help_report(page: int = 1, *, indonesian: bool = True) -> ScreenReport:
    """Paged help: one topic per page plus the combined view as an extra page."""
    pages = Messages.HELP_PAGES_ID if indonesian else Messages.HELP_PAGES_EN
    combined = Messages.HELP_TEXT_ID if indonesian else Messages.HELP_TEXT_EN

    if page > len(pages):
        return ScreenReport(
            screen="help",
            text=combined,
            page=page,
            pages=len(pages),
            copy_text=to_plain_text(combined),
        )

    index = min(max(page, 1), len(pages)) - 1
    topic = pages[index]
    text = f"{Messages.SCREEN_HELP}\n{bold(topic.title)}\n\n<blockquote>{topic.body}</blockquote>"
    return ScreenReport(
        screen="help",
        text=text,
        page=index + 1,
        pages=len(pages),
        copy_text=to_plain_text(text),
    )


def home_panel() -> ScreenReport:
    """Welcome-screen quick panel that can morph into any dashboard in place."""
    return ScreenReport(screen="home", text=Messages.INLINE_HOME_PANEL)
