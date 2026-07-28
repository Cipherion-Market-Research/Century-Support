"""Generic async retry/backoff, copied from kpi_sync/retry.py's approach
(own copy -- each service in this repo keeps its dependencies isolated)."""
import asyncio
import random
from typing import Awaitable, Callable, Optional, TypeVar

from drift_monitor.config import Config

T = TypeVar("T")


def backoff_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
    return delay * (0.5 + random.random() * 0.5)  # jitter in [0.5x, 1x] of the capped delay


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
) -> T:
    max_attempts = max_attempts or Config.RETRY_MAX_ATTEMPTS
    base_delay = Config.RETRY_BASE_DELAY_S if base_delay is None else base_delay
    max_delay = Config.RETRY_MAX_DELAY_S if max_delay is None else max_delay

    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception as e:  # noqa: BLE001 -- deliberately broad: any fetch-layer failure is retryable
            last_exc = e
            if attempt < max_attempts:
                await asyncio.sleep(backoff_delay(attempt, base_delay, max_delay))
            continue
    raise last_exc
