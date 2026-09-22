"""Entity-safe HTML formatting helpers for Telegram messages.

Telegram only accepts the tags listed in the Bot API formatting grammar, so every
dynamic value is escaped *before* it is wrapped in a decoration tag. The helpers
build on :mod:`aiogram.utils.text_decorations`, which keeps the emitted markup in
sync with what the library parses, and :func:`validate_html` can prove that a
rendered message stays inside the documented entity contract.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from aiogram.utils.text_decorations import html_decoration as _html

MAX_MESSAGE_LENGTH: Final = 4096
MAX_MESSAGE_ENTITIES: Final = 100
MAX_COPY_TEXT_LENGTH: Final = 256
MAX_CUSTOM_EMOJI_ID_LENGTH: Final = 64

TAG_PATTERN: Final = re.compile(r"</?([a-z-]+)((?:\s+[^<>]*?)?)\s*/?>", re.IGNORECASE)
ATTR_PATTERN: Final = re.compile(r'([a-z-]+)\s*=\s*"([^"]*)"', re.IGNORECASE)

ALLOWED_TAGS: Final = frozenset(
    {
        "b",
        "strong",
        "i",
        "em",
        "u",
        "ins",
        "s",
        "strike",
        "del",
        "tg-spoiler",
        "a",
        "tg-emoji",
        "tg-time",
        "code",
        "pre",
        "blockquote",
    }
)
ATOMIC_TAGS: Final = frozenset({"code", "pre", "tg-emoji", "tg-time"})
ALLOWED_ATTRS: Final = {
    "a": frozenset({"href"}),
    "code": frozenset({"class"}),
    "tg-emoji": frozenset({"emoji-id"}),
    "tg-time": frozenset({"unix", "format"}),
}
HIGHLIGHT_CLASS_PATTERN: Final = re.compile(r"language-[A-Za-z0-9+#_-]+")
PRE_HIGHLIGHT_CHILD: Final = "code"
BARE_AMPERSAND_PATTERN: Final = re.compile(
    r"&(?!(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);)"
)

BAR_FULL: Final = "▰"
BAR_EMPTY: Final = "▱"
DIVIDER: Final = "━━━━━━━━━━━━━━"

LEVEL_OK: Final = "🟢"
LEVEL_WARN: Final = "🟧"
LEVEL_CRITICAL: Final = "🟥"


def esc(value: object) -> str:
    """Escape a dynamic value so it cannot inject or break message entities.

    :class:`Entity` values are already escaped and pass through unchanged, which
    lets assembled blocks be wrapped by a block entity without double escaping.
    """
    if isinstance(value, Entity):
        return str(value)
    return html.escape(str(value), quote=True)


class Entity(str):
    """HTML already escaped by this module.

    Only use it for markup produced by these helpers (or values escaped with
    :func:`esc`): the decorating helpers trust it verbatim.
    """


def entity(*parts: object) -> Entity:
    """Join trusted, pre-escaped fragments into one block of markup."""
    return Entity("\n".join(str(part) for part in parts))


_quote = esc


def bold(value: object) -> str:
    """Bold entity (``<b>``)."""
    return _html.bold(_quote(value))


def italic(value: object) -> str:
    """Italic entity (``<i>``)."""
    return _html.italic(_quote(value))


def underline(value: object) -> str:
    """Underline entity (``<u>``)."""
    return _html.underline(_quote(value))


def strike(value: object) -> str:
    """Strikethrough entity (``<s>``)."""
    return _html.strikethrough(_quote(value))


def spoiler(value: object) -> str:
    """Spoiler entity (``<span class="tg-spoiler">``)."""
    return _html.spoiler(_quote(value))


def code(value: object) -> str:
    """Monospace entity (``<code>``)."""
    return _html.code(_quote(value))


def pre(value: object) -> str:
    """Preformatted block (``<pre>``)."""
    return _html.pre(_quote(value))


def pre_code(value: object, language: str = "bash") -> str:
    """Syntax-highlighted block.

    Telegram documents the highlight form as ``<pre><code class="language-*">``,
    so the markup is emitted directly instead of relying on the library helper.
    The language token is reduced to its first safe word.
    """
    words = re.sub(r"[^A-Za-z0-9+#_-]", " ", str(language)).split()
    safe_language = words[0] if words else "text"
    return f'<pre><code class="language-{safe_language}">{_quote(value)}</code></pre>'


def blockquote(value: object) -> str:
    """Blockquote entity."""
    return _html.blockquote(_quote(value))


def expandable_blockquote(value: object) -> str:
    """Expandable blockquote entity (taps open the collapsed body)."""
    return _html.expandable_blockquote(_quote(value))


def link(value: object, url: str) -> str:
    """Inline text link; the label is escaped, the URL is attribute-quoted."""
    return _html.link(_quote(value), link=_quote(url))


def user_link(value: object, user_id: int) -> str:
    """Mention a user by ID without needing a public username."""
    return _html.link(_quote(value), link=f"tg://user?id={int(user_id)}")


def time_tag(value: object, unix_time: int | datetime, date_time_format: str | None = None) -> str:
    """Date/time entity rendered in the reader's own locale and timezone."""
    return _html.date_time(_quote(value), unix_time=unix_time, date_time_format=date_time_format)


def custom_emoji(value: object, emoji_id: str) -> str:
    """Custom (premium) emoji entity; only usable when the bot owns the emoji."""
    return _html.custom_emoji(_quote(value), custom_emoji_id=_quote(emoji_id).strip('"'))


def iso_moment(moment: datetime) -> int:
    """Unix timestamp for date/time entities, defaulting to UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp())


def now_tag(date_time_format: str = "HH:mm:ss") -> str:
    """Live clock entity for dashboard headers."""
    moment = datetime.now(UTC)
    return time_tag(f"{moment:%H:%M:%S} UTC", moment, date_time_format)


@dataclass(frozen=True, slots=True)
class Severity:
    """Visual severity of a percentage metric."""

    level: str
    label: str
    style: str


def severity(percent: float) -> Severity:
    """Classify a 0-100 percentage into a shared colour vocabulary."""
    if percent >= 90:
        return Severity(LEVEL_CRITICAL, "kritis", "danger")
    if percent >= 70:
        return Severity(LEVEL_WARN, "tinggi", "success")
    return Severity(LEVEL_OK, "normal", "primary")


def progress_bar(percent: float, width: int = 10) -> str:
    """Coloured progress bar using the level emoji plus block characters."""
    bounded = max(0.0, min(100.0, float(percent)))
    filled = int(round(width * bounded / 100))
    bar = f"{BAR_FULL * filled}{BAR_EMPTY * (width - filled)}"
    return f"{severity(bounded).level} {bar} {bold(f'{bounded:.0f}%')}"


def metric(label: str, value: object, *, unit: str = "", icon: str = "") -> str:
    """One ``label: value`` row with a single bold entity for the value."""
    head = f"{icon} " if icon else ""
    tail = f" {unit}" if unit else ""
    return f"{head}{italic(label)}: {bold(value)}{tail}"


def metric_lines(pairs: Iterable[tuple[str, object]]) -> str:
    """Multi-line metric list; one entity per row keeps the entity budget low."""
    return "\n".join(metric(label, value) for label, value in pairs)


def section(title: str, body: str, *, icon: str = "") -> str:
    """Section heading plus body, both inside a single blockquote entity."""
    head = f"{icon} {bold(title)}" if icon else bold(title)
    return f"{head}\n{blockquote(body)}"


def divider() -> str:
    """Thin separator line for dense dashboards."""
    return DIVIDER


def tag_count(text: str) -> int:
    """Number of opening tags, i.e. the entity count Telegram will decode."""
    return sum(1 for match in TAG_PATTERN.finditer(text) if not match.group(0).startswith("</"))


def iter_tags(text: str) -> Iterator[tuple[str, str, bool]]:
    """Yield ``(name, attributes, is_closing)`` for every HTML tag in ``text``."""
    for match in TAG_PATTERN.finditer(text):
        raw = match.group(0)
        yield match.group(1).lower(), match.group(2) or "", raw.startswith("</")


def validate_html(text: str) -> list[str]:
    """Return the entity-contract violations found in ``text`` (empty when valid)."""
    problems: list[str] = []
    stack: list[str] = []
    for name, attrs, is_closing in iter_tags(text):
        if name not in ALLOWED_TAGS:
            problems.append(f"tag <{name}> is not part of the Bot API formatting grammar")
            continue
        if is_closing:
            if not stack or stack.pop() != name:
                problems.append(f"closing tag </{name}> without a matching opening tag")
            continue
        if (
            stack
            and stack[-1] in ATOMIC_TAGS
            and (name, stack[-1])
            != (
                PRE_HIGHLIGHT_CHILD,
                "pre",
            )
        ):
            problems.append(f"<{name}> cannot be nested inside <{stack[-1]}>")
        stack.append(name)
        for attr, value in ATTR_PATTERN.findall(attrs):
            allowed = ALLOWED_ATTRS.get(name, frozenset())
            if attr.lower() not in allowed:
                problems.append(f"attribute {attr!r} is not valid on <{name}>")
            elif name == "code" and not HIGHLIGHT_CLASS_PATTERN.fullmatch(value):
                problems.append(f"<code class={value!r}> must be a language-* highlight class")
    if stack:
        problems.append(f"unclosed tag <{stack[-1]}>")
    if BARE_AMPERSAND_PATTERN.search(text):
        problems.append("bare '&' must be escaped as &amp;")
    if len(text) > MAX_MESSAGE_LENGTH:
        problems.append(f"text length {len(text)} exceeds {MAX_MESSAGE_LENGTH}")
    if tag_count(text) > MAX_MESSAGE_ENTITIES:
        problems.append(f"entity count {tag_count(text)} exceeds {MAX_MESSAGE_ENTITIES}")
    return problems


def is_valid_html(text: str) -> bool:
    """Whether ``text`` satisfies the entity contract."""
    return not validate_html(text)


def to_plain_text(text: str) -> str:
    """Strip entity tags and decode entities for clipboard/copy payloads."""
    return html.unescape(re.sub(r"<[^<>]*>", "", text))
