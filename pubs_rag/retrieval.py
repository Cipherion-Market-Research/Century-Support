"""Retrieval function: query -> ranked chunks with citation metadata.

This is the function WP-5 (Century Core) calls for RAG answers; each result
carries everything C2's `fact`/`paragraph` blocks need to cite a source
(title + date + source_url) without a second lookup.
"""
from dataclasses import dataclass

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


async def retrieve(conn, provider: EmbeddingProvider, query: str, top_k: int = 5) -> list[RetrievedChunk]:
    from pubs_rag import db

    [query_embedding] = provider.embed([query])
    rows = await db.search_chunks(conn, query_embedding, top_k)
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
