"""/stats -- claim-portal metrics (C3 source `claim_api`). Per WP-1's A10
relabeling: these are claim-PORTAL metrics (cipherions = claiming wallets),
not "community members"; percent_staked and the nested `contract` metric
are deliberately excluded (percent_staked can read >100%, nonsensical as a
percentage; `contract` is a different-scale, contract-wide total, not a
per-user stat). Stale KPIs are never quoted (C3): a stale metric is
dropped from the response entirely rather than shown as if fresh.
"""
from century_core.models import FactBlock, HeadingBlock, LinkItem, LinksBlock, ResponseIR, ResponseMeta, WarningBlock

_METRICS = [
    ("cipherions", "Claiming wallets"),
    ("total_contributions", "Total funds raised"),
    ("total_cpx_presold", "Total CPX presold"),
    ("total_staked", "Total CPX staked"),
]


def _display_value(value) -> str:
    if isinstance(value, dict) and "ui" in value:
        return str(value["ui"])
    return str(value)


async def handle_stats(args: str, stores) -> ResponseIR:
    blocks = [HeadingBlock(text="Claim Portal Stats (2025 token distribution)")]
    kpis_used = []

    for metric, label in _METRICS:
        reading = await stores.kpi.read("claim_api", metric)
        if reading is None or reading.stale:
            continue
        blocks.append(
            FactBlock(
                label=label,
                value=_display_value(reading.value),
                source=reading.source_url,
                as_of=reading.fetched_at,
            )
        )
        kpis_used.append(f"kpi:claim_api:{metric}")

    if not kpis_used:
        blocks.append(
            WarningBlock(
                md="Live claim-portal stats are temporarily unavailable (feed stale or not yet "
                "populated). Check the claim portal directly for the latest numbers."
            )
        )

    portal = stores.facts.get("links.claim_portal")
    link_url = str(portal.value) if portal is not None and not portal.is_unknown else "https://ciphex.io"
    blocks.append(LinksBlock(items=[LinkItem(label="Claim portal", url=link_url)]))

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=[], kpis_used=kpis_used),
    )
