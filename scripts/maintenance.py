#!/usr/bin/env python3
"""Toggle the global maintenance-mode switch (WP-7c rollback ledger).

Data-only, no deploy: sets/clears a single Redis key that both serving
surfaces check on every request --
  - the live Telegram bot (core/message_handler.py, core/command_handler.py)
  - century_core's POST /v1/messages (century_core/routes/messages.py)

Usage:
    python scripts/maintenance.py on ["custom holding message"]
    python scripts/maintenance.py off

`on` with no message sets an empty string -- the key still EXISTS (so
maintenance mode is on), but each surface falls back to its own
MAINTENANCE_DEFAULT_MESSAGE env var / built-in default rather than serving
an empty reply. `off` is a plain DEL and restores normal serving instantly.

Talks to REDIS_URL (the same env var both core/ and century_core/ read).
"""
import asyncio
import os
import sys

MAINTENANCE_KEY = "ops:maintenance_mode"


async def _run(action: str, message: str) -> None:
    import redis.asyncio as redis_lib

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    client = redis_lib.from_url(redis_url, encoding="utf-8", decode_responses=True)
    try:
        if action == "on":
            await client.set(MAINTENANCE_KEY, message)
            shown = message or "(empty -- each surface will use its own default message)"
            print(f"maintenance mode ON: {shown}")
        else:
            deleted = await client.delete(MAINTENANCE_KEY)
            print("maintenance mode OFF" + (" (was already off)" if not deleted else ""))
    finally:
        await client.aclose()


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("on", "off"):
        print("usage: python scripts/maintenance.py on [message] | off", file=sys.stderr)
        sys.exit(1)

    action = sys.argv[1]
    message = " ".join(sys.argv[2:]) if action == "on" else ""
    asyncio.run(_run(action, message))


if __name__ == "__main__":
    main()
