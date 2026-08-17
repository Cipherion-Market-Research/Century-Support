"""/price -- owner ruling 2026-08-17: CPX is not listed on any exchange and
has no market price to quote. The bot must NEVER output a CPX price figure
in any form -- $0.25, $0.115, $0.124, and the previously-referenced $0.20
contribute-page figure are all banned (guardrails.py backstops this at the
text level, but this handler shouldn't rely on that alone: it never reads
or renders round-terms.new_round_price_usd, which is itself excluded from
Q&A search results -- see Config.BLOCKED_FACT_KEYS). Price is TBD: not
listed; the roadmap includes a DEX/CEX listing initiative for later in
2026, with an announcement expected Q3/Q4 2026. The Contribution Program
(see /contribute) has separately not opened and carries no dollar figures
of its own.
"""
from century_core.config import Config
from century_core.models import HeadingBlock, LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta

_DEFAULT_LISTING_SENTENCE = (
    "Ciphex's roadmap includes a DEX/CEX listing initiative for later in 2026, with an "
    "announcement expected Q3/Q4 2026."
)
_TOKEN_PAGE_FALLBACK_URL = "https://ciphex.io/ciphex-token"


async def handle_price(args: str, stores) -> ResponseIR:
    facts_used = []

    listing = stores.facts.get("identity.listing_initiative")
    if listing is not None and not listing.is_unknown:
        listing_sentence = str(listing.value)
        facts_used.append("identity.listing_initiative")
    else:
        listing_sentence = _DEFAULT_LISTING_SENTENCE

    token_page = stores.facts.get("links.token_page")
    if token_page is not None and not token_page.is_unknown:
        token_page_url = str(token_page.value)
        facts_used.append("links.token_page")
    else:
        token_page_url = _TOKEN_PAGE_FALLBACK_URL

    blocks = [
        HeadingBlock(text="CPX Price"),
        ParagraphBlock(
            md="CPX is not yet listed on an exchange — there is no market price to quote (TBD)."
        ),
        ParagraphBlock(
            md=f"{listing_sentence} Once CPX is listed, live pricing will be connected here from a "
            "market data feed."
        ),
        ParagraphBlock(md="The Contribution Program has not opened; see /contribute."),
        LinksBlock(
            items=[
                LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL),
                LinkItem(label="CPX Token", url=token_page_url),
            ]
        ),
    ]

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
