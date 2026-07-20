"""/claim -- token claiming portal."""
from century_core.models import FactBlock, HeadingBlock, LinkItem, LinksBlock, ResponseIR, ResponseMeta, WarningBlock


async def handle_claim(args: str, stores) -> ResponseIR:
    portal = stores.facts.get("links.claim_portal")

    blocks = [HeadingBlock(text="Claim Portal")]
    facts_used = []

    if portal is not None and not portal.is_unknown:
        blocks.append(
            FactBlock(
                label="Token claiming portal",
                value=str(portal.value),
                source=portal.source_url,
                as_of=str(portal.verified_on),
            )
        )
        facts_used.append("links.claim_portal")
        link_url = str(portal.value)
    else:
        link_url = "https://ciphex.io"

    blocks.append(
        WarningBlock(
            md="Only ever use the official claim portal. Never share your wallet seed phrase — "
            "Ciphex will never DM you first asking for it."
        )
    )
    blocks.append(LinksBlock(items=[LinkItem(label="Claim portal", url=link_url)]))

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
