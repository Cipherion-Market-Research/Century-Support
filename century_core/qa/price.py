"""Deterministic detection for price-intent questions (owner ruling
2026-08-17): "what's the price of CPX", "how much does CPX cost", "what's
CPX worth" etc. must all route to the same deterministic /price response
(century_core.commands.price.handle_price) rather than the generic
facts-search + LLM Q&A path -- CPX has no market price to quote, and the
free-form LLM path is exactly the surface that could otherwise invent or
leak a banned figure.

Deliberately conservative (word-boundary token match against a small,
specific trigger set) so it doesn't swallow supply/stats/other questions
that happen to share vocabulary -- see is_supply_question in supply.py for
the same pattern applied to burn/supply questions, checked first in
qa/router.py so a query like "total supply" is never misrouted here.
"""
import re

_PRICE_TRIGGERS = {"price", "priced", "pricing", "cost", "costs", "worth"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HOW_MUCH_IS_RE = re.compile(r"\bhow much is\b")


def is_price_question(query: str) -> bool:
    tokens = set(_TOKEN_RE.findall(query.lower()))
    if tokens & _PRICE_TRIGGERS:
        return True
    return bool(_HOW_MUCH_IS_RE.search(query.lower()))


# --- Listing-intent questions route to the same deterministic answer ------
#
# "when does ciphex start trading on exchanges" (live test, 2026-08-18) got
# an honest-but-empty refusal from the LLM path even though the
# identity.listing_initiative fact answers it exactly -- keyword retrieval
# didn't rank the fact and the question carries no price-trigger token. The
# deterministic /price response already states listing status and the
# expected announcement window, so listing intent routes there too.
#
# Conservative by the same rules as is_price_question: "listing"/"listed"/
# "dex"/"cex" are inherently listing-topic tokens; the broader
# "exchange(s)" only counts when paired with a timing/trading token, so
# "the exchange value of each token" (Contribution Program vocabulary)
# never routes here.
_LISTING_TOKENS = {"listing", "listed", "dex", "cex"}
_EXCHANGE_TOKENS = {"exchange", "exchanges"}
_TIMING_TOKENS = {
    "when", "date", "start", "starts", "started", "starting",
    "launch", "launched", "launching", "live", "soon",
    "trade", "trading", "tradable", "buy", "sell",
}


def is_listing_question(query: str) -> bool:
    tokens = set(_TOKEN_RE.findall(query.lower()))
    if tokens & _LISTING_TOKENS:
        return True
    return bool(tokens & _EXCHANGE_TOKENS) and bool(tokens & _TIMING_TOKENS)
