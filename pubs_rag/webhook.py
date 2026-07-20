"""GitHub webhook receiver for ciphex-website pushes.

On a push to the configured branch that touches either publication index
page or the PDF asset directory, re-parses both index pages and (re)ingests
any PDF whose content changed (new sha256) — see ingest.ingest_document for
the idempotency rule that makes this safe to call repeatedly.
"""
import hashlib
import hmac
import json
import logging
from pathlib import PurePosixPath

import aiohttp
from aiohttp import web

from pubs_rag import ingest, site_parser
from pubs_rag.config import Config
from pubs_rag.pdf_extract import extract_pdf_text

logger = logging.getLogger(__name__)


def verify_signature(secret: str, payload: bytes, signature_header: str) -> bool:
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def relevant_paths_changed(push_payload: dict) -> bool:
    watched_exact = set(Config.PUBLICATION_INDEX_PATHS)
    for commit in push_payload.get("commits", []):
        changed = [*commit.get("added", []), *commit.get("modified", []), *commit.get("removed", [])]
        for path in changed:
            if path in watched_exact or path.startswith(Config.PDF_ASSET_PATH_PREFIX):
                return True
    return False


async def fetch_raw_file(session: aiohttp.ClientSession, owner: str, repo: str, ref: str, path: str) -> bytes:
    url = f"{Config.GITHUB_API_BASE_URL}/{owner}/{repo}/{ref}/{path}"
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=Config.HTTP_TIMEOUT_S)) as resp:
        resp.raise_for_status()
        return await resp.read()


async def refresh_publications(conn, provider, session: aiohttp.ClientSession, ref: str = None) -> list:
    """Re-parse both publication index pages and ingest any new/changed PDF
    they reference. Returns the list of ingest.IngestResult."""
    ref = ref or Config.GITHUB_REPO_BRANCH
    results = []
    for index_path in Config.PUBLICATION_INDEX_PATHS:
        html_bytes = await fetch_raw_file(
            session, Config.GITHUB_REPO_OWNER, Config.GITHUB_REPO_NAME, ref, index_path
        )
        listed_on = PurePosixPath(index_path).stem
        entries = site_parser.parse_publication_index(html_bytes.decode("utf-8"), listed_on)

        for entry in entries:
            pdf_filename = PurePosixPath(entry["pdf_path"]).name
            pdf_repo_path = f"{Config.PDF_ASSET_PATH_PREFIX}{pdf_filename}"
            pdf_bytes = await fetch_raw_file(
                session, Config.GITHUB_REPO_OWNER, Config.GITHUB_REPO_NAME, ref, pdf_repo_path
            )
            sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            extracted = extract_pdf_text(pdf_bytes)

            doc_meta = {
                "sha256": sha256,
                "kind": "pdf",
                "slug": entry["slug"],
                "title": entry["title"],
                "date": entry["date"],
                "source_url": f"{Config.SITE_BASE_URL}{entry['pdf_path']}",
                "listed_on": listed_on,
            }
            result = await ingest.ingest_document(conn, provider, doc_meta, extracted.text)
            logger.info(
                "webhook refresh: %s -> %s",
                entry["slug"],
                "skipped (unchanged)" if result.skipped else f"ingested ({result.chunk_count} chunks)",
            )
            results.append(result)

    return results


async def handle_webhook(request: web.Request) -> web.Response:
    body = await request.read()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(Config.GITHUB_WEBHOOK_SECRET, body, signature):
        return web.json_response({"error": "invalid signature"}, status=401)

    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return web.json_response({"ok": True})
    if event != "push":
        return web.json_response({"ignored": f"event={event}"}, status=202)

    payload = json.loads(body)
    expected_ref = f"refs/heads/{Config.GITHUB_REPO_BRANCH}"
    if payload.get("ref") != expected_ref:
        return web.json_response({"ignored": f"ref={payload.get('ref')}"}, status=202)
    if not relevant_paths_changed(payload):
        return web.json_response({"ignored": "no watched paths changed"}, status=202)

    conn = request.app["db_conn"]
    provider = request.app["embedding_provider"]
    session = request.app["http_session"]
    results = await refresh_publications(conn, provider, session, ref=payload.get("after"))

    return web.json_response(
        {
            "ingested": [
                {
                    "slug": r.slug,
                    "sha256": r.sha256,
                    "skipped": r.skipped,
                    "superseded": r.superseded,
                    "chunk_count": r.chunk_count,
                }
                for r in results
            ]
        }
    )
