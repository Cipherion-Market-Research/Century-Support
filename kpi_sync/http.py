"""Shared HTTP fetch helper: retry/backoff + optional rate limiting.

Zero scraping — every call here is a GET against a documented JSON API.
"""
import asyncio
import random
from typing import Any, Optional

import aiohttp

from kpi_sync.config import Config
from kpi_sync.ratelimiter import AsyncRateLimiter


class FetchError(Exception):
    pass


def _backoff_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
    return delay * (0.5 + random.random() * 0.5)  # jitter in [0.5x, 1x] of the capped delay


async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    rate_limiter: Optional[AsyncRateLimiter] = None,
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    headers: Optional[dict] = None,
) -> Any:
    max_attempts = max_attempts or Config.RETRY_MAX_ATTEMPTS
    base_delay = Config.RETRY_BASE_DELAY_S if base_delay is None else base_delay
    max_delay = Config.RETRY_MAX_DELAY_S if max_delay is None else max_delay
    timeout = aiohttp.ClientTimeout(total=Config.HTTP_TIMEOUT_S)

    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        if rate_limiter is not None:
            await rate_limiter.acquire()
        try:
            async with session.get(url, timeout=timeout, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after
                        else _backoff_delay(attempt, base_delay, max_delay)
                    )
                    last_exc = FetchError(f"429 rate limited by {url}")
                    if attempt < max_attempts:
                        await asyncio.sleep(delay)
                    continue
                if resp.status >= 500:
                    last_exc = FetchError(f"{resp.status} from {url}")
                    if attempt < max_attempts:
                        await asyncio.sleep(_backoff_delay(attempt, base_delay, max_delay))
                    continue
                # Non-retryable 4xx
                body = await resp.text()
                raise FetchError(f"{resp.status} from {url}: {body[:500]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_exc = e
            if attempt < max_attempts:
                await asyncio.sleep(_backoff_delay(attempt, base_delay, max_delay))
            continue

    raise FetchError(f"failed to fetch {url} after {max_attempts} attempts: {last_exc}") from last_exc
