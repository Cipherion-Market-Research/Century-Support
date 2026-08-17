"""Deterministic short-circuit for greetings/smalltalk/off-topic requests
(go-live incident 2026-08-17): "write me a poem" fell through to the
facts+RAG+LLM path, which had nothing relevant to say and produced an
"I don't know" answer padded with irrelevant publication citations (see
qa/router.py's unknown-answer handling and Config.RAG_MIN_SCORE for the
other half of that fix). Greetings and requests that are plainly not about
Ciphex at all shouldn't reach facts search or the LLM in the first place --
they get a fixed, deterministic scope reply instead.

Deliberately conservative, same pattern as is_price_question/
is_supply_question: a short message that consists *only* of greeting/
smalltalk tokens, or one of a small set of specific smalltalk phrasings
("write me a poem", "who are you", ...). Must NOT swallow real questions
that happen to contain a greeting-like substring inside a longer word
("history" contains "hi" as a substring but not as a token) or a real
on-topic question that happens to be short.
"""
import re

from century_core.config import Config
from century_core.models import LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta

_TOKEN_RE = re.compile(r"[a-z0-9']+")

_GREETING_TOKENS = {
    "hi",
    "hey",
    "hello",
    "hiya",
    "yo",
    "sup",
    "gm",
    "gn",
    "thanks",
    "thank",
    "thx",
    "ty",
    "cheers",
}
# Filler tokens allowed alongside a greeting token without disqualifying the
# short-message match (e.g. "hi there", "hey!", "thanks a lot").
_FILLER_TOKENS = {"there", "you", "a", "lot", "so", "much"}
_MAX_GREETING_TOKENS = 4

_SMALLTALK_PATTERNS = [
    re.compile(r"\b(write|compose|make|give)\s+me\s+a\s+(poem|song|joke|story|rap|haiku)\b", re.IGNORECASE),
    re.compile(r"\btell\s+me\s+a\s+joke\b", re.IGNORECASE),
    re.compile(r"\bsing\s+(me\s+)?a\s+song\b", re.IGNORECASE),
    re.compile(r"^\s*who\s+are\s+you\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*what\s+are\s+you\??\s*$", re.IGNORECASE),
    re.compile(r"^\s*how\s+are\s+you\??\s*$", re.IGNORECASE),
]


def is_offtopic_question(query: str) -> bool:
    stripped = query.strip()
    if not stripped:
        return False

    for pattern in _SMALLTALK_PATTERNS:
        if pattern.search(stripped):
            return True

    tokens = _TOKEN_RE.findall(stripped.lower())
    if not tokens or len(tokens) > _MAX_GREETING_TOKENS:
        return False
    if not (set(tokens) & _GREETING_TOKENS):
        return False
    # Every token must be a greeting token or an allowed filler -- a short
    # message like "history of ciphex" has few tokens but none of them are
    # greeting tokens (already excluded above); this guards against a short
    # message that mixes a greeting word with a real question, e.g.
    # "hi, which chain is cpx on" (5+ tokens anyway, but stay conservative).
    return set(tokens) <= (_GREETING_TOKENS | _FILLER_TOKENS)


_SCOPE_REPLY = (
    "I'm Century, the Ciphex support assistant — I can help with CPX, the Contribution "
    "Program, claiming, supply and burn figures, and the Ciphex ecosystem. Try /help for commands."
)


def offtopic_response() -> ResponseIR:
    """Fixed scope reply for greetings/smalltalk -- no fact/RAG citations
    (there's nothing being cited; a link list here would be exactly the
    "irrelevant citation" bug this module exists to avoid). `answer_kind`
    is "refusal": there's no better-fitting kind in models.AnswerKind
    (command/faq/rag/llm/refusal) for a deterministic non-answer that isn't
    grounded in any fact/KPI/RAG hit, which is the same reasoning
    response_guard.safe_refusal() uses."""
    return ResponseIR(
        blocks=[
            ParagraphBlock(md=_SCOPE_REPLY),
            LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]),
        ],
        meta=ResponseMeta(answer_kind="refusal", facts_used=[], kpis_used=[]),
    )
