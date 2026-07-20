"""Command handlers exercised against the REAL facts.yaml (it's the actual
seed store WP-5 must answer from — see docs/CONTRACTS.md C4) with a fake
Redis for KPI-backed commands. This is the "all §2 critical topics answer
correctly against seeded stores" acceptance line for the command surface.
"""
from century_core import guardrails
from century_core.commands.audit import handle_audit
from century_core.commands.ca import handle_ca
from century_core.commands.claim import handle_claim
from century_core.commands.price import handle_price
from century_core.commands.publications import handle_publications
from century_core.commands.stats import handle_stats


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


async def test_price_quotes_legacy_historical_price(stub_stores):
    response = await handle_price("", stub_stores)
    text = _all_text(response)
    assert "0.26" in text
    assert "round-terms.legacy_2025_price_usd" in response.meta.facts_used


async def test_price_never_quotes_banned_new_round_figures(stub_stores):
    response = await handle_price("", stub_stores)
    result = guardrails.check_text(_all_text(response))
    assert result.ok, result.violations


async def test_price_says_terms_not_final(stub_stores):
    response = await handle_price("", stub_stores)
    text = _all_text(response).lower()
    assert "not been finalized" in text or "not finalized" in text


# ──────────────────────────────── /ca ────────────────────────────────


async def test_ca_lists_both_chains(stub_stores):
    response = await handle_ca("", stub_stores)
    text = _all_text(response)
    assert "0x18b33687d1c804Dd4ea6c82106e54923c23a652E" in text  # Ethereum
    assert "0x7A8Fc21fd34DE3dD5131a965fb3995f484f50D59" in text  # Base
    assert "contracts.cpx_token_ethereum" in response.meta.facts_used
    assert "contracts.cpx_token_base" in response.meta.facts_used


async def test_ca_includes_scam_safety_warning(stub_stores):
    response = await handle_ca("", stub_stores)
    warning_blocks = [b for b in response.blocks if b.type == "warning"]
    assert warning_blocks
    assert "not by itself evidence of a scam" in warning_blocks[0].md


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


# ─────────────────────────── /publications ───────────────────────────


async def test_publications_degrades_gracefully_without_rag(stub_stores):
    assert stub_stores.rag_conn is None
    response = await handle_publications("", stub_stores)
    text = _all_text(response).lower()
    assert "unavailable" in text
    assert "ciphex.io/ecosystem-publications" in _all_text(response)
