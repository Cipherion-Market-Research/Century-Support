"""WP-7c: serving quarantine.

Acceptance covered here: new document invisible to retrieval until
approved; superseded document's chunks absent from retrieve() results;
grandfathered corpus docs still served; revoke instantly pulls an approved
doc back out of retrieval; the QUARANTINE_ENABLED kill switch.
"""
import json
from pathlib import Path

import pytest

from pubs_rag import db, ingest
from pubs_rag.config import Config
from pubs_rag.embeddings import HashingEmbeddingProvider
from pubs_rag.quarantine import GRANDFATHERED_SHA256, is_grandfathered
from pubs_rag.retrieval import retrieve

KB_SOURCE = Path(__file__).resolve().parents[2] / "data" / "kb_source"


@pytest.fixture
def provider():
    return HashingEmbeddingProvider(dim=Config.EMBEDDING_DIM)


def test_grandfather_list_is_the_seeded_corpus_not_arbitrary():
    assert len(GRANDFATHERED_SHA256) == 12
    assert is_grandfathered("d81cb03825264d79ed0dfeb9b67a4b8a828eafbbe78c4f7b480a7ba948832a55")
    assert not is_grandfathered("0" * 64)


async def test_grandfathered_corpus_docs_are_served_by_default(db_conn, provider):
    """Not a frozen count: the corpus grows forever (new PDFs land via the
    webhook, un-grandfathered by construction -- see quarantine.py's module
    docstring). What must hold regardless of corpus size is that every
    document GRANDFATHERED_SHA256 actually names, and that is still present
    in the current inventory with extraction=="ok", lands approved. A
    grandfathered sha256 whose original doc has since left the corpus
    (renamed/removed) is simply not ingested at all -- nothing to assert
    about it here."""
    await ingest.ingest_inventory(db_conn, provider, str(KB_SOURCE))

    inventory = json.loads((KB_SOURCE / "inventory.json").read_text())
    grandfathered_in_corpus = {
        e["sha256"]
        for e in inventory
        if e["kind"] == "pdf" and e.get("extraction") == "ok" and e["sha256"] in GRANDFATHERED_SHA256
    }
    assert grandfathered_in_corpus, "fixture/inventory drift: no grandfathered docs found in current inventory"

    rows = await db_conn.fetch("SELECT sha256, approved FROM documents")
    approved_by_sha = {r["sha256"]: r["approved"] for r in rows}

    for sha256 in grandfathered_in_corpus:
        assert approved_by_sha.get(sha256) is True

    results = await retrieve(db_conn, provider, "burn cycle", top_k=3)
    assert any(r.slug == "algorithmic-austerity" for r in results)


async def test_new_document_invisible_until_approved(db_conn, provider):
    doc = {
        "sha256": "1" * 64,
        "kind": "pdf",
        "slug": "brand-new-pub",
        "title": "Brand New Publication",
        "date": "July 20, 2026",
        "source_url": "https://ciphex.io/assets/documents/brand-new-pub.pdf",
        "listed_on": "ecosystem-updates",
    }
    result = await ingest.ingest_document(db_conn, provider, doc, "unique content about a brand new topic zzyzx")
    assert result.skipped is False

    row = await db_conn.fetchrow("SELECT approved FROM documents WHERE sha256 = $1", "1" * 64)
    assert row["approved"] is False

    results = await retrieve(db_conn, provider, "zzyzx", top_k=5)
    assert not any(r.slug == "brand-new-pub" for r in results)

    # Admin escape hatch still sees it.
    admin_results = await retrieve(db_conn, provider, "zzyzx", top_k=5, include_unapproved=True)
    assert any(r.slug == "brand-new-pub" for r in admin_results)

    # Approve it -> now visible via the default (non-admin) call too.
    updated = await db.set_approved(db_conn, "brand-new-pub", True)
    assert updated == 1
    results_after_approval = await retrieve(db_conn, provider, "zzyzx", top_k=5)
    assert any(r.slug == "brand-new-pub" for r in results_after_approval)


async def test_approved_doc_revoked_becomes_invisible(db_conn, provider):
    doc = {
        "sha256": "2" * 64,
        "kind": "pdf",
        "slug": "revoke-me",
        "title": "Revoke Me",
        "date": None,
        "source_url": "https://ciphex.io/assets/documents/revoke-me.pdf",
        "listed_on": "ecosystem-updates",
    }
    await ingest.ingest_document(db_conn, provider, doc, "content about qorvexnimbus widgets")
    approved = await db.set_approved(db_conn, "2" * 64, True)
    assert approved == 1
    assert any(
        r.slug == "revoke-me"
        for r in await retrieve(db_conn, provider, "qorvexnimbus", top_k=5)
    )

    revoked = await db.set_approved(db_conn, "2" * 64, False)
    assert revoked == 1
    assert not any(
        r.slug == "revoke-me"
        for r in await retrieve(db_conn, provider, "qorvexnimbus", top_k=5)
    )


async def test_superseded_document_chunks_absent_from_retrieval_results(db_conn, provider):
    """Distinct from the existing idempotency test's DB-level chunk check:
    this asserts the superseded doc's content is unreachable through the
    actual retrieve() path a caller uses, not just absent from the table."""
    doc_v1 = {
        "sha256": "3" * 64,
        "kind": "pdf",
        "slug": "supersede-me",
        "title": "Supersede Me v1",
        "date": "January 1, 2026",
        "source_url": "https://ciphex.io/assets/documents/supersede-me.pdf",
        "listed_on": "ecosystem-updates",
    }
    await ingest.ingest_document(db_conn, provider, doc_v1, "original quixplorbat content")
    await db.set_approved(db_conn, "3" * 64, True)
    assert any(
        r.slug == "supersede-me"
        for r in await retrieve(db_conn, provider, "quixplorbat", top_k=5)
    )

    doc_v2 = {**doc_v1, "sha256": "4" * 64, "title": "Supersede Me v2"}
    result_v2 = await ingest.ingest_document(db_conn, provider, doc_v2, "revised quixplorbat content, expanded")
    assert result_v2.superseded is True

    # Old sha's chunks are gone (cascade-deleted), and the new sha256's
    # version starts unapproved -- so the slug is invisible either way
    # until the new version is explicitly approved.
    assert not any(
        r.slug == "supersede-me"
        for r in await retrieve(db_conn, provider, "quixplorbat", top_k=5)
    )
    old_chunks = await db_conn.fetch(
        "SELECT 1 FROM chunks WHERE document_sha256 = $1", "3" * 64
    )
    assert old_chunks == []

    # Approving the new version restores visibility (proves this isn't
    # simply "the topic is now unfindable" -- the *new* doc serves once
    # reviewed).
    await db.set_approved(db_conn, "4" * 64, True)
    assert any(
        r.slug == "supersede-me"
        for r in await retrieve(db_conn, provider, "quixplorbat", top_k=5)
    )


async def test_quarantine_disabled_flag_serves_everything_regardless_of_approval(db_conn, provider, monkeypatch):
    monkeypatch.setattr(Config, "QUARANTINE_ENABLED", False)
    doc = {
        "sha256": "5" * 64,
        "kind": "pdf",
        "slug": "unapproved-but-flag-off",
        "title": "Unapproved But Flag Off",
        "date": None,
        "source_url": "https://ciphex.io/assets/documents/unapproved-but-flag-off.pdf",
        "listed_on": "ecosystem-updates",
    }
    await ingest.ingest_document(db_conn, provider, doc, "content about wibbleflax devices")
    row = await db_conn.fetchrow("SELECT approved FROM documents WHERE sha256 = $1", "5" * 64)
    assert row["approved"] is False  # ingestion bookkeeping is unaffected by the flag

    results = await retrieve(db_conn, provider, "wibbleflax", top_k=5)
    assert any(r.slug == "unapproved-but-flag-off" for r in results)


async def test_list_pending_returns_only_unapproved_docs(db_conn, provider):
    """Not "pending is exactly one doc": the seeded corpus itself can
    legitimately contain non-grandfathered PDFs (any inventory entry whose
    sha256 isn't in GRANDFATHERED_SHA256 -- e.g. a genuinely new document
    added to the corpus after the grandfather list was frozen), so
    ingest_inventory() alone can already leave something pending before
    "pending-doc" is even ingested. What must hold regardless of how many
    that is: list_pending() never includes an approved doc, and it does
    include the one document this test explicitly leaves unapproved."""
    await ingest.ingest_inventory(db_conn, provider, str(KB_SOURCE))  # whole ok-extraction corpus, grandfathered-approved
    doc = {
        "sha256": "6" * 64,
        "kind": "pdf",
        "slug": "pending-doc",
        "title": "Pending Doc",
        "date": None,
        "source_url": "https://ciphex.io/assets/documents/pending-doc.pdf",
        "listed_on": "ecosystem-updates",
    }
    await ingest.ingest_document(db_conn, provider, doc, "some pending content")

    pending_slugs = {p["slug"] for p in await db.list_pending(db_conn)}
    assert "pending-doc" in pending_slugs

    approved_slugs = {
        r["slug"] for r in await db_conn.fetch("SELECT slug FROM documents WHERE approved = TRUE")
    }
    assert pending_slugs.isdisjoint(approved_slugs)


async def test_approve_and_revoke_accept_slug_or_sha256(db_conn, provider):
    doc = {
        "sha256": "7" * 64,
        "kind": "pdf",
        "slug": "identifier-test",
        "title": "Identifier Test",
        "date": None,
        "source_url": "https://ciphex.io/assets/documents/identifier-test.pdf",
        "listed_on": "ecosystem-updates",
    }
    await ingest.ingest_document(db_conn, provider, doc, "content here")

    assert await db.set_approved(db_conn, "identifier-test", True) == 1
    assert await db.set_approved(db_conn, "7" * 64, False) == 1
    assert await db.set_approved(db_conn, "no-such-slug", True) == 0
