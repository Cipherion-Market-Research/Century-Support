"""/ca -- contract addresses. Owner ruling 2026-08-17: CPX is an ERC-20
token on Ethereum mainnet ONLY. Base is never presented as a legitimate
CPX deployment -- contracts.cpx_token_base is excluded from this handler
entirely (and from Q&A search results, see Config.BLOCKED_FACT_KEYS)."""
from century_core.config import Config
from century_core.models import FactBlock, HeadingBlock, LinkItem, LinksBlock, ResponseIR, ResponseMeta, WarningBlock

_DEFAULT_EXCLUSIVITY_SENTENCE = (
    'CPX exists only on Ethereum mainnet. A "CPX" token on any other chain is not the official '
    "Ciphex token — verify the address above before interacting with anything."
)


async def handle_ca(args: str, stores) -> ResponseIR:
    blocks = [HeadingBlock(text="CPX Contract Addresses")]
    facts_used = []

    fact = stores.facts.get("contracts.cpx_token_ethereum")
    if fact is not None and not fact.is_unknown:
        value = fact.value
        blocks.append(
            FactBlock(
                label="CPX on Ethereum mainnet",
                value=f"{value['address']} ({value['chain']})",
                source=fact.source_url,
                as_of=str(fact.verified_on),
            )
        )
        facts_used.append("contracts.cpx_token_ethereum")

    if not facts_used:
        blocks.append(WarningBlock(md="I don't have a verified contract address on file right now."))
    else:
        exclusivity = stores.facts.get("contracts.cpx_chain_exclusivity")
        if exclusivity is not None and not exclusivity.is_unknown:
            exclusivity_text = str(exclusivity.value)
            facts_used.append("contracts.cpx_chain_exclusivity")
        else:
            exclusivity_text = _DEFAULT_EXCLUSIVITY_SENTENCE
        blocks.append(WarningBlock(md=exclusivity_text))

    blocks.append(LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]))

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
