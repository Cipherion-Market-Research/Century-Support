"""Keyword-overlap search over facts.yaml for the Q&A path.

Deliberately simple: a ~90-fact store doesn't need a vector index, and a
transparent, deterministic scorer is easier to reason about (and to write
guardrail/coverage tests against) than an embedding-based one. Publications
content is out of scope here — that's pubs_rag.retrieve() — per WP-5 brief
item 2: page-level/identity/numeric questions answer from facts.yaml, not
RAG.

Scoring rework (live tester feedback, 2026-08-26 -- item 2 of the Sprint 2
remediation). Plain unweighted token-overlap counting had three proven
failure modes:

  1. "who is the ciphex leadership team?" was refused while "who is the CPX
     leadership team?" was answered -- the SAME fact (legal.governance)
     scored differently purely because "cpx" happened to appear once in an
     unrelated fact's notes and "ciphex" didn't, and every fact mentions
     "ciphex"/"cpx" somewhere, so those two tokens are pure noise as
     discriminators, not signal.
  2. "what is AMS?" was refused because the bare "ams" token also matches
     the ams.ciphex.io domain facts (links.alpha_dashboard,
     identity.canonical_alpha_domain), splitting the vote against
     products.ciphex_alpha_description, the fact that actually answers the
     question.
  3. "digital financing" landed on the general Financing Activities legal
     disclosure instead of the Contribution Program, and "risk management"
     pulled the FATF restricted-persons fact -- both purely coincidental
     single-word overlaps ("financing", "risk") outweighing what the
     question actually meant.

Two changes fix this without touching the public interface:

  (a) Corpus-frequency (IDF-style) down-weighting, computed once per store
      instance (see _corpus_weights / _WEIGHTS_CACHE below) and cached for
      the store's lifetime -- in production that's the whole process, since
      century_core.app wires up facts_store.default_store()'s one
      process-wide singleton. A token's weight is log(N / df) where N is
      the number of servable facts and df is how many of them contain the
      token: a token every fact contains (ciphex, cpx, ...) scores ~0 and
      can no longer swing a ranking; a token only 1-2 facts contain
      (leadership, risk, ...) scores highest. Key+value tokens count at
      full weight; notes-only tokens count at a reduced weight
      (_NOTES_DISCOUNT) -- notes are internal audit/provenance commentary,
      not the fact's actual content, and are where incidental word
      collisions live (e.g. "...phrase it to users as something the team
      has indicated..." in identity.dex_live_status's notes has nothing to
      do with a "leadership team" query, but was previously inflating that
      fact's score on team/leadership-adjacent queries).
  (b) A small explicit query-side alias/synonym table (_QUERY_ALIASES)
      applied to the query's tokens before scoring, so a query token also
      credits a fact for a synonym/expansion it uses instead: "ams"/"ems"
      pull in "alpha"/"asset"/"execution"/"management"/"system" so
      products.ciphex_alpha_description (which spells all of those out)
      stops splitting the vote with the ams.ciphex.io domain facts;
      "financing" pulls in "contribution"/"program" so a financing query
      can reach the Contribution Program facts even though they never say
      "financing"; "team"/"leadership"/"management" are mutual aliases;
      "ciphex"/"cpx" are mutual aliases (belt-and-suspenders alongside (a)
      -- (a) already neutralizes them as discriminators, this guarantees a
      fact written with only one spelling is still reachable by a query
      using the other); "token"/"tokens" pull in "stack" so a
      token-vs-system question also retrieves identity.product_stack
      (item 4 of this sprint: the "CPX is the token, Ciphex Alpha is the
      system" distinction) alongside whatever grounds the actual answer.

The interface is unchanged: search_facts(store, query, limit) still
returns the same `list[tuple[key, fact]]` shape, so no caller needs to
change.
"""
import math
import re
import weakref

from century_core.config import Config

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


# --- (b) query-side alias/synonym table --------------------------------
#
# Deliberately small and hand-picked from tester-proven failures, not a
# general thesaurus -- each entry exists because a specific live-tester
# question needed it (see the module docstring). Applied to QUERY tokens
# only, never to fact haystacks, so it can only ever make a fact easier to
# find, never introduce a new false match inside facts.yaml's own text.
_QUERY_ALIASES: dict[str, set[str]] = {
    "ams": {"alpha", "asset", "management", "system"},
    "ems": {"alpha", "execution"},
    "abigail": {"alpha"},
    "financing": {"contribution", "program"},
    "team": {"leadership", "management"},
    "leadership": {"team", "management"},
    "management": {"team", "leadership"},
    "ciphex": {"cpx"},
    "cpx": {"ciphex"},
    # Item 4 (token-vs-system disambiguation): a "token" question should
    # also retrieve identity.product_stack (key contains "stack"), which
    # lists CPX Token and Ciphex Alpha as separate line items -- see
    # qa/router.py's build_context for the paired context-note that uses
    # this co-occurrence.
    "token": {"stack"},
    "tokens": {"stack"},
}


def _expand_query_tokens(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for token in tokens:
        expanded |= _QUERY_ALIASES.get(token, set())
    return expanded


# --- (a) corpus-frequency down-weighting --------------------------------

# Notes fields are internal audit/provenance commentary about a fact, not
# the fact's own content -- a word that only shows up in a fact's notes
# (e.g. "...check with the team..." in identity.dex_live_status) is far
# weaker evidence of topical relevance than the same word in the fact's
# key or value. Full weight for key/value hits, this fraction for
# notes-only hits.
_NOTES_DISCOUNT = 0.25


class _CorpusWeights:
    """Precomputed per-token IDF-style weights for one store instance,
    split into "primary" (key+value) token sets and "secondary"
    (notes-only) token sets per fact so scoring can apply _NOTES_DISCOUNT.
    """

    __slots__ = ("primary_tokens", "secondary_tokens", "weight")

    def __init__(self, primary_tokens, secondary_tokens, weight):
        self.primary_tokens = primary_tokens
        self.secondary_tokens = secondary_tokens
        self.weight = weight


# Cached per store instance (weak-keyed so a store that's garbage
# collected doesn't leak its cache entry) -- computed once for the store's
# effective lifetime, which in production is the whole process (see
# module docstring).
_WEIGHTS_CACHE: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _servable_facts(store):
    for key in store.keys():
        if key in Config.BLOCKED_FACT_KEYS:
            # Never let a blocked key's vocabulary shape scoring, same as
            # it's never let into results below.
            continue
        fact = store.get(key)
        if fact is None or fact.is_unknown:
            continue
        yield key, fact


def _corpus_weights(store) -> _CorpusWeights:
    cached = _WEIGHTS_CACHE.get(store)
    if cached is not None:
        return cached

    primary_tokens: dict[str, set[str]] = {}
    secondary_tokens: dict[str, set[str]] = {}
    doc_freq: dict[str, int] = {}
    doc_count = 0

    for key, fact in _servable_facts(store):
        doc_count += 1
        primary = _tokens(f"{key} {fact.value}")
        secondary = _tokens(fact.notes or "") - primary
        primary_tokens[key] = primary
        secondary_tokens[key] = secondary
        for token in primary | secondary:
            doc_freq[token] = doc_freq.get(token, 0) + 1

    weight = {
        token: math.log(doc_count / freq) if freq else 0.0
        for token, freq in doc_freq.items()
    }

    weights = _CorpusWeights(primary_tokens, secondary_tokens, weight)
    try:
        _WEIGHTS_CACHE[store] = weights
    except TypeError:
        # Store doesn't support weak references (e.g. an unusual test
        # double) -- fine to just not cache; scoring still works, it's
        # simply recomputed next call.
        pass
    return weights


def _fact_score(weights: _CorpusWeights, key: str, query_tokens: set[str]) -> float:
    primary_hit = query_tokens & weights.primary_tokens.get(key, set())
    secondary_hit = query_tokens & weights.secondary_tokens.get(key, set())
    score = sum(weights.weight.get(t, 0.0) for t in primary_hit)
    score += _NOTES_DISCOUNT * sum(weights.weight.get(t, 0.0) for t in secondary_hit)
    return score


def search_facts_scored(store, query: str, limit: int = 3) -> list[tuple[float, str, object]]:
    """Same ranking as search_facts, but keeps the numeric score in the
    result -- `list[tuple[score, key, fact]]`, highest first. Used by
    qa/router.py's link-relevance capping (item 3, live tester feedback
    2026-08-26): a fact can be worth putting in the LLM's context (a low
    bar -- more grounding rarely hurts) without being worth a citation
    LINK, which readers treat as an endorsement of relevance. search_facts
    below is a thin wrapper that drops the score for callers that only
    ever needed the (key, fact) shape."""
    query_tokens = _expand_query_tokens(_tokens(query))
    if not query_tokens:
        return []

    weights = _corpus_weights(store)

    scored = []
    for key, fact in _servable_facts(store):
        score = _fact_score(weights, key, query_tokens)
        if score > 0:
            scored.append((score, key, fact))

    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:limit]


def search_facts(store, query: str, limit: int = 3) -> list[tuple[str, object]]:
    return [(key, fact) for _, key, fact in search_facts_scored(store, query, limit)]
