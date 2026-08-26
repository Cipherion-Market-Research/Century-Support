"""Tests for the pages RAG corpus (Sprint 3): site_pages/page_chunks --
a SECOND, SEPARATE index from documents/chunks (see pubs_rag/db.py's
module docstring for why).

Offline (no database): frontmatter-stripping, the inventory filter
(select_ingestable_page_entries), and page_url_for_slug. DB-dependent
(skip cleanly without Postgres, see conftest.py's db_conn fixture):
ingest_pages_inventory against the real committed corpus, idempotency,
supersede, approval quarantine, and retrieve_pages ranking/citation shape.
"""
import json
from pathlib import Path

import pytest

from pubs_rag import db, ingest
from pubs_rag.config import Config
from pubs_rag.embeddings import HashingEmbeddingProvider
from pubs_rag.retrieval import page_url_for_slug, retrieve_pages

KB_SOURCE = Path(__file__).resolve().parents[2] / "data" / "kb_source"
_INVENTORY = json.loads((KB_SOURCE / "inventory.json").read_text())

# Whatever inventory.json currently lists as an in-scope, ok-extraction
# page -- never a frozen number (same convention as
# test_ingest_and_retrieval.py's INGESTABLE_PDF_COUNT).
INGESTABLE_PAGE_COUNT = sum(
    1
    for e in _INVENTORY
    if e["kind"] == "page"
    and e.get("extraction") == "ok"
    and e["slug"] not in Config.PAGE_CORPUS_EXCLUDED_SLUGS
)


@pytest.fixture
def provider():
    return HashingEmbeddingProvider(dim=Config.EMBEDDING_DIM)


# ─────────────────────────── offline ───────────────────────────


def test_strip_page_frontmatter_removes_only_the_comment_block():
    raw = (
        "<!--\nsource_url: https://ciphex.io/example\nfetched: 2026-08-26\n"
        "page_title: Example\nkind: site page copy\n-->\n\n"
        "# Example\n\nBody text here."
    )
    stripped = ingest.strip_page_frontmatter(raw)
    assert "source_url:" not in stripped
    assert "fetched:" not in stripped
    assert stripped.startswith("# Example")
    assert "Body text here." in stripped


def test_strip_page_frontmatter_is_a_noop_without_a_comment_block():
    raw = "# Example\n\nBody text here."
    assert ingest.strip_page_frontmatter(raw) == raw


def test_select_ingestable_page_entries_filters_kind_exclusion_and_extraction():
    inventory = [
        {"kind": "page", "slug": "index", "extraction": "ok"},
        {"kind": "page", "slug": "insights-and-publications", "extraction": "ok"},  # excluded slug
        {"kind": "page", "slug": "404", "extraction": "ok"},  # excluded slug
        {"kind": "page", "slug": "broken-page", "extraction": "failed"},  # bad extraction
        {"kind": "pdf", "slug": "some-pdf", "extraction": "ok"},  # wrong kind
    ]
    selected = ingest.select_ingestable_page_entries(inventory)
    assert [e["slug"] for e in selected] == ["index"]


def test_select_ingestable_page_entries_against_real_inventory_matches_scope():
    selected = ingest.select_ingestable_page_entries(_INVENTORY)
    slugs = {e["slug"] for e in selected}
    assert "leadership-team" in slugs
    assert "index" in slugs
    for excluded in Config.PAGE_CORPUS_EXCLUDED_SLUGS:
        assert excluded not in slugs
    assert len(selected) == INGESTABLE_PAGE_COUNT > 0


def test_page_url_for_slug_index_is_bare_root():
    assert page_url_for_slug("index") == "https://ciphex.io/"


def test_page_url_for_slug_other_pages():
    assert page_url_for_slug("leadership-team") == "https://ciphex.io/leadership-team"


# ─────────────────────────── DB-dependent ───────────────────────────


async def test_full_pages_corpus_ingest_is_idempotent(db_conn, provider):
    first = await ingest.ingest_pages_inventory(db_conn, provider, str(KB_SOURCE))
    assert first.ingested == INGESTABLE_PAGE_COUNT > 0
    assert first.skipped == 0
    chunk_count_after_first = await db.count_page_chunks(db_conn)
    assert chunk_count_after_first > 0
    # Separate corpus: ingesting pages must never touch documents/chunks.
    assert await db.count_chunks(db_conn) == 0

    second = await ingest.ingest_pages_inventory(db_conn, provider, str(KB_SOURCE))
    assert second.ingested == 0
    assert second.skipped == INGESTABLE_PAGE_COUNT

    assert await db.count_page_chunks(db_conn) == chunk_count_after_first  # zero duplicates


async def test_new_page_ingested_unapproved_and_invisible_to_retrieve_pages(db_conn, provider):
    await ingest.ingest_pages_inventory(db_conn, provider, str(KB_SOURCE))

    # WP-7c-style quarantine, extended to pages: nothing is grandfathered,
    # so retrieve_pages() over the freshly-seeded corpus finds nothing
    # until an operator approves it.
    results = await retrieve_pages(db_conn, provider, "leadership team experience", top_k=5)
    assert results == []

    pending = await db.list_pending_pages(db_conn)
    pending_slugs = {row["slug"] for row in pending}
    assert "leadership-team" in pending_slugs
    assert len(pending) == INGESTABLE_PAGE_COUNT


async def test_approve_makes_a_page_eligible_for_retrieve_pages(db_conn, provider):
    await ingest.ingest_pages_inventory(db_conn, provider, str(KB_SOURCE))
    updated = await db.set_page_approved(db_conn, "leadership-team", True)
    assert updated == 1

    results = await retrieve_pages(db_conn, provider, "leadership team experience", top_k=5)
    assert results, "expected at least one approved page chunk"
    assert any(r.slug == "leadership-team" for r in results)
    top = next(r for r in results if r.slug == "leadership-team")
    assert top.page_url == "https://ciphex.io/leadership-team"
    assert top.title  # non-empty


async def test_revoke_pulls_a_page_back_out_of_retrieve_pages(db_conn, provider):
    await ingest.ingest_pages_inventory(db_conn, provider, str(KB_SOURCE))
    await db.set_page_approved(db_conn, "leadership-team", True)
    assert any(
        r.slug == "leadership-team"
        for r in await retrieve_pages(db_conn, provider, "leadership team experience", top_k=5)
    )

    await db.set_page_approved(db_conn, "leadership-team", False)
    assert not any(
        r.slug == "leadership-team"
        for r in await retrieve_pages(db_conn, provider, "leadership team experience", top_k=5)
    )


async def test_retrieve_pages_include_unapproved_escape_hatch(db_conn, provider):
    await ingest.ingest_pages_inventory(db_conn, provider, str(KB_SOURCE))
    results = await retrieve_pages(
        db_conn, provider, "leadership team experience", top_k=5, include_unapproved=True
    )
    assert any(r.slug == "leadership-team" for r in results)


async def test_updated_page_content_supersedes_stale_page(db_conn, provider):
    page_v1 = {
        "sha256": "a" * 64,
        "slug": "test-page",
        "title": "Test Page v1",
        "source_url": "https://ciphex.io/test-page",
        "captured_at": "2026-08-01",
        "source_ref": "deadbeef",
    }
    result_v1 = await ingest.ingest_page_document(db_conn, provider, page_v1, "original page content about widgets")
    assert result_v1.skipped is False
    assert result_v1.superseded is False

    page_v2 = {**page_v1, "sha256": "b" * 64, "title": "Test Page v2"}
    result_v2 = await ingest.ingest_page_document(db_conn, provider, page_v2, "revised page content about gadgets")
    assert result_v2.skipped is False
    assert result_v2.superseded is True

    row = await db_conn.fetchrow("SELECT sha256, title FROM site_pages WHERE slug = $1", "test-page")
    assert row["sha256"] == "b" * 64
    assert row["title"] == "Test Page v2"

    remaining = await db_conn.fetch(
        "SELECT page_sha256 FROM page_chunks WHERE page_sha256 = $1", "a" * 64
    )
    assert remaining == []  # old chunks cascade-deleted, no orphans


async def test_new_page_document_defaults_unapproved_no_grandfathering(db_conn, provider):
    page = {
        "sha256": "c" * 64,
        "slug": "another-test-page",
        "title": "Another Test Page",
        "source_url": "https://ciphex.io/another-test-page",
        "captured_at": "2026-08-26",
        "source_ref": "cafef00d",
    }
    await ingest.ingest_page_document(db_conn, provider, page, "some brand new page content")
    row = await db_conn.fetchrow("SELECT approved FROM site_pages WHERE sha256 = $1", "c" * 64)
    assert row["approved"] is False


async def test_recency_cutoff_does_not_apply_to_pages(db_conn, provider, monkeypatch):
    # A page captured long before Config.SERVE_DOCS_SINCE must still serve
    # -- pages have no recency-cutoff gate at all (see retrieval.py's
    # module docstring: freshness is the harvester's job, not a serving
    # filter).
    monkeypatch.setattr(Config, "SERVE_DOCS_SINCE", "2099-01-01")
    page = {
        "sha256": "d" * 64,
        "slug": "old-captured-page",
        "title": "Old Captured Page",
        "source_url": "https://ciphex.io/old-captured-page",
        "captured_at": "2020-01-01",
        "source_ref": "old-ref",
    }
    await ingest.ingest_page_document(db_conn, provider, page, "some old-captured but still-current page content")
    await db.set_page_approved(db_conn, "old-captured-page", True)

    results = await retrieve_pages(db_conn, provider, "old-captured but still-current page content", top_k=3)
    assert any(r.slug == "old-captured-page" for r in results)
