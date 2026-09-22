"""Tests for the hybrid inline overlay: callback contract and styled buttons."""

from __future__ import annotations

import pytest
from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardMarkup

from bot import inline
from bot.formatting import MAX_COPY_TEXT_LENGTH
from bot.keyboards import NavigationButtons, make_confirm_keyboard, make_home_keyboard
from bot.texts import Messages

VALID_CATALOG = {
    "refresh": "5368324170671202286",
    "detail": "5368324170671202287",
    "reveal": "5368324170671202288",
    "copy": "5368324170671202289",
    "docs": "5368324170671202290",
    "page": "5368324170671202291",
    "prev": "5368324170671202292",
    "next": "5368324170671202293",
    "status": "5368324170671202294",
    "ping": "5368324170671202295",
    "help": "5368324170671202296",
    "home": "5368324170671202297",
    "menu_status": "5368324170671202298",
    "menu_cpu": "5368324170671202299",
    "cancel": "5368324170671202300",
}


def buttons(markup: InlineKeyboardMarkup) -> list:
    """Flatten an inline keyboard into a single button list."""
    return [button for row in markup.inline_keyboard for button in row]


def payload(action: inline.OverlayAction, screen: str, **kwargs) -> inline.OverlayCallback:
    """Build a payload with sensible defaults."""
    return inline.OverlayCallback(action=action, screen=screen, **kwargs)


class TestCallbackCodec:
    """Callback payloads must round-trip and stay inside the 64-byte limit."""

    @pytest.mark.parametrize("action", list(inline.OverlayAction))
    @pytest.mark.parametrize("screen", sorted(inline.OVERLAY_SCREENS))
    def test_round_trip(self, action, screen):
        original = payload(action, screen, view=inline.DETAIL_VIEW, reveal=True, page=7)
        decoded = inline.OverlayCallback.parse(original.encode())

        assert decoded == original
        assert len(original.encode().encode()) <= inline.MAX_CALLBACK_BYTES

    @pytest.mark.parametrize(
        "data",
        [
            None,
            "",
            "other:r:status:c:0:1",
            "tsd:r:status:c:0",
            "tsd:zz:status:c:0:1",
            "tsd:r:unknown-screen:c:0:1",
            "tsd:r:status:x:0:1",
            "tsd:r:status:c:2:1",
            "tsd:r:status:c:0:0",
            "tsd:r:status:c:0:1000",
            "tsd:r:status:c:0:abc",
            "tsd:r:status:c:0:1" + "x" * 64,
        ],
    )
    def test_malformed_payloads_are_rejected(self, data):
        assert inline.OverlayCallback.parse(data) is None

    def test_encode_rejects_oversized_screen(self):
        oversized = inline.OverlayCallback(
            action=inline.OverlayAction.REFRESH,
            screen="s" * inline.MAX_CALLBACK_BYTES,
        )
        with pytest.raises(ValueError):
            oversized.encode()

    def test_with_action_keeps_state(self):
        original = payload(inline.OverlayAction.INFO, "status", view=inline.DETAIL_VIEW, page=2)
        swapped = original.with_action(inline.OverlayAction.DETAIL, view=inline.DEFAULT_VIEW)

        assert swapped.action is inline.OverlayAction.DETAIL
        assert swapped.view == inline.DEFAULT_VIEW
        assert swapped.page == 2
        assert original.action is inline.OverlayAction.INFO

    def test_detail_flag_tracks_view(self):
        assert payload(inline.OverlayAction.DETAIL, "status", view=inline.DETAIL_VIEW).detail
        assert not payload(inline.OverlayAction.DETAIL, "status").detail


class TestIconCatalog:
    """Custom emoji ids are optional and must be validated before use."""

    def test_missing_catalog_is_ignored(self):
        assert inline.resolve_icon(None, "refresh") is None
        assert inline.resolve_icon({}, "refresh") is None

    def test_invalid_ids_are_dropped(self):
        assert inline.resolve_icon({"refresh": "emoji"}, "refresh") is None
        assert inline.resolve_icon({"refresh": "5" * 65}, "refresh") is None
        assert inline.resolve_icon({"refresh": "   "}, "refresh") is None

    def test_valid_id_is_used(self):
        assert inline.resolve_icon(VALID_CATALOG, "refresh") == VALID_CATALOG["refresh"]


class TestOverlayBuilder:
    """Buttons must be styled meaningfully and only expose useful actions."""

    def test_refresh_is_primary_and_turns_danger_on_attention(self):
        calm = buttons(inline.build_overlay(payload(inline.OverlayAction.REFRESH, "status")))
        degraded = buttons(
            inline.build_overlay(payload(inline.OverlayAction.REFRESH, "status"), attention=True)
        )

        assert calm[0].text == Messages.INLINE_REFRESH
        assert calm[0].style == ButtonStyle.PRIMARY
        assert degraded[0].style == ButtonStyle.DANGER

    def test_active_toggles_turn_success(self):
        markup = inline.build_overlay(
            payload(
                inline.OverlayAction.DETAIL,
                "network",
                view=inline.DETAIL_VIEW,
                reveal=True,
            )
        )
        labels = {button.text: button.style for button in buttons(markup)}

        assert labels[Messages.INLINE_DETAIL_LESS] == ButtonStyle.SUCCESS
        assert labels[Messages.INLINE_REVEAL_HIDE] == ButtonStyle.SUCCESS

    def test_inactive_toggles_stay_primary(self):
        markup = inline.build_overlay(payload(inline.OverlayAction.REFRESH, "network"))
        labels = {button.text: button.style for button in buttons(markup)}

        assert labels[Messages.INLINE_DETAIL_MORE] == ButtonStyle.PRIMARY
        assert labels[Messages.INLINE_REVEAL_SHOW] == ButtonStyle.PRIMARY

    def test_screens_without_detail_or_reveal_hide_those_buttons(self):
        texts = {
            button.text
            for button in buttons(
                inline.build_overlay(payload(inline.OverlayAction.REFRESH, "ping"))
            )
        }

        assert Messages.INLINE_DETAIL_MORE not in texts
        assert Messages.INLINE_REVEAL_SHOW in texts

    def test_copy_button_is_bounded_and_has_no_callback(self):
        markup = inline.build_overlay(
            payload(inline.OverlayAction.REFRESH, "status"),
            copy_content="x" * (MAX_COPY_TEXT_LENGTH + 100),
        )
        copy_buttons = [button for button in buttons(markup) if button.copy_text is not None]

        assert len(copy_buttons) == 1
        button = copy_buttons[0]
        assert len(button.copy_text.text) == MAX_COPY_TEXT_LENGTH
        assert button.callback_data is None
        assert button.style == ButtonStyle.SUCCESS

    def test_docs_button_uses_url_style(self):
        markup = inline.build_overlay(payload(inline.OverlayAction.REFRESH, "status"))
        docs = [button for button in buttons(markup) if button.url is not None]

        assert len(docs) == 1
        assert docs[0].url == inline.DOCS_URL
        assert docs[0].text == Messages.INLINE_DOCS

    def test_pagination_only_appears_for_multiple_pages(self):
        single = inline.build_overlay(payload(inline.OverlayAction.REFRESH, "status"), pages=1)
        paged = inline.build_overlay(payload(inline.OverlayAction.REFRESH, "status"), pages=3)

        assert inline.Messages.INLINE_PREV not in {b.text for b in buttons(single)}
        paged_texts = {b.text for b in buttons(paged)}
        assert {inline.Messages.INLINE_PREV, inline.Messages.INLINE_NEXT} <= paged_texts
        assert Messages.INLINE_PAGE_INDICATOR.format(page=1, pages=3) in paged_texts

    def test_pagination_wraps_around(self):
        markup = inline.build_overlay(
            payload(inline.OverlayAction.REFRESH, "status", page=3), pages=3
        )
        decoded = {b.text: inline.OverlayCallback.parse(b.callback_data) for b in buttons(markup)}

        assert decoded[inline.Messages.INLINE_NEXT].page == 1
        assert decoded[inline.Messages.INLINE_PREV].page == 2

    def test_quick_actions_offer_dashboards_from_home(self):
        markup = inline.build_overlay(payload(inline.OverlayAction.SHOW, "home"))
        decoded = {b.text: inline.OverlayCallback.parse(b.callback_data) for b in buttons(markup)}

        assert decoded[Messages.INLINE_QUICK_STATUS].screen == "status"
        assert decoded[Messages.INLINE_QUICK_PING].screen == "ping"
        assert decoded[Messages.INLINE_QUICK_HELP].screen == "help"

    def test_reports_offer_a_way_back_to_the_summary(self):
        markup = inline.build_overlay(payload(inline.OverlayAction.REFRESH, "status"))
        decoded = {b.text: inline.OverlayCallback.parse(b.callback_data) for b in buttons(markup)}

        assert decoded[Messages.INLINE_QUICK_HOME].screen == "home"

    def test_icons_are_attached_when_configured(self):
        markup = inline.build_overlay(
            payload(inline.OverlayAction.REFRESH, "status"),
            catalog=VALID_CATALOG,
        )
        icons = {button.text: button.icon_custom_emoji_id for button in buttons(markup)}

        assert icons[Messages.INLINE_REFRESH] == VALID_CATALOG["refresh"]
        assert icons[Messages.INLINE_QUICK_STATUS] == VALID_CATALOG["status"]

    def test_no_icons_without_catalog(self):
        markup = inline.build_overlay(payload(inline.OverlayAction.REFRESH, "status"))
        assert all(button.icon_custom_emoji_id is None for button in buttons(markup))

    def test_help_overlay_offers_all_pages_view(self):
        markup = inline.build_help_overlay(payload(inline.OverlayAction.PAGE, "help", page=1))
        decoded = {b.text: inline.OverlayCallback.parse(b.callback_data) for b in buttons(markup)}

        assert decoded[Messages.INLINE_HELP_ALL].page == inline.MAX_PAGE
        assert decoded[inline.Messages.INLINE_NEXT].page == 2

    def test_help_overlay_marks_combined_view(self):
        markup = inline.build_help_overlay(
            payload(inline.OverlayAction.SHOW, "help", page=inline.MAX_PAGE)
        )
        texts = {button.text for button in buttons(markup)}

        assert Messages.INLINE_PAGE_ALL in texts

    def test_callbacks_are_always_parseable(self):
        screens = sorted(inline.OVERLAY_SCREENS)
        for screen in screens:
            markup = inline.build_overlay(
                payload(inline.OverlayAction.REFRESH, screen, page=2), pages=4
            )
            for button in buttons(markup):
                if button.callback_data is None:
                    continue
                decoded = inline.OverlayCallback.parse(button.callback_data)
                assert decoded is not None, button.callback_data
                assert decoded.screen in inline.OVERLAY_SCREENS


class TestReplyKeyboardStyling:
    """Reply Keyboard keeps its labels but gains Bot API styling."""

    def test_navigation_buttons_are_styled(self):
        assert NavigationButtons.cancel().style == ButtonStyle.DANGER
        assert NavigationButtons.home().style == ButtonStyle.PRIMARY
        assert NavigationButtons.back().style == ButtonStyle.PRIMARY

    def test_confirm_keyboard_styles(self):
        markup = make_confirm_keyboard()
        labels = {button.text: button.style for row in markup.keyboard for button in row}

        assert labels[Messages.BTN_YES] == ButtonStyle.SUCCESS
        assert labels[Messages.BTN_NO] == ButtonStyle.DANGER

    def test_home_keyboard_keeps_navigation_row(self):
        markup = make_home_keyboard()
        last_row = [button.text for button in markup.keyboard[-1]]

        assert last_row == [Messages.BTN_CANCEL, Messages.BTN_BACK, Messages.BTN_HOME]

    def test_keyboard_icons_come_from_the_catalog(self):
        markup = make_home_keyboard(VALID_CATALOG)
        status = next(
            button
            for row in markup.keyboard
            for button in row
            if button.text == Messages.MENU_STATUS
        )

        assert status.icon_custom_emoji_id == VALID_CATALOG["menu_status"]

    def test_unknown_buttons_have_no_style(self):
        from bot.keyboards import action_button

        assert action_button("Plain").style is None
