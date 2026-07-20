"""Postgres + pgvector storage layer.

asyncpg throughout (not psycopg2) so the webhook HTTP server (aiohttp) never
blocks its event loop on a DB call.

Idempotency contract (WP-4 acceptance: "re-run produces zero duplicates"):
`documents.sha256` is the primary key. `ingest.ingest_document` looks up the
existing sha256 for a slug before writing — an identical re-run (same
bytes -> same sha256) is a no-op; a changed publication (new bytes -> new
sha256 for a known slug) supersedes the old document row, which cascades
to delete its chunks, so a slug never has two documents' chunks live at
once.
"""
import asyncpg
from pgvector.asyncpg import register_vector

from pubs_rag.config import Config

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    sha256 TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    date TEXT,
    source_url TEXT NOT NULL,
    listed_on TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS documents_slug_idx ON documents (slug);

-- No ANN index (ivfflat/hnsw) yet: at this corpus size (tens of documents,
-- low hundreds of chunks) a plain sequential scan over `embedding <=>` is
-- fast and gives exact nearest neighbors. Add an ivfflat/hnsw index once
-- the chunk count grows into the tens of thousands and exact scan latency
-- becomes a problem.
CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    document_sha256 TEXT NOT NULL REFERENCES documents(sha256) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR({dim}) NOT NULL,
    UNIQUE (document_sha256, chunk_index)
);
"""


async def connect(dsn: str = None) -> asyncpg.Connection:
    conn = await asyncpg.connect(dsn or Config.POSTGRES_DSN)
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    await register_vector(conn)
    return conn


async def init_schema(conn: asyncpg.Connection, dim: int = None) -> None:
    await conn.execute(DDL.format(dim=dim or Config.EMBEDDING_DIM))


async def get_document_sha_by_slug(conn: asyncpg.Connection, slug: str) -> str | None:
    return await conn.fetchval("SELECT sha256 FROM documents WHERE slug = $1", slug)


async def delete_document(conn: asyncpg.Connection, sha256: str) -> None:
    # ON DELETE CASCADE on chunks.document_sha256 removes its chunks too.
    await conn.execute("DELETE FROM documents WHERE sha256 = $1", sha256)


async def upsert_document(
    conn: asyncpg.Connection,
    *,
    sha256: str,
    kind: str,
    slug: str,
    title: str,
    date: str | None,
    source_url: str,
    listed_on: str | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO documents (sha256, kind, slug, title, date, source_url, listed_on)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (sha256) DO NOTHING
        """,
        sha256,
        kind,
        slug,
        title,
        date,
        source_url,
        listed_on,
    )


async def insert_chunks(
    conn: asyncpg.Connection, sha256: str, chunks: list[str], embeddings: list[list[float]]
) -> None:
    rows = [(sha256, i, content, embedding) for i, (content, embedding) in enumerate(zip(chunks, embeddings))]
    await conn.executemany(
        """
        INSERT INTO chunks (document_sha256, chunk_index, content, embedding)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (document_sha256, chunk_index) DO NOTHING
        """,
        rows,
    )


async def count_chunks(conn: asyncpg.Connection) -> int:
    return await conn.fetchval("SELECT count(*) FROM chunks")


async def search_chunks(conn: asyncpg.Connection, query_embedding: list[float], top_k: int = 5) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT
            c.content,
            c.chunk_index,
            d.title,
            d.date,
            d.source_url,
            d.slug,
            d.kind,
            1 - (c.embedding <=> $1) AS score
        FROM chunks c
        JOIN documents d ON d.sha256 = c.document_sha256
        ORDER BY c.embedding <=> $1
        LIMIT $2
        """,
        query_embedding,
        top_k,
    )
    return [dict(r) for r in rows]
