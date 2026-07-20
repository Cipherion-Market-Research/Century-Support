"""FastAPI app factory. Wires real facts_store/Redis/pubs_rag/LLM stores
into app.state via a lifespan context manager; routes read them through
century_core.deps.get_stores. Tests build their own app and override
get_stores instead of calling create_app() — see tests/conftest.py.
"""
import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis_lib
from fastapi import FastAPI

from century_core.config import Config
from century_core.kpi_reader import KpiReader
from century_core.llm import get_llm_provider
from century_core.routes import broadcasts, facts, health, messages
from century_core.stores import Stores
from facts_store import default_store

logging.basicConfig(level=Config.LOG_LEVEL)
logger = logging.getLogger(__name__)


async def _build_rag():
    """Best-effort: publications RAG is a real dependency (Postgres +
    embeddings API) that may not be reachable in every deployment stage.
    Q&A and /publications degrade gracefully (facts.yaml-only answers,
    "index unavailable" warning) rather than the whole service failing to
    start when it's down."""
    try:
        from pubs_rag import db as pubs_rag_db
        from pubs_rag.config import Config as PubsRagConfig
        from pubs_rag.embeddings import get_embedding_provider

        conn = await pubs_rag_db.connect(Config.PUBS_RAG_POSTGRES_DSN)
        provider = get_embedding_provider(PubsRagConfig)
        return conn, provider
    except Exception as exc:
        logger.warning("publications RAG unavailable at startup, degrading gracefully: %s", exc)
        return None, None


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = redis_lib.from_url(Config.REDIS_URL, encoding="utf-8", decode_responses=True)
    rag_conn, rag_provider = await _build_rag()

    app.state.stores = Stores(
        facts=default_store(),
        kpi=KpiReader(redis_client),
        llm=get_llm_provider(Config),
        rag_conn=rag_conn,
        rag_provider=rag_provider,
    )

    yield

    await app.state.stores.kpi.redis.aclose()
    if app.state.stores.rag_conn is not None:
        await app.state.stores.rag_conn.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Century Core", version="1.0", lifespan=lifespan)

    app.include_router(messages.router)
    app.include_router(facts.router)
    app.include_router(broadcasts.router)
    app.include_router(health.router)

    return app
