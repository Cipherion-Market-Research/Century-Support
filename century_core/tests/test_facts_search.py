"""qa/facts_search.py: keyword-overlap search over facts.yaml, and the
2026-08-17 servable-facts exclusion (Config.BLOCKED_FACT_KEYS) -- these
keys exist for historical/scam-verification/audit purposes only and must
never be servable to a user, even when they'd otherwise score highest for
a query.
"""
import pytest

from century_core.config import Config
from century_core.qa.facts_search import search_facts, search_facts_scored


def test_blocked_keys_are_defined_and_nonempty():
    assert Config.BLOCKED_FACT_KEYS == {
        "contracts.base_presale",
        "contracts.cpx_token_base",
        "links.claim_portal_legacy_redirect",
        "links.ecosystem_publications",
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


def test_ecosystem_publications_never_surfaces_for_publications_query(facts):
    # Bot Parameter Requirements (2026-08-18): the Insights & Publications
    # section is excluded from the bot's knowledge base -- this link must
    # never be servable, even for a query that names it directly.
    results = search_facts(facts, "ciphex insights and publications reports", limit=10)
    keys = {key for key, _ in results}
    assert "links.ecosystem_publications" not in keys


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


# ───────────────────── scoring rework (item 2, live tester feedback, 2026-08-26) ─────────────────────
# Tester-proven defects with plain unweighted token-overlap counting:
#   - "who is the ciphex leadership team?" refused, "who is the CPX
#     leadership team?" answered -- the SAME fact, differing only by which
#     of "ciphex"/"cpx" the query happened to spell out.
#   - "what is AMS?" refused because "ams" also matches the ams.ciphex.io
#     domain facts, diluting products.ciphex_alpha_description.
#   - "digital financing" landed on the general Financing Activities legal
#     disclosure instead of the Contribution Program.
#   - "risk management" pulled the FATF restricted-persons fact.
# See qa/facts_search.py's module docstring for the corpus-frequency
# down-weighting + alias-table design that fixes these.


LEADERSHIP_TEAM_PHRASING_PAIRS = [
    ("who is the ciphex leadership team?", "who is the CPX leadership team?"),
    ("who is the ciphex management team?", "who is the CPX management team?"),
]


@pytest.mark.parametrize("ciphex_phrasing, cpx_phrasing", LEADERSHIP_TEAM_PHRASING_PAIRS)
def test_ciphex_cpx_phrasing_pairs_score_identically(facts, ciphex_phrasing, cpx_phrasing):
    # Exact transcript regression: these two phrasings differ only in
    # brand-word spelling and must resolve to the same top fact with the
    # same (or near-identical) score -- see the ciphex<->cpx mutual alias
    # and the corpus-frequency down-weighting that makes "ciphex"/"cpx"
    # near-zero discriminators on their own.
    ciphex_hits = search_facts_scored(facts, ciphex_phrasing, limit=5)
    cpx_hits = search_facts_scored(facts, cpx_phrasing, limit=5)
    assert ciphex_hits and cpx_hits
    assert ciphex_hits[0][1] == cpx_hits[0][1] == "legal.governance"
    assert ciphex_hits[0][0] == pytest.approx(cpx_hits[0][0], rel=1e-6)


@pytest.mark.parametrize("ciphex_phrasing, cpx_phrasing", LEADERSHIP_TEAM_PHRASING_PAIRS)
def test_ciphex_cpx_phrasing_pairs_both_surface_governance_fact(facts, ciphex_phrasing, cpx_phrasing):
    # Unscored search_facts (the unchanged public interface) must also
    # return the same top key for both spellings -- neither phrasing is
    # left refused while the other is answered.
    ciphex_keys = [key for key, _ in search_facts(facts, ciphex_phrasing, limit=3)]
    cpx_keys = [key for key, _ in search_facts(facts, cpx_phrasing, limit=3)]
    assert "legal.governance" in ciphex_keys
    assert "legal.governance" in cpx_keys


def test_ams_query_surfaces_alpha_description_in_top3(facts):
    # "what is AMS?" previously refused -- the bare "ams" token split the
    # vote with the ams.ciphex.io domain facts. The "ams" -> alpha/asset/
    # management/system query alias should now put
    # products.ciphex_alpha_description (which spells all of those out)
    # in the top-3.
    hits = search_facts(facts, "what is AMS?", limit=3)
    keys = [key for key, _ in hits]
    assert "products.ciphex_alpha_description" in keys


def test_digital_financing_query_does_not_top_the_financing_activities_legal_fact(facts):
    # "digital financing" previously landed on the general Financing
    # Activities legal disclosure instead of the Contribution Program --
    # the "financing" -> contribution/program query alias should now favor
    # the round-terms.new_round_* Contribution Program facts.
    hits = search_facts(facts, "digital financing", limit=3)
    keys = [key for key, _ in hits]
    assert keys
    assert keys[0] != "legal.future_financing_restricted_persons"
    assert any(key.startswith("round-terms.new_round") for key in keys)


def test_risk_management_query_does_not_top_the_fatf_restricted_persons_fact(facts):
    # "risk management" previously pulled the FATF restricted-persons fact
    # (a coincidental single-token "risk" overlap) as its top hit.
    hits = search_facts_scored(facts, "risk management", limit=3)
    assert hits
    assert hits[0][1] != "legal.future_financing_restricted_persons"


# --- algorithmic properties, isolated from facts.yaml's specific content ---
#
# The tests above prove the real corpus behaves correctly; these prove WHY,
# against a small synthetic store, so the scoring design itself (not just
# today's facts.yaml content) is under regression.


class _FakeFact:
    def __init__(self, value, notes=None):
        self.value = value
        self.notes = notes
        self.is_unknown = False


class _FakeStore:
    def __init__(self, facts_by_key):
        self._facts = facts_by_key

    def keys(self):
        return self._facts.keys()

    def get(self, key):
        return self._facts.get(key)


def test_corpus_frequency_downweights_a_near_ubiquitous_token():
    # "cpx" appears in 3 of 4 facts below (near-ubiquitous, weak
    # discriminator); "unicorn" appears in exactly 1 of 4 (highly
    # discriminating). A query matching only the near-ubiquitous token must
    # score far below a query matching only the rare one, even though both
    # are single-token, single-fact-set overlaps under the old unweighted
    # scheme.
    store = _FakeStore(
        {
            "a.one": _FakeFact("cpx common thing one"),
            "a.two": _FakeFact("cpx common thing two"),
            "a.three": _FakeFact("cpx common thing three"),
            "a.four": _FakeFact("unicorn rare thing"),
        }
    )
    cpx_only = search_facts_scored(store, "cpx", limit=4)
    unicorn_only = search_facts_scored(store, "unicorn", limit=4)
    assert cpx_only and unicorn_only
    assert unicorn_only[0][0] > cpx_only[0][0]


def test_corpus_frequency_weight_is_zero_for_a_token_in_every_fact():
    store = _FakeStore(
        {
            "a.one": _FakeFact("ciphex thing one"),
            "a.two": _FakeFact("ciphex thing two"),
        }
    )
    # "ciphex" is in every fact -> log(N/N) == 0 -> contributes nothing.
    hits = search_facts_scored(store, "ciphex", limit=2)
    assert hits == []


def test_alias_table_ams_expands_to_alpha_asset_management_system():
    store = _FakeStore(
        {
            "products.alpha": _FakeFact("Ciphex Alpha comprises an asset management system"),
            "identity.domain": _FakeFact("ams example domain, unrelated to the product"),
        }
    )
    hits = search_facts(store, "what is AMS?", limit=2)
    keys = [key for key, _ in hits]
    assert "products.alpha" in keys
    # The fact that spells out the aliased words should outrank the fact
    # that only matches the bare "ams" token.
    assert keys[0] == "products.alpha"


def test_notes_only_matches_are_discounted_relative_to_value_matches():
    # A word that only shows up in a fact's `notes` (internal audit
    # commentary) is weaker evidence of topical relevance than the same
    # word in the fact's own `value` -- see qa/facts_search.py's
    # _NOTES_DISCOUNT. Real-corpus regression: identity.dex_live_status's
    # notes happen to say "...the team has indicated..." which must not
    # outweigh legal.governance's value-level "...leadership team" mention.
    # A third, unrelated filler fact keeps "team"'s corpus frequency below
    # 100% (df=2 of 3) so it has a non-zero weight to discount in the
    # first place.
    store = _FakeStore(
        {
            "a.value_match": _FakeFact("the leadership team decides direction"),
            "a.notes_match": _FakeFact("unrelated value text", notes="ask the team for details"),
            "a.filler": _FakeFact("completely unrelated filler content"),
        }
    )
    hits = search_facts_scored(store, "team", limit=3)
    assert hits[0][1] == "a.value_match"
    notes_match_score = next(score for score, key, _ in hits if key == "a.notes_match")
    value_match_score = hits[0][0]
    assert notes_match_score < value_match_score
