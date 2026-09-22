"""Reply keyboard builders - the mandatory navigation surface.

Inline keyboards only ever act as an overlay on report messages, so every screen
keeps its Reply Keyboard with ``Cancel``/``Back``/``Home``. Buttons also carry the
Bot API button style and, when the deployment configures custom emoji ids, a
premium icon.
"""

from __future__ import annotations

from aiogram.enums import ButtonStyle
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot.inline import resolve_icon
from bot.texts import Messages

BUTTON_ICON_KEYS: dict[str, str] = {
    Messages.BTN_HOME: "home",
    Messages.BTN_BACK: "back",
    Messages.BTN_CANCEL: "cancel",
    Messages.BTN_YES: "yes",
    Messages.BTN_NO: "no",
    Messages.MENU_STATUS: "menu_status",
    Messages.MENU_MONITOR: "menu_monitor",
    Messages.MENU_PING: "menu_ping",
    Messages.MENU_HELP: "menu_help",
    Messages.MENU_CPU: "menu_cpu",
    Messages.MENU_MEMORY: "menu_memory",
    Messages.MENU_NETWORK: "menu_network",
    Messages.MENU_DISK: "menu_disk",
    Messages.MENU_PROCESSES: "menu_processes",
}

BUTTON_STYLES: dict[str, str] = {
    Messages.BTN_CANCEL: ButtonStyle.DANGER,
    Messages.BTN_NO: ButtonStyle.DANGER,
    Messages.BTN_HOME: ButtonStyle.PRIMARY,
    Messages.BTN_BACK: ButtonStyle.PRIMARY,
    Messages.BTN_YES: ButtonStyle.SUCCESS,
    Messages.MENU_STATUS: ButtonStyle.SUCCESS,
    Messages.MENU_MONITOR: ButtonStyle.PRIMARY,
    Messages.MENU_PING: ButtonStyle.SUCCESS,
    Messages.MENU_HELP: ButtonStyle.PRIMARY,
    Messages.MENU_CPU: ButtonStyle.PRIMARY,
    Messages.MENU_MEMORY: ButtonStyle.PRIMARY,
    Messages.MENU_NETWORK: ButtonStyle.PRIMARY,
    Messages.MENU_DISK: ButtonStyle.PRIMARY,
    Messages.MENU_PROCESSES: ButtonStyle.PRIMARY,
}

INPUT_PLACEHOLDER = "Ketik perintah atau pilih menu…"


def action_button(text: str, catalog: dict[str, str] | None = None) -> KeyboardButton:
    """Reply-keyboard button with its configured style and optional custom emoji."""
    icon_key = BUTTON_ICON_KEYS.get(text)
    return KeyboardButton(
        text=text,
        style=BUTTON_STYLES.get(text),
        icon_custom_emoji_id=resolve_icon(catalog, icon_key) if icon_key else None,
    )


class NavigationButtons:
    """Factory for navigation button row."""

    @staticmethod
    def home(catalog: dict[str, str] | None = None) -> KeyboardButton:
        return action_button(Messages.BTN_HOME, catalog)

    @staticmethod
    def back(catalog: dict[str, str] | None = None) -> KeyboardButton:
        return action_button(Messages.BTN_BACK, catalog)

    @staticmethod
    def cancel(catalog: dict[str, str] | None = None) -> KeyboardButton:
        return action_button(Messages.BTN_CANCEL, catalog)

    @staticmethod
    def nav_row(catalog: dict[str, str] | None = None) -> list[KeyboardButton]:
        """Return the standard navigation button row: [Cancel, Back, Home]."""
        return [
            NavigationButtons.cancel(catalog),
            NavigationButtons.back(catalog),
            NavigationButtons.home(catalog),
        ]


def build_nav_row(catalog: dict[str, str] | None = None) -> list[KeyboardButton]:
    """Build standard navigation buttons row."""
    return NavigationButtons.nav_row(catalog)


def make_reply_keyboard(  # noqa: PLR0913 - mirrors the ReplyKeyboardMarkup fields
    rows: list[list[KeyboardButton]] | None = None,
    include_nav: bool = True,
    resize_keyboard: bool = True,
    one_time_keyboard: bool = False,
    catalog: dict[str, str] | None = None,
) -> ReplyKeyboardMarkup:
    """Create a ReplyKeyboardMarkup with optional navigation row.

    Args:
        rows: List of button rows (each row is a list of KeyboardButton).
        include_nav: If True, appends the standard [Cancel, Back, Home] row.
        resize_keyboard: Auto-resize keyboard.
        one_time_keyboard: Hide keyboard after first selection.
        catalog: Optional custom-emoji id catalog for button icons.

    Returns:
        ReplyKeyboardMarkup ready for aiogram.
    """
    keyboard: list[list[KeyboardButton]] = [row[:] for row in rows] if rows else []
    if include_nav:
        keyboard.append(NavigationButtons.nav_row(catalog))

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=resize_keyboard,
        one_time_keyboard=one_time_keyboard,
        input_field_placeholder=INPUT_PLACEHOLDER,
    )


def make_home_keyboard(catalog: dict[str, str] | None = None) -> ReplyKeyboardMarkup:
    """Create home screen keyboard with primary navigation."""
    return make_reply_keyboard(
        rows=[
            [action_button(Messages.MENU_STATUS, catalog)],
            [action_button(Messages.MENU_MONITOR, catalog)],
            [action_button(Messages.MENU_PING, catalog)],
            [action_button(Messages.MENU_HELP, catalog)],
        ],
        catalog=catalog,
    )


def make_monitor_keyboard(catalog: dict[str, str] | None = None) -> ReplyKeyboardMarkup:
    """Create monitor submenu keyboard."""
    return make_reply_keyboard(
        rows=[
            [
                action_button(Messages.MENU_CPU, catalog),
                action_button(Messages.MENU_MEMORY, catalog),
            ],
            [
                action_button(Messages.MENU_NETWORK, catalog),
                action_button(Messages.MENU_DISK, catalog),
            ],
            [action_button(Messages.MENU_PROCESSES, catalog)],
        ],
        catalog=catalog,
    )


def make_cancel_only_keyboard(catalog: dict[str, str] | None = None) -> ReplyKeyboardMarkup:
    """Keyboard with only the navigation row (Cancel/Back/Home) for critical steps."""
    return make_reply_keyboard(rows=None, include_nav=True, catalog=catalog)


def make_confirm_keyboard(catalog: dict[str, str] | None = None) -> ReplyKeyboardMarkup:
    """Keyboard with Yes/No for confirmations plus the standard navigation row."""
    return make_reply_keyboard(
        rows=[
            [
                action_button(Messages.BTN_YES, catalog),
                action_button(Messages.BTN_NO, catalog),
            ],
        ],
        catalog=catalog,
    )


def make_server_selector(
    servers: list[str], catalog: dict[str, str] | None = None
) -> ReplyKeyboardMarkup:
    """Create keyboard for server selection with pagination."""
    rows: list[list[KeyboardButton]] = [[KeyboardButton(text=name)] for name in servers]
    nav = NavigationButtons.nav_row(catalog)
    nav.append(KeyboardButton(text=Messages.BTN_NEXT))
    rows.append(nav)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
