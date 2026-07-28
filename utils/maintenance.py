"""Global maintenance-mode switch (WP-7c rollback ledger, owner-approved
2026-07-20 -- see docs/BUILD_HANDOFF.md "Rollback & kill-switch ledger").

Live-bot side of the same Redis contract century_core/maintenance.py
implements, so one toggle affects both serving surfaces identically:
  - key `ops:maintenance_mode` ABSENT             -> normal operation.
  - key present, non-empty                        -> its value IS the
    holding message.
  - key present, empty ""                         -> fall back to the
    MAINTENANCE_DEFAULT_MESSAGE env var (or the built-in default below).

Toggle, data-only, no deploy:
    SET ops:maintenance_mode "We're doing scheduled maintenance..."
    DEL ops:maintenance_mode
or the convenience wrapper: `python scripts/maintenance.py on|off [message]`.

FAIL-OPEN: any Redis error while checking the flag is treated as "not in
maintenance" -- this check must never itself be able to take the bot down.
"""
import os
from typing import Optional

MAINTENANCE_KEY = "ops:maintenance_mode"

_DEFAULT_MESSAGE = (
    "We're currently updating our information. Please check back shortly "
    "— for urgent issues contact support@ciphex.io."
)


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
    return raw if raw else os.environ.get("MAINTENANCE_DEFAULT_MESSAGE", _DEFAULT_MESSAGE)
