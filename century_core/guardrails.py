"""Guardrails: pure, deterministic checks over composed response text.

Enforced structurally on every outgoing response (not just via an LLM
system prompt) so this behavior is unit-testable without a live LLM and
can't be talked around by a misbehaving or jailbroken model. Per the WP-5
brief: no purchase solicitation; no APY/yield invention; LLM-composed
numbers must trace back to the supplied context. Owner ruling 2026-08-17:
CPX has no market price to quote -- it is not yet listed on any exchange.
The bot must NEVER output a CPX price figure in any form. Every historical
or staged figure stays banned regardless of phrasing or source, including
the $0.20 figure that was briefly referenced from the contribute page:
$0.25, $0.115, $0.124, and $0.20 are all banned.
"""
import re
from dataclasses import dataclass, field
from typing import Iterable

_SOLICITATION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\byou should (?:buy|purchase|invest)\b",
        r"\bwe recommend (?:buying|purchasing|investing)\b",
        r"\b(?:great|good|perfect|best|ideal) time to (?:buy|invest)\b",
        r"\bdon'?t miss (?:out|this)\b",
        r"\bact now\b",
        r"\bbuy (?:now|today)\b",
        r"\bstrong buy\b",
        r"\bguaranteed (?:returns?|profits?|gains?)\b",
        r"\b(?:excellent|amazing|can'?t[- ]miss) investment\b",
        r"\bnow is the time\b",
    ]
]

_APY_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\b\d+(?:\.\d+)?\s*%\s*(?:apy|apr|annual (?:yield|return|percentage)|per year)\b",
        r"\byield of \d+(?:\.\d+)?\s*%",
    ]
]

# Owner ruling 2026-08-17: CPX is not listed on any exchange -- there is no
# market price to quote. The bot must NEVER output a CPX price figure, full
# stop, regardless of source or phrasing. Word-boundary-safe so "$1.025" or
# "10.250" don't false-positive. Each pattern also excludes a trailing "%"
# (optionally preceded by whitespace): "0.25%" is a percentage (e.g. the fee
# schedule "0.25% to 0.03%" in data/llm_composite.md / data/training/faq.json),
# not a price, and must not be caught here -- a bare number followed by "%"
# can never be a USD price quote in this bot's copy.
_BANNED_PRICE_PATTERNS = [
    re.compile(r"(?<![\d.])\$?0\.25(?!\d)(?!\s*%)"),
    re.compile(r"(?<![\d.])\$?0\.115(?!\d)(?!\s*%)"),
    re.compile(r"(?<![\d.])\$?0\.124(?!\d)(?!\s*%)"),
    re.compile(r"(?<![\d.])\$?0\.20(?!\d)(?!\s*%)"),
]

# Owner ruling 2026-07-30 (reaffirmed 2026-08-17): "presale" is banned
# vocabulary in user-facing output (legal exposure), with NO exemptions --
# not even inside a URL/hostname/path. The program is a Contribution
# Program; the terminology is "contribution(s)". Historic rounds are "the
# 2025 token distribution". A string like "presale.ciphex.io" or
# "/api/presale" must never reach a user, so it is not exempted from this
# ban even when it originates from facts.yaml or RAG context.
_BANNED_TERM_PATTERNS = [
    re.compile(r"(?i)\bpre-?sales?\b"),
]

_NUMBER_RE = re.compile(r"\d[\d,]*\.?\d*")


@dataclass
class GuardrailResult:
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def check_text(text: str) -> GuardrailResult:
    """Structural/policy checks that apply to ANY outgoing text, whether
    template-built or LLM-composed."""
    violations = []
    for pattern in _SOLICITATION_PATTERNS:
        if pattern.search(text):
            violations.append(f"solicitation language matched {pattern.pattern!r}")
    for pattern in _APY_PATTERNS:
        if pattern.search(text):
            violations.append(f"invented APY/yield claim matched {pattern.pattern!r}")
    for pattern in _BANNED_PRICE_PATTERNS:
        if pattern.search(text):
            violations.append(f"banned new-round price figure matched {pattern.pattern!r}")
    for pattern in _BANNED_TERM_PATTERNS:
        if pattern.search(text):
            violations.append(f"banned terminology matched {pattern.pattern!r}")
    return GuardrailResult(violations=violations)


def _normalize_number(raw) -> str:
    s = str(raw).replace(",", "").replace("$", "").rstrip("%").strip()
    try:
        f = float(s)
    except ValueError:
        return ""
    return str(int(f)) if f == int(f) else str(f)


def extract_numbers(text: str) -> set[str]:
    return {_normalize_number(m.group()) for m in _NUMBER_RE.finditer(text)} - {""}


def check_numeric_provenance(text: str, allowed_numbers: Iterable) -> GuardrailResult:
    """Every numeric token in `text` must trace back to a number present in
    `allowed_numbers` (the retrieved fact/KPI/RAG context handed to the
    LLM) -- catches an LLM inventing a plausible-sounding but unsourced
    number. Only meaningful for LLM-composed text; template-built command
    responses are numerically grounded by construction and skip this."""
    allowed = {_normalize_number(n) for n in allowed_numbers} - {""}
    violations = [
        f"unsourced number in response: {token!r}"
        for token in extract_numbers(text)
        if token not in allowed
    ]
    return GuardrailResult(violations=violations)


def enforce(text: str, allowed_numbers: Iterable = ()) -> GuardrailResult:
    """Full guardrail pass: structural checks always; numeric-provenance
    check only when an allowed-numbers context set is supplied."""
    result = check_text(text)
    allowed = list(allowed_numbers)
    if allowed:
        result.violations.extend(check_numeric_provenance(text, allowed).violations)
    return result
