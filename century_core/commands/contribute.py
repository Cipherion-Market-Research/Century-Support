"""/contribute -- Ciphex Contribution Program (Phase I) status. Owner
ruling 2026-08-17 (D-1): NO dollar figures anywhere in this response --
only CPX-denominated figures. round-terms.new_round_price_usd is a banned
CPX price figure and is never read here (see Config.BLOCKED_FACT_KEYS).

round-terms.new_round_max_contribution and round-terms.new_round_stage_structure
are contract keys that may not exist in facts.yaml yet -- every read below
goes through the standard stores.facts.get(...) + is_unknown graceful
fallback so this handler works whether or not they're present.
"""
import re

from century_core.commands._related import related_footer
from century_core.models import (
    HeadingBlock,
    LinkItem,
    LinksBlock,
    ParagraphBlock,
    ResponseIR,
    ResponseMeta,
)

_CONTRIBUTE_URL = "https://ciphex.io/contribute"

_DEFAULT_STATUS_SENTENCE = (
    'The Contribution Program has not opened. The contribution panel currently shows "Preparing '
    "Access\" — the program begins on a date determined by Ciphex, and no start date is currently "
    "published."
)
_DEFAULT_STAGE_SENTENCE = (
    "There are three 30-day stages — Early, Growth, and Final — for a total of 70,000,000 CPX."
)
_DEFAULT_TIER_MINIMUMS = [1000, 2000, 3000]
_DEFAULT_MAX_CONTRIBUTION_CPX = 100000
_DEFAULT_LOCKUP_DAYS = 90
_DEFAULT_VESTING_DAYS = 90
_DEFAULT_VESTING_INSTALLMENTS = "three equal monthly installments"


def _format_tier_minimums(values) -> str:
    return " / ".join(f"{int(v):,}" for v in values) + " CPX"


def _numeric_cpx(value) -> int:
    if isinstance(value, dict):
        value = value.get("cpx")
    if isinstance(value, (int, float)):
        return int(value)
    # Descriptive fact values (e.g. "100,000 CPX or the equivalent exchange
    # value of ...") carry a dollar figure that must never render here (owner
    # ruling D-1) -- extract only the leading CPX amount.
    match = re.match(r"\s*([\d,]+)(?=\s*CPX\b|\s*$)", str(value))
    if match is None:
        raise ValueError(f"no CPX figure in {value!r}")
    return int(match.group(1).replace(",", ""))


async def handle_contribute(args: str, stores) -> ResponseIR:
    facts_used = []

    status = stores.facts.get("round-terms.new_round_status")
    if status is not None and not status.is_unknown:
        facts_used.append("round-terms.new_round_status")
    status_sentence = _DEFAULT_STATUS_SENTENCE

    stage_structure = stores.facts.get("round-terms.new_round_stage_structure")
    if stage_structure is not None and not stage_structure.is_unknown:
        stage_sentence = str(stage_structure.value)
        facts_used.append("round-terms.new_round_stage_structure")
    else:
        stage_sentence = _DEFAULT_STAGE_SENTENCE

    tier_minimums = stores.facts.get("round-terms.new_round_tier_minimums_cpx")
    if tier_minimums is not None and not tier_minimums.is_unknown:
        tier_text = _format_tier_minimums(tier_minimums.value)
        facts_used.append("round-terms.new_round_tier_minimums_cpx")
    else:
        tier_text = _format_tier_minimums(_DEFAULT_TIER_MINIMUMS)

    max_contribution = stores.facts.get("round-terms.new_round_max_contribution")
    if max_contribution is not None and not max_contribution.is_unknown:
        max_text = f"{_numeric_cpx(max_contribution.value):,} CPX"
        facts_used.append("round-terms.new_round_max_contribution")
    else:
        max_text = f"{_DEFAULT_MAX_CONTRIBUTION_CPX:,} CPX"

    lockup = stores.facts.get("round-terms.new_round_lockup_days")
    if lockup is not None and not lockup.is_unknown:
        lockup_days = lockup.value
        facts_used.append("round-terms.new_round_lockup_days")
    else:
        lockup_days = _DEFAULT_LOCKUP_DAYS

    vesting = stores.facts.get("round-terms.new_round_vesting_days")
    if vesting is not None and not vesting.is_unknown:
        vesting_days = vesting.value
        facts_used.append("round-terms.new_round_vesting_days")
    else:
        vesting_days = _DEFAULT_VESTING_DAYS

    installments = stores.facts.get("round-terms.new_round_vesting_installments")
    if installments is not None and not installments.is_unknown:
        installments_text = str(installments.value)
        facts_used.append("round-terms.new_round_vesting_installments")
    else:
        installments_text = _DEFAULT_VESTING_INSTALLMENTS

    blocks = [
        HeadingBlock(text="Ciphex Contribution Program (Phase I)"),
        ParagraphBlock(md=status_sentence),
        ParagraphBlock(md=stage_sentence),
        ParagraphBlock(md=f"Stage minimums (Early / Growth / Final): {tier_text}."),
        ParagraphBlock(md=f"Maximum single contribution: {max_text}."),
        ParagraphBlock(
            md=f"A {lockup_days}-day lockup applies, followed by a {vesting_days}-day vesting "
            f"period released in {installments_text}."
        ),
        ParagraphBlock(
            md="See the full terms and eligibility (some jurisdictions are restricted) at the link below."
        ),
        LinksBlock(items=[LinkItem(label="Contribution Program", url=_CONTRIBUTE_URL)]),
        related_footer(("claim", "claiming portal"), ("price", "price info")),
    ]

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
