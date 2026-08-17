"""Deterministic handling for token-holder-count questions (go-live
incident 2026-08-17): a user asked "what is the actual token holder number
for ciphex?" and the generic facts+RAG+LLM path had no relevant fact or
publication, so it dead-ended into a padded "I don't know" answer. The
holder count IS publicly visible -- on Etherscan's token page -- but
there's no live feed for it (Etherscan's tokenholdercount endpoint is a
paid-tier API; per owner instruction, no poller is being added for this).
So this is a fixed, deterministic pointer to Etherscan, the same pattern
as qa/price.py's deterministic /price short-circuit.

Deliberately conservative (require "holder"/"holders" literally in the
text), same word-boundary-token pattern as is_price_question/
is_supply_question, so it doesn't swallow supply questions -- "how many
tokens are there" is a supply question (qa/supply.py, checked first in
qa/router.py), not a holder-count question.
"""
import re

from century_core.models import LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta

_HOLDER_TRIGGERS = {"holder", "holders"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")

_FALLBACK_EXPLORER_URL = "https://etherscan.io/token/0x18b33687d1c804Dd4ea6c82106e54923c23a652E"


def is_holder_question(query: str) -> bool:
    tokens = set(_TOKEN_RE.findall(query.lower()))
    return bool(tokens & _HOLDER_TRIGGERS)


async def answer_holder_question(stores) -> ResponseIR:
    facts_used = []
    explorer_url = _FALLBACK_EXPLORER_URL

    fact = stores.facts.get("contracts.cpx_token_ethereum")
    if fact is not None and not fact.is_unknown and isinstance(fact.value, dict):
        candidate = fact.value.get("explorer_url")
        if candidate:
            explorer_url = candidate
            facts_used.append("contracts.cpx_token_ethereum")

    blocks = [
        ParagraphBlock(
            md="Ciphex doesn't publish a live holder count here yet. The current CPX holder "
            "count is publicly visible on Etherscan:"
        ),
        LinksBlock(items=[LinkItem(label="CPX Holders (Etherscan)", url=explorer_url)]),
    ]

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="faq", facts_used=facts_used, kpis_used=[]),
    )
