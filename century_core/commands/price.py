"""/price -- WP-5 brief item 3: 2025 round concluded ($0.26, historical);
a smaller market-expansion round is expected to complete in the coming
weeks, then a DEX listing; the new round's price/terms are not final.
Quote NEITHER $0.25 (staged copy) nor $0.115 (on-chain read) — see
round-terms.new_round_price_usd's note in facts.yaml for the full
reconciliation history. kpi:onchain_base:token_price is the live read of
that same unreconciled ~$0.115 figure and is deliberately never surfaced
here for the same reason (guardrails.py also backstops this at the text
level, but the handler shouldn't rely on that alone).
"""
from century_core.config import Config
from century_core.models import FactBlock, HeadingBlock, LinkItem, LinksBlock, ResponseIR, ResponseMeta, WarningBlock


async def handle_price(args: str, stores) -> ResponseIR:
    legacy = stores.facts.get("round-terms.legacy_2025_price_usd")
    timeline = stores.facts.get("round-terms.market_expansion_timeline")

    blocks = [HeadingBlock(text="CPX Price")]
    facts_used = []

    if legacy is not None and not legacy.is_unknown:
        blocks.append(
            FactBlock(
                label="2025 contribution round price (concluded, historical)",
                value=f"${float(legacy.value):.2f}",
                source=legacy.source_url,
                as_of=str(legacy.verified_on),
            )
        )
        facts_used.append("round-terms.legacy_2025_price_usd")

    warning_text = "The new market-expansion round's price has not been finalized or published. "
    if timeline is not None and not timeline.is_unknown:
        warning_text += str(timeline.value) + " "
        facts_used.append("round-terms.market_expansion_timeline")
    warning_text += "This is not a live market price and CPX has no confirmed live trading pair yet."
    blocks.append(WarningBlock(md=warning_text))

    blocks.append(LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]))

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
