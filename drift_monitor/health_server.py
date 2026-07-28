"""Health HTTP endpoint: reports whether the poll loop is enabled and when
it last ran, reading local state (this service has no Redis of its own).
"""
from aiohttp import web

from drift_monitor.config import Config
from drift_monitor.state import PollState


def create_health_app(poll_state: PollState) -> web.Application:
    app = web.Application()

    async def health(request: web.Request) -> web.Response:
        payload = {
            "ok": True,
            "content_enabled": Config.CONTENT_ENABLED,
            "open_prs": Config.OPEN_PRS,
            "tracked_ref": Config.TRACKED_REF,
            "last_checked_at": poll_state.get_last_checked(),
        }
        return web.json_response(payload, status=200)

    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    return app


async def run_health_server(poll_state: PollState, host: str, port: int) -> web.AppRunner:
    app = create_health_app(poll_state)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
