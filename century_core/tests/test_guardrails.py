from century_core import guardrails


# ─────────────────────────── solicitation ban ───────────────────────────


def test_flags_solicitation_language():
    result = guardrails.check_text("You should buy CPX now, it's a great time to invest!")
    assert not result.ok
    assert any("solicitation" in v for v in result.violations)


def test_flags_guaranteed_returns_claim():
    result = guardrails.check_text("This offers guaranteed returns for early participants.")
    assert not result.ok


def test_clean_factual_text_passes():
    result = guardrails.check_text("CPX is an ERC-20 token deployed on Ethereum mainnet.")
    assert result.ok


# ────────────────────────────── APY ban ──────────────────────────────


def test_flags_invented_apy_claim():
    result = guardrails.check_text("Stakers can earn 12% APY on their CPX.")
    assert not result.ok
    assert any("APY" in v for v in result.violations)


def test_flags_invented_yield_claim():
    result = guardrails.check_text("This produces a yield of 8.5% annually.")
    assert not result.ok


def test_does_not_flag_unrelated_percent():
    result = guardrails.check_text("The allocation is 35.38% CPX Reserves.")
    assert result.ok


# ────────────────────── new-round price-quoting ban ──────────────────────


def test_flags_bare_0_25():
    result = guardrails.check_text("The new round is priced at 0.25 per CPX.")
    assert not result.ok
    assert any("price" in v for v in result.violations)


def test_flags_dollar_0_25():
    result = guardrails.check_text("New round price: $0.25/CPX.")
    assert not result.ok


def test_flags_0_115():
    result = guardrails.check_text("On-chain reads show ~$0.115/CPX for the new round.")
    assert not result.ok


def test_does_not_flag_legacy_026_price():
    result = guardrails.check_text("The concluded 2025 round price was $0.26.")
    assert result.ok


def test_does_not_false_positive_on_unrelated_larger_number():
    # "$1.025" contains the substring "0.25" -- must not false-positive.
    result = guardrails.check_text("The total raised was $1.025 million.")
    assert result.ok


def test_does_not_false_positive_on_0_2501():
    result = guardrails.check_text("A ratio of 0.2501 was observed.")
    assert result.ok


# ───────────────────────── numeric provenance ─────────────────────────


def test_numeric_provenance_passes_when_number_in_context():
    result = guardrails.check_numeric_provenance(
        "The max supply is 1500000000 CPX.", allowed_numbers={"1500000000"}
    )
    assert result.ok


def test_numeric_provenance_flags_unsourced_number():
    result = guardrails.check_numeric_provenance(
        "The max supply is 999999999 CPX.", allowed_numbers={"1500000000"}
    )
    assert not result.ok
    assert any("999999999" in v for v in result.violations)


def test_numeric_provenance_handles_formatted_numbers():
    result = guardrails.check_numeric_provenance(
        "That's about 1,500,000,000 CPX.", allowed_numbers={1500000000}
    )
    assert result.ok


def test_extract_numbers_normalizes_commas_and_dollar_signs():
    assert guardrails.extract_numbers("$1,018,545,702 effective supply") == {"1018545702"}


# ──────────────────────────── enforce() combo ────────────────────────────


def test_enforce_runs_both_checks():
    result = guardrails.enforce(
        "You should buy now! Price is 0.25 and an invented 42 CPX bonus.",
        allowed_numbers={"0.26"},
    )
    assert not result.ok
    joined = " ".join(result.violations)
    assert "solicitation" in joined
    assert "price" in joined
    assert "42" in joined


def test_enforce_clean_response_with_context_passes():
    result = guardrails.enforce(
        "The concluded 2025 round price was $0.26.",
        allowed_numbers={"0.26", "2025"},
    )
    assert result.ok


def test_enforce_skips_provenance_check_when_no_context_given():
    # No allowed_numbers supplied (e.g. template-built command responses) --
    # only the structural checks run.
    result = guardrails.enforce("The max supply is 1500000000 CPX.")
    assert result.ok
