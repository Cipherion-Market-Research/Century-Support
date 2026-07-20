import time

import pytest

from kpi_sync.ratelimiter import AsyncRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_burst_up_to_max_calls():
    limiter = AsyncRateLimiter(max_calls=3, period_s=10.0)
    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire()
    # All three should be effectively instant -- no throttling until the
    # budget is exhausted.
    assert time.monotonic() - start < 0.5


@pytest.mark.asyncio
async def test_rate_limiter_throttles_beyond_budget():
    limiter = AsyncRateLimiter(max_calls=2, period_s=0.3)
    await limiter.acquire()
    await limiter.acquire()
    start = time.monotonic()
    await limiter.acquire()  # 3rd call must wait for the window to free up
    elapsed = time.monotonic() - start
    assert elapsed >= 0.2
