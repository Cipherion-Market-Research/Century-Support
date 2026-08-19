"""/help and /start -- grouped help layout, natural-language teasers, and
the order/no-footer guarantees from the 2026-08-19 live tester UX pass."""
from century_core import guardrails, response_guard
from century_core.commands.misc import handle_help, handle_start
from century_core.commands.registry import HANDLERS


def _all_text(response):
    parts = []
    for block in response.blocks:
        if block.type == "heading":
            parts.append(block.text)
        elif block.type in ("paragraph", "warning"):
            parts.append(block.md)
        elif block.type == "fact":
            parts.append(f"{block.label} {block.value}")
        elif block.type in ("links", "buttons"):
            parts.extend(item.url for item in block.items)
            parts.extend(item.label for item in block.items)
    return "\n".join(parts)


# ─────────────────────────────── /help ───────────────────────────────


async def test_help_registration_order_matches_registry(stub_stores):
    # Telegram renders /help and the command menu in registration order --
    # pin /help's own command sequence to century_core.commands.registry's
    # HANDLERS order so the two can't silently drift apart.
    response = await handle_help("", stub_stores)
    text = _all_text(response)
    positions = {name: text.find(f"/{name}") for name in HANDLERS}
    assert all(pos != -1 for pos in positions.values()), positions
    ordered_names = sorted(positions, key=positions.get)
    assert ordered_names == list(HANDLERS.keys())


async def test_help_has_grouped_headings_in_order(stub_stores):
    response = await handle_help("", stub_stores)
    # Search the help paragraph body only -- the response's own HeadingBlock
    # ("Century — Ciphex Support") would otherwise false-match "Support".
    text = "\n".join(b.md for b in response.blocks if b.type == "paragraph")
    headings = ["Token & Market", "Claiming & Participation", "Project Info", "Support"]
    positions = [text.find(h) for h in headings]
    assert all(p != -1 for p in positions), (headings, positions)
    assert positions == sorted(positions)


async def test_help_groups_contain_the_right_commands():
    from century_core.commands import misc

    text = misc._HELP_TEXT
    groups = {
        "Token & Market": ["/price", "/ca", "/supply", "/stats"],
        "Claiming & Participation": ["/claim", "/contribute"],
        "Project Info": ["/ecosystem", "/audit", "/updates"],
        "Support": ["/contact", "/help", "/start"],
    }
    bounds = sorted((text.index(f"**{heading}:**"), heading) for heading in groups)
    for i, (start, heading) in enumerate(bounds):
        end = bounds[i + 1][0] if i + 1 < len(bounds) else len(text)
        section = text[start:end]
        for command in groups[heading]:
            assert f"`{command}`" in section, (heading, command, section)


async def test_help_includes_natural_language_teaser(stub_stores):
    response = await handle_help("", stub_stores)
    text = _all_text(response)
    assert "You can also just ask a question" in text
    assert '"How do I claim my tokens?"' in text
    assert '"What is CPX?"' in text
    assert '"When will CPX be listed?"' in text


async def test_help_has_no_related_footer(stub_stores):
    response = await handle_help("", stub_stores)
    assert not any(
        b.type == "paragraph" and b.md.startswith("Related:") for b in response.blocks
    )


async def test_help_survives_response_guard(stub_stores):
    response = await handle_help("", stub_stores)
    result = guardrails.check_text(_all_text(response))
    assert result.ok, result.violations
    guarded = response_guard.enforce_response(response)
    assert guarded.meta.answer_kind != "refusal"


# ─────────────────────────────── /start ───────────────────────────────


async def test_start_keeps_welcome_and_scam_warning(stub_stores):
    response = await handle_start("", stub_stores)
    text = _all_text(response)
    assert "I'm Century" in text
    assert "never DM you first" in text
    assert "seed phrase" in text


async def test_start_includes_teaser_line(stub_stores):
    response = await handle_start("", stub_stores)
    text = _all_text(response)
    assert "What can I help with?" in text
    assert '"How do I claim my tokens?"' in text
    assert '"What is CPX?"' in text
    assert "/help" in text


async def test_start_teaser_comes_after_scam_warning(stub_stores):
    response = await handle_start("", stub_stores)
    text = _all_text(response)
    assert text.index("seed phrase") < text.index("What can I help with?")


async def test_start_has_no_related_footer(stub_stores):
    response = await handle_start("", stub_stores)
    assert not any(
        b.type == "paragraph" and b.md.startswith("Related:") for b in response.blocks
    )


async def test_start_survives_response_guard(stub_stores):
    response = await handle_start("", stub_stores)
    result = guardrails.check_text(_all_text(response))
    assert result.ok, result.violations
    guarded = response_guard.enforce_response(response)
    assert guarded.meta.answer_kind != "refusal"
