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

Serving quarantine (WP-7c): `documents.approved` gates whether a document's
chunks are eligible for retrieval (see retrieval.retrieve() /
search_chunks()). New rows default approved=FALSE; the original 12-document
corpus is grandfathered TRUE by an explicit sha256 allowlist (see
quarantine.py), not by "whatever is already in this table".

Pages corpus (Sprint 3): `site_pages` + `page_chunks` are a SECOND,
SEPARATE corpus from `documents` + `chunks` above -- deliberately not one
shared table. A July 2026 finding showed pages and PDFs mixed into one RAG
index rank badly against each other (exact-phrase page copy crowds out
publication prose discussing the same topic, and vice versa), so the two
are kept structurally apart: separate tables, separate retrieval functions
(retrieval.retrieve() vs retrieval.retrieve_pages()), joined only at the
router layer (century_core/qa/router.py / pages_retrieval.py). The schema
otherwise mirrors `documents`/`chunks` deliberately: sha256 primary key
(same idempotency contract -- identical re-harvest is a no-op, changed
bytes supersede the old row and cascade-delete its chunks), an `approved`
quarantine column defaulting FALSE (own approve/revoke/list-pending CLI
support -- see main.py's --pages flag), plus `captured_at` (the harvest
date recorded in data/kb_source/inventory.json's "harvested_at") and
`source_ref` (the ciphex-website commit sha the page was harvested from --
inventory.json's "source_ref", see scripts/harvest_pages.py). Unlike
`documents`, there is no recency-cutoff gate on pages at serving time:
retrieval.retrieve_pages() never applies Config.SERVE_DOCS_SINCE -- pages
are the always-current site, freshness is scripts/harvest_pages.py's job
(re-run it, not a serving-time filter), see retrieval.py's module
docstring.
"""
import asyncpg

from pubs_rag.config import Config
from pubs_rag.quarantine import looks_like_sha256

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
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Belt-and-suspenders for a documents table that already existed before the
-- WP-7c quarantine column landed: CREATE TABLE IF NOT EXISTS above is a
-- no-op against an existing table, so the column needs its own migration
-- statement. Safe/idempotent to run on every startup.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT FALSE;

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

-- Pages corpus (Sprint 3) -- a second, separate corpus from documents/
-- chunks above; see this module's docstring for why.
CREATE TABLE IF NOT EXISTS site_pages (
    sha256 TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    captured_at TEXT,
    source_ref TEXT,
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE site_pages ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS site_pages_slug_idx ON site_pages (slug);

CREATE TABLE IF NOT EXISTS page_chunks (
    id BIGSERIAL PRIMARY KEY,
    page_sha256 TEXT NOT NULL REFERENCES site_pages(sha256) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR({dim}) NOT NULL,
    UNIQUE (page_sha256, chunk_index)
);
"""


async def connect(dsn: str = None) -> asyncpg.Connection:
    conn = await asyncpg.connect(dsn or Config.POSTGRES_DSN)
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Imported here (after the connection attempt), rather than at module
    # scope, so this module -- and anything that merely imports it, e.g. the
    # test conftest -- can be collected, and DB-dependent tests can still
    # skip cleanly on "no Postgres reachable", in an environment without
    # pgvector installed. The deployed service always has it (see
    # requirements.txt), so a genuinely missing pgvector still fails loudly
    # once a real connection is available, just at connect time instead of
    # import time.
    from pgvector.asyncpg import register_vector

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
    approved: bool = False,
) -> None:
    await conn.execute(
        """
        INSERT INTO documents (sha256, kind, slug, title, date, source_url, listed_on, approved)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (sha256) DO NOTHING
        """,
        sha256,
        kind,
        slug,
        title,
        date,
        source_url,
        listed_on,
        approved,
    )


def _rowcount(execute_result: str) -> int:
    """asyncpg Connection.execute() returns a command tag like "UPDATE 3"."""
    try:
        return int(execute_result.rsplit(" ", 1)[-1])
    except (ValueError, AttributeError):
        return 0


async def set_approved(conn: asyncpg.Connection, identifier: str, approved: bool) -> int:
    """Set `approved` on the document(s) matching `identifier` (a full
    sha256 or a slug). Returns the number of rows updated."""
    if looks_like_sha256(identifier):
        result = await conn.execute(
            "UPDATE documents SET approved = $1 WHERE sha256 = $2", approved, identifier
        )
    else:
        result = await conn.execute(
            "UPDATE documents SET approved = $1 WHERE slug = $2", approved, identifier
        )
    return _rowcount(result)


async def list_pending(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT sha256, slug, title, date, source_url, ingested_at
        FROM documents
        WHERE approved = FALSE
        ORDER BY ingested_at
        """
    )
    return [dict(r) for r in rows]


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


async def search_chunks(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    top_k: int = 5,
    *,
    approved_only: bool = True,
) -> list[dict]:
    # WP-7c serving quarantine: approved_only=True (the default) restricts
    # results to documents.approved=TRUE -- an unapproved/pending document's
    # chunks are never eligible for a match, not merely deprioritized.
    where_clause = "WHERE d.approved = TRUE" if approved_only else ""
    rows = await conn.fetch(
        f"""
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
        {where_clause}
        ORDER BY c.embedding <=> $1
        LIMIT $2
        """,
        query_embedding,
        top_k,
    )
    return [dict(r) for r in rows]


# ─────────────────────── Pages corpus (Sprint 3) ───────────────────────
# Mirrors the documents/chunks functions above -- see this module's
# docstring for why the two corpora are kept in separate tables.


async def get_page_sha_by_slug(conn: asyncpg.Connection, slug: str) -> str | None:
    return await conn.fetchval("SELECT sha256 FROM site_pages WHERE slug = $1", slug)


async def delete_page(conn: asyncpg.Connection, sha256: str) -> None:
    # ON DELETE CASCADE on page_chunks.page_sha256 removes its chunks too.
    await conn.execute("DELETE FROM site_pages WHERE sha256 = $1", sha256)


async def upsert_page(
    conn: asyncpg.Connection,
    *,
    sha256: str,
    slug: str,
    title: str,
    source_url: str,
    captured_at: str | None,
    source_ref: str | None,
    approved: bool = False,
) -> None:
    await conn.execute(
        """
        INSERT INTO site_pages (sha256, slug, title, source_url, captured_at, source_ref, approved)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (sha256) DO NOTHING
        """,
        sha256,
        slug,
        title,
        source_url,
        captured_at,
        source_ref,
        approved,
    )


async def set_page_approved(conn: asyncpg.Connection, identifier: str, approved: bool) -> int:
    """Set `approved` on the page(s) matching `identifier` (a full sha256
    or a slug). Returns the number of rows updated -- same shape as
    set_approved() above, for the documents corpus."""
    if looks_like_sha256(identifier):
        result = await conn.execute(
            "UPDATE site_pages SET approved = $1 WHERE sha256 = $2", approved, identifier
        )
    else:
        result = await conn.execute(
            "UPDATE site_pages SET approved = $1 WHERE slug = $2", approved, identifier
        )
    return _rowcount(result)


async def list_pending_pages(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT sha256, slug, title, source_url, captured_at, ingested_at
        FROM site_pages
        WHERE approved = FALSE
        ORDER BY ingested_at
        """
    )
    return [dict(r) for r in rows]


async def insert_page_chunks(
    conn: asyncpg.Connection, sha256: str, chunks: list[str], embeddings: list[list[float]]
) -> None:
    rows = [(sha256, i, content, embedding) for i, (content, embedding) in enumerate(zip(chunks, embeddings))]
    await conn.executemany(
        """
        INSERT INTO page_chunks (page_sha256, chunk_index, content, embedding)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (page_sha256, chunk_index) DO NOTHING
        """,
        rows,
    )


async def count_page_chunks(conn: asyncpg.Connection) -> int:
    return await conn.fetchval("SELECT count(*) FROM page_chunks")


async def search_page_chunks(
    conn: asyncpg.Connection,
    query_embedding: list[float],
    top_k: int = 5,
    *,
    approved_only: bool = True,
) -> list[dict]:
    # Same serving-quarantine shape as search_chunks() above, but NO
    # recency-cutoff filter -- pages have no equivalent of
    # Config.SERVE_DOCS_SINCE (see retrieval.retrieve_pages()'s docstring).
    where_clause = "WHERE p.approved = TRUE" if approved_only else ""
    rows = await conn.fetch(
        f"""
        SELECT
            pc.content,
            pc.chunk_index,
            p.title,
            p.source_url,
            p.slug,
            p.captured_at,
            1 - (pc.embedding <=> $1) AS score
        FROM page_chunks pc
        JOIN site_pages p ON p.sha256 = pc.page_sha256
        {where_clause}
        ORDER BY pc.embedding <=> $1
        LIMIT $2
        """,
        query_embedding,
        top_k,
    )
    return [dict(r) for r in rows]
