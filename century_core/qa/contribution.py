"""Deterministic detection for contribution-program-intent questions (live
tester feedback, 2026-08-26): five nearly-identical-intent questions --
"when can I contribute?", "how long will the contribution program run?",
"how many months will contributions be permitted?", "when does the
contribution program start?", "how do I participate in the contribution
program?" -- produced one good answer, three outright refusals, and one
flat-wrong answer from the generic facts-search + LLM path. All five ask
the same thing the deterministic /contribute response
(century_core.commands.contribute.handle_contribute) already answers in
full (status/stages/minimums/max/lockup/vesting), so they route there
instead of relying on facts_search ranking to surface the right
round-terms.* facts.

Deliberately conservative, same word-boundary-token pattern as
qa/price.py: a contribution-topic noun/verb token alone is not enough
(e.g. a stray "contribution" in unrelated prose), and an intent/timing
token alone is not enough (e.g. bare "when"/"program") -- both sets must
be hit. Checked in qa/router.py AFTER price/listing/buy (so "how do I buy
CPX" keeps its existing deterministic /price route even though it also
overlaps "contribution" vocabulary in some phrasings) and BEFORE holders.
"""
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Contribution-topic nouns/verbs -- unambiguous on their own that the topic
# is the Contribution Program.
_CONTRIBUTION_TOPIC_TOKENS = {
    "contribute", "contribution", "contributions", "participate", "participation",
}

# Intent/timing/scope tokens: pairs with a topic token above to confirm the
# question is asking about the program's timing, duration, or terms (not
# just mentioning "contribution" in passing). "minimum"/"minimums" added
# (live tester feedback, 2026-08-26): "what is the minimum contribution?"
# is answered well by facts_search today, but the deterministic /contribute
# response states the exact tier minimums (Early/Growth/Final) in the same
# breath as the rest of the program terms -- routing it here keeps that
# answer consistent with every other contribution-timing question rather
# than leaving it to keyword-overlap luck.
_CONTRIBUTION_INTENT_TOKENS = {
    "program", "round", "start", "starts", "begin", "begins", "when", "long",
    "months", "duration", "run", "permitted", "open", "opens",
    "minimum", "minimums",
}


def is_contribution_question(query: str) -> bool:
    tokens = set(_TOKEN_RE.findall(query.lower()))
    return bool(tokens & _CONTRIBUTION_TOPIC_TOKENS) and bool(tokens & _CONTRIBUTION_INTENT_TOKENS)
