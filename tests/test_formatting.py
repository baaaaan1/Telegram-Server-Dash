"""Tests for entity-compliant HTML formatting.

The Bot API only parses a fixed tag set, caps messages at 4096 characters and 100
entities, and treats the payload as markup, so these tests prove that every
dynamic value is escaped and every template stays inside the grammar.
"""

from __future__ import annotations

import pytest

from bot import formatting as fmt
from bot.texts import Messages

ATTACK_STRINGS = [
    "<b>pwned</b>",
    "</blockquote><script>alert(1)</script>",
    "&lt;b&gt;already escaped&lt;/b&gt;",
    'href="x" onmouseover="y"',
    "<tg-emoji emoji-id='1'>x</tg-emoji>",
]


class TestEscaping:
    """Dynamic values must never reach Telegram as markup."""

    @pytest.mark.parametrize("payload", ATTACK_STRINGS)
    def test_decorations_escape_their_input(self, payload):
        rendered = "".join(
            [
                fmt.bold(payload),
                fmt.italic(payload),
                fmt.code(payload),
                fmt.pre(payload),
                fmt.spoiler(payload),
                fmt.blockquote(payload),
                fmt.expandable_blockquote(payload),
                fmt.underline(payload),
                fmt.strike(payload),
            ]
        )

        assert fmt.validate_html(rendered) == []
        assert "<b>pwned</b>" not in rendered
        assert fmt.to_plain_text(fmt.bold(payload)) == payload

    @pytest.mark.parametrize("payload", ATTACK_STRINGS)
    def test_texts_render_helpers_escape_server_data(self, payload):
        rendered = "\n".join(
            [
                Messages.server_line(payload, online=True, group=payload),
                Messages.server_details(payload, payload, payload, payload, payload),
                Messages.report_heading("status", Messages.METHOD_STATUS_LINE),
                Messages.nav_header("status"),
            ]
        )

        assert fmt.validate_html(rendered) == []
        assert "\n<b>" not in rendered

    def test_hidden_value_uses_spoiler_entity(self):
        hidden = Messages.hidden_value("10.0.0.1", reveal=False)
        assert hidden == fmt.spoiler("10.0.0.1")
        assert Messages.hidden_value("10.0.0.1", reveal=True) == "10.0.0.1"


class TestEntityGrammar:
    """The validator itself must reject anything outside the documented grammar."""

    def test_accepts_documented_entities(self):
        text = (
            f"{fmt.bold('b')}{fmt.italic('i')}{fmt.underline('u')}{fmt.strike('s')}"
            f"{fmt.spoiler('hidden')}{fmt.code('code')}{fmt.pre_code('ls -la')}"
            f"{fmt.blockquote('quote')}{fmt.expandable_blockquote('more')}"
            f"{fmt.link('docs', 'https://example.com')}{fmt.user_link('me', 42)}"
            f"{fmt.time_tag('now', 1700000000, 'D MMM YYYY')}"
            f"{fmt.custom_emoji('*', '5368324170671202286')}"
        )
        assert fmt.validate_html(text) == []
        assert fmt.tag_count(text) == 14

    def test_rejects_unknown_tags_and_attributes(self):
        assert "not part of the Bot API formatting grammar" in "".join(
            fmt.validate_html("<script>x</script>")
        )
        assert "attribute 'style'" in "".join(fmt.validate_html('<b style="x">y</b>'))

    def test_rejects_unbalanced_and_atomic_nesting(self):
        assert fmt.validate_html("<b>unclosed")
        assert fmt.validate_html("</i>")
        assert fmt.validate_html("<code><b>nested</b></code>")

    def test_requires_language_class_for_highlight_blocks(self):
        assert "language-* highlight class" in "".join(
            fmt.validate_html('<pre><code class="python">x</code></pre>')
        )
        assert fmt.validate_html(fmt.pre_code("uptime", "bash")) == []

    def test_rejects_length_and_entity_budget_overflows(self):
        assert "exceeds 4096" in "".join(fmt.validate_html("x" * 4097))
        crowded = "".join(fmt.bold("x") for _ in range(fmt.MAX_MESSAGE_ENTITIES + 1))
        assert "entity count" in "".join(fmt.validate_html(crowded))


class TestTemplates:
    """Every shipped template must be sendable as-is."""

    def test_every_message_constant_is_valid(self):
        constants = {
            name: value
            for name, value in vars(Messages).items()
            if not name.startswith("_") and isinstance(value, str)
        }
        assert constants
        for name, value in constants.items():
            assert fmt.validate_html(value) == [], name
            assert fmt.tag_count(value) <= fmt.MAX_MESSAGE_ENTITIES, name

    def test_help_pages_stay_within_budget(self):
        for page in Messages.HELP_PAGES_ID + Messages.HELP_PAGES_EN:
            text = f"{fmt.bold(page.title)}\n<blockquote>{page.body}</blockquote>"
            assert fmt.validate_html(text) == [], page.key

    def test_titles_are_data_not_markup(self):
        titles = "".join(page.title for page in Messages.HELP_PAGES_ID)
        assert "&" in titles
        assert fmt.bold(titles).count("&amp;") == titles.count("&")

    def test_combined_help_is_within_limits(self):
        for text in (Messages.HELP_TEXT_ID, Messages.HELP_TEXT_EN):
            assert fmt.validate_html(text) == []
            assert len(text) <= fmt.MAX_MESSAGE_LENGTH

    def test_welcome_uses_advanced_entities(self):
        assert "<blockquote expandable>" in Messages.WELCOME_ID
        assert "tg-spoiler" in Messages.WELCOME_ID
        assert fmt.validate_html(Messages.WELCOME_ID) == []

    def test_method_descriptions_are_rich(self):
        lines = [
            Messages.METHOD_STATUS_LINE,
            Messages.METHOD_CPU_LINE,
            Messages.METHOD_MEMORY_LINE,
            Messages.METHOD_NETWORK_LINE,
            Messages.METHOD_DISK_LINE,
            Messages.METHOD_PROCESSES_LINE,
        ]
        for line in lines:
            assert "<i>" in line
            assert fmt.validate_html(line) == []


class TestRenderers:
    """Small renderers share one colour vocabulary and stay entity-safe."""

    def test_progress_bar_is_bounded(self):
        assert "0%" in fmt.progress_bar(-5)
        assert "100%" in fmt.progress_bar(250)
        assert fmt.LEVEL_CRITICAL in fmt.progress_bar(95)
        assert fmt.LEVEL_WARN in fmt.progress_bar(75)
        assert fmt.LEVEL_OK in fmt.progress_bar(10)

    def test_progress_bar_width_is_stable(self):
        for percent in (0, 42, 100):
            bar = fmt.progress_bar(percent, width=8)
            assert bar.count(fmt.BAR_FULL) + bar.count(fmt.BAR_EMPTY) == 8

    def test_severity_styles_match_button_palette(self):
        assert fmt.severity(95).style == "danger"
        assert fmt.severity(75).style == "success"
        assert fmt.severity(5).style == "primary"

    def test_metric_and_section_render_entities(self):
        row = fmt.metric("Load", "0.10", icon="📈")
        assert row == "📈 <i>Load</i>: <b>0.10</b>"
        assert "<blockquote>" in fmt.section("CPU", row, icon="🖥️")

    def test_time_and_custom_emoji_tags(self):
        clock = fmt.time_tag("12:00", 1700000000, "HH:mm")
        assert clock.startswith('<tg-time unix="1700000000" format="HH:mm">')
        emoji = fmt.custom_emoji("*", "5368324170671202286")
        assert emoji == '<tg-emoji emoji-id="5368324170671202286">*</tg-emoji>'

    def test_to_plain_text_decodes_entities(self):
        plain = fmt.to_plain_text(fmt.bold("a & b"))
        assert plain == "a & b"

    def test_pre_code_uses_documented_highlight_markup(self):
        assert fmt.pre_code("uptime", "bash") == (
            '<pre><code class="language-bash">uptime</code></pre>'
        )

    def test_pre_code_sanitises_language(self):
        assert 'class="language-b"' in fmt.pre_code("x", "b sh; rm -rf /")
        assert 'class="language-text"' in fmt.pre_code("x", ";;;")
