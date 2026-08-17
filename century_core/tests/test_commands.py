"""Command handlers exercised against the REAL facts.yaml (it's the actual
seed store WP-5 must answer from — see docs/CONTRACTS.md C4) with a fake
Redis for KPI-backed commands. This is the "all §2 critical topics answer
correctly against seeded stores" acceptance line for the command surface.
"""
import pytest

from century_core import guardrails, response_guard
from century_core.config import Config
from century_core.commands.audit import handle_audit
from century_core.commands.ca import handle_ca
from century_core.commands.claim import handle_claim
from century_core.commands.contact import handle_contact
from century_core.commands.contribute import handle_contribute
from century_core.commands.ecosystem import handle_ecosystem
from century_core.commands.price import handle_price
from century_core.commands.publications import handle_publications
from century_core.commands.stats import handle_stats
from century_core.commands.supply import handle_supply
from century_core.tests.conftest import make_fact


def _all_text(response):
    parts = []
    for block in response.blocks:
        if block.type == "heading":
            parts.append(block.text)
        elif block.type in ("paragraph", "warning"):
            parts.append(block.md)
        elif block.type == "fact":
            parts.append(f"{block.label} {block.value}")
        elif block.type in ("links", "buttons"):
            parts.extend(item.url for item in block.items)
            parts.extend(item.label for item in block.items)
    return "\n".join(parts)


# ─────────────────────────────── /price ───────────────────────────────


async def test_price_never_quotes_any_price_figure(stub_stores):
    # Owner ruling 2026-08-17: CPX is not listed anywhere -- the bot must
    # NEVER output a CPX price figure, in any form, full stop.
    response = await handle_price("", stub_stores)
    text = _all_text(response)
    assert "$" not in text
    result = guardrails.check_text(text)
    assert result.ok, result.violations


async def test_price_never_reads_the_blocked_price_fact(stub_stores):
    # round-terms.new_round_price_usd is a banned CPX price figure --
    # never touched by this handler.
    response = await handle_price("", stub_stores)
    assert "round-terms.new_round_price_usd" not in response.meta.facts_used


async def test_price_says_not_listed_tbd(stub_stores):
    response = await handle_price("", stub_stores)
    text = _all_text(response)
    assert "not yet listed" in text.lower()
    assert "TBD" in text


async def test_price_mentions_listing_roadmap_default_copy(stub_stores):
    response = await handle_price("", stub_stores)
    text = _all_text(response)
    assert "DEX/CEX listing initiative" in text
    assert "Q3/Q4 2026" in text


async def test_price_uses_listing_initiative_fact_when_present(make_overlay_stores):
    # identity.listing_initiative is a contract key that may not exist in
    # facts.yaml yet -- when present, its value must be rendered instead of
    # the literal fallback copy.
    stores = make_overlay_stores(
        {"identity.listing_initiative": make_fact("A listing announcement is expected in September 2026.")}
    )
    response = await handle_price("", stores)
    text = _all_text(response)
    assert "A listing announcement is expected in September 2026." in text
    assert "identity.listing_initiative" in response.meta.facts_used


async def test_price_falls_back_when_listing_initiative_unknown(make_overlay_stores):
    stores = make_overlay_stores({"identity.listing_initiative": None})
    response = await handle_price("", stores)
    text = _all_text(response)
    assert "DEX/CEX listing initiative" in text
    assert "identity.listing_initiative" not in response.meta.facts_used


async def test_price_references_contribute_command(stub_stores):
    response = await handle_price("", stub_stores)
    text = _all_text(response)
    assert "/contribute" in text


async def test_price_uses_contribution_program_vocabulary_not_presale(stub_stores):
    response = await handle_price("", stub_stores)
    text = _all_text(response).lower()
    assert "presale" not in text


async def test_price_token_page_link_falls_back_without_fact(stub_stores):
    response = await handle_price("", stub_stores)
    links = [b for b in response.blocks if b.type == "links"][0]
    urls = [item.url for item in links.items]
    assert "https://ciphex.io/ciphex-token" in urls
    assert "links.token_page" not in response.meta.facts_used


async def test_price_token_page_link_uses_fact_when_present(make_overlay_stores):
    stores = make_overlay_stores({"links.token_page": make_fact("https://ciphex.io/cpx-token-page")})
    response = await handle_price("", stores)
    links = [b for b in response.blocks if b.type == "links"][0]
    urls = [item.url for item in links.items]
    assert "https://ciphex.io/cpx-token-page" in urls
    assert "links.token_page" in response.meta.facts_used


async def test_price_survives_response_guard(stub_stores):
    response = await handle_price("", stub_stores)
    guarded = response_guard.enforce_response(response)
    assert guarded.meta.answer_kind != "refusal"


# ──────────────────────────────── /ca ────────────────────────────────


async def test_ca_lists_ethereum_address(stub_stores):
    response = await handle_ca("", stub_stores)
    text = _all_text(response)
    assert "0x18b33687d1c804Dd4ea6c82106e54923c23a652E" in text  # Ethereum
    assert "contracts.cpx_token_ethereum" in response.meta.facts_used


async def test_ca_never_mentions_base(stub_stores):
    # Owner ruling 2026-08-17: CPX is ERC-20 on Ethereum only -- Base is
    # never presented as a legitimate deployment.
    response = await handle_ca("", stub_stores)
    text = _all_text(response)
    assert "Base" not in text
    assert "0x7A8Fc21fd34DE3dD5131a965fb3995f484f50D59" not in text
    assert "contracts.cpx_token_base" not in response.meta.facts_used


async def test_ca_includes_chain_exclusivity_warning_default_copy(stub_stores):
    response = await handle_ca("", stub_stores)
    warning_blocks = [b for b in response.blocks if b.type == "warning"]
    assert warning_blocks
    assert "only on Ethereum mainnet" in warning_blocks[0].md
    assert "contracts.cpx_chain_exclusivity" not in response.meta.facts_used


async def test_ca_uses_chain_exclusivity_fact_when_present(make_overlay_stores):
    # contracts.cpx_chain_exclusivity is a contract key that may not exist
    # in facts.yaml yet -- when present, its value must be rendered instead
    # of the literal fallback sentence.
    stores = make_overlay_stores(
        {"contracts.cpx_chain_exclusivity": make_fact("CPX has never been deployed to any chain other than Ethereum.")}
    )
    response = await handle_ca("", stores)
    warning_blocks = [b for b in response.blocks if b.type == "warning"]
    assert "CPX has never been deployed to any chain other than Ethereum." in warning_blocks[0].md
    assert "contracts.cpx_chain_exclusivity" in response.meta.facts_used


# ─────────────────────────────── /claim ───────────────────────────────


async def test_claim_cites_official_portal(stub_stores):
    response = await handle_claim("", stub_stores)
    text = _all_text(response)
    assert "claim.ciphex.io" in text


async def test_claim_warns_about_seed_phrase(stub_stores):
    response = await handle_claim("", stub_stores)
    text = _all_text(response).lower()
    assert "seed phrase" in text


# ─────────────────────────────── /audit ───────────────────────────────


async def test_audit_links_certik_skynet(stub_stores):
    response = await handle_audit("", stub_stores)
    text = _all_text(response)
    assert "skynet.certik.com" in text


# ─────────────────────────────── /stats ───────────────────────────────


async def test_stats_reports_fresh_kpis_with_as_of(stub_stores):
    stub_stores.kpi.redis.seed_kpi("claim_api", "cipherions", 62)
    stub_stores.kpi.redis.seed_kpi("claim_api", "total_contributions", {"ui": "$1.82M", "raw": 1818927.09})

    response = await handle_stats("", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    assert len(fact_blocks) == 2
    for block in fact_blocks:
        assert block.as_of  # every number carries an as-of, per C3/C2
    assert "kpi:claim_api:cipherions" in response.meta.kpis_used


async def test_stats_omits_stale_kpis_instead_of_quoting_them(stub_stores):
    stub_stores.kpi.redis.seed_kpi(
        "claim_api", "cipherions", 62, fetched_at="2020-01-01T00:00:00Z", stale_after_s=1800
    )
    response = await handle_stats("", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    assert fact_blocks == []
    assert response.meta.kpis_used == []
    warning_blocks = [b for b in response.blocks if b.type == "warning"]
    assert warning_blocks  # says stats are unavailable rather than showing stale numbers


async def test_stats_excludes_nonsensical_percent_staked(stub_stores):
    stub_stores.kpi.redis.seed_kpi("claim_api", "percent_staked", {"ui": "105.41", "raw": 105.41})
    stub_stores.kpi.redis.seed_kpi("claim_api", "cipherions", 62)

    response = await handle_stats("", stub_stores)
    assert "kpi:claim_api:percent_staked" not in response.meta.kpis_used


async def test_stats_heading_uses_token_distribution_not_round(stub_stores):
    response = await handle_stats("", stub_stores)
    heading = next(b for b in response.blocks if b.type == "heading")
    assert heading.text == "Claim Portal Stats (2025 token distribution)"
    assert "round)" not in heading.text


async def test_stats_relabels_presold_metric_to_distributed(stub_stores):
    # "Total CPX presold" -> "Total CPX distributed" ("presold"/"presale"
    # vocabulary is banned).
    stub_stores.kpi.redis.seed_kpi("claim_api", "total_cpx_presold", {"ui": "500,000,000", "raw": 500000000})
    response = await handle_stats("", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "Total CPX distributed" in labels
    assert not any("presold" in label.lower() for label in labels)


# ─────────────────────────── /publications ───────────────────────────


async def test_publications_degrades_gracefully_without_rag(stub_stores):
    assert stub_stores.rag_conn is None
    response = await handle_publications("", stub_stores)
    text = _all_text(response).lower()
    assert "unavailable" in text
    assert "ciphex.io/insights-and-publications" in _all_text(response)


# ─────────────────────────────── /contribute ───────────────────────────────


async def test_contribute_says_program_not_open(stub_stores):
    response = await handle_contribute("", stub_stores)
    text = _all_text(response)
    assert "has not opened" in text
    assert "Preparing Access" in text


async def test_contribute_lists_stage_structure_and_minimums(stub_stores):
    response = await handle_contribute("", stub_stores)
    text = _all_text(response)
    assert "30-day" in text
    assert "70,000,000 CPX" in text
    assert "1,000" in text and "2,000" in text and "3,000" in text


async def test_contribute_lists_max_contribution_default_fallback(stub_stores):
    # round-terms.new_round_max_contribution is a contract key that may not
    # exist in facts.yaml yet -- graceful fallback to the literal copy.
    response = await handle_contribute("", stub_stores)
    text = _all_text(response)
    assert "100,000 CPX" in text
    assert "round-terms.new_round_max_contribution" not in response.meta.facts_used


async def test_contribute_uses_max_contribution_fact_when_present(make_overlay_stores):
    stores = make_overlay_stores({"round-terms.new_round_max_contribution": make_fact({"cpx": 250000})})
    response = await handle_contribute("", stores)
    text = _all_text(response)
    assert "250,000 CPX" in text
    assert "round-terms.new_round_max_contribution" in response.meta.facts_used


async def test_contribute_uses_stage_structure_fact_when_present(make_overlay_stores):
    stores = make_overlay_stores(
        {"round-terms.new_round_stage_structure": make_fact("Two 45-day stages: Early and Final.")}
    )
    response = await handle_contribute("", stores)
    text = _all_text(response)
    assert "Two 45-day stages: Early and Final." in text
    assert "round-terms.new_round_stage_structure" in response.meta.facts_used


async def test_contribute_lockup_and_vesting_terms(stub_stores):
    response = await handle_contribute("", stub_stores)
    text = _all_text(response)
    assert "90-day lockup" in text
    assert "90-day vesting" in text
    # facts.yaml's round-terms.new_round_vesting_installments reads
    # "3 equal monthly installments" -- sourced from facts, not hardcoded.
    assert "equal monthly installments" in text
    assert "round-terms.new_round_vesting_installments" in response.meta.facts_used


async def test_contribute_vesting_installments_fallback_when_unknown(make_overlay_stores):
    stores = make_overlay_stores({"round-terms.new_round_vesting_installments": None})
    response = await handle_contribute("", stores)
    text = _all_text(response)
    assert "three equal monthly installments" in text
    assert "round-terms.new_round_vesting_installments" not in response.meta.facts_used


async def test_contribute_has_no_dollar_figures(stub_stores):
    # Owner ruling 2026-08-17 (D-1): NO dollar figures anywhere in /contribute.
    response = await handle_contribute("", stub_stores)
    text = _all_text(response)
    assert "$" not in text
    result = guardrails.check_text(text)
    assert result.ok, result.violations


async def test_contribute_links_to_contribute_page_with_eligibility_note(stub_stores):
    response = await handle_contribute("", stub_stores)
    text = _all_text(response)
    assert "https://ciphex.io/contribute" in text
    assert "eligibility" in text.lower()
    assert "restricted" in text.lower()


# ────────────────────────────────── /contact ──────────────────────────────────


async def test_contact_lists_general_and_partnerships_emails(stub_stores):
    response = await handle_contact("", stub_stores)
    text = _all_text(response)
    assert "hello@ciphex.io" in text
    assert "partnerships@ciphex.io" in text


async def test_contact_response_sla_from_fact(stub_stores):
    response = await handle_contact("", stub_stores)
    text = _all_text(response)
    assert "72 business hours" in text
    assert "links.contact_response_sla" in response.meta.facts_used


async def test_contact_response_sla_fallback_when_unknown(make_overlay_stores):
    stores = make_overlay_stores({"links.contact_response_sla": None})
    response = await handle_contact("", stores)
    text = _all_text(response)
    assert "72 business hours" in text
    assert "links.contact_response_sla" not in response.meta.facts_used


async def test_contact_includes_telegram_link(stub_stores):
    response = await handle_contact("", stub_stores)
    links = [b for b in response.blocks if b.type == "links"][0]
    assert any("t.me" in item.url for item in links.items)


async def test_contact_warns_never_dms_first(stub_stores):
    response = await handle_contact("", stub_stores)
    text = _all_text(response).lower()
    assert "never dm you first" in text
    assert "seed phrase" in text


# ───────────────────────────────── /ecosystem ─────────────────────────────────


async def test_ecosystem_lists_all_four_products(stub_stores):
    response = await handle_ecosystem("", stub_stores)
    text = _all_text(response)
    assert "CPX Token" in text
    assert "Ciphex Alpha" in text
    assert "Atlas RWA Services" in text
    assert "Ciphex Connect" in text


async def test_ecosystem_default_links_fall_back_gracefully(stub_stores):
    # None of the four link contract keys exist in facts.yaml yet --
    # every link must still resolve to a sane literal fallback.
    response = await handle_ecosystem("", stub_stores)
    links = [b for b in response.blocks if b.type == "links"][0]
    urls = [item.url for item in links.items]
    assert "https://ciphex.io/ciphex-token" in urls
    assert "https://ams.ciphex.io" in urls
    assert "https://ciphex.io/atlas-rwa-services" in urls
    assert "https://connect.ciphex.io" in urls
    assert response.meta.facts_used == []


async def test_ecosystem_uses_connect_portal_fact_when_present(make_overlay_stores):
    stores = make_overlay_stores({"links.connect_portal": make_fact("https://connect.ciphex.io/join")})
    response = await handle_ecosystem("", stores)
    links = [b for b in response.blocks if b.type == "links"][0]
    urls = [item.url for item in links.items]
    assert "https://connect.ciphex.io/join" in urls
    assert "links.connect_portal" in response.meta.facts_used


async def test_ecosystem_uses_connect_program_description_fact_when_present(make_overlay_stores):
    stores = make_overlay_stores(
        {"identity.connect_program": make_fact("a points-based loyalty and rewards program for CPX holders.")}
    )
    response = await handle_ecosystem("", stores)
    text = _all_text(response)
    assert "a points-based loyalty and rewards program for CPX holders." in text
    assert "identity.connect_program" in response.meta.facts_used


async def test_ecosystem_atlas_text_mentions_pre_commercial_and_contact(stub_stores):
    response = await handle_ecosystem("", stub_stores)
    text = _all_text(response).lower()
    assert "pre-commercial" in text
    assert "/contact" in text


# ────────────────────────────────── /supply ──────────────────────────────────


async def test_supply_command_delegates_to_qa_supply_answer(stub_stores):
    response = await handle_supply("", stub_stores)
    fact_blocks = [b for b in response.blocks if b.type == "fact"]
    labels = {b.label for b in fact_blocks}
    assert "On-chain totalSupply() (Ethereum)" in labels
    assert "Effective supply (post Burn Cycle 1)" in labels


# ───────────────────── every command passes response_guard ─────────────────────


@pytest.mark.parametrize(
    "handler",
    [
        handle_price,
        handle_ca,
        handle_claim,
        handle_audit,
        handle_stats,
        handle_publications,
        handle_contribute,
        handle_contact,
        handle_ecosystem,
        handle_supply,
    ],
)
async def test_every_command_response_passes_guard(handler, stub_stores):
    response = await handler("", stub_stores)
    result = guardrails.check_text(_all_text(response))
    assert result.ok, (handler.__name__, result.violations)
