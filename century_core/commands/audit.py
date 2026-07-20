"""/audit -- CertiK Skynet audit status. Link only, never scrape or
re-derive a score (tokenomics.audit_status's note: CertiK Skynet 403s
plain HTTP clients and the site's own display is a hardcoded fallback)."""
from century_core.models import FactBlock, HeadingBlock, LinkItem, LinksBlock, ResponseIR, ResponseMeta


async def handle_audit(args: str, stores) -> ResponseIR:
    status = stores.facts.get("tokenomics.audit_status")
    skynet = stores.facts.get("links.certik_skynet")

    blocks = [HeadingBlock(text="Security Audit")]
    facts_used = []

    if status is not None and not status.is_unknown:
        blocks.append(
            FactBlock(
                label="CertiK Skynet audit status",
                value=str(status.value),
                source=status.source_url,
                as_of=str(status.verified_on),
            )
        )
        facts_used.append("tokenomics.audit_status")

    link_url = "https://ciphex.io"
    if skynet is not None and not skynet.is_unknown:
        link_url = str(skynet.value)
        facts_used.append("links.certik_skynet")

    blocks.append(LinksBlock(items=[LinkItem(label="CertiK Skynet", url=link_url)]))

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
