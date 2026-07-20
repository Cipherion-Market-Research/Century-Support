"""Runtime store bundle passed to every command/Q&A handler.

Tests build a Stores with a real (or fixture) FactsStore, an in-memory
fake KpiReader, a StubLLMProvider, and rag_conn/rag_provider left None —
see century_core/tests/conftest.py. Production wiring lives in app.py.
"""
from dataclasses import dataclass
from typing import Any, Optional

from facts_store import FactsStore

from century_core.kpi_reader import KpiReader
from century_core.llm import LLMProvider


@dataclass
class Stores:
    facts: FactsStore
    kpi: KpiReader  # kpi.redis is also reused directly by /v1/broadcasts to enqueue
    llm: LLMProvider
    rag_conn: Optional[Any] = None  # asyncpg connection into pubs_rag's DB, or None if unavailable
    rag_provider: Optional[Any] = None  # pubs_rag embeddings.EmbeddingProvider, or None
