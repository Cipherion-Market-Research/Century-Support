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

# "value"/"valuation" added (live tester feedback, 2026-08-26: "what is the
# value of CPX?" x2 fell through to RAG/LLM instead of the deterministic
# /price answer). Conservative in the same word-boundary-token way as the
# rest of this module -- see is_listing_question below for the specific
# interaction check against Contribution Program vocabulary ("the exchange
# value of each token"), which has neither a price trigger token match here
# (this set only gates is_price_question) nor a timing token, so it is
# unaffected by this addition.
_PRICE_TRIGGERS = {"price", "priced", "pricing", "cost", "costs", "worth", "value", "valuation"}
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
# Conservative by the same rules as is_price_question: "listing"/"listed"
# stay sufficient alone (unambiguously listing-topic). Bare "dex"/"cex" are
# NOT standalone triggers -- live tester feedback, 2026-08-26: "can I do
# autonomous portfolio management on the DEX?" / "...on the CEX?" (flat
# wrong x2) routed here purely off the bare token, with no listing/timing
# intent at all. dex/cex now require a timing/trading token alongside them,
# same conservative pairing as the "exchange(s)" rule below (which already
# keeps "the exchange value of each token" -- Contribution Program
# vocabulary -- from routing here).
_STANDALONE_LISTING_TOKENS = {"listing", "listed"}
_DEX_CEX_TOKENS = {"dex", "cex"}
_EXCHANGE_TOKENS = {"exchange", "exchanges"}
_TIMING_TOKENS = {
    "when", "date", "start", "starts", "started", "starting", "will",
    "launch", "launched", "launching", "live", "soon",
    "trade", "trading", "tradable", "buy", "sell",
    # "available"/"availability" (live tester feedback, 2026-08-26: "where
    # will CPX be available?" and similar phrasings) -- deliberately added
    # as a *timing* token, paired below, not a standalone listing token:
    # "available" alone is too generic a word (e.g. "is a demo available")
    # to be a safe standalone trigger. Checked against Contribution Program
    # vocabulary: "the exchange value of each token" has no timing token at
    # all (neither "available" nor any other), so it still does not route.
    "available", "availability",
}


def is_listing_question(query: str) -> bool:
    tokens = set(_TOKEN_RE.findall(query.lower()))
    if tokens & _STANDALONE_LISTING_TOKENS:
        return True
    if (tokens & _DEX_CEX_TOKENS) and (tokens & _TIMING_TOKENS):
        return True
    return bool(tokens & _EXCHANGE_TOKENS) and bool(tokens & _TIMING_TOKENS)


# --- Buy-intent questions route to the same deterministic answer ----------
#
# "How do I buy CPX" (live tester feedback, 2026-08-19) fell through to RAG
# and served a 2025-era update's stale claim ("initial DEX listing is
# targeted for September 2025") -- the worst answer surfaced in that test
# pass. The deterministic /price response already states CPX is not yet
# listed, the Contribution Program has not opened, and the expected
# announcement window, with official links -- exactly the correct answer to
# "how do I buy" today, so buy-intent routes there too.
#
# Conservative by the same rule as is_price_question/is_listing_question:
# a buy-verb token alone is not enough (e.g. "when will contributors buy
# in" has no CPX/token word), and a token-word alone is not enough (e.g.
# "how many tokens were burned" has no buy-verb) -- both sets must be hit.
_BUY_TRIGGERS = {"buy", "buying", "purchase", "purchasing", "acquire", "invest", "investing"}
_TOKEN_WORDS = {"cpx", "ciphex", "token", "tokens", "coin"}


def is_buy_question(query: str) -> bool:
    tokens = set(_TOKEN_RE.findall(query.lower()))
    return bool(tokens & _BUY_TRIGGERS) and bool(tokens & _TOKEN_WORDS)
