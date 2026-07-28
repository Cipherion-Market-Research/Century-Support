"""Reconcile a changed hunk against facts.yaml.

Deterministic, regex-based token extraction by category (numbers, emails,
0x addresses, URLs, dates) -- no LLM. A hunk is "mapped" to a fact key
when a token removed from the old side exactly matches that fact's
current published value; it is "unmapped" when none of its changed
tokens correspond to any known fact value (WP-7a brief: "hunks touching
no fact are flagged 'unmapped change'").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from drift_monitor.diff_engine import Hunk
from facts_store.loader import FactsStore

# --- category regexes -------------------------------------------------

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
URL_RE = re.compile(r"https?://[^\s)\"'<>]+")
# ISO date, or "Month D, YYYY" / "D Month YYYY".
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
DATE_RE = re.compile(
    rf"\b\d{{4}}-\d{{2}}-\d{{2}}\b"
    rf"|\b(?:{_MONTHS})\s+\d{{1,2}},?\s+\d{{4}}\b"
    rf"|\b\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}}\b"
)
# Standalone numbers: integers/decimals, optional thousands commas, optional %.
# Deliberately excludes numbers embedded in words/hex (handled by ADDRESS_RE
# separately, matched first so its spans are consumed).
NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?(?![\w])")

CATEGORIES = ("address", "email", "url", "date", "number")


def _normalize_number(token: str) -> str:
    return token.replace(",", "")


def extract_tokens(text: str) -> dict:
    """Return {category: set(normalized tokens)} found in `text`.

    Matching order matters: addresses and emails are pulled out (and their
    spans effectively claimed) before the generic number pattern would
    otherwise partially match digits inside them.
    """
    remaining = text
    found: dict = {cat: set() for cat in CATEGORIES}

    for m in ADDRESS_RE.finditer(remaining):
        found["address"].add(m.group(0).lower())
    remaining = ADDRESS_RE.sub(" ", remaining)

    for m in EMAIL_RE.finditer(remaining):
        found["email"].add(m.group(0).lower())
    remaining = EMAIL_RE.sub(" ", remaining)

    for m in URL_RE.finditer(remaining):
        found["url"].add(m.group(0).rstrip(".,;:)"))
    remaining = URL_RE.sub(" ", remaining)

    for m in DATE_RE.finditer(remaining):
        found["date"].add(m.group(0))
    remaining = DATE_RE.sub(" ", remaining)

    for m in NUMBER_RE.finditer(remaining):
        found["number"].add(_normalize_number(m.group(0)))

    return found


def _flatten_fact_value(value: Any) -> list:
    """Scalar -> [str(value)]; list -> each item flattened; dict -> each
    value flattened. Keeps matching simple: any leaf value the fact
    contains is a candidate for a page-text match."""
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_flatten_fact_value(item))
        return out
    if isinstance(value, dict):
        out = []
        for item in value.values():
            out.extend(_flatten_fact_value(item))
        return out
    return [str(value)]


def _normalize_fact_leaf(leaf: str) -> tuple:
    """Return (category_guess, normalized_value) for a flattened fact leaf,
    so it can be compared against extract_tokens() output category-by-category."""
    if ADDRESS_RE.fullmatch(leaf):
        return "address", leaf.lower()
    if EMAIL_RE.fullmatch(leaf):
        return "email", leaf.lower()
    if URL_RE.fullmatch(leaf):
        return "url", leaf.rstrip(".,;:)")
    if DATE_RE.fullmatch(leaf):
        return "date", leaf
    # Plain numeric leaf (int/float/percent stored as plain text)
    stripped = leaf.replace(",", "")
    if re.fullmatch(r"-?\d+(\.\d+)?%?", stripped):
        return "number", stripped
    return "text", leaf


def build_fact_value_index(store: FactsStore) -> dict:
    """{(category, normalized_value): [fact_key, ...]} across every
    non-unknown fact, for O(1) reverse lookup from a page-text token back
    to the fact(s) it could belong to."""
    index: dict = {}
    for key in store.keys():
        fact = store.get(key)
        if fact is None or fact.is_unknown:
            continue
        for leaf in _flatten_fact_value(fact.value):
            category, normalized = _normalize_fact_leaf(leaf)
            index.setdefault((category, normalized), []).append(key)
    return index


@dataclass
class HunkFinding:
    hunk: Hunk
    mapped_fact_keys: list  # fact keys whose current value appears (and changed) in this hunk
    unmapped: bool
    removed_tokens: dict  # category -> set of tokens present in old_lines but not new_lines
    added_tokens: dict  # category -> set of tokens present in new_lines but not old_lines


def reconcile_hunk(hunk: Hunk, fact_value_index: dict) -> HunkFinding:
    old_tokens = extract_tokens(hunk.old_text)
    new_tokens = extract_tokens(hunk.new_text)

    removed = {cat: old_tokens[cat] - new_tokens[cat] for cat in CATEGORIES}
    added = {cat: new_tokens[cat] - old_tokens[cat] for cat in CATEGORIES}

    mapped_keys: list = []
    for cat in CATEGORIES:
        for token in removed[cat] | added[cat]:
            for key in fact_value_index.get((cat, token), []):
                if key not in mapped_keys:
                    mapped_keys.append(key)

    return HunkFinding(
        hunk=hunk,
        mapped_fact_keys=mapped_keys,
        unmapped=len(mapped_keys) == 0,
        removed_tokens=removed,
        added_tokens=added,
    )


def reconcile_hunks(hunks: list, store: FactsStore) -> list:
    index = build_fact_value_index(store)
    return [reconcile_hunk(h, index) for h in hunks]


def propose_new_value(finding: HunkFinding, fact_key: str, store: FactsStore) -> Optional[str]:
    """Best-effort proposed replacement value for a mapped fact: the
    single added token in the same category as the fact's current
    (removed) value, if there is exactly one candidate. Returns None when
    ambiguous -- callers must render that as "manual review", never guess."""
    fact = store.get(fact_key)
    if fact is None:
        return None
    for leaf in _flatten_fact_value(fact.value):
        category, normalized = _normalize_fact_leaf(leaf)
        if normalized in finding.removed_tokens.get(category, set()):
            candidates = finding.added_tokens.get(category, set())
            if len(candidates) == 1:
                return next(iter(candidates))
            return None
    return None
