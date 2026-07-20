"""Canonical facts store (C4, docs/CONTRACTS.md).

facts.yaml is the single source of truth for numeric and identity answers.
It changes only via reviewed PR — see CONTRIBUTING.md.

Usage:
    from facts_store import default_store

    store = default_store()
    fact = store.get("tokenomics.max_supply_cpx")
    if fact is None or fact.is_unknown:
        ...  # answer "I don't know" + the official link — never guess
    else:
        fact.value, fact.source_url, fact.verified_on
"""
from .exceptions import FactsValidationError
from .loader import DEFAULT_FACTS_PATH, FactsStore, default_store, load_facts_file
from .schema import ALLOWED_CATEGORIES, Fact, FactsFile

__all__ = [
    "ALLOWED_CATEGORIES",
    "DEFAULT_FACTS_PATH",
    "Fact",
    "FactsFile",
    "FactsStore",
    "FactsValidationError",
    "default_store",
    "load_facts_file",
]
