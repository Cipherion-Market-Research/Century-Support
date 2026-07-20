from pathlib import Path

import pytest

from pubs_rag import db, ingest
from pubs_rag.config import Config
from pubs_rag.embeddings import HashingEmbeddingProvider
from pubs_rag.retrieval import retrieve

KB_SOURCE = Path(__file__).resolve().parents[2] / "data" / "kb_source"


@pytest.fixture
def provider():
    return HashingEmbeddingProvider(dim=Config.EMBEDDING_DIM)


async def test_full_corpus_ingest_is_idempotent(db_conn, provider):
    first = await ingest.ingest_inventory(db_conn, provider, str(KB_SOURCE))
    assert first.ingested == 12  # PDFs only — see ingest.py module docstring
    assert first.skipped == 0
    chunk_count_after_first = await db.count_chunks(db_conn)
    assert chunk_count_after_first > 0

    second = await ingest.ingest_inventory(db_conn, provider, str(KB_SOURCE))
    assert second.ingested == 0
    assert second.skipped == 12

    chunk_count_after_second = await db.count_chunks(db_conn)
    assert chunk_count_after_second == chunk_count_after_first  # zero duplicates


async def test_query_burn_cycle_returns_tokenomics_publication_with_citation(db_conn, provider):
    await ingest.ingest_inventory(db_conn, provider, str(KB_SOURCE))

    results = await retrieve(db_conn, provider, "burn cycle", top_k=3)
    assert results, "expected at least one result"

    top = results[0]
    assert top.slug == "algorithmic-austerity"
    assert top.kind == "pdf"
    assert top.title == "Self-Optimizing Smart Contracts"
    assert top.date == "January 28, 2025"
    assert top.source_url == "https://ciphex.io/assets/documents/algorithmic-austerity.pdf"


async def test_updated_content_supersedes_stale_document(db_conn, provider):
    doc_v1 = {
        "sha256": "a" * 64,
        "kind": "pdf",
        "slug": "test-doc",
        "title": "Test Doc v1",
        "date": "January 1, 2026",
        "source_url": "https://ciphex.io/assets/documents/test-doc.pdf",
        "listed_on": "ecosystem-updates",
    }
    result_v1 = await ingest.ingest_document(db_conn, provider, doc_v1, "original content about widgets")
    assert result_v1.skipped is False
    assert result_v1.superseded is False

    doc_v2 = {**doc_v1, "sha256": "b" * 64, "title": "Test Doc v2"}
    result_v2 = await ingest.ingest_document(db_conn, provider, doc_v2, "revised content about gadgets")
    assert result_v2.skipped is False
    assert result_v2.superseded is True

    row = await db_conn.fetchrow("SELECT sha256, title FROM documents WHERE slug = $1", "test-doc")
    assert row["sha256"] == "b" * 64
    assert row["title"] == "Test Doc v2"

    remaining_chunks = await db_conn.fetch(
        "SELECT document_sha256 FROM chunks WHERE document_sha256 = $1", "a" * 64
    )
    assert remaining_chunks == []  # old chunks cascade-deleted, no orphans


async def test_rerun_after_supersede_is_a_noop(db_conn, provider):
    doc = {
        "sha256": "c" * 64,
        "kind": "page",
        "slug": "test-page",
        "title": "Test Page",
        "date": None,
        "source_url": "https://ciphex.io/test-page",
        "listed_on": None,
    }
    await ingest.ingest_document(db_conn, provider, doc, "some page content here")
    chunk_count = await db.count_chunks(db_conn)

    repeat = await ingest.ingest_document(db_conn, provider, doc, "some page content here")
    assert repeat.skipped is True
    assert await db.count_chunks(db_conn) == chunk_count
