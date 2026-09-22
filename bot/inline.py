"""Inline overlay keyboards and their callback contract.

The Reply Keyboard stays the mandatory navigation surface; inline keyboards are
an *optional* overlay that re-renders one existing message in place with
``edit_text``, so switching view, revealing values, paging servers, or doing a
manual refresh never adds new chat messages.

Callback payloads are compact, validated on decode, and capped at the 64-byte
Telegram limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Self

from aiogram.enums import ButtonStyle
from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from bot.formatting import MAX_COPY_TEXT_LENGTH, MAX_CUSTOM_EMOJI_ID_LENGTH
from bot.texts import Messages

CALLBACK_PREFIX: Final = "tsd"
CALLBACK_SEPARATOR: Final = ":"
CALLBACK_FIELDS: Final = 6
MAX_CALLBACK_BYTES: Final = 64

DEFAULT_VIEW: Final = "c"
DETAIL_VIEW: Final = "f"
VIEW_CODES: Final = frozenset({DEFAULT_VIEW, DETAIL_VIEW})

MIN_PAGE: Final = 1
MAX_PAGE: Final = 99

DOCS_URL: Final = "https://github.com/baaaaan1/telegram-server-dash"

OVERLAY_SCREENS: Final = frozenset(
    {
        "home",
        "status",
        "ping",
        "monitor",
        "cpu",
        "memory",
        "network",
        "disk",
        "processes",
        "help",
    }
)

SCREENS_WITH_DETAIL: Final = frozenset({"status", "cpu", "memory", "network", "disk", "processes"})
SCREENS_WITH_REVEAL: Final = frozenset({"status", "ping", "network"})
SCREENS_WITH_COPY: Final = frozenset(
    {"status", "ping", "cpu", "memory", "network", "disk", "processes"}
)


class OverlayAction(StrEnum):
    """Actions an inline overlay button can request."""

    REFRESH = "r"
    DETAIL = "d"
    REVEAL = "s"
    PAGE = "p"
    SHOW = "v"
    INFO = "i"


@dataclass(frozen=True, slots=True)
class OverlayCallback:
    """Decoded inline callback payload for one report message."""

    action: OverlayAction
    screen: str
    view: str = DEFAULT_VIEW
    reveal: bool = False
    page: int = MIN_PAGE

    @property
    def detail(self) -> bool:
        """Whether the payload asks for the expanded (full) view."""
        return self.view == DETAIL_VIEW

    def encode(self) -> str:
        """Serialise to a callback-data string that fits the 64-byte limit."""
        payload = CALLBACK_SEPARATOR.join(
            [
                CALLBACK_PREFIX,
                str(self.action),
                self.screen,
                self.view,
                "1" if self.reveal else "0",
                str(self.page),
            ]
        )
        if len(payload.encode()) > MAX_CALLBACK_BYTES:
            msg = f"callback payload {payload!r} exceeds {MAX_CALLBACK_BYTES} bytes"
            raise ValueError(msg)
        return payload

    def with_action(
        self,
        action: OverlayAction,
        *,
        screen: str | None = None,
        view: str | None = None,
        reveal: bool | None = None,
        page: int | None = None,
    ) -> Self:
        """Return a copy of this payload with one action swapped in."""
        return type(self)(
            action=action,
            screen=self.screen if screen is None else screen,
            view=self.view if view is None else view,
            reveal=self.reveal if reveal is None else reveal,
            page=self.page if page is None else page,
        )

    @classmethod
    def parse(cls, data: str | None) -> Self | None:
        """Decode and validate a callback payload; ``None`` when malformed."""
        if not data or len(data.encode()) > MAX_CALLBACK_BYTES:
            return None
        parts = data.split(CALLBACK_SEPARATOR)
        if len(parts) != CALLBACK_FIELDS or parts[0] != CALLBACK_PREFIX:
            return None
        try:
            action = OverlayAction(parts[1])
        except ValueError:
            return None

        screen, view, reveal_flag, page_raw = parts[2], parts[3], parts[4], parts[5]
        page = int(page_raw) if page_raw.isdigit() else 0
        valid = (
            screen in OVERLAY_SCREENS
            and view in VIEW_CODES
            and reveal_flag in {"0", "1"}
            and MIN_PAGE <= page <= MAX_PAGE
        )
        if not valid:
            return None
        return cls(action=action, screen=screen, view=view, reveal=reveal_flag == "1", page=page)


def resolve_icon(catalog: dict[str, str] | None, key: str) -> str | None:
    """Look up a validated custom-emoji id; invalid or missing ids become ``None``."""
    if not catalog:
        return None
    emoji_id = str(catalog.get(key, "")).strip()
    if not emoji_id or not emoji_id.isdigit():
        return None
    if len(emoji_id) > MAX_CUSTOM_EMOJI_ID_LENGTH:
        return None
    return emoji_id


def _control(
    text: str,
    payload: OverlayCallback,
    *,
    style: str | None = None,
    icon_id: str | None = None,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=payload.encode(),
        style=style,
        icon_custom_emoji_id=icon_id,
    )


def _url_button(text: str, url: str, *, icon_id: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        url=url,
        style=ButtonStyle.PRIMARY,
        icon_custom_emoji_id=icon_id,
    )


def _copy_button(text: str, content: str, *, icon_id: str | None = None) -> InlineKeyboardButton:
    clipped = content[:MAX_COPY_TEXT_LENGTH]
    return InlineKeyboardButton(
        text=text,
        copy_text=CopyTextButton(text=clipped),
        style=ButtonStyle.SUCCESS,
        icon_custom_emoji_id=icon_id,
    )


def build_overlay(  # noqa: PLR0913 - explicit knobs keep the builder declarative
    payload: OverlayCallback,
    *,
    pages: int = MIN_PAGE,
    attention: bool = False,
    copy_content: str | None = None,
    catalog: dict[str, str] | None = None,
    quick_actions: bool = True,
) -> InlineKeyboardMarkup:
    """Build the styled inline overlay for a report message.

    ``attention`` paints the refresh control red (degraded host), detail and
    reveal toggles turn green while their mode is active, copy and docs stay
    green/blue, and pagination only appears when there is more than one page.
    """
    rows: list[list[InlineKeyboardButton]] = []

    controls = [
        _control(
            Messages.INLINE_REFRESH,
            payload.with_action(OverlayAction.REFRESH),
            style=ButtonStyle.DANGER if attention else ButtonStyle.PRIMARY,
            icon_id=resolve_icon(catalog, "refresh"),
        )
    ]
    if payload.screen in SCREENS_WITH_DETAIL:
        controls.append(
            _control(
                Messages.INLINE_DETAIL_LESS if payload.detail else Messages.INLINE_DETAIL_MORE,
                payload.with_action(
                    OverlayAction.DETAIL,
                    view=DEFAULT_VIEW if payload.detail else DETAIL_VIEW,
                ),
                style=ButtonStyle.SUCCESS if payload.detail else ButtonStyle.PRIMARY,
                icon_id=resolve_icon(catalog, "detail"),
            )
        )
    if payload.screen in SCREENS_WITH_REVEAL:
        controls.append(
            _control(
                Messages.INLINE_REVEAL_HIDE if payload.reveal else Messages.INLINE_REVEAL_SHOW,
                payload.with_action(OverlayAction.REVEAL, reveal=not payload.reveal),
                style=ButtonStyle.SUCCESS if payload.reveal else ButtonStyle.PRIMARY,
                icon_id=resolve_icon(catalog, "reveal"),
            )
        )
    rows.append(controls)

    utilities: list[InlineKeyboardButton] = []
    if copy_content and payload.screen in SCREENS_WITH_COPY:
        utilities.append(
            _copy_button(
                Messages.INLINE_COPY,
                copy_content,
                icon_id=resolve_icon(catalog, "copy"),
            )
        )
    utilities.append(
        _url_button(
            Messages.INLINE_DOCS,
            DOCS_URL,
            icon_id=resolve_icon(catalog, "docs"),
        )
    )
    rows.append(utilities)

    if quick_actions:
        rows.append(_quick_row(payload, catalog))

    if pages > MIN_PAGE:
        rows.append(_pagination_row(payload, pages, catalog))

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _quick_row(
    payload: OverlayCallback,
    catalog: dict[str, str] | None,
) -> list[InlineKeyboardButton]:
    """Shortcut row: jump between the primary dashboards inside this message."""
    if payload.screen == "home":
        shortcuts = [
            (Messages.INLINE_QUICK_STATUS, "status", ButtonStyle.PRIMARY, "status"),
            (Messages.INLINE_QUICK_PING, "ping", ButtonStyle.SUCCESS, "ping"),
            (Messages.INLINE_QUICK_HELP, "help", ButtonStyle.PRIMARY, "help"),
        ]
    else:
        shortcuts = [
            (Messages.INLINE_QUICK_HOME, "home", ButtonStyle.PRIMARY, "home"),
            (Messages.INLINE_QUICK_STATUS, "status", ButtonStyle.PRIMARY, "status"),
        ]
    return [
        _control(
            text,
            payload.with_action(OverlayAction.SHOW, screen=target, page=MIN_PAGE),
            style=style,
            icon_id=resolve_icon(catalog, icon_key),
        )
        for text, target, style, icon_key in shortcuts
    ]


def _pagination_row(
    payload: OverlayCallback,
    pages: int,
    catalog: dict[str, str] | None,
) -> list[InlineKeyboardButton]:
    page = min(max(payload.page, MIN_PAGE), pages)
    previous = page - 1 if page > MIN_PAGE else pages
    following = page + 1 if page < pages else MIN_PAGE
    return [
        _control(
            Messages.INLINE_PREV,
            payload.with_action(OverlayAction.PAGE, page=previous),
            style=ButtonStyle.PRIMARY,
            icon_id=resolve_icon(catalog, "prev"),
        ),
        _control(
            Messages.INLINE_PAGE_INDICATOR.format(page=page, pages=pages),
            payload.with_action(
                OverlayAction.INFO,
                view=DETAIL_VIEW if payload.detail else DEFAULT_VIEW,
                page=page,
            ),
            style=ButtonStyle.SUCCESS,
            icon_id=resolve_icon(catalog, "page"),
        ),
        _control(
            Messages.INLINE_NEXT,
            payload.with_action(OverlayAction.PAGE, page=following),
            style=ButtonStyle.PRIMARY,
            icon_id=resolve_icon(catalog, "next"),
        ),
    ]


def build_help_overlay(
    payload: OverlayCallback,
    *,
    catalog: dict[str, str] | None = None,
) -> InlineKeyboardMarkup:
    """Overlay for the paged help screen: page stepper plus a full-text view."""
    pages = len(Messages.HELP_PAGES_ID)
    showing_all = payload.page > pages
    page = pages if showing_all else min(max(payload.page, MIN_PAGE), pages)
    previous = page - 1 if page > MIN_PAGE else pages
    following = page + 1 if page < pages else MIN_PAGE
    indicator = (
        Messages.INLINE_PAGE_ALL
        if showing_all
        else Messages.INLINE_PAGE_INDICATOR.format(page=page, pages=pages)
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _control(
                    Messages.INLINE_PREV,
                    payload.with_action(OverlayAction.PAGE, page=previous),
                    style=ButtonStyle.PRIMARY,
                    icon_id=resolve_icon(catalog, "prev"),
                ),
                _control(
                    indicator,
                    payload.with_action(OverlayAction.INFO, page=page),
                    style=ButtonStyle.SUCCESS,
                    icon_id=resolve_icon(catalog, "page"),
                ),
                _control(
                    Messages.INLINE_NEXT,
                    payload.with_action(OverlayAction.PAGE, page=following),
                    style=ButtonStyle.PRIMARY,
                    icon_id=resolve_icon(catalog, "next"),
                ),
            ],
            [
                _control(
                    Messages.INLINE_HELP_ALL,
                    payload.with_action(OverlayAction.SHOW, screen="help", page=MAX_PAGE),
                    style=ButtonStyle.SUCCESS if not showing_all else ButtonStyle.PRIMARY,
                    icon_id=resolve_icon(catalog, "help"),
                ),
                _url_button(
                    Messages.INLINE_DOCS,
                    DOCS_URL,
                    icon_id=resolve_icon(catalog, "docs"),
                ),
            ],
        ]
    )
