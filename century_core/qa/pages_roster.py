"""Team-member roster: deterministic person-question routing over the
harvested leadership-team page (Sprint 3, owner-flagged regression: direct
name queries like "Who is Kevin?" were falling through to the graceful
refusal even though the answer sits verbatim on ciphex.io/leadership-team).

The leadership page's markup (see scripts/harvest_pages.py's extraction)
renders each team member as a tight, regular 6-paragraph run once
harvested to markdown:

    <Full Name>
    <tier chip, e.g. "Ecosystem" or "Contributor">
    <role>
    <credential line, starts with a number>
    <credential line>
    <credential line>

This module parses that structure directly out of
data/kb_source/pages/leadership-team.md (no DB/embeddings needed -- this
route is fully deterministic and works even with rag_conn=None) rather
than going through pubs_rag's retrieve_pages(), per the Sprint 3 brief
("retrieve that person's section from the page corpus, or direct from the
markdown if simpler").

Parsing happens once, lazily, on first call (get_roster() below), then
stays cached for the process lifetime -- "AT STARTUP" per the brief, in
the sense that the first Q&A request pays the parse cost and every
request after that is free, without needing an explicit app-boot hook.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from century_core.models import LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta

_LEADERSHIP_SLUG = "leadership-team"
_LEADERSHIP_URL = "https://ciphex.io/leadership-team"
_LEADERSHIP_MD_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "kb_source" / "pages" / f"{_LEADERSHIP_SLUG}.md"
)

_FRONTMATTER_RE = re.compile(r"\A<!--.*?-->\s*", re.DOTALL)
_CREDENTIAL_RE = re.compile(r"^\d+\+?\s*(?:yrs?\.?|years?)\b", re.IGNORECASE)
# A name paragraph: 2-5 whitespace-separated tokens, each starting with a
# letter (no digits/punctuation-only tokens) -- permissive about casing
# within a token (allows "du Preez"-style lowercase particles) since this
# is a structural-position guard, not the primary matcher.
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z.'’\-]*(?:\s+[A-Za-z][A-Za-z.'’\-]*){1,4}$")
# The page's own "N+ years of combined ... expertise" sentence, extracted
# rather than hardcoded so a future re-harvest with an updated figure is
# picked up automatically.
_YEARS_SUMMARY_RE = re.compile(r"\b\d+\+?\s+years?\s+of\s+combined\b.*", re.IGNORECASE)

_INTENT_WORDS = ("who", "about", "tell", "background", "experience", "bio", "relationship", "relation", "involvement", "role")
_TEAM_PHRASES = ("leadership team", "the team", "ciphex team", "the leadership")


def _normalize_apostrophes(text: str) -> str:
    return text.replace("’", "'").replace("‘", "'")


@dataclass(frozen=True)
class Person:
    full_name: str
    first_name: str
    tier: str  # the page's "chip" label, e.g. "Ecosystem" / "Contributor"
    role: str
    credentials: tuple[str, ...]


@dataclass(frozen=True)
class Roster:
    people: tuple[Person, ...]
    years_summary: str  # e.g. "100+ years of combined professional expertise." or "" if not found


_EMPTY_ROSTER = Roster(people=(), years_summary="")


def _split_paragraphs(markdown_text: str) -> list[str]:
    body = _FRONTMATTER_RE.sub("", markdown_text, count=1)
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def parse_leadership_markdown(markdown_text: str) -> Roster:
    """Pure function, no I/O -- parses the harvested leadership page's
    markdown body into a Roster. See module docstring for the structural
    pattern this looks for."""
    paragraphs = _split_paragraphs(markdown_text)

    years_summary = ""
    for p in paragraphs:
        m = _YEARS_SUMMARY_RE.search(p)
        if m:
            years_summary = m.group(0)
            break

    people: list[Person] = []
    seen_full_names: set[str] = set()
    i = 0
    n = len(paragraphs)
    while i < n:
        if not _CREDENTIAL_RE.match(paragraphs[i]):
            i += 1
            continue
        # Found the start of a credential run -- walk it forward.
        run_start = i
        run_end = i
        while run_end < n and _CREDENTIAL_RE.match(paragraphs[run_end]):
            run_end += 1
        credentials = tuple(paragraphs[run_start:run_end])

        if run_start >= 3:
            name_candidate = paragraphs[run_start - 3]
            tier_candidate = paragraphs[run_start - 2]
            role_candidate = paragraphs[run_start - 1]
            if _NAME_RE.match(name_candidate) and not _CREDENTIAL_RE.match(name_candidate):
                full_name = name_candidate
                if full_name not in seen_full_names:
                    seen_full_names.add(full_name)
                    first_name = full_name.split()[0]
                    people.append(
                        Person(
                            full_name=full_name,
                            first_name=first_name,
                            tier=tier_candidate,
                            role=role_candidate,
                            credentials=credentials,
                        )
                    )
        i = run_end

    return Roster(people=tuple(people), years_summary=years_summary)


@lru_cache(maxsize=1)
def get_roster() -> Roster:
    """Lazy-cached: parses data/kb_source/pages/leadership-team.md on first
    call, then reuses the result for the process lifetime. Never raises --
    a missing/unreadable/unparseable file yields an empty Roster, and
    is_person_question() below always returns False against an empty
    roster (nothing grounded to answer with)."""
    try:
        text = _LEADERSHIP_MD_PATH.read_text(encoding="utf-8")
    except OSError:
        return _EMPTY_ROSTER
    try:
        return parse_leadership_markdown(text)
    except Exception:
        return _EMPTY_ROSTER


_NAME_TOKEN_RE = re.compile(r"[a-z']+")


def _match_people(query_lower: str, roster: Roster) -> list[Person]:
    """Full-name substring match wins outright (unambiguous by
    construction -- two different people never share a full name on this
    page). Otherwise, a first-name TOKEN match (not substring, so "art" in
    "smart" can never match "Art") against every person sharing that first
    name -- may return more than one (e.g. multiple "Michael"s)."""
    normalized_query = _normalize_apostrophes(query_lower)
    for person in roster.people:
        if _normalize_apostrophes(person.full_name.lower()) in normalized_query:
            return [person]

    tokens = set(_NAME_TOKEN_RE.findall(normalized_query))
    matches = [p for p in roster.people if p.first_name.lower() in tokens]
    return matches


def is_person_question(query: str, roster: Optional[Roster] = None) -> bool:
    roster = roster if roster is not None else get_roster()
    if not roster.people:
        return False

    q = query.lower()
    if not any(word in q for word in _INTENT_WORDS):
        return False

    if any(phrase in q for phrase in _TEAM_PHRASES):
        return True

    return bool(_match_people(q, roster))


def _person_snippet(person: Person) -> str:
    creds = "; ".join(person.credentials)
    return f"{person.full_name} — {person.role} ({person.tier} team). {creds}."


def _team_overview_snippet(roster: Roster) -> str:
    summary = (
        roster.years_summary
        or "decades of combined experience across capital markets, technology, and "
        "digital-asset infrastructure"
    )
    names = ", ".join(p.full_name for p in roster.people)
    return f"The Ciphex leadership team brings {summary} Team members include: {names}."


def answer_person_question(query: str, roster: Optional[Roster] = None) -> ResponseIR:
    """Deterministic answer for a query is_person_question() has already
    matched. Always grounded in the parsed roster -- never calls the LLM.
    Returns a ResponseIR with answer_kind "faq" (same convention as
    qa/holders.py's deterministic answer)."""
    roster = roster if roster is not None else get_roster()
    q = query.lower()

    matches = [] if any(phrase in q for phrase in _TEAM_PHRASES) else _match_people(q, roster)

    if len(matches) == 1:
        text = _person_snippet(matches[0])
    elif len(matches) > 1:
        # Ambiguous first name (e.g. "who is Michael?" -- several
        # Michaels on the team): list all matches rather than guessing.
        lines = "; ".join(_person_snippet(p) for p in matches)
        text = f"There's more than one match on the Ciphex leadership team: {lines}"
    else:
        text = _team_overview_snippet(roster)

    blocks = [
        ParagraphBlock(md=text),
        LinksBlock(items=[LinkItem(label="Ciphex Leadership Team", url=_LEADERSHIP_URL)]),
    ]
    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="faq", facts_used=[], kpis_used=[]),
    )
