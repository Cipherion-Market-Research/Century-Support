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


def test_does_not_flag_fee_percentage_0_25_percent():
    # "0.25%" is a fee-schedule percentage (data/llm_composite.md,
    # data/training/faq.json: "fees range from 0.25% to 0.03%"), not a
    # price quote -- must not be caught by the banned-price patterns.
    result = guardrails.check_text("Fees range from 0.25% to 0.03% depending on tier.")
    assert result.ok, result.violations


def test_does_not_flag_fee_percentage_with_dollar_sign_style_spacing():
    result = guardrails.check_text("The maker fee is 0.25 % of the trade.")
    assert result.ok, result.violations


def test_still_flags_bare_0_25_per_cpx():
    result = guardrails.check_text("0.25 per CPX is the going rate.")
    assert not result.ok


def test_still_flags_price_is_0_25():
    result = guardrails.check_text("The price is 0.25 for the new round.")
    assert not result.ok


def test_still_flags_dollar_0_25_alongside_percent_elsewhere():
    # A genuine price quote must still be caught even in a message that
    # also contains an unrelated legitimate percentage.
    result = guardrails.check_text("Fees are 0.25% but the token is $0.25.")
    assert not result.ok


def test_flags_dollar_0_20():
    # Owner ruling 2026-08-17: CPX has no market price to quote -- $0.20
    # (the formerly-referenced contribute-page figure) is now banned too.
    result = guardrails.check_text("CPX is priced at $0.20 per token.")
    assert not result.ok
    assert any("price" in v for v in result.violations)


def test_flags_bare_0_20():
    result = guardrails.check_text("0.20 per CPX is the going rate.")
    assert not result.ok


def test_does_not_flag_0_20_percent():
    result = guardrails.check_text("The fee is 0.20% of the trade.")
    assert result.ok, result.violations


def test_does_not_false_positive_on_70_million_cpx():
    result = guardrails.check_text("The Contribution Program totals 70,000,000 CPX across three stages.")
    assert result.ok, result.violations


def test_does_not_false_positive_on_dollar_20000():
    result = guardrails.check_text("The Stage 3 minimum is worth $20,000 at some hypothetical valuation.")
    assert result.ok, result.violations


def test_does_not_false_positive_on_dollar_200():
    result = guardrails.check_text("The Stage 1 minimum works out to $200.")
    assert result.ok, result.violations


def test_does_not_false_positive_on_a_date():
    result = guardrails.check_text("The kb_source harvest was taken on 2026-07-20.")
    assert result.ok, result.violations


def test_does_not_false_positive_on_effective_supply_figure():
    result = guardrails.check_text("Effective supply after Burn Cycle 1 is 1,018,545,702 CPX.")
    assert result.ok, result.violations


# ────────────────────────── banned-term ("presale") ban ──────────────────────────


def test_flags_presale_inside_legacy_redirect_url():
    # Owner ruling 2026-08-17: "presale" is banned with NO exemptions --
    # not even inside a URL/hostname. facts.yaml's
    # links.claim_portal_legacy_redirect literal value must never reach a
    # user; it is excluded from Q&A search entirely (Config.BLOCKED_FACT_KEYS)
    # and this ban is the text-level backstop.
    result = guardrails.check_text(
        "The old link https://presale.ciphex.io now redirects to claim.ciphex.io."
    )
    assert not result.ok
    assert any("terminology" in v for v in result.violations)


def test_flags_presale_inside_api_path():
    # Owner ruling 2026-08-17: no exemptions, even inside a path segment.
    result = guardrails.check_text("The claim portal exposes a public JSON feed at /api/presale.")
    assert not result.ok
    assert any("terminology" in v for v in result.violations)


def test_flags_standalone_presale_in_prose():
    result = guardrails.check_text("Is the presale open yet?")
    assert not result.ok
    assert any("terminology" in v for v in result.violations)


def test_flags_standalone_pre_sale_hyphenated():
    result = guardrails.check_text("The pre-sale hasn't started.")
    assert not result.ok


def test_flags_standalone_presales_plural():
    result = guardrails.check_text("We don't run presales here.")
    assert not result.ok


def test_flags_capitalized_pre_sale():
    result = guardrails.check_text("Join our Pre-Sale today!")
    assert not result.ok


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
