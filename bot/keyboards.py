"""Reply keyboard builders - Reply Keyboard only (no Inline Keyboard)."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot.texts import Messages


class NavigationButtons:
    """Factory for navigation button row."""

    @staticmethod
    def home() -> KeyboardButton:
        return KeyboardButton(text=Messages.BTN_HOME)

    @staticmethod
    def back() -> KeyboardButton:
        return KeyboardButton(text=Messages.BTN_BACK)

    @staticmethod
    def cancel() -> KeyboardButton:
        return KeyboardButton(text=Messages.BTN_CANCEL)

    @staticmethod
    def nav_row() -> list[KeyboardButton]:
        """Return the standard navigation button row: [Cancel, Back, Home]."""
        return [
            NavigationButtons.cancel(),
            NavigationButtons.back(),
            NavigationButtons.home(),
        ]


def build_nav_row() -> list[KeyboardButton]:
    """Build standard navigation buttons row."""
    return NavigationButtons.nav_row()


def make_reply_keyboard(
    rows: list[list[KeyboardButton]] | None = None,
    include_nav: bool = True,
    resize_keyboard: bool = True,
    one_time_keyboard: bool = False,
) -> ReplyKeyboardMarkup:
    """
    Create a ReplyKeyboardMarkup with optional navigation row.

    Args:
        rows: List of button rows (each row is a list of KeyboardButton).
        include_nav: If True, appends the standard [Cancel, Back, Home] row.
        resize_keyboard: Auto-resize keyboard.
        one_time_keyboard: Hide keyboard after first selection.

    Returns:
        ReplyKeyboardMarkup ready for aiogram.
    """
    keyboard: list[list[KeyboardButton]] = [row[:] for row in rows] if rows else []
    if include_nav:
        keyboard.append(NavigationButtons.nav_row())

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=resize_keyboard,
        one_time_keyboard=one_time_keyboard,
        input_field_placeholder="Ketik atau pilih menu...",
    )


def make_home_keyboard() -> ReplyKeyboardMarkup:
    """Create home screen keyboard with primary navigation."""
    return make_reply_keyboard(
        rows=[
            [KeyboardButton(text=Messages.MENU_STATUS)],
            [KeyboardButton(text=Messages.MENU_MONITOR)],
            [KeyboardButton(text=Messages.MENU_PING)],
            [KeyboardButton(text=Messages.MENU_HELP)],
        ]
    )


def make_monitor_keyboard() -> ReplyKeyboardMarkup:
    """Create monitor submenu keyboard."""
    return make_reply_keyboard(
        rows=[
            [KeyboardButton(text=Messages.MENU_CPU), KeyboardButton(text=Messages.MENU_MEMORY)],
            [KeyboardButton(text=Messages.MENU_NETWORK), KeyboardButton(text=Messages.MENU_DISK)],
            [KeyboardButton(text=Messages.MENU_PROCESSES)],
        ]
    )


def make_cancel_only_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard with only the navigation row (Cancel/Back/Home) for critical steps."""
    return make_reply_keyboard(rows=None, include_nav=True)


def make_confirm_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard with Yes/No for confirmations plus the standard navigation row."""
    return make_reply_keyboard(
        rows=[
            [KeyboardButton(text=Messages.BTN_YES), KeyboardButton(text=Messages.BTN_NO)],
        ]
    )


def make_server_selector(servers: list[str]) -> ReplyKeyboardMarkup:
    """Create keyboard for server selection with pagination."""
    from aiogram.types import KeyboardButton

    rows: list[list[KeyboardButton]] = []
    for name in servers:
        rows.append([KeyboardButton(text=name)])

    nav = NavigationButtons.nav_row()
    nav.append(KeyboardButton(text="Next →"))

    rows.append(nav)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
