"""Guardrails: pure, deterministic checks over composed response text.

Enforced structurally on every outgoing response (not just via an LLM
system prompt) so this behavior is unit-testable without a live LLM and
can't be talked around by a misbehaving or jailbroken model. Per the WP-5
brief: no purchase solicitation; no APY/yield invention; the new round's
price is quoted as neither $0.25 nor $0.115 (round-terms.new_round_price_usd
note — unreconciled staged-vs-on-chain figures, owner directive); LLM-
composed numbers must trace back to the supplied context.
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

# Owner directive (round-terms.new_round_price_usd note, Sprint-1): the new
# round's price is unreconciled between staged copy ($0.25) and an on-chain
# read (~$0.115) -- quote NEITHER, unconditionally, regardless of source or
# phrasing. Word-boundary-safe so "$1.025" or "10.250" don't false-positive.
_BANNED_PRICE_PATTERNS = [
    re.compile(r"(?<![\d.])\$?0\.25(?!\d)"),
    re.compile(r"(?<![\d.])\$?0\.115(?!\d)"),
    # 2026-07-30: the live contribute page now publishes $0.20 while the
    # on-chain read reports ~$0.124 (and the contract price escalates over
    # time) -- still unreconciled, so the standing quote-neither directive
    # extends to both new observations until the owner closes it.
    re.compile(r"(?<![\d.])\$?0\.20(?!\d)"),
    re.compile(r"(?<![\d.])\$?0\.124(?!\d)"),
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
