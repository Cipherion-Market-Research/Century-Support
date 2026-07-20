"""Health HTTP endpoint: aggregates every *running* poller's `__health` key
so an external monitor (or WP-7's drift/staleness alerting) has one place
to look."""
from aiohttp import web

from kpi_sync.config import Config
from kpi_sync.envelope import KpiStore

CORE_SOURCES = [
    "claim_api",
    "ams_marketing",
    "ams_keymetrics",
    "onchain_base",
    "onchain_eth",
]


def active_sources() -> list:
    """Sources this deployment actually polls. abacus_index is omitted
    unless explicitly enabled (Amendment C-R1) -- a poller that isn't
    running has no health to report, and listing it as permanently
    unhealthy would just be noise."""
    sources = list(CORE_SOURCES)
    if Config.ABACUS_ENABLED:
        sources.append("abacus_index")
    return sources


def create_health_app(store: KpiStore) -> web.Application:
    app = web.Application()

    async def health(request: web.Request) -> web.Response:
        sources = {}
        overall_ok = True
        for source_key in active_sources():
            status = await store.read_health(source_key)
            if status is None:
                # Never polled yet (e.g. still starting up) -- distinct
                # from an explicit ok=False, but still not a clean bill of
                # health.
                status = {"ok": None, "last_success": None, "consecutive_failures": 0}
                overall_ok = False
            elif not status.get("ok"):
                overall_ok = False
            sources[source_key] = status
        payload = {"ok": overall_ok, "sources": sources}
        return web.json_response(payload, status=200 if overall_ok else 503)

    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    return app


async def run_health_server(store: KpiStore, host: str, port: int) -> web.AppRunner:
    app = create_health_app(store)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
