"""Tests for century_core/qa/pages_retrieval.py -- the None-safe wrapper
over pubs_rag.retrieval.retrieve_pages (Sprint 3 pages corpus)."""
from dataclasses import dataclass

from century_core.config import Config
from century_core.qa.pages_retrieval import search_pages


@dataclass
class _FakePageChunk:
    content: str
    title: str
    slug: str
    score: float
    page_url: str


async def test_search_pages_returns_empty_when_rag_conn_is_none(stub_stores):
    # stub_stores fixture leaves rag_conn=None, rag_provider=None by
    # default -- same None-safety contract as qa/router.py's _rag_search.
    assert await search_pages(stub_stores, "who is on the leadership team") == []


async def test_search_pages_returns_empty_when_rag_provider_is_none(stub_stores):
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = None
    assert await search_pages(stub_stores, "who is on the leadership team") == []


async def test_search_pages_filters_below_min_score(stub_stores, monkeypatch):
    async def fake_retrieve_pages(conn, provider, query, top_k=3, **kwargs):
        return [
            _FakePageChunk(
                content="low relevance chunk",
                title="Leadership Team",
                slug="leadership-team",
                score=Config.RAG_MIN_SCORE - 0.01,
                page_url="https://ciphex.io/leadership-team",
            ),
            _FakePageChunk(
                content="high relevance chunk",
                title="Leadership Team",
                slug="leadership-team",
                score=Config.RAG_MIN_SCORE + 0.01,
                page_url="https://ciphex.io/leadership-team",
            ),
        ]

    monkeypatch.setattr("pubs_rag.retrieval.retrieve_pages", fake_retrieve_pages)
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    results = await search_pages(stub_stores, "some query")
    assert len(results) == 1
    assert results[0].content == "high relevance chunk"


async def test_search_pages_passes_top_k_of_three(stub_stores, monkeypatch):
    seen = {}

    async def fake_retrieve_pages(conn, provider, query, top_k=3, **kwargs):
        seen["top_k"] = top_k
        return []

    monkeypatch.setattr("pubs_rag.retrieval.retrieve_pages", fake_retrieve_pages)
    stub_stores.rag_conn = object()
    stub_stores.rag_provider = object()

    await search_pages(stub_stores, "some query")
    assert seen["top_k"] == 3
