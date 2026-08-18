"""Final guardrail gate applied to every ResponseIR right before it leaves
/v1/messages -- the single choke point, so a violation is caught
regardless of whether it originated in a command template or LLM output.

Structural checks only (solicitation/APY/price-ban) -- numeric-provenance
checking needs the actual LLM-context pairing to avoid false positives on
incidental digits in link labels (e.g. a fact key like
"legacy_2025_vesting_months"), so that check runs in qa/router.py directly
against the raw LLM output before this gate ever sees it.
"""
import logging
import re

from century_core import guardrails
from century_core.config import Config
from century_core.models import LinkItem, LinksBlock, ResponseIR, ResponseMeta, WarningBlock

logger = logging.getLogger(__name__)

# Go-live incident 2026-08-17: a RAG chunk pulled from an older PDF echoed
# the brand's pre-2026-07-29 spelling ("CipheX Alpha Network") straight
# into an LLM-composed answer. The live site and current copy have
# standardized on "Ciphex" (see facts.yaml identity.brand_name notes) --
# every casing/typo variant of the brand word gets normalized on the way
# out, regardless of which layer (facts.yaml, a publication chunk, the LLM)
# it came from.
#
# Two patterns:
#   - any case variant of the correct 6-letter spelling "Ciphex" (CipheX,
#     CIPHEX, ciphex, ...) -- normalizing "Ciphex" -> "Ciphex" is a no-op.
#   - "CipherX"/"Cipher-X" (7 letters, an extra "r") -- a variant spelling
#     that showed up in older internal text.
# Neither pattern can ever match "Cipherion" (the real legal entity name,
# facts.yaml identity.legal_entity: "Cipherion Capital SA") -- "Cipherion"
# has "cipheri..." where these patterns need a literal "x" (pattern 1) or
# "-x"/"x" immediately after "cipher" (pattern 2), so it never matches and
# is never rewritten.
_BRAND_CANONICAL = "Ciphex"
_BRAND_PATTERNS = [
    re.compile(r"\bciphex\b", re.IGNORECASE),
    re.compile(r"\bcipher-?x\b", re.IGNORECASE),
]


def _normalize_token_brand(token: str) -> str:
    # Never touch a token that looks like a URL or email address -- a raw
    # link or address pasted inline in prose must not be rewritten even if
    # it happens to contain a brand-spelling substring (e.g. a URL path
    # segment).
    if "://" in token or "@" in token:
        return token
    result = token
    for pattern in _BRAND_PATTERNS:
        result = pattern.sub(_BRAND_CANONICAL, result)
    return result


# The "(url)" half of a markdown link "[label](url)" -- protected wholesale
# (not just token-skipped) since a URL may contain no whitespace at all and
# would otherwise be swept up as a single "token" that still gets scanned;
# protecting it explicitly is the belt to the token-level check's braces.
_MD_LINK_URL_RE = re.compile(r"\]\(([^)]*)\)")


def normalize_brand_text(text: str) -> str:
    """Rewrite legacy brand-spelling variants to the canonical "Ciphex" in
    free text/markdown, without touching URLs, email addresses, or
    "Cipherion" (the real legal entity name). Safe to call on any
    text/md field; safe to call twice (idempotent)."""
    if not text:
        return text

    protected: list[str] = []

    def _protect(match: "re.Match[str]") -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    working = _MD_LINK_URL_RE.sub(_protect, text)
    working = re.sub(r"\S+", lambda m: _normalize_token_brand(m.group(0)), working)
    for i, original in enumerate(protected):
        working = working.replace(f"\x00{i}\x00", original)
    return working


def _normalize_block_brand(block):
    if block.type == "heading":
        return block.model_copy(update={"text": normalize_brand_text(block.text)})
    if block.type in ("paragraph", "warning"):
        return block.model_copy(update={"md": normalize_brand_text(block.md)})
    if block.type == "fact":
        # .source is a URL field (like LinkItem.url below) -- never touched.
        return block.model_copy(
            update={
                "label": normalize_brand_text(block.label),
                "value": normalize_brand_text(block.value),
            }
        )
    if block.type in ("links", "buttons"):
        return block.model_copy(
            update={
                "items": [
                    item.model_copy(update={"label": normalize_brand_text(item.label)})
                    for item in block.items
                ]
            }
        )
    return block


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


def _url_allowed(url: str) -> bool:
    return url.startswith(Config.ALLOWED_LINK_PREFIXES)


def _filter_links_block(block):
    """Drop any LinkItem whose url isn't on the allowlist (production
    audit, 2026-08-18 -- see Config.ALLOWED_LINK_PREFIXES). Returns the
    filtered block, or None if filtering left it with zero items (an empty
    LinksBlock/ButtonsBlock is removed from the response entirely rather
    than rendered as a heading with nothing under it)."""
    if block.type not in ("links", "buttons"):
        return block

    kept = []
    for item in block.items:
        if _url_allowed(item.url):
            kept.append(item)
        else:
            logger.warning("response_guard: dropping non-allowlisted link url=%r label=%r", item.url, item.label)

    if not kept:
        return None
    if len(kept) == len(block.items):
        return block
    return block.model_copy(update={"items": kept})


def safe_refusal() -> ResponseIR:
    return ResponseIR(
        blocks=[
            WarningBlock(md="I can't confirm that yet — please check the official site instead."),
            LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]),
        ],
        meta=ResponseMeta(answer_kind="refusal", facts_used=[], kpis_used=[]),
    )


def enforce_response(response: ResponseIR) -> ResponseIR:
    normalized_blocks = [_normalize_block_brand(block) for block in response.blocks]
    response = response.model_copy(update={"blocks": normalized_blocks})

    text = _extract_text(response)
    result = guardrails.check_text(text)
    if not result.ok:
        return safe_refusal()

    # Final structural pass, applied after the text-guardrail check above so
    # a refusal never depends on link content: drop any LinkItem whose url
    # isn't on Config.ALLOWED_LINK_PREFIXES (production audit, 2026-08-18 --
    # a fact citation rendering the literal "internal://..." source_url as
    # an unclickable link, and RAG citations linking now-404 PDF urls). A
    # LinksBlock/ButtonsBlock left with zero items after filtering is
    # dropped from the response entirely -- it's fine for a response to end
    # with no links where it previously had citations.
    filtered_blocks = []
    for block in response.blocks:
        filtered = _filter_links_block(block)
        if filtered is not None:
            filtered_blocks.append(filtered)
    if filtered_blocks != response.blocks:
        response = response.model_copy(update={"blocks": filtered_blocks})

    return response
