"""Entrypoint: wires Redis, the shared HTTP session, every poller, and the
health server; handles graceful shutdown on SIGTERM/SIGINT (Railway sends
SIGTERM on redeploy/stop)."""
import asyncio
import os
import signal
import sys

# Railway's "Root Directory" for this service is kpi_sync/ itself (see
# railway.json), but this file still uses absolute `kpi_sync.xxx` imports
# so it also runs as `python -m kpi_sync.main` from the repo root (e.g.
# local dev, tests). Making the repo root importable either way means this
# doesn't silently break if one of those invocation styles changes.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp
import redis.asyncio as redis_lib

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore
from kpi_sync.health_server import run_health_server
from kpi_sync.logging_setup import get_logger, setup_logging
from kpi_sync.pollers.abacus_index import AbacusIndexPoller
from kpi_sync.pollers.ams_keymetrics import AmsKeyMetricsPoller
from kpi_sync.pollers.ams_marketing import AmsMarketingPoller
from kpi_sync.pollers.claim_api import ClaimApiPoller
from kpi_sync.pollers.onchain import OnchainBasePoller, OnchainEthPoller, PresaleActivity
from kpi_sync.ratelimiter import AsyncRateLimiter

logger = get_logger("kpi_sync.main")


def build_pollers(store: KpiStore, session: aiohttp.ClientSession) -> list:
    # Shared across both ams.* pollers -- the 10 req/min budget is per host,
    # not per poller.
    ams_rate_limiter = AsyncRateLimiter(Config.AMS_RATE_LIMIT_PER_MIN, 60.0)
    activity = PresaleActivity()
    return [
        ClaimApiPoller(store, session),
        AmsMarketingPoller(store, session, ams_rate_limiter),
        AmsKeyMetricsPoller(store, session, ams_rate_limiter),
        AbacusIndexPoller(store, session),
        OnchainBasePoller(store, activity),
        OnchainEthPoller(store, activity),
    ]


async def main() -> None:
    setup_logging(Config.LOG_LEVEL)
    redis_client = redis_lib.from_url(Config.REDIS_URL, encoding="utf-8", decode_responses=True)
    store = KpiStore(redis_client)

    async with aiohttp.ClientSession() as session:
        pollers = build_pollers(store, session)
        runner = await run_health_server(store, Config.HEALTH_HOST, Config.HEALTH_PORT)
        logger.info(
            "kpi_sync started",
            extra={"event": "startup"},
        )

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass  # signal handlers aren't available on every platform (e.g. Windows)

        tasks = [asyncio.create_task(p.run_forever()) for p in pollers]

        await stop_event.wait()
        logger.info("shutting down", extra={"event": "shutdown"})

        for poller in pollers:
            poller.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        for poller in pollers:
            w3 = getattr(poller, "w3", None)
            if w3 is not None:
                await w3.provider.disconnect()

        await runner.cleanup()
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
