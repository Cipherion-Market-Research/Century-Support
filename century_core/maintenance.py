"""Global maintenance-mode switch (WP-7c rollback ledger, owner-approved
2026-07-20 -- see docs/BUILD_HANDOFF.md "Rollback & kill-switch ledger").

Convention: a single Redis key `ops:maintenance_mode`, shared with the live
Telegram bot's own copy of this check (utils/maintenance.py) so one toggle
affects both serving surfaces identically:
  - key ABSENT             -> normal operation.
  - key present, non-empty -> its string value IS the holding message.
  - key present, empty ""  -> fall back to Config.MAINTENANCE_DEFAULT_MESSAGE.

Toggle, data-only, no deploy:
    SET ops:maintenance_mode "We're doing scheduled maintenance..."
    DEL ops:maintenance_mode
or the convenience wrapper: `python scripts/maintenance.py on|off [message]`.

FAIL-OPEN: any Redis error while checking the flag is treated as "not in
maintenance" -- this check exists to make outages *graceful*, so it must
never itself be a way to cause one.
"""
from typing import Optional

from century_core.config import Config

MAINTENANCE_KEY = "ops:maintenance_mode"


async def get_maintenance_message(redis_client) -> Optional[str]:
    """Returns the holding message if maintenance mode is on, else None."""
    if redis_client is None:
        return None
    try:
        raw = await redis_client.get(MAINTENANCE_KEY)
    except Exception:
        # Fail-open: a Redis hiccup must never block normal serving.
        return None
    if raw is None:
        return None
    return raw if raw else Config.MAINTENANCE_DEFAULT_MESSAGE
