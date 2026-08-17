"""qa/facts_search.py: keyword-overlap search over facts.yaml, and the
2026-08-17 servable-facts exclusion (Config.BLOCKED_FACT_KEYS) -- these
keys exist for historical/scam-verification/audit purposes only and must
never be servable to a user, even when they'd otherwise score highest for
a query.
"""
from century_core.config import Config
from century_core.qa.facts_search import search_facts


def test_blocked_keys_are_defined_and_nonempty():
    assert Config.BLOCKED_FACT_KEYS == {
        "contracts.base_presale",
        "contracts.cpx_token_base",
        "links.claim_portal_legacy_redirect",
        "round-terms.new_round_price_usd",
    }


def test_base_presale_never_surfaces_for_base_contract_query(facts):
    results = search_facts(facts, "Base contract address", limit=10)
    keys = {key for key, _ in results}
    assert "contracts.base_presale" not in keys
    assert "contracts.cpx_token_base" not in keys


def test_legacy_redirect_never_surfaces_for_presale_redirect_query(facts):
    results = search_facts(facts, "presale redirect old link", limit=10)
    keys = {key for key, _ in results}
    assert "links.claim_portal_legacy_redirect" not in keys


def test_new_round_price_never_surfaces_for_price_query(facts):
    results = search_facts(facts, "price of the new round", limit=10)
    keys = {key for key, _ in results}
    assert "round-terms.new_round_price_usd" not in keys


def test_search_still_returns_other_relevant_facts_for_price_query(facts):
    # The blocked key is excluded, but the query should still be able to
    # surface OTHER, non-blocked facts (e.g. the round's status/name).
    results = search_facts(facts, "new round contribution program status", limit=10)
    keys = {key for key, _ in results}
    assert keys  # not empty -- the exclusion doesn't break search generally
    assert "round-terms.new_round_price_usd" not in keys


def test_all_blocked_keys_excluded_across_a_broad_query(facts):
    # A very broad query touching every category should never resurface a
    # blocked key regardless of overlap score.
    results = search_facts(
        facts, "ciphex cpx base ethereum contract presale price round token legacy redirect", limit=50
    )
    keys = {key for key, _ in results}
    assert keys.isdisjoint(Config.BLOCKED_FACT_KEYS)
