"""/help and /start -- static, no store lookups needed."""
from century_core.config import Config
from century_core.models import HeadingBlock, LinkItem, LinksBlock, ParagraphBlock, ResponseIR, ResponseMeta

_HELP_TEXT = (
    "**Available commands:**\n"
    "`/price` — CPX price info\n"
    "`/ca` — contract addresses\n"
    "`/claim` — token claiming portal\n"
    "`/audit` — security audit status\n"
    "`/stats` — claim portal stats\n"
    "`/publications` — recent Ciphex publications\n\n"
    "You can also ask a question in plain text."
)


async def handle_help(args: str, stores) -> ResponseIR:
    return ResponseIR(
        blocks=[
            HeadingBlock(text="Century — Ciphex Support"),
            ParagraphBlock(md=_HELP_TEXT),
        ],
        meta=ResponseMeta(answer_kind="command", facts_used=[], kpis_used=[]),
    )


async def handle_start(args: str, stores) -> ResponseIR:
    return ResponseIR(
        blocks=[
            HeadingBlock(text="Welcome to Ciphex Support"),
            ParagraphBlock(
                md="I'm Century, the official Ciphex (CPX) support assistant. Ask me a question "
                "or use `/help` to see available commands.\n\n"
                "⚠️ Ciphex will never DM you first, and will never ask for your wallet seed phrase."
            ),
            LinksBlock(items=[LinkItem(label="Ciphex", url=Config.OFFICIAL_SITE_URL)]),
        ],
        meta=ResponseMeta(answer_kind="command", facts_used=[], kpis_used=[]),
    )
