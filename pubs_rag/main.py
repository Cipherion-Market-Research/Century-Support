"""Entry point for the publications RAG service (WP-4).

Two modes:
  - `python -m pubs_rag.main serve`   (default) run the webhook + health
    HTTP server.
  - `python -m pubs_rag.main ingest`  one-shot ingestion of the seed corpus
    (data/kb_source/) for initial DB population or a manual re-run.
"""
import asyncio
import logging
import sys

import aiohttp
from aiohttp import web

from pubs_rag import db, ingest
from pubs_rag.config import Config
from pubs_rag.embeddings import get_embedding_provider
from pubs_rag.webhook import handle_webhook

logging.basicConfig(level=Config.LOG_LEVEL)
logger = logging.getLogger(__name__)


async def handle_health(request: web.Request) -> web.Response:
    conn = request.app["db_conn"]
    try:
        chunk_count = await db.count_chunks(conn)
        return web.json_response({"ok": True, "chunks": chunk_count})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=503)


async def make_app() -> web.Application:
    app = web.Application()
    conn = await db.connect()
    await db.init_schema(conn)

    app["db_conn"] = conn
    app["embedding_provider"] = get_embedding_provider(Config)
    app["http_session"] = aiohttp.ClientSession()

    app.router.add_post("/webhook/github", handle_webhook)
    app.router.add_get("/health", handle_health)

    async def on_cleanup(app: web.Application) -> None:
        await app["http_session"].close()
        await app["db_conn"].close()

    app.on_cleanup.append(on_cleanup)
    return app


async def run_ingest() -> None:
    conn = await db.connect()
    await db.init_schema(conn)
    provider = get_embedding_provider(Config)
    summary = await ingest.ingest_inventory(conn, provider)
    logger.info(
        "ingest complete: %d ingested, %d skipped (unchanged), %d superseded",
        summary.ingested,
        summary.skipped,
        summary.superseded,
    )
    await conn.close()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if mode == "ingest":
        asyncio.run(run_ingest())
    elif mode == "serve":
        web.run_app(make_app(), host=Config.HEALTH_HOST, port=Config.HEALTH_PORT)
    else:
        print("usage: python -m pubs_rag.main [serve|ingest]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
