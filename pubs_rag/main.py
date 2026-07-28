"""Entry point for the publications RAG service (WP-4).

Modes:
  - `python -m pubs_rag.main serve`   (default) run the webhook + health
    HTTP server.
  - `python -m pubs_rag.main ingest`  one-shot ingestion of the seed corpus
    (data/kb_source/) for initial DB population or a manual re-run.
  - `python -m pubs_rag.main approve <sha256-or-slug>` (WP-7c serving
    quarantine) mark a document approved -- its chunks become eligible for
    retrieve() immediately, no restart/deploy needed.
  - `python -m pubs_rag.main revoke <sha256-or-slug>` (WP-7c) the inverse:
    mark approved=false, instantly pulling a document's chunks out of
    retrieval -- the kill switch for a bad/retracted publication.
  - `python -m pubs_rag.main list-pending` (WP-7c) list documents awaiting
    approval (approved=false), oldest first.
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

    # ciphex-website is a private repo: the webhook receiver stays up and
    # can still accept/verify events without a token, but every raw-content
    # fetch it triggers will 404 until PUBS_RAG_GITHUB_TOKEN is set. Warn
    # loudly at startup rather than only discovering this on the first push.
    if not Config.GITHUB_TOKEN:
        logger.warning(
            "PUBS_RAG_GITHUB_TOKEN is not set -- ciphex-website is a private "
            "repo, so webhook-triggered GitHub content fetches will fail "
            "with a 404 until it is configured. The webhook endpoint itself "
            "still accepts and verifies events."
        )

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


async def run_set_approved(identifier: str, approved: bool) -> None:
    conn = await db.connect()
    await db.init_schema(conn)
    try:
        updated = await db.set_approved(conn, identifier, approved)
        verb = "approved" if approved else "revoked"
        if updated == 0:
            print(f"no document matched {identifier!r} -- nothing {verb}", file=sys.stderr)
            sys.exit(1)
        print(f"{verb}: {updated} document(s) matching {identifier!r}")
    finally:
        await conn.close()


async def run_list_pending() -> None:
    conn = await db.connect()
    await db.init_schema(conn)
    try:
        pending = await db.list_pending(conn)
        if not pending:
            print("no documents pending approval")
            return
        for row in pending:
            print(f"{row['sha256']}  {row['slug']:<40}  {row['title']}  (ingested {row['ingested_at']})")
    finally:
        await conn.close()


def _require_identifier(argv: list, mode: str) -> str:
    if len(argv) < 3:
        print(f"usage: python -m pubs_rag.main {mode} <sha256-or-slug>", file=sys.stderr)
        sys.exit(1)
    return argv[2]


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if mode == "ingest":
        asyncio.run(run_ingest())
    elif mode == "serve":
        web.run_app(make_app(), host=Config.HEALTH_HOST, port=Config.HEALTH_PORT)
    elif mode == "approve":
        identifier = _require_identifier(sys.argv, "approve")
        asyncio.run(run_set_approved(identifier, True))
    elif mode == "revoke":
        identifier = _require_identifier(sys.argv, "revoke")
        asyncio.run(run_set_approved(identifier, False))
    elif mode == "list-pending":
        asyncio.run(run_list_pending())
    else:
        print(
            "usage: python -m pubs_rag.main [serve|ingest|approve <sha256-or-slug>"
            "|revoke <sha256-or-slug>|list-pending]",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
