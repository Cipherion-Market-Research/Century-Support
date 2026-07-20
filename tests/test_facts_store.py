# tests/test_facts_store.py
import textwrap
from pathlib import Path

import pytest

from facts_store import ALLOWED_CATEGORIES, FactsValidationError, load_facts_file
from facts_store.loader import DEFAULT_FACTS_PATH


def write_yaml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "facts.yaml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The real facts.yaml
# ---------------------------------------------------------------------------

def test_repo_facts_yaml_is_valid():
    """The real facts.yaml at the repo root must pass full validation."""
    facts_file = load_facts_file(DEFAULT_FACTS_PATH)
    assert facts_file.version == 1
    assert len(facts_file.facts) > 0


def test_repo_facts_yaml_every_key_has_allowed_category():
    facts_file = load_facts_file(DEFAULT_FACTS_PATH)
    for key in facts_file.facts:
        category = key.split(".", 1)[0]
        assert category in ALLOWED_CATEGORIES, f"orphaned category in key {key!r}"


def test_repo_facts_yaml_every_fact_has_provenance():
    facts_file = load_facts_file(DEFAULT_FACTS_PATH)
    for key, fact in facts_file.facts.items():
        assert fact.source_url and fact.source_url.strip(), f"{key} missing source_url"
        assert fact.verified_on is not None, f"{key} missing verified_on"


def test_repo_facts_yaml_resolved_oq_items_are_no_longer_unknown():
    """OQ-1/OQ-2/OQ-3 (docs/CONTRACTS.md) were resolved by the owner on 2026-07-20
    review and must carry real values now, not the unknown sentinel."""
    facts_file = load_facts_file(DEFAULT_FACTS_PATH)
    for key in (
        "identity.support_email",
        "identity.canonical_alpha_domain",
        "identity.dex_live_status",
    ):
        assert key in facts_file.facts, f"expected {key} to be present"
        assert not facts_file.facts[key].is_unknown, f"{key} was resolved by the owner and should not be unknown"


def test_repo_facts_yaml_oq5_burn_address_is_unknown():
    """OQ-5 (new, raised by Agent C's on-chain finding) must be the unknown sentinel."""
    facts_file = load_facts_file(DEFAULT_FACTS_PATH)
    assert "tokenomics.burn_cycle_1_burn_address" in facts_file.facts
    assert facts_file.facts["tokenomics.burn_cycle_1_burn_address"].is_unknown

    # round-terms.new_round_lockup_interest also remains an open unknown
    assert facts_file.facts["round-terms.new_round_lockup_interest"].is_unknown


def test_repo_facts_yaml_distinguishes_onchain_from_fd_supply():
    """Guard against the on-chain-vs-FD-supply confusion flagged in review:
    the two figures must never collapse to the same value."""
    facts_file = load_facts_file(DEFAULT_FACTS_PATH)
    onchain = facts_file.facts["tokenomics.onchain_total_supply_eth"].value
    fd_supply = facts_file.facts["tokenomics.fy2026_fd_supply"].value
    assert onchain == 1500000000
    assert fd_supply == 1018545702
    assert onchain != fd_supply


def test_repo_facts_yaml_has_at_least_ten_facts_per_wp2_acceptance():
    facts_file = load_facts_file(DEFAULT_FACTS_PATH)
    assert len(facts_file.facts) >= 10


# ---------------------------------------------------------------------------
# Schema / format enforcement, on synthetic fixtures
# ---------------------------------------------------------------------------

def test_minimal_valid_file_loads(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          identity.brand_name:
            value: "Ciphex"
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/"
        """,
    )
    facts_file = load_facts_file(path)
    assert facts_file.facts["identity.brand_name"].value == "Ciphex"


def test_unknown_sentinel_is_accepted(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          identity.support_email:
            value: unknown
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/contact"
        """,
    )
    facts_file = load_facts_file(path)
    assert facts_file.facts["identity.support_email"].is_unknown


def test_rejects_orphan_category_prefix(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          toknomics.max_supply_cpx:
            value: 1500000000
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/ciphex-token"
        """,
    )
    with pytest.raises(FactsValidationError, match="orphaned category prefix"):
        load_facts_file(path)


def test_rejects_malformed_key_without_category(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          max_supply_cpx:
            value: 1500000000
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/ciphex-token"
        """,
    )
    with pytest.raises(FactsValidationError, match="malformed fact key"):
        load_facts_file(path)


def test_rejects_missing_source_url(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          tokenomics.max_supply_cpx:
            value: 1500000000
            verified_on: "2026-07-20"
        """,
    )
    with pytest.raises(FactsValidationError):
        load_facts_file(path)


def test_rejects_blank_source_url(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          tokenomics.max_supply_cpx:
            value: 1500000000
            verified_on: "2026-07-20"
            source_url: ""
        """,
    )
    with pytest.raises(FactsValidationError):
        load_facts_file(path)


def test_rejects_extra_unknown_field_on_fact(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          tokenomics.max_supply_cpx:
            value: 1500000000
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/ciphex-token"
            confidence: "high"
        """,
    )
    with pytest.raises(FactsValidationError):
        load_facts_file(path)


def test_rejects_wrong_schema_version(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 2
        facts: {}
        """,
    )
    with pytest.raises(FactsValidationError, match="unsupported facts.yaml schema version"):
        load_facts_file(path)


def test_rejects_duplicate_key(tmp_path):
    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          tokenomics.max_supply_cpx:
            value: 1500000000
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/ciphex-token"
          tokenomics.max_supply_cpx:
            value: 999
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/ciphex-token"
        """,
    )
    with pytest.raises(FactsValidationError, match="duplicate key"):
        load_facts_file(path)


def test_rejects_invalid_yaml(tmp_path):
    path = tmp_path / "facts.yaml"
    path.write_text("version: 1\nfacts: [this, is, not, a, mapping", encoding="utf-8")
    with pytest.raises(FactsValidationError, match="not valid YAML"):
        load_facts_file(path)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FactsValidationError, match="could not read"):
        load_facts_file(tmp_path / "does-not-exist.yaml")


# ---------------------------------------------------------------------------
# FactsStore accessor
# ---------------------------------------------------------------------------

def test_facts_store_get_and_contains(tmp_path):
    from facts_store import FactsStore

    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          links.website:
            value: "https://ciphex.io"
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/"
        """,
    )
    store = FactsStore.load(path)
    assert "links.website" in store
    assert store.get("links.website").value == "https://ciphex.io"
    assert store.get("links.nonexistent") is None
    assert len(store) == 1


def test_facts_store_by_category(tmp_path):
    from facts_store import FactsStore

    path = write_yaml(
        tmp_path,
        """
        version: 1
        facts:
          links.website:
            value: "https://ciphex.io"
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/"
          links.telegram:
            value: "https://t.me/ciphexgroup"
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/community"
          legal.governance:
            value: "no community voting"
            verified_on: "2026-07-20"
            source_url: "https://ciphex.io/leadership-team"
        """,
    )
    store = FactsStore.load(path)
    links = store.by_category("links")
    assert set(links) == {"links.website", "links.telegram"}
