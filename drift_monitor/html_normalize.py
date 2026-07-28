"""Deterministic chrome-free body-text extraction from a repo source HTML
file (src/*.html), for diffing against the sha256 baseline manifest.

No LLM, no live network -- pure string/DOM processing so it is exactly
reproducible given the same bytes, which is what makes the sha256
baseline meaningful (WP-7a brief: diff REPO SOURCES, chrome-free).
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Tags that are never part of the page's factual body copy: navigation
# chrome, scripts/styles, and structural wrappers common to this site's
# templates.
_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "noscript", "svg")
_STRIP_SELECTORS = (
    "[data-nav]",
    ".nav",
    ".navbar",
    ".footer",
    ".site-footer",
    ".site-header",
)

_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")


def _collapse_lines(raw_text: str) -> str:
    """Whitespace-collapse each line and drop blank lines entirely (not
    just collapse them) -- paragraph spacing carries no factual content,
    and dropping it makes the line-level diff robust to pure
    whitespace/formatting churn that would otherwise flag as noise."""
    lines = []
    for line in raw_text.splitlines():
        collapsed = _WHITESPACE_RE.sub(" ", line).strip()
        if collapsed:
            lines.append(collapsed)
    return "\n".join(lines)


def extract_body_text(html: str) -> str:
    """Strip chrome (nav/header/footer/script/style) and return normalized,
    whitespace-collapsed body text, one block of copy per line.

    Deterministic: same input bytes always produce the same output string,
    which is required for the sha256 baseline comparison to be meaningful.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in _STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for selector in _STRIP_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    body = soup.body or soup
    # get_text with a newline separator keeps block-level structure so the
    # line-based diff engine downstream produces sensible hunks instead of
    # one giant single-line change.
    raw_text = body.get_text(separator="\n")
    return _collapse_lines(raw_text)


def normalize_plain_text(text: str) -> str:
    """Apply the same whitespace normalization to already-plain text (used
    for the data/kb_source/*.md seed baseline, which is not raw HTML)."""
    return _collapse_lines(text)
