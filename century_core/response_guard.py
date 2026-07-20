"""Final guardrail gate applied to every ResponseIR right before it leaves
/v1/messages -- the single choke point, so a violation is caught
regardless of whether it originated in a command template or LLM output.

Structural checks only (solicitation/APY/price-ban) -- numeric-provenance
checking needs the actual LLM-context pairing to avoid false positives on
incidental digits in link labels (e.g. a fact key like
"legacy_2025_vesting_months"), so that check runs in qa/router.py directly
against the raw LLM output before this gate ever sees it.
"""
from century_core import guardrails
from century_core.config import Config
from century_core.models import LinkItem, LinksBlock, ResponseIR, ResponseMeta, WarningBlock


def _extract_text(response: ResponseIR) -> str:
    parts = []
    for block in response.blocks:
        if block.type == "heading":
            parts.append(block.text)
        elif block.type in ("paragraph", "warning"):
            parts.append(block.md)
        elif block.type == "fact":
            parts.append(f"{block.label} {block.value}")
        elif block.type in ("links", "buttons"):
            parts.extend(item.label for item in block.items)
    return "\n".join(parts)


def safe_refusal() -> ResponseIR:
    return ResponseIR(
        blocks=[
            WarningBlock(md="I can't confirm that yet — please check the official site instead."),
            LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]),
        ],
        meta=ResponseMeta(answer_kind="refusal", facts_used=[], kpis_used=[]),
    )


def enforce_response(response: ResponseIR) -> ResponseIR:
    text = _extract_text(response)
    result = guardrails.check_text(text)
    if not result.ok:
        return safe_refusal()
    return response
