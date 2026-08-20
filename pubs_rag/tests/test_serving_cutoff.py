"""Serving recency cutoff (positioning-freshness policy, owner feedback
2026-08-19): retrieval.retrieve() must exclude approved-but-stale documents
dated before Config.SERVE_DOCS_SINCE, independent of the WP-7c quarantine
`approved` gate covered by test_quarantine.py.
"""
from datetime import date

import pytest

from pubs_rag import date_utils, ingest
from pubs_rag.config import Config
from pubs_rag.embeddings import HashingEmbeddingProvider
from pubs_rag.retrieval import retrieve


@pytest.fixture
def provider():
    return HashingEmbeddingProvider(dim=Config.EMBEDDING_DIM)


async def _ingest_and_approve(db_conn, provider, *, sha256, slug, title, date_str, content):
    doc = {
        "sha256": sha256,
        "kind": "pdf",
        "slug": slug,
        "title": title,
        "date": date_str,
        "source_url": f"https://ciphex.io/assets/documents/{slug}.pdf",
        "listed_on": "internal-updates",
    }
    from pubs_rag import db

    await ingest.ingest_document(db_conn, provider, doc, content)
    approved = await db.set_approved(db_conn, sha256, True)
    assert approved == 1


async def test_pre_cutoff_document_excluded_from_retrieval_even_when_approved(db_conn, provider):
    # Default cutoff is 2026-05-01 -- a document dated before it must not
    # be retrievable even though it's explicitly approved (the quarantine
    # gate passing is not enough; the freshness gate must also pass).
    await _ingest_and_approve(
        db_conn,
        provider,
        sha256="a1" * 32,
        slug="pre-cutoff-doc",
        title="Pre-Cutoff Update",
        date_str="April 15, 2026",
        content="unique content about quarnoxfizzle widgets",
    )

    results = await retrieve(db_conn, provider, "quarnoxfizzle", top_k=5)
    assert not any(r.slug == "pre-cutoff-doc" for r in results)

    # The admin escape hatch is about approval state, not freshness -- it
    # does not bypass the recency cutoff either.
    admin_results = await retrieve(db_conn, provider, "quarnoxfizzle", top_k=5, include_unapproved=True)
    assert not any(r.slug == "pre-cutoff-doc" for r in admin_results)


async def test_post_cutoff_document_is_retrievable(db_conn, provider):
    await _ingest_and_approve(
        db_conn,
        provider,
        sha256="a2" * 32,
        slug="post-cutoff-doc",
        title="Post-Cutoff Update",
        date_str="July 25, 2026",
        content="unique content about zynthralquomp devices",
    )

    results = await retrieve(db_conn, provider, "zynthralquomp", top_k=5)
    assert any(r.slug == "post-cutoff-doc" for r in results)


async def test_null_date_document_excluded_and_logged(db_conn, provider, caplog):
    await _ingest_and_approve(
        db_conn,
        provider,
        sha256="a3" * 32,
        slug="null-date-doc",
        title="Null Date Update",
        date_str=None,
        content="unique content about vorptangle machines",
    )

    with caplog.at_level("WARNING", logger="pubs_rag.retrieval"):
        results = await retrieve(db_conn, provider, "vorptangle", top_k=5)

    assert not any(r.slug == "null-date-doc" for r in results)
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "null-date-doc" in message


async def test_unparseable_date_document_excluded_and_logged_once(db_conn, provider, caplog):
    await _ingest_and_approve(
        db_conn,
        provider,
        sha256="a4" * 32,
        slug="weird-date-doc",
        title="Weird Date Update",
        date_str="not-a-real-date",
        content="unique content about plexnorvium alloys",
    )

    with caplog.at_level("WARNING", logger="pubs_rag.retrieval"):
        await retrieve(db_conn, provider, "plexnorvium", top_k=5)
        # A second query against the same document must not log again --
        # "log once", not "log every query".
        await retrieve(db_conn, provider, "plexnorvium", top_k=5)

    assert len(caplog.records) == 1
    assert "weird-date-doc" in caplog.records[0].getMessage()


async def test_cutoff_disabled_serves_everything_approved_regardless_of_date(db_conn, provider, monkeypatch):
    monkeypatch.setattr(Config, "SERVE_DOCS_SINCE", "")
    await _ingest_and_approve(
        db_conn,
        provider,
        sha256="a5" * 32,
        slug="ancient-doc",
        title="Ancient Update",
        date_str="January 1, 2020",
        content="unique content about grimtharble spindles",
    )

    results = await retrieve(db_conn, provider, "grimtharble", top_k=5)
    assert any(r.slug == "ancient-doc" for r in results)


def test_parse_document_date_handles_the_real_stored_display_format():
    # "%B %d, %Y" -- the format every ecosystem-update-*.pdf's `date` field
    # actually uses in data/kb_source/inventory.json, including both
    # zero-padded and non-zero-padded days.
    assert date_utils.parse_document_date("July 25, 2026") == date(2026, 7, 25)
    assert date_utils.parse_document_date("May 08, 2026") == date(2026, 5, 8)
    assert date_utils.parse_document_date("December 31, 2025") == date(2025, 12, 31)
    assert date_utils.parse_document_date("February 27, 2026") == date(2026, 2, 27)


def test_parse_document_date_handles_iso_fallback():
    assert date_utils.parse_document_date("2026-07-20") == date(2026, 7, 20)


def test_parse_document_date_returns_none_for_null_blank_and_garbage():
    assert date_utils.parse_document_date(None) is None
    assert date_utils.parse_document_date("") is None
    assert date_utils.parse_document_date("   ") is None
    assert date_utils.parse_document_date("not-a-real-date") is None


def test_parse_cutoff_empty_string_disables():
    assert date_utils.parse_cutoff("") is None
    assert date_utils.parse_cutoff(None) is None
    assert date_utils.parse_cutoff("2026-05-01") == date(2026, 5, 1)


def test_default_cutoff_config_value():
    # Documents this module's contract: the shipped default boundary is
    # the mid-2026 rebrand date (owner feedback 2026-08-19). Adjustable via
    # PUBS_RAG_SERVE_DOCS_SINCE without a code change (see config.py).
    assert Config.SERVE_DOCS_SINCE == "2026-05-01"
