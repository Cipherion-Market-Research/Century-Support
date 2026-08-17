"""/price -- WP-5 brief item 3, updated per owner ruling 2026-07-30: the
live ciphex.io/contribute page is the source of truth for the current
Contribution Program. Its published $0.20/CPX price
(round-terms.new_round_price_usd) is THE referenceable current-program
price and must be read from facts.yaml at runtime -- never hardcode a
number here. Quote neither the retired $0.25 staged figure nor the
deprecated on-chain reads (~$0.115-$0.124) from contracts.base_presale
(see that fact's notes: legacy staging data, never referenced for current
state) -- guardrails.py backstops this at the text level, but the handler
shouldn't rely on that alone. The Contribution Program has NOT opened --
it "begins on a date determined by Ciphex" and no start date is published
(round-terms.new_round_status / round-terms.market_expansion_timeline) --
so this handler must never say or imply the program is open, and must make
no timing promises. kpi:onchain_base:token_price is the live read of that
same deprecated on-chain figure and is deliberately never surfaced here for
the same reason.
"""
from century_core.config import Config
from century_core.models import FactBlock, HeadingBlock, LinkItem, LinksBlock, ResponseIR, ResponseMeta, WarningBlock


async def handle_price(args: str, stores) -> ResponseIR:
    legacy = stores.facts.get("round-terms.legacy_2025_price_usd")
    current_price = stores.facts.get("round-terms.new_round_price_usd")
    timeline = stores.facts.get("round-terms.market_expansion_timeline")

    blocks = [HeadingBlock(text="CPX Price")]
    facts_used = []

    if legacy is not None and not legacy.is_unknown:
        blocks.append(
            FactBlock(
                label="2025 token distribution price (concluded, historical)",
                value=f"${float(legacy.value):.2f}",
                source=legacy.source_url,
                as_of=str(legacy.verified_on),
            )
        )
        facts_used.append("round-terms.legacy_2025_price_usd")

    if current_price is not None and not current_price.is_unknown:
        blocks.append(
            FactBlock(
                label="Contribution Program price (published)",
                value=f"${float(current_price.value):.2f}/CPX",
                source=current_price.source_url,
                as_of=str(current_price.verified_on),
            )
        )
        facts_used.append("round-terms.new_round_price_usd")
        warning_text = (
            "This is the published exchange price for Ciphex's Contribution Program "
            "(token distribution) -- it is not a live market price, and CPX has no "
            "confirmed live trading pair yet. "
        )
    else:
        warning_text = "The Contribution Program's price has not been published yet. "

    warning_text += (
        "The Contribution Program has not opened, and no start date is currently "
        "published. "
    )
    if timeline is not None and not timeline.is_unknown:
        warning_text += str(timeline.value) + " "
        facts_used.append("round-terms.market_expansion_timeline")

    blocks.append(WarningBlock(md=warning_text.strip()))
    blocks.append(LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]))

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
