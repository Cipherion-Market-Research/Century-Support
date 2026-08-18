"""Deterministic handling for total-supply questions (WP-5 brief item 4):
answers must distinguish on-chain totalSupply (1.5B, unchanged since Burn
Cycle 1 was a transfer to a dead address, not a supply-reducing call) from
effective/circulating supply (1,018,545,702 = totalSupply - burn-address
balance). Prefers live kpi:onchain_eth:total_supply / kpi:onchain:*
readings over the static facts.yaml snapshot when fresh, falling back to
facts.yaml when the KPI feed is missing or stale (see
tokenomics.onchain_total_supply_eth / tokenomics.fy2026_fd_supply and
their notes in facts.yaml for the full reconciliation history).

Handled as its own deterministic path rather than left to the generic
keyword+LLM Q&A route because this exact on-chain-vs-effective distinction
is the one topic the WP-5 brief calls out by name as easy to get wrong.

Also triggers on burn phrasing ("burn", "burned", "how many tokens were
burned") -- Burn Cycle 1 is exactly the on-chain-vs-effective-supply
distinction this module explains, so a burn question should get the same
grounded, deterministic answer rather than a free-form LLM one.
"""
import re

from century_core.models import FactBlock, HeadingBlock, ParagraphBlock, ResponseIR, ResponseMeta

_SUPPLY_TRIGGERS = {"supply", "circulating", "totalsupply", "outstanding", "burned", "burn", "burns"}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def is_supply_question(query: str) -> bool:
    tokens = set(_TOKEN_RE.findall(query.lower()))
    return bool(tokens & _SUPPLY_TRIGGERS)


def _numeric(value) -> float:
    return value.get("cpx") if isinstance(value, dict) else value


async def answer_supply_question(stores) -> ResponseIR:
    kpis_used = []
    facts_used = []
    blocks = [HeadingBlock(text="CPX Supply")]

    total_supply = await stores.kpi.read("onchain_eth", "total_supply")
    if total_supply is not None and not total_supply.stale:
        blocks.append(
            FactBlock(
                label="On-chain totalSupply() (Ethereum)",
                value=f"{_numeric(total_supply.value):,.0f} CPX",
                source=total_supply.source_url,
                as_of=total_supply.fetched_at,
            )
        )
        kpis_used.append("kpi:onchain_eth:total_supply")
    else:
        fact = stores.facts.get("tokenomics.onchain_total_supply_eth")
        if fact is not None and not fact.is_unknown:
            blocks.append(
                FactBlock(
                    label="On-chain totalSupply() (Ethereum)",
                    value=f"{fact.value:,} CPX",
                    source=fact.source_url,
                    as_of=str(fact.verified_on),
                )
            )
            facts_used.append("tokenomics.onchain_total_supply_eth")

    effective_supply = await stores.kpi.read("onchain", "effective_supply_cpx")
    if effective_supply is not None and not effective_supply.stale:
        blocks.append(
            FactBlock(
                label="Effective supply (post Burn Cycle 1)",
                value=f"{_numeric(effective_supply.value):,.0f} CPX",
                source=effective_supply.source_url,
                as_of=effective_supply.fetched_at,
            )
        )
        kpis_used.append("kpi:onchain:effective_supply_cpx")
    else:
        fact = stores.facts.get("tokenomics.fy2026_fd_supply")
        if fact is not None and not fact.is_unknown:
            blocks.append(
                FactBlock(
                    label="Effective supply (post Burn Cycle 1)",
                    value=f"{fact.value:,} CPX",
                    source=fact.source_url,
                    as_of=str(fact.verified_on),
                )
            )
            facts_used.append("tokenomics.fy2026_fd_supply")

    blocks.append(
        ParagraphBlock(
            md="Both figures are correct. Burn Cycle 1 permanently removed CPX by sending it to "
            "an inaccessible burn address, so Etherscan's raw `totalSupply()` still includes those "
            "tokens. Effective supply subtracts the burn address balance and matches Ciphex's "
            "published fully-diluted supply. (Effective supply is not circulating supply -- a "
            "portion remains subject to lockup and vesting.)"
        )
    )

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="faq", facts_used=facts_used, kpis_used=kpis_used),
    )
