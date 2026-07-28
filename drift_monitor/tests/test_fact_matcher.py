from drift_monitor.diff_engine import compute_hunks
from drift_monitor.fact_matcher import (
    build_fact_value_index,
    extract_tokens,
    propose_new_value,
    reconcile_hunk,
    reconcile_hunks,
)


def test_extract_tokens_categorizes_correctly():
    text = (
        "Email support@ciphex.io, address 0x18b33687d1c804Dd4ea6c82106e54923c23a652E, "
        "url https://ciphex.io, number 481,454,298, date 2026-07-20."
    )
    tokens = extract_tokens(text)
    assert "support@ciphex.io" in tokens["email"]
    assert "0x18b33687d1c804dd4ea6c82106e54923c23a652e" in tokens["address"]
    assert "https://ciphex.io" in tokens["url"]
    assert "481454298" in tokens["number"]
    assert "2026-07-20" in tokens["date"]
    # the address's hex digits must not also leak into the number bucket
    assert not any(t.startswith("18b3") for t in tokens["number"])


def test_extract_tokens_number_normalizes_commas():
    tokens = extract_tokens("64,000,000 CPX cap")
    assert "64000000" in tokens["number"]


def test_build_fact_value_index_skips_unknown(facts_store):
    index = build_fact_value_index(facts_store)
    # identity.oq1_support_routing is `unknown` in the fixture -- must not
    # appear in the index under any category.
    assert all("oq1_support_routing" not in keys for keys in index.values())
    assert index[("email", "support@ciphex.io")] == ["identity.support_email"]
    assert index[("number", "481454298")] == ["tokenomics.burn_cycle_1_cpx"]
    assert index[("address", "0x18b33687d1c804dd4ea6c82106e54923c23a652e")] == ["contracts.cpx_eth"]


def test_reconcile_hunk_maps_known_fact_change(facts_store):
    old = "Contact support at support@ciphex.io for help."
    new = "Contact support at help@ciphex.io for help."
    hunks = compute_hunks(old, new)
    assert len(hunks) == 1
    finding = reconcile_hunk(hunks[0], build_fact_value_index(facts_store))

    assert finding.unmapped is False
    assert finding.mapped_fact_keys == ["identity.support_email"]

    proposed = propose_new_value(finding, "identity.support_email", facts_store)
    assert proposed == "help@ciphex.io"


def test_reconcile_hunk_flags_unmapped_change(facts_store):
    old = "Nothing factual here."
    new = "Nothing factual here, except a new marketing tagline."
    hunks = compute_hunks(old, new)
    finding = reconcile_hunk(hunks[0], build_fact_value_index(facts_store))

    assert finding.unmapped is True
    assert finding.mapped_fact_keys == []


def test_reconcile_hunks_batches_multiple_hunks(facts_store):
    old = "a\nsupport@ciphex.io\nb\nunrelated old copy"
    new = "a\nhelp@ciphex.io\nb\nunrelated NEW copy"
    hunks = compute_hunks(old, new)
    findings = reconcile_hunks(hunks, facts_store)
    assert any(not f.unmapped for f in findings)
    assert any(f.unmapped for f in findings)
