"""Deterministic non-English input gate (live tester feedback, 2026-08-19):
a Mandarin message got a confused English reply -- the facts+RAG+LLM path
has no way to detect or handle a non-English question, so it should never
be reached at all for one. Checked FIRST in qa/router.py's answer_question,
before even the offtopic short-circuit, since a non-English message isn't
"off-topic" -- it's a language mismatch, and deserves its own reply.

Heuristic, not language detection: strip whitespace/digits/punctuation/
emoji (by only ever looking at alphabetic characters -- `str.isalpha()`
already excludes all of those) and check whether more than half of the
remaining letters belong to a non-Latin script, using `unicodedata.name`'s
"LATIN ..." prefix as the script test (stdlib only, no new deps). This
reliably flags CJK, Cyrillic, Arabic, Hangul, etc. text.

Deliberately out of scope: Latin-script non-English input (Spanish,
French, ...) -- "¿cómo funciona esto?" is composed entirely of Latin
letters (accented or not; `unicodedata.name('ó')` is still
"LATIN SMALL LETTER O WITH ACUTE") and will pass this gate untouched. That
is a known, accepted limitation, not a bug: distinguishing "English" from
"Spanish" both written in Latin script needs real language detection, which
is out of scope for this conservative heuristic.
"""
import unicodedata

from century_core.config import Config
from century_core.models import LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta

_NON_ENGLISH_SCRIPT_RATIO_THRESHOLD = 0.5


def _is_latin_letter(ch: str) -> bool:
    return unicodedata.name(ch, "").startswith("LATIN")


def is_non_english_question(query: str) -> bool:
    """True when more than half of the alphabetic characters in `query`
    are outside the Latin script. A message with no alphabetic characters
    at all (only digits/punctuation/emoji/whitespace) is never flagged --
    there's no script to judge."""
    letters = [ch for ch in query if ch.isalpha()]
    if not letters:
        return False
    non_latin_count = sum(1 for ch in letters if not _is_latin_letter(ch))
    return (non_latin_count / len(letters)) > _NON_ENGLISH_SCRIPT_RATIO_THRESHOLD


_NON_ENGLISH_REPLY = (
    "I currently support English only. Please send your question in English, or use /help "
    "to see available commands."
)


def non_english_response() -> ResponseIR:
    """Fixed, deterministic reply -- no facts/RAG citations, no LLM call
    (there's nothing to ground or translate). `answer_kind` is "refusal",
    same reasoning as offtopic.offtopic_response(): a deterministic
    non-answer that isn't grounded in any fact/KPI/RAG hit."""
    return ResponseIR(
        blocks=[
            ParagraphBlock(md=_NON_ENGLISH_REPLY),
            LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]),
        ],
        meta=ResponseMeta(answer_kind="refusal", facts_used=[], kpis_used=[]),
    )
