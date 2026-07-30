"""C2 -> MarkdownV2 renderer tests: one per block type, MarkdownV2
escaping edge cases, 4096-char splitting on block boundaries, and a
same-facts-guarantee property test proving the renderer adds no content
beyond formatting and a small fixed connector vocabulary.
"""
import re

import pytest

from telegram_adapter.markdown import (
    MAX_MESSAGE_LEN,
    escape_code,
    escape_link_url,
    escape_text,
    render_block,
    render_blocks,
    render_portable_markdown,
)

# All 18 MarkdownV2 reserved characters named in the WP-6a brief.
RESERVED_CHARS = "_*[]()~`>#+-=|{}.!"


# ─────────────────────────────── Escaping edge cases ───────────────────────────────


@pytest.mark.parametrize("ch", list(RESERVED_CHARS))
def test_each_reserved_char_is_escaped_in_plain_text(ch):
    escaped = escape_text(f"a{ch}b")
    assert escaped == f"a\\{ch}b"


def test_backslash_itself_is_escaped():
    assert escape_text("a\\b") == "a\\\\b"


def test_plain_paragraph_with_every_reserved_char_round_trips_escaped():
    raw = "Use " + RESERVED_CHARS + " carefully."
    rendered = render_portable_markdown(raw)
    for ch in RESERVED_CHARS:
        assert f"\\{ch}" in rendered
    # No unescaped reserved char should slip through.
    unescaped = re.sub(r"\\.", "", rendered)
    for ch in RESERVED_CHARS:
        assert ch not in unescaped


def test_code_span_escapes_only_backtick_and_backslash():
    assert escape_code("a`b\\c") == "a\\`b\\\\c"
    # A reserved char like '.' or '*' inside code is NOT escaped -- Telegram
    # only requires backtick/backslash escaping inside code entities.
    assert escape_code("v1.2.3_x") == "v1.2.3_x"


def test_link_url_escapes_only_close_paren_and_backslash():
    assert escape_link_url("https://x.io/a(b)c\\d") == "https://x.io/a(b\\)c\\\\d"


def test_render_code_span():
    rendered = render_portable_markdown("run `pip.install(x)` now")
    assert rendered == "run `pip\\.install\\(x\\)` now"


def test_render_bold_maps_double_star_to_single_star_telegram_bold():
    rendered = render_portable_markdown("**bold**")
    assert rendered == "*bold*"


def test_render_italic_maps_single_star_to_underscore_telegram_italic():
    rendered = render_portable_markdown("*italic*")
    assert rendered == "_italic_"


def test_render_link():
    rendered = render_portable_markdown("[Ciphex](https://ciphex.io/page(1))")
    assert rendered == "[Ciphex](https://ciphex.io/page\\(1\\))"


def test_render_mixed_portable_markdown():
    rendered = render_portable_markdown("**Note:** see `/help` or [docs](https://ciphex.io).")
    assert rendered == "*Note:* see `/help` or [docs](https://ciphex.io)\\."


# ─────────────────────────────────── Block types ───────────────────────────────────


def test_heading_block_renders_bold_line():
    assert render_block({"type": "heading", "text": "CPX Price"}) == "*CPX Price*"


def test_heading_block_escapes_special_chars():
    assert render_block({"type": "heading", "text": "Q&A: Price!"}) == "*Q&A: Price\\!*"


def test_paragraph_block_uses_portable_markdown_renderer():
    block = {"type": "paragraph", "md": "See **CPX** at [ciphex.io](https://ciphex.io)."}
    assert render_block(block) == render_portable_markdown(block["md"])


def test_fact_block_always_shows_as_of_visibly():
    block = {
        "type": "fact",
        "label": "FY2026 FD supply",
        "value": "1,018,545,702",
        "source": "https://ciphex.io/tokenomics",
        "as_of": "2026-07-20",
    }
    rendered = render_block(block)
    assert "1,018,545,702" in rendered.replace("\\", "")
    assert "2026\\-07\\-20" in rendered or "2026-07-20" in rendered.replace("\\", "")
    assert "As of" in rendered
    assert "ciphex.io/tokenomics" in rendered


def test_links_block_renders_inline_links():
    block = {"type": "links", "items": [{"label": "Ciphex", "url": "https://ciphex.io"}]}
    assert render_block(block) == "[Ciphex](https://ciphex.io)"


def test_links_block_multiple_items_one_per_line():
    block = {
        "type": "links",
        "items": [
            {"label": "Site", "url": "https://ciphex.io"},
            {"label": "Docs", "url": "https://ciphex.io/docs"},
        ],
    }
    rendered = render_block(block)
    assert rendered == "[Site](https://ciphex.io)\n[Docs](https://ciphex.io/docs)"


def test_warning_block_is_prefixed():
    block = {"type": "warning", "md": "Not a live market price."}
    rendered = render_block(block)
    assert rendered.startswith("⚠️ *Warning:* ")
    assert "Not a live market price" in rendered.replace("\\", "")


def test_buttons_block_renders_no_text():
    block = {"type": "buttons", "items": [{"label": "Claim", "url": "https://claim.ciphex.io"}]}
    assert render_block(block) == ""


def test_unknown_block_type_raises():
    with pytest.raises(ValueError):
        render_block({"type": "nope"})


# ───────────────────────────────── render_blocks() ─────────────────────────────────


def test_render_blocks_joins_with_blank_line():
    ir = {
        "blocks": [
            {"type": "heading", "text": "CPX Price"},
            {"type": "paragraph", "md": "Some info."},
        ],
        "meta": {"answer_kind": "command"},
    }
    messages = render_blocks(ir)
    assert len(messages) == 1
    assert messages[0].text == "*CPX Price*\n\nSome info\\."


def test_render_blocks_buttons_attach_to_last_message_only():
    ir = {
        "blocks": [
            {"type": "heading", "text": "Claim"},
            {
                "type": "buttons",
                "items": [{"label": "Open portal", "url": "https://claim.ciphex.io"}],
            },
        ],
        "meta": {"answer_kind": "command"},
    }
    messages = render_blocks(ir)
    assert len(messages) == 1
    assert messages[0].buttons == [("Open portal", "https://claim.ciphex.io")]


def test_render_blocks_splits_at_4096_on_block_boundaries_only():
    # Five blocks, each individually well under the limit, whose combined
    # length forces a split. The split must land between blocks, never
    # inside one.
    block_text = "x" * 1000
    ir = {
        "blocks": [{"type": "paragraph", "md": block_text} for _ in range(5)],
        "meta": {"answer_kind": "faq"},
    }
    messages = render_blocks(ir)

    assert len(messages) > 1
    for msg in messages:
        assert len(msg.text) <= MAX_MESSAGE_LEN

    # Every individual block's rendered text appears wholly intact inside
    # exactly one message part -- never truncated or split across two.
    rendered_block = render_portable_markdown(block_text)
    total_occurrences = sum(msg.text.count(rendered_block) for msg in messages)
    assert total_occurrences == 5

    # Reassembling every part with the same "\n\n" join the renderer uses
    # internally reconstructs the exact original concatenation.
    assert "\n\n".join(msg.text for msg in messages) == "\n\n".join([rendered_block] * 5)


def test_render_blocks_empty_ir_yields_one_empty_message():
    messages = render_blocks({"blocks": [], "meta": {"answer_kind": "refusal"}})
    assert len(messages) == 1
    assert messages[0].text == ""


# ───────────────────────── Same-facts-guarantee property test ─────────────────────────

# Fixed connector vocabulary the renderer is allowed to add beyond the IR's
# own field values (see markdown.py's render_block for where each one is
# introduced). Anything outside this set (plus MarkdownV2 punctuation) that
# shows up in rendered output would mean the renderer invented content.
_CONNECTOR_WORDS = {"source", "as", "of", "warning"}


def _words(text: str) -> set:
    unescaped = re.sub(r"\\(.)", r"\1", text)
    return {w.lower() for w in re.findall(r"[A-Za-z0-9]+", unescaped)}


@pytest.mark.parametrize(
    "block",
    [
        {"type": "heading", "text": "Zebra7 Quokka Heading"},
        {"type": "paragraph", "md": "Narwhal9 says **Falcon3** and `Otter2` plus [Ibex5](https://example.com/ibex5)"},
        {
            "type": "fact",
            "label": "Mongoose4 label",
            "value": "Toucan6value",
            "source": "https://example.com/gecko8",
            "as_of": "2026-01-02",
        },
        {"type": "links", "items": [{"label": "Wombat1", "url": "https://example.com/wombat1"}]},
        {"type": "warning", "md": "Alpaca2 caution message"},
    ],
    ids=["heading", "paragraph", "fact", "links", "warning"],
)
def test_renderer_adds_no_words_beyond_ir_and_connectors(block):
    ir_words = set()
    for key, value in block.items():
        if key == "type":
            continue  # structural metadata, not user-facing content
        if isinstance(value, str):
            ir_words |= _words(value)
        elif isinstance(value, list):
            for item in value:
                for k, v in item.items():
                    if k == "type":
                        continue
                    ir_words |= _words(v)

    rendered_words = _words(render_block(block))
    extra = rendered_words - ir_words - _CONNECTOR_WORDS
    assert extra == set(), f"renderer introduced unexplained content: {extra}"

    # ...and nothing from the IR was dropped either (mod formatting).
    missing = ir_words - rendered_words
    assert missing == set(), f"renderer dropped IR content: {missing}"
