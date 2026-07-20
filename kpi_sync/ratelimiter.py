"""Sliding-window async rate limiter, used to keep ams.ciphex.io calls
under its published 10 req/min budget across all pollers that share it."""
import asyncio
import time


class AsyncRateLimiter:
    def __init__(self, max_calls: int, period_s: float):
        self.max_calls = max_calls
        self.period_s = period_s
        self._call_times = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._call_times = [t for t in self._call_times if now - t < self.period_s]
            if len(self._call_times) >= self.max_calls:
                wait_for = self.period_s - (now - self._call_times[0])
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                now = time.monotonic()
                self._call_times = [t for t in self._call_times if now - t < self.period_s]
            self._call_times.append(now)
