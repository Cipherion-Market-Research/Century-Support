import asyncpg
import pytest

from pubs_rag import db


@pytest.fixture
async def db_conn():
    """Real Postgres+pgvector connection for integration tests. Skips
    (rather than fails) when no database is reachable, so the offline unit
    tests still run in an environment without Postgres — see
    PUBS_RAG_POSTGRES_DSN in pubs_rag/config.py."""
    try:
        conn = await db.connect()
    except (OSError, asyncpg.PostgresError) as e:
        pytest.skip(f"no Postgres reachable: {e}")
        return

    await db.init_schema(conn)
    await conn.execute("TRUNCATE chunks, documents RESTART IDENTITY CASCADE")
    try:
        yield conn
    finally:
        await conn.close()
