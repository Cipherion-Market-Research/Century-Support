"""/ca -- contract addresses. Both Ethereum and Base deployments are
legitimate (contracts.cpx_token_base's note: "a second, LEGITIMATE CPX
deployment... a user citing this Base address is not necessarily
describing a scam" -- the pre-fix bot had a false-positive risk here)."""
from century_core.config import Config
from century_core.models import FactBlock, HeadingBlock, LinkItem, LinksBlock, ResponseIR, ResponseMeta, WarningBlock

_CONTRACT_FACTS = [
    ("contracts.cpx_token_ethereum", "CPX on Ethereum mainnet"),
    ("contracts.cpx_token_base", "CPX on Base (new round)"),
]


async def handle_ca(args: str, stores) -> ResponseIR:
    blocks = [HeadingBlock(text="CPX Contract Addresses")]
    facts_used = []

    for key, label in _CONTRACT_FACTS:
        fact = stores.facts.get(key)
        if fact is None or fact.is_unknown:
            continue
        value = fact.value
        blocks.append(
            FactBlock(
                label=label,
                value=f"{value['address']} ({value['chain']})",
                source=fact.source_url,
                as_of=str(fact.verified_on),
            )
        )
        facts_used.append(key)

    if not facts_used:
        blocks.append(WarningBlock(md="I don't have a verified contract address on file right now."))
    else:
        blocks.append(
            WarningBlock(
                md="Both addresses above are legitimate Ciphex deployments on different chains — "
                "a Base-chain address is not by itself evidence of a scam. Always verify against "
                "the official site before sending funds anywhere."
            )
        )

    blocks.append(LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]))

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
