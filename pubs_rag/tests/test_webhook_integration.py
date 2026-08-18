"""End-to-end simulation of a GitHub push to ciphex-website that adds a new
PDF (WP-4 acceptance: "a simulated webhook push ingests a new PDF
end-to-end"). No real network calls to GitHub: a local aiohttp TestServer
stands in for raw.githubusercontent.com, serving the real fixture HTML (one
entry added) plus real bytes for every already-known PDF and a freshly
generated one for the new entry. This exercises the actual
webhook.handle_webhook -> refresh_publications -> ingest.ingest_document ->
retrieval.retrieve path with nothing mocked below the HTTP boundary.
"""
import hashlib
import hmac
import json
from pathlib import Path

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from pubs_rag import db, ingest
from pubs_rag.config import Config
from pubs_rag.embeddings import HashingEmbeddingProvider
from pubs_rag.retrieval import retrieve
from pubs_rag.webhook import handle_webhook

FIXTURES = Path(__file__).parent / "fixtures"
KB_SOURCE = Path(__file__).resolve().parents[2] / "data" / "kb_source"
WEBHOOK_SECRET = "test-webhook-secret"
NEW_SLUG = "new-test-publication"

# The corpus grows forever, so "how many already-known PDFs get re-synced
# unchanged" is never a frozen number -- it's whatever inventory.json
# currently lists with extraction=="ok" (exactly what ingest_inventory()
# seeds the corpus with in the setup step below).
_INVENTORY = json.loads((KB_SOURCE / "inventory.json").read_text())
KNOWN_PDF_COUNT = sum(1 for e in _INVENTORY if e["kind"] == "pdf" and e.get("extraction") == "ok")

_NEW_CARD_HTML = (
    f'<button type="button" class="pdf-preview-card" data-slug="{NEW_SLUG}" '
    f'data-title="New Test Publication" data-date="July 20, 2026" '
    f'data-pdf="/assets/documents/{NEW_SLUG}.pdf"></button>'
)


def _updates_html_with_new_entry() -> str:
    html = (FIXTURES / "internal-updates.html").read_text()
    marker = '<main id="main-content">'
    assert marker in html
    return html.replace(marker, marker + _NEW_CARD_HTML, 1)


def _make_test_pdf(text: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text=text)
    return bytes(pdf.output())


async def _make_fake_github_server(updates_html: str) -> TestServer:
    app = web.Application()
    owner, repo, ref = Config.GITHUB_REPO_OWNER, Config.GITHUB_REPO_NAME, Config.GITHUB_REPO_BRANCH
    # Generated once and reused for every request — fpdf2 embeds a
    # generation timestamp, so calling it fresh per-request would make the
    # "new" PDF's bytes (and sha256) change on every fetch, breaking the
    # idempotent-replay assertion below even though the content is
    # unchanged.
    new_pdf_bytes = _make_test_pdf(
        "Ciphex burn cycle test publication content for the simulated webhook push."
    )

    async def serve_updates_html(request):
        return web.Response(body=updates_html.encode("utf-8"))

    async def serve_pdf(request):
        filename = request.match_info["filename"]
        if filename == f"{NEW_SLUG}.pdf":
            body = new_pdf_bytes
        else:
            path = KB_SOURCE / "pdfs" / filename
            if not path.exists():
                return web.Response(status=404)
            body = path.read_bytes()
        return web.Response(body=body)

    # Route registration is driven by the real Config.PUBLICATION_INDEX_PATHS
    # (not a hardcoded page name) so this fake server always matches
    # whatever index-page path(s) the code under test will actually
    # request. Only src/internal-updates.html is watched -- the Insights &
    # Publications section is excluded from the bot's knowledge base (Bot
    # Parameter Requirements, 2026-08-18; see config.py) -- so there is no
    # publications route to fake here at all.
    (updates_path,) = Config.PUBLICATION_INDEX_PATHS
    app.router.add_get(f"/{owner}/{repo}/{ref}/{updates_path}", serve_updates_html)
    app.router.add_get(f"/{owner}/{repo}/{ref}/public/assets/documents/{{filename}}", serve_pdf)

    server = TestServer(app)
    await server.start_server()
    return server


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _push_payload_adding_new_pdf() -> bytes:
    (updates_path,) = Config.PUBLICATION_INDEX_PATHS
    payload = {
        "ref": f"refs/heads/{Config.GITHUB_REPO_BRANCH}",
        "commits": [
            {
                "added": [f"public/assets/documents/{NEW_SLUG}.pdf", updates_path],
                "modified": [],
                "removed": [],
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


async def test_simulated_webhook_push_ingests_new_pdf_end_to_end(db_conn, monkeypatch):
    provider = HashingEmbeddingProvider(dim=Config.EMBEDDING_DIM)
    # Seed the corpus first, like a real long-running deployment.
    await ingest.ingest_inventory(db_conn, provider, str(KB_SOURCE))

    fake_github = await _make_fake_github_server(_updates_html_with_new_entry())
    monkeypatch.setattr(Config, "GITHUB_API_BASE_URL", f"http://127.0.0.1:{fake_github.port}")
    monkeypatch.setattr(Config, "GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)

    webhook_app = web.Application()
    webhook_app["db_conn"] = db_conn
    webhook_app["embedding_provider"] = provider
    webhook_app.router.add_post("/webhook/github", handle_webhook)

    async with aiohttp.ClientSession() as http_session:
        webhook_app["http_session"] = http_session
        webhook_server = TestServer(webhook_app)
        await webhook_server.start_server()
        client = aiohttp.ClientSession(base_url=f"http://127.0.0.1:{webhook_server.port}")
        try:
            body = _push_payload_adding_new_pdf()
            headers = {
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _sign(WEBHOOK_SECRET, body),
                "Content-Type": "application/json",
            }

            resp = await client.post("/webhook/github", data=body, headers=headers)
            assert resp.status == 200
            data = await resp.json()
            by_slug = {r["slug"]: r for r in data["ingested"]}

            assert NEW_SLUG in by_slug
            assert by_slug[NEW_SLUG]["skipped"] is False
            assert by_slug[NEW_SLUG]["chunk_count"] >= 1
            # Every already-known PDF on the updates+publications pages is
            # re-synced but unchanged -> skipped, proving the webhook
            # doesn't blindly re-embed the whole corpus on every push. Not a
            # frozen count: whatever the current ok-extraction corpus holds
            # (KNOWN_PDF_COUNT, seeded above by ingest_inventory).
            unchanged = [slug for slug, r in by_slug.items() if slug != NEW_SLUG]
            assert len(unchanged) == KNOWN_PDF_COUNT
            assert all(by_slug[slug]["skipped"] for slug in unchanged)

            # WP-7c serving quarantine: a webhook-ingested document lands
            # unapproved by default, so it must be invisible to the same
            # retrieve() WP-5 calls -- not merely present-but-unranked.
            results = await retrieve(db_conn, provider, "simulated webhook push", top_k=3)
            assert not any(r.slug == NEW_SLUG for r in results)

            # The admin escape hatch sees it pending approval...
            unapproved_results = await retrieve(
                db_conn, provider, "simulated webhook push", top_k=3, include_unapproved=True
            )
            hit = next((r for r in unapproved_results if r.slug == NEW_SLUG), None)
            assert hit is not None
            assert hit.title == "New Test Publication"
            assert hit.date == "July 20, 2026"
            assert hit.source_url == f"{Config.SITE_BASE_URL}/assets/documents/{NEW_SLUG}.pdf"

            # ...and once approved (the CLI's underlying DB call), it's
            # retrievable end-to-end via the same fn WP-5 will call, with
            # nothing mocked below the HTTP boundary.
            updated = await db.set_approved(db_conn, NEW_SLUG, True)
            assert updated == 1
            approved_results = await retrieve(db_conn, provider, "simulated webhook push", top_k=3)
            hit = next((r for r in approved_results if r.slug == NEW_SLUG), None)
            assert hit is not None
            assert hit.title == "New Test Publication"

            # replaying the identical push is idempotent — zero duplicates
            resp2 = await client.post("/webhook/github", data=body, headers=headers)
            data2 = await resp2.json()
            new_entry_2 = next(r for r in data2["ingested"] if r["slug"] == NEW_SLUG)
            assert new_entry_2["skipped"] is True
        finally:
            await client.close()
            await webhook_server.close()
            await fake_github.close()


async def test_webhook_rejects_bad_signature(db_conn, monkeypatch):
    monkeypatch.setattr(Config, "GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    webhook_app = web.Application()
    webhook_app["db_conn"] = db_conn
    webhook_app["embedding_provider"] = HashingEmbeddingProvider(dim=Config.EMBEDDING_DIM)
    webhook_app.router.add_post("/webhook/github", handle_webhook)

    async with aiohttp.ClientSession() as http_session:
        webhook_app["http_session"] = http_session
        server = TestServer(webhook_app)
        await server.start_server()
        client = aiohttp.ClientSession(base_url=f"http://127.0.0.1:{server.port}")
        try:
            body = _push_payload_adding_new_pdf()
            resp = await client.post(
                "/webhook/github",
                data=body,
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": _sign("wrong-secret", body),
                    "Content-Type": "application/json",
                },
            )
            assert resp.status == 401
        finally:
            await client.close()
            await server.close()


async def test_webhook_ignores_non_main_branch_push_with_zero_ingestion(db_conn, monkeypatch):
    """Owner directive (main-branch-only rule, docs/BUILD_HANDOFF.md): a
    push to any ref other than refs/heads/main must be a pure no-op -- no
    fetch, no ingest, not even an attempt -- since non-main branches may
    carry unreleased/sensitive content. GITHUB_REPO_BRANCH defaults to
    "main", so a refs/heads/dev push must be ignored without ever reaching
    GitHub (no fake server is even started here -- if the code tried to
    fetch, this test would hang/error on connection refused)."""
    monkeypatch.setattr(Config, "GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    webhook_app = web.Application()
    webhook_app["db_conn"] = db_conn
    webhook_app["embedding_provider"] = HashingEmbeddingProvider(dim=Config.EMBEDDING_DIM)
    webhook_app.router.add_post("/webhook/github", handle_webhook)

    chunk_count_before = await db.count_chunks(db_conn)

    async with aiohttp.ClientSession() as http_session:
        webhook_app["http_session"] = http_session
        server = TestServer(webhook_app)
        await server.start_server()
        client = aiohttp.ClientSession(base_url=f"http://127.0.0.1:{server.port}")
        try:
            payload = {
                "ref": "refs/heads/dev",
                "commits": [
                    {
                        "added": [f"public/assets/documents/{NEW_SLUG}.pdf", "src/internal-updates.html"],
                        "modified": [],
                        "removed": [],
                    }
                ],
            }
            body = json.dumps(payload).encode("utf-8")
            resp = await client.post(
                "/webhook/github",
                data=body,
                headers={
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": _sign(WEBHOOK_SECRET, body),
                    "Content-Type": "application/json",
                },
            )
            assert resp.status == 202
            data = await resp.json()
            assert data == {"ignored": "ref=refs/heads/dev"}
        finally:
            await client.close()
            await server.close()

    assert await db.count_chunks(db_conn) == chunk_count_before
    row_count = await db_conn.fetchval("SELECT count(*) FROM documents")
    assert row_count == 0
