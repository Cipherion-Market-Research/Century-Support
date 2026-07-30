"""HTTP client for Century Core's `POST /v1/messages` (C1 in, C2 out).

Hard rule (owner ruling): this adapter never calls the per-key facts
lookup route on a user's behalf -- that would let a channel bypass every
guardrail Century Core enforces on an answer. This module talks to exactly
one Century Core path, built from a single literal below
(`_MESSAGES_PATH`), and nothing else in this package constructs any other
Century Core route. tests/test_never_facts_endpoint.py statically greps
this package's source for the forbidden route and asserts it never
appears.
"""
import asyncio
from typing import Optional

import aiohttp

from telegram_adapter.config import Config

_MESSAGES_PATH = "/v1/messages"

# Shown to the user only when Century Core could not be reached at all
# (timeout, connection error, or a non-200 response) after every retry is
# exhausted. Deliberately generic -- no Ciphex facts, numbers, or copy: the
# "no hardcoded facts/copy" rule applies to rendering; this is the one
# adapter-authored string that exists because there is no C2 response to
# render.
CORE_FAILURE_MESSAGE = (
    "Sorry, I couldn't reach the support service right now. Please try again shortly."
)


async def post_message(session: aiohttp.ClientSession, envelope: dict) -> Optional[dict]:
    """POST a C1 envelope to Century Core; returns the parsed C2 ResponseIR
    dict, or None if every attempt failed (caller falls back to
    CORE_FAILURE_MESSAGE)."""
    url = Config.CENTURY_CORE_URL.rstrip("/") + _MESSAGES_PATH
    timeout = aiohttp.ClientTimeout(total=Config.CORE_HTTP_TIMEOUT_S)

    for attempt in range(1, Config.CORE_RETRY_MAX_ATTEMPTS + 1):
        try:
            async with session.post(url, json=envelope, timeout=timeout) as resp:
                if resp.status == 200:
                    return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        if attempt < Config.CORE_RETRY_MAX_ATTEMPTS:
            await asyncio.sleep(Config.CORE_RETRY_BASE_DELAY_S * attempt)

    return None
