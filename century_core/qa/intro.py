"""Deterministic detection for introductory/"what is Ciphex" questions
(live tester feedback, 2026-08-19): "what is cipex", "what is CPHEX", "Tell
me a little bit about what CipheX is", "I want to understand Ciphex and the
CPX token" all fell through to RAG and produced unapproved paraphrases
citing old PDFs. century_core.commands.ecosystem.handle_ecosystem is
already the approved, deterministic intro answer -- it describes CPX,
Alpha, Atlas, and Connect with official page links (not PDFs) -- so
intro-intent questions route there instead of facts search/RAG.

Deliberately conservative, same pattern as is_price_question/
is_listing_question/is_buy_question: a small set of specific introductory
phrasings ("what is <brand>", "tell me about <brand>", "explain <brand>",
"introduce/introduction to <brand>", "(help me )?understand <brand>"),
each requiring a brand token (Ciphex/CPX or a small, explicit set of common
misspellings -- not a fuzzy-distance algorithm) to appear right where the
phrasing expects it. This must NOT swallow "what is the total supply",
"what is the contract address", or "what is the exchange value" -- none of
"total"/"contract"/"exchange" is a brand token, so the "what is (the/a )?
<brand>" pattern simply doesn't match; those questions also have their own
earlier, more specific routes in qa/router.py (supply questions in
particular are checked well before intro).

Over-capture fix (live tester feedback, 2026-08-26): "what is Ciphex
Alpha?" (should hit products.ciphex_alpha_description via facts search
instead), "what is ciphex's relationship with CertiK/Kevin O'Brien/Steve
Martin" (a possessive, not an intro question), and "tell me about ciphex
connect" (should describe the Connect program specifically, not the whole
ecosystem) were all swallowed by the "what is <brand>" / "tell me about
<brand>" patterns even though the brand token wasn't actually the end of
the noun phrase. Those two patterns now require the brand token to be the
terminal content word of the question -- allowing only a trailing "token"/
"platform"/"is" (the copula in "tell me ... about what CipheX is") or pure
punctuation after it, and NOT a trailing "'s" possessive or another noun
("alpha", "connect", ...) that continues the phrase past the brand. The
"explain"/"introduce"/"understand" patterns are intentionally left as-is --
no tester failure implicates them, and "I want to understand Ciphex and the
CPX token" (an existing passing regression) legitimately continues past the
brand token and must keep matching.
"""
import re

# Small, explicit set of common misspellings alongside the two correct
# forms -- not a fuzzy/edit-distance matcher, per the brief.
_BRANDISH = r"(?:ciphex|cpx|cipex|cphex|ciphx|cyphex)"

# Applied right after the brand token in the "what is <brand>" / "tell me
# about <brand>" patterns: the brand must be the terminal content word of
# the question. A trailing "'s" (possessive) or any other word ("alpha",
# "connect", "relationship", ...) fails to match this suffix, so the whole
# pattern fails to match at that position -- see module docstring.
_TERMINAL_SUFFIX = r"\b(?:\s+(?:token|platform|is))?[?!.,:;]*\s*$"

_INTRO_PATTERNS = [
    re.compile(rf"\bwhat\s+is\s+(?:a\s+|an\s+|the\s+)?{_BRANDISH}{_TERMINAL_SUFFIX}", re.IGNORECASE),
    re.compile(
        rf"\btell\s+me\s+(?:a\s+little\s+(?:bit\s+)?)?about\s+(?:what\s+)?{_BRANDISH}{_TERMINAL_SUFFIX}",
        re.IGNORECASE,
    ),
    re.compile(rf"\bexplain\s+(?:to\s+me\s+)?(?:what\s+)?{_BRANDISH}\b", re.IGNORECASE),
    re.compile(rf"\bintroduc(?:e\s+(?:me\s+to\s+)?|tion\s+to\s+){_BRANDISH}\b", re.IGNORECASE),
    re.compile(rf"\b(?:help\s+me\s+)?understand\s+{_BRANDISH}\b", re.IGNORECASE),
]


def is_intro_question(query: str) -> bool:
    return any(pattern.search(query) for pattern in _INTRO_PATTERNS)
