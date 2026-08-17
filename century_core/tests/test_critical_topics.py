"""WP-5 acceptance: "all §2 critical topics answer correctly against
seeded stores." Spot-checks the audit's drift-matrix topics directly
against the real, committed facts.yaml (not a fixture) -- this is the
actual seed store the service ships with.
"""
from facts_store import default_store

from century_core import guardrails
from century_core.commands.ca import handle_ca
from century_core.commands.claim import handle_claim
from century_core.commands.price import handle_price
from century_core.qa.router import answer_question
from century_core.tests.test_commands import _all_text


def test_whitepaper_confirmed_not_published():
    store = default_store()
    fact = store.get("links.whitepaper")
    assert fact is not None and not fact.is_unknown
    assert "no whitepaper" in fact.value.lower() or "none" in fact.value.lower()


def test_support_email_oq1_resolved():
    store = default_store()
    fact = store.get("identity.support_email")
    assert fact is not None and not fact.is_unknown
    assert fact.value == "support@ciphex.io"


def test_burn_cycle_1_figures_correct():
    store = default_store()
    amount = store.get("tokenomics.burn_cycle_1_amount_cpx")
    percent = store.get("tokenomics.burn_cycle_1_percent")
    assert amount.value == 481454298
    assert "32.10" in percent.value


def test_burn_cycle_1_reconciles_max_supply_to_fd_supply():
    store = default_store()
    max_supply = store.get("tokenomics.max_supply_cpx").value
    burned = store.get("tokenomics.burn_cycle_1_amount_cpx").value
    fd_supply = store.get("tokenomics.fy2026_fd_supply").value
    assert max_supply - burned == fd_supply == 1018545702


def test_stale_95_percent_burn_figure_is_not_present_anywhere():
    # The audit flagged the OLD bot's "95% burn over a decade" as a 10x
    # overstatement (correct figure: ~50% by EYE2030). Make sure that
    # stale figure never appears in facts.yaml.
    store = default_store()
    for key in store.keys():
        fact = store.get(key)
        assert "95%" not in str(fact.value)


async def test_dex_not_live_oq3_resolved():
    store = default_store()
    fact = store.get("identity.dex_live_status")
    assert fact is not None and not fact.is_unknown
    assert "not live" in fact.value.lower()


async def test_price_command_never_leaks_any_price_figure(stub_stores):
    # Owner ruling 2026-08-17: CPX has no market price to quote -- no price
    # figure of any kind, current or historical, is ever output.
    response = await handle_price("", stub_stores)
    result = guardrails.check_text(_all_text(response))
    assert result.ok, result.violations
    text = _all_text(response)
    assert "$" not in text
    assert "TBD" in text


async def test_claim_portal_topic(stub_stores):
    response = await handle_claim("", stub_stores)
    assert "claim.ciphex.io" in _all_text(response)


async def test_contract_address_topic_is_ethereum_only(stub_stores):
    # Owner ruling 2026-08-17: CPX is ERC-20 on Ethereum mainnet only --
    # Base is never presented as a legitimate deployment.
    response = await handle_ca("", stub_stores)
    text = _all_text(response)
    assert "Ethereum" in text
    assert "Base" not in text


async def test_qa_price_question_routes_to_deterministic_price_command_not_llm(stub_stores):
    # Owner ruling 2026-08-17: price questions are intercepted by the
    # price-intent detector and answered deterministically -- the LLM is
    # never even called, so it can never leak a banned figure here. Even
    # a query using banned "presale" vocabulary must never echo it back.
    stub_stores.llm._response = "The new round is priced at $0.25/CPX."
    response = await answer_question("what is the price of the new presale round?", stub_stores)
    assert response.meta.answer_kind == "command"
    text_parts = []
    for block in response.blocks:
        if block.type == "paragraph":
            text_parts.append(block.md)
    result = guardrails.check_text(" ".join(text_parts))
    assert result.ok, result.violations


async def test_qa_llm_leaking_price_on_a_non_price_question_is_blocked(stub_stores):
    # A question that does NOT hit the price-intent detector, where the LLM
    # invents a banned price figure anyway -- guardrails must still catch it.
    stub_stores.llm._response = "By the way, the token is priced at $0.25/CPX."
    response = await answer_question("where can I claim my tokens?", stub_stores)
    assert response.meta.answer_kind == "refusal"
