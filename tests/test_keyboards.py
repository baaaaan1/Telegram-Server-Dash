"""Tests for keyboard builders."""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot.keyboards import (
    NavigationButtons,
    build_nav_row,
    make_cancel_only_keyboard,
    make_confirm_keyboard,
    make_home_keyboard,
    make_reply_keyboard,
    make_server_selector,
)
from bot.texts import Messages


class TestNavigationButtons:
    """Tests for navigation button factories."""

    def test_home_button(self):
        """Test home button creation."""
        btn = NavigationButtons.home()
        assert btn.text == Messages.BTN_HOME
        assert isinstance(btn, KeyboardButton)

    def test_back_button(self):
        """Test back button creation."""
        btn = NavigationButtons.back()
        assert btn.text == Messages.BTN_BACK
        assert isinstance(btn, KeyboardButton)

    def test_cancel_button(self):
        """Test cancel button creation."""
        btn = NavigationButtons.cancel()
        assert btn.text == Messages.BTN_CANCEL
        assert isinstance(btn, KeyboardButton)

    def test_nav_row(self):
        """Test navigation row returns three buttons in order."""
        row = NavigationButtons.nav_row()
        assert len(row) == 3
        assert row[0].text == Messages.BTN_CANCEL
        assert row[1].text == Messages.BTN_BACK
        assert row[2].text == Messages.BTN_HOME


class TestBuildNavRow:
    """Tests for build_nav_row function."""

    def test_build_nav_row(self):
        """Test build_nav_row returns list of buttons."""
        row = build_nav_row()
        assert row == NavigationButtons.nav_row()


class TestMakeReplyKeyboard:
    """Tests for make_reply_keyboard function."""

    def test_empty_keyboard_with_nav(self):
        """Test keyboard with only nav row."""
        kb = make_reply_keyboard(rows=None, include_nav=True)
        assert isinstance(kb, ReplyKeyboardMarkup)
        assert len(kb.keyboard) == 1
        assert len(kb.keyboard[0]) == 3

    def test_keyboard_without_nav(self):
        """Test keyboard without navigation row."""
        btn = KeyboardButton(text="OK")
        kb = make_reply_keyboard(rows=[[btn]], include_nav=False)
        assert len(kb.keyboard) == 1
        assert len(kb.keyboard[0]) == 1

    def test_multiple_rows_with_nav(self):
        """Test keyboard with multiple rows plus nav."""
        kb = make_reply_keyboard(
            rows=[[KeyboardButton(text="A"), KeyboardButton(text="B")], [KeyboardButton(text="C")]]
        )
        assert len(kb.keyboard) == 3
        assert len(kb.keyboard[0]) == 2

    def test_resize_keyboard_default(self):
        """Test resize_keyboard defaults to True."""
        kb = make_reply_keyboard()
        assert kb.resize_keyboard is True

    def test_one_time_keyboard_default(self):
        """Test one_time_keyboard defaults to False."""
        kb = make_reply_keyboard()
        assert kb.one_time_keyboard is False


class TestSpecificKeyboards:
    """Tests for pre-built keyboard helpers."""

    def test_make_home_keyboard(self):
        """Test home keyboard has main menu buttons."""
        kb = make_home_keyboard()
        texts = {btn.text for row in kb.keyboard for btn in row}
        assert Messages.MENU_STATUS in texts

    def test_make_cancel_only_keyboard(self):
        """Test cancel-only keyboard has single button with nav row."""
        kb = make_cancel_only_keyboard()
        assert len(kb.keyboard) == 1

    def test_make_confirm_keyboard(self):
        """Test confirm keyboard has Yes/No buttons."""
        kb = make_confirm_keyboard()
        texts = {btn.text for row in kb.keyboard for btn in row}
        assert "Ya" in "".join(texts)

    def test_make_server_selector(self):
        """Test server selector keyboard."""
        kb = make_server_selector(["server1", "server2"])
        all_buttons = [btn.text for row in kb.keyboard for btn in row]
        assert "server1" in all_buttons
        assert "server2" in all_buttons
