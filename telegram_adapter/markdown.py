"""C2 response IR -> Telegram MarkdownV2 renderer.

Pure and network-free: takes plain dicts shaped like the C2 `ResponseIR`
JSON (docs/CONTRACTS.md) and produces MarkdownV2 text plus button
specs. Never imports python-telegram-bot -- keyboard construction from the
`buttons` field this module returns happens one layer up, in bot_sender.py,
so this module (and its tests) never need a live Telegram connection.

Renderer rule (C2, hard rule): renderers translate blocks, they never add,
reorder, or invent content. Every block type below only rearranges/escapes
the IR's own field values plus a small fixed set of connector words
("Source", "As", "of", "Warning") -- see tests/test_markdown_render.py's
same-facts-guarantee property test.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

MAX_MESSAGE_LEN = 4096

# Telegram MarkdownV2 reserved characters that must be backslash-escaped
# wherever they appear as literal text (i.e. outside of the markup we
# construct ourselves). Backslash itself is included since it is the
# escape character -- a literal backslash in source content must be
# escaped first or it would corrupt the next character's escaping.
# https://core.telegram.org/bots/api#markdownv2-style
_RESERVED = set("_*[]()~`>#+-=|{}.!\\")

# Inside `code`/```pre``` entities only backtick and backslash need escaping.
_CODE_RESERVED = set("`\\")

# Inside the (...) part of an inline link, only ')' and '\' need escaping.
_LINK_URL_RESERVED = set(")\\")


def escape_text(s: str) -> str:
    return "".join(("\\" + c if c in _RESERVED else c) for c in s)


def escape_code(s: str) -> str:
    return "".join(("\\" + c if c in _CODE_RESERVED else c) for c in s)


def escape_link_url(s: str) -> str:
    return "".join(("\\" + c if c in _LINK_URL_RESERVED else c) for c in s)


# Portable-markdown subset (docs/CONTRACTS.md C2): **bold**, *italic*,
# `code`, [label](url). No nesting, no tables/images/raw HTML. Order
# matters: `code` and `link` are unambiguous (backtick / `[` prefixed);
# `bold` is tried before `italic` so "**x**" isn't mis-tokenized as italic
# markers around a lone "*". Label/URL require >=1 char (`+`, not `*`) --
# a real link is never empty, and this also keeps incidental "[]()"-shaped
# character runs (e.g. several reserved chars typed adjacently in plain
# text) from being mis-tokenized as a bogus empty link.
_TOKEN_RE = re.compile(
    r"(?P<code>`[^`]*`)"
    r"|(?P<link>\[[^\]]+\]\([^)]+\))"
    r"|(?P<bold>\*\*[^*]+?\*\*)"
    r"|(?P<italic>\*[^*]+?\*)"
)
_LINK_RE = re.compile(r"^\[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)$")

# Known limitation shared with plain CommonMark: a URL containing a literal
# ')' (e.g. a Wikipedia-style disambiguation link) truncates at that first
# ')' rather than the link's real closing delimiter. Century Core's own
# link/button URLs are plain ciphex.io paths and have never needed a
# parenthesized URL; documented here rather than hidden.


def render_portable_markdown(md: str) -> str:
    """Translate the frozen portable-markdown subset into Telegram
    MarkdownV2, escaping literal content but never the markup we emit."""
    out = []
    pos = 0
    for m in _TOKEN_RE.finditer(md):
        if m.start() > pos:
            out.append(escape_text(md[pos : m.start()]))
        if m.group("code") is not None:
            inner = m.group("code")[1:-1]
            out.append("`" + escape_code(inner) + "`")
        elif m.group("link") is not None:
            link_match = _LINK_RE.match(m.group("link"))
            label, url = link_match.group("label"), link_match.group("url")
            out.append("[" + escape_text(label) + "](" + escape_link_url(url) + ")")
        elif m.group("bold") is not None:
            inner = m.group("bold")[2:-2]
            out.append("*" + escape_text(inner) + "*")
        elif m.group("italic") is not None:
            inner = m.group("italic")[1:-1]
            out.append("_" + escape_text(inner) + "_")
        pos = m.end()
    if pos < len(md):
        out.append(escape_text(md[pos:]))
    return "".join(out)


def render_block(block: dict) -> str:
    """Render a single C2 block to MarkdownV2 text. `buttons` blocks
    render to "" here -- they carry no message text, only reply-markup
    (see render_blocks)."""
    block_type = block["type"]

    if block_type == "heading":
        return "*" + escape_text(block["text"]) + "*"

    if block_type == "paragraph":
        return render_portable_markdown(block["md"])

    if block_type == "fact":
        label = escape_text(block["label"])
        value = escape_text(block["value"])
        source = block["source"]
        source_text = escape_text(source)
        source_url = escape_link_url(source)
        as_of = escape_text(block["as_of"])
        # Hard rule (C2): as_of must be rendered visibly wherever a fact
        # appears -- "As of {as_of}" below is not optional decoration.
        return (
            f"*{label}*\n"
            f"{value}\n"
            f"Source: [{source_text}]({source_url})\n"
            f"As of {as_of}"
        )

    if block_type == "links":
        lines = [
            "[" + escape_text(item["label"]) + "](" + escape_link_url(item["url"]) + ")"
            for item in block["items"]
        ]
        return "\n".join(lines)

    if block_type == "warning":
        return "⚠️ *Warning:* " + render_portable_markdown(block["md"])

    if block_type == "buttons":
        return ""

    raise ValueError(f"unknown C2 block type: {block_type!r}")


@dataclass
class RenderedMessage:
    text: str
    buttons: List[Tuple[str, str]] = field(default_factory=list)  # (label, url) pairs


def render_blocks(ir: dict) -> List[RenderedMessage]:
    """Render a full C2 ResponseIR into one or more outgoing Telegram
    messages, splitting at 4096 chars on block boundaries only (a single
    block is never split mid-content), with any `buttons` blocks combined
    into a URL inline keyboard attached to the final message part."""
    chunks: List[str] = []
    buttons: List[Tuple[str, str]] = []

    for blk in ir.get("blocks", []):
        if blk["type"] == "buttons":
            buttons.extend((item["label"], item["url"]) for item in blk["items"])
            continue
        rendered = render_block(blk)
        if rendered:
            chunks.append(rendered)

    parts: List[str] = []
    current = ""
    for chunk in chunks:
        candidate = chunk if not current else current + "\n\n" + chunk
        if len(candidate) > MAX_MESSAGE_LEN and current:
            parts.append(current)
            current = chunk
        else:
            current = candidate
    parts.append(current)  # always at least one part, even if current == ""

    messages = [RenderedMessage(text=p) for p in parts]
    if buttons:
        messages[-1].buttons = buttons
    return messages
