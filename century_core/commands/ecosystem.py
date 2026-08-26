"""/ecosystem -- overview of the Ciphex product stack. identity.connect_program,
links.connect_portal, links.alpha_ams, and links.atlas_page are contract
keys that may not exist in facts.yaml yet -- every read below goes through
the standard stores.facts.get(...) + is_unknown graceful fallback.
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

_TOKEN_PAGE_FALLBACK_URL = "https://ciphex.io/ciphex-token"
_ALPHA_AMS_FALLBACK_URL = "https://ams.ciphex.io"
_ATLAS_PAGE_FALLBACK_URL = "https://ciphex.io/atlas-rwa-services"
_CONNECT_PORTAL_FALLBACK_URL = "https://connect.ciphex.io"

_DEFAULT_CONNECT_SENTENCE = "a community participation program."

# Live tester feedback, 2026-08-26: the rendered paragraph doubled the
# program name -- "Ciphex Connect™ & Momentum Rewards™ — Ciphex Connect™ &
# Momentum Rewards™ — a community participation/loyalty program at
# connect.ciphex.io." -- because identity.connect_program's own value
# already opens with the name, and the render below unconditionally
# prepends a bolded copy of the same name in front of it. Strip a leading
# copy of the title (plus its separator) from the fact value before
# prepending the bolded title, so the name is never rendered twice
# regardless of how facts.yaml phrases the fact -- the default fallback
# sentence (which doesn't include the name) passes through unchanged.
_CONNECT_TITLE = "Ciphex Connect™ & Momentum Rewards™"
_CONNECT_TITLE_PREFIX_RE = re.compile(
    r"^\s*" + re.escape(_CONNECT_TITLE) + r"\s*[—–\-:]\s*",
    re.IGNORECASE,
)


def _strip_connect_title_prefix(sentence: str) -> str:
    return _CONNECT_TITLE_PREFIX_RE.sub("", sentence)


async def handle_ecosystem(args: str, stores) -> ResponseIR:
    facts_used = []

    token_page = stores.facts.get("links.token_page")
    if token_page is not None and not token_page.is_unknown:
        token_page_url = str(token_page.value)
        facts_used.append("links.token_page")
    else:
        token_page_url = _TOKEN_PAGE_FALLBACK_URL

    alpha_ams = stores.facts.get("links.alpha_ams")
    if alpha_ams is not None and not alpha_ams.is_unknown:
        alpha_ams_url = str(alpha_ams.value)
        facts_used.append("links.alpha_ams")
    else:
        alpha_ams_url = _ALPHA_AMS_FALLBACK_URL

    atlas_page = stores.facts.get("links.atlas_page")
    if atlas_page is not None and not atlas_page.is_unknown:
        atlas_page_url = str(atlas_page.value)
        facts_used.append("links.atlas_page")
    else:
        atlas_page_url = _ATLAS_PAGE_FALLBACK_URL

    connect_portal = stores.facts.get("links.connect_portal")
    if connect_portal is not None and not connect_portal.is_unknown:
        connect_portal_url = str(connect_portal.value)
        facts_used.append("links.connect_portal")
    else:
        connect_portal_url = _CONNECT_PORTAL_FALLBACK_URL

    connect_program = stores.facts.get("identity.connect_program")
    if connect_program is not None and not connect_program.is_unknown:
        connect_sentence = str(connect_program.value)
        facts_used.append("identity.connect_program")
    else:
        connect_sentence = _DEFAULT_CONNECT_SENTENCE

    blocks = [
        HeadingBlock(text="The Ciphex Ecosystem"),
        ParagraphBlock(md="**CPX Token** — the ERC-20 utility token of the Ciphex ecosystem."),
        ParagraphBlock(
            md="**Ciphex Alpha** — Autonomous Market Systems, Phase 3 (pre-commercial)."
        ),
        ParagraphBlock(
            md="**Atlas RWA Services** — enterprise tokenization, pre-commercial testing; demo by "
            "request via the contact page (see /contact)."
        ),
        ParagraphBlock(md=f"**{_CONNECT_TITLE}** — {_strip_connect_title_prefix(connect_sentence)}"),
        LinksBlock(
            items=[
                LinkItem(label="CPX Token", url=token_page_url),
                LinkItem(label="Ciphex Alpha", url=alpha_ams_url),
                LinkItem(label="Atlas RWA Services", url=atlas_page_url),
                LinkItem(label="Ciphex Connect", url=connect_portal_url),
            ]
        ),
        related_footer(("updates", "announcements"), ("contact", "contact Ciphex")),
    ]

    return ResponseIR(
        blocks=blocks,
        meta=ResponseMeta(answer_kind="command", facts_used=facts_used, kpis_used=[]),
    )
