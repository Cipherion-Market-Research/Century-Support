"""Retrieval function: query -> ranked chunks with citation metadata.

This is the function WP-5 (Century Core) calls for RAG answers; each result
carries everything C2's `fact`/`paragraph` blocks need to cite a source
(title + date + source_url) without a second lookup.

Serving quarantine (WP-7c): unapproved documents (not yet reviewed, or a
superseded/retracted version) are excluded by default -- a document must be
explicitly approved (`python -m pubs_rag.main approve`) before its chunks
are eligible for a user-facing answer. `include_unapproved=True` is the
admin/test escape hatch (e.g. `list-pending`-adjacent tooling); ordinary
callers (WP-5) never pass it. PUBS_RAG_QUARANTINE_ENABLED=false is the kill
switch that turns the whole filter off (serves regardless of approval
state), for parity with kpi_sync's per-source enable-flag pattern.
"""
from dataclasses import dataclass

from pubs_rag.config import Config
from pubs_rag.embeddings import EmbeddingProvider


@dataclass
class RetrievedChunk:
    content: str
    title: str
    date: str | None
    source_url: str
    slug: str
    kind: str
    score: float


async def retrieve(
    conn,
    provider: EmbeddingProvider,
    query: str,
    top_k: int = 5,
    *,
    include_unapproved: bool = False,
) -> list[RetrievedChunk]:
    from pubs_rag import db

    approved_only = Config.QUARANTINE_ENABLED and not include_unapproved
    [query_embedding] = provider.embed([query])
    rows = await db.search_chunks(conn, query_embedding, top_k, approved_only=approved_only)
    return [
        RetrievedChunk(
            content=row["content"],
            title=row["title"],
            date=row["date"],
            source_url=row["source_url"],
            slug=row["slug"],
            kind=row["kind"],
            score=row["score"],
        )
        for row in rows
    ]
