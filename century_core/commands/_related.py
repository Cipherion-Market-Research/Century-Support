"""Shared "Related:" footer builder appended to each command's response
(live tester feedback 2026-08-19, UX item 4). Keeps the near-identical
footer line construction DRY across the individual command handlers
instead of duplicating the join logic nine times. Not itself a command
handler -- imported by the handlers that need a footer.

No footer on /help or /start (there's nothing more targeted to point to
than the full command list they already show). /updates belongs to
another work package and is not touched here.
"""
from century_core.models import ParagraphBlock


def related_footer(*commands: tuple[str, str]) -> ParagraphBlock:
    """Build the "Related: /x — desc · /y — desc" footer paragraph from
    (command_name, description) pairs, rendered in the given order."""
    joined = " · ".join(f"/{name} — {desc}" for name, desc in commands)
    return ParagraphBlock(md=f"Related: {joined}")
