"""Keyword-overlap search over facts.yaml for the Q&A path.

Deliberately simple: a ~90-fact store doesn't need a vector index, and a
transparent, deterministic scorer is easier to reason about (and to write
guardrail/coverage tests against) than an embedding-based one. Publications
content is out of scope here — that's pubs_rag.retrieve() — per WP-5 brief
item 2: page-level/identity/numeric questions answer from facts.yaml, not
RAG.
"""
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def search_facts(store, query: str, limit: int = 3) -> list[tuple[str, object]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    scored = []
    for key in store.keys():
        fact = store.get(key)
        if fact is None or fact.is_unknown:
            continue
        haystack = f"{key} {fact.value} {fact.notes or ''}"
        overlap = len(query_tokens & _tokens(haystack))
        if overlap:
            scored.append((overlap, key, fact))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [(key, fact) for _, key, fact in scored[:limit]]
