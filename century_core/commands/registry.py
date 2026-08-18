"""Command detection + dispatch.

C1 rule: `command` is non-null only when the platform natively parsed a
command; core also detects command-like text itself (adapters don't).
`detect_command` implements that second half.
"""
import re
from typing import Optional

from century_core.commands.audit import handle_audit
from century_core.commands.ca import handle_ca
from century_core.commands.claim import handle_claim
from century_core.commands.contact import handle_contact
from century_core.commands.contribute import handle_contribute
from century_core.commands.ecosystem import handle_ecosystem
from century_core.commands.misc import handle_help, handle_start
from century_core.commands.price import handle_price
from century_core.commands.stats import handle_stats
from century_core.commands.supply import handle_supply
from century_core.commands.updates import handle_updates
from century_core.models import InboundMessage

_COMMAND_TEXT_RE = re.compile(r"^/(\w+)(?:@\w+)?\s*(.*)$", re.DOTALL)

HANDLERS = {
    "price": handle_price,
    "ca": handle_ca,
    "claim": handle_claim,
    "audit": handle_audit,
    "stats": handle_stats,
    "updates": handle_updates,
    "contribute": handle_contribute,
    "contact": handle_contact,
    "ecosystem": handle_ecosystem,
    "supply": handle_supply,
    "help": handle_help,
    "start": handle_start,
}


def detect_command(message: InboundMessage) -> Optional[tuple[str, str]]:
    if message.command is not None:
        return message.command.name.lower(), message.command.args

    match = _COMMAND_TEXT_RE.match(message.text.strip())
    if match:
        return match.group(1).lower(), match.group(2).strip()

    return None


async def dispatch_command(name: str, args: str, stores):
    handler = HANDLERS.get(name)
    if handler is None:
        return None
    return await handler(args, stores)
