"""Entry point for the publications RAG service (WP-4).

Modes:
  - `python -m pubs_rag.main serve`   (default) run the webhook + health
    HTTP server.
  - `python -m pubs_rag.main ingest`  one-shot ingestion of the seed corpus
    (data/kb_source/) for initial DB population or a manual re-run.
  - `python -m pubs_rag.main ingest-pages` (Sprint 3) one-shot ingestion of
    the pages corpus (data/kb_source/pages/, seeded/refreshed by
    scripts/harvest_pages.py) into the separate site_pages/page_chunks
    tables -- see pubs_rag/db.py's module docstring for why pages and PDFs
    are never mixed into one index.
  - `python -m pubs_rag.main approve <sha256-or-slug> [--pages]` (WP-7c
    serving quarantine) mark a document (or, with --pages, a page)
    approved -- its chunks become eligible for retrieve()/retrieve_pages()
    immediately, no restart/deploy needed.
  - `python -m pubs_rag.main revoke <sha256-or-slug> [--pages]` (WP-7c) the
    inverse: mark approved=false, instantly pulling a document's (or
    page's) chunks out of retrieval -- the kill switch for a bad/retracted
    publication or page.
  - `python -m pubs_rag.main list-pending [--pages]` (WP-7c) list documents
    (or, with --pages, pages) awaiting approval (approved=false), oldest
    first.
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


async def run_ingest_pages() -> None:
    conn = await db.connect()
    await db.init_schema(conn)
    provider = get_embedding_provider(Config)
    summary = await ingest.ingest_pages_inventory(conn, provider)
    logger.info(
        "ingest-pages complete: %d ingested, %d skipped (unchanged), %d superseded",
        summary.ingested,
        summary.skipped,
        summary.superseded,
    )
    await conn.close()


async def run_set_approved(identifier: str, approved: bool, *, pages: bool = False) -> None:
    conn = await db.connect()
    await db.init_schema(conn)
    try:
        set_fn = db.set_page_approved if pages else db.set_approved
        noun = "page" if pages else "document"
        updated = await set_fn(conn, identifier, approved)
        verb = "approved" if approved else "revoked"
        if updated == 0:
            print(f"no {noun} matched {identifier!r} -- nothing {verb}", file=sys.stderr)
            sys.exit(1)
        print(f"{verb}: {updated} {noun}(s) matching {identifier!r}")
    finally:
        await conn.close()


async def run_list_pending(*, pages: bool = False) -> None:
    conn = await db.connect()
    await db.init_schema(conn)
    try:
        noun = "pages" if pages else "documents"
        pending = await (db.list_pending_pages(conn) if pages else db.list_pending(conn))
        if not pending:
            print(f"no {noun} pending approval")
            return
        for row in pending:
            print(f"{row['sha256']}  {row['slug']:<40}  {row['title']}  (ingested {row['ingested_at']})")
    finally:
        await conn.close()


def _require_identifier(argv: list, mode: str) -> tuple[str, bool]:
    """Parses `<sha256-or-slug> [--pages]` from argv[2:] (order-agnostic --
    `--pages` may come before or after the identifier). Returns
    (identifier, pages_flag)."""
    rest = [a for a in argv[2:] if a]
    pages = "--pages" in rest
    positional = [a for a in rest if a != "--pages"]
    if not positional:
        print(f"usage: python -m pubs_rag.main {mode} <sha256-or-slug> [--pages]", file=sys.stderr)
        sys.exit(1)
    return positional[0], pages


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if mode == "ingest":
        asyncio.run(run_ingest())
    elif mode == "ingest-pages":
        asyncio.run(run_ingest_pages())
    elif mode == "serve":
        web.run_app(make_app(), host=Config.HEALTH_HOST, port=Config.HEALTH_PORT)
    elif mode == "approve":
        identifier, pages = _require_identifier(sys.argv, "approve")
        asyncio.run(run_set_approved(identifier, True, pages=pages))
    elif mode == "revoke":
        identifier, pages = _require_identifier(sys.argv, "revoke")
        asyncio.run(run_set_approved(identifier, False, pages=pages))
    elif mode == "list-pending":
        pages = "--pages" in sys.argv[2:]
        asyncio.run(run_list_pending(pages=pages))
    else:
        print(
            "usage: python -m pubs_rag.main [serve|ingest|ingest-pages"
            "|approve <sha256-or-slug> [--pages]|revoke <sha256-or-slug> [--pages]"
            "|list-pending [--pages]]",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
