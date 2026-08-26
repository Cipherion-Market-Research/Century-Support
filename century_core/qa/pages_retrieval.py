"""Wrapper over pubs_rag.retrieval.retrieve_pages -- the pages RAG corpus
(Sprint 3), a SECOND, SEPARATE index from the Internal-Updates corpus
qa/router.py's _rag_search already queries (see pubs_rag/db.py's module
docstring for why pages and PDFs are never mixed into one index; a July
2026 finding showed the two rank badly against each other in one shared
index).

None-safe like _rag_search in qa/router.py: stores.rag_conn/rag_provider
are the SAME connection/embedding-provider pair used for both corpora
(site_pages/page_chunks live in the same Postgres database as
documents/chunks, just separate tables) -- when either is None (no RAG
backend wired up, e.g. every test using the stub_stores fixture), this
returns [] rather than erroring, exactly like the existing RAG path.
"""
from century_core.config import Config

# Top-3 pages hits per the Sprint 3 brief -- deliberately smaller than
# RAG_TOP_K (Internal Updates), since a page match is usually one clearly
# relevant page rather than several chunks worth citing.
PAGES_TOP_K = 3


async def search_pages(stores, question: str):
    if stores.rag_conn is None or stores.rag_provider is None:
        return []
    from pubs_rag.retrieval import retrieve_pages

    hits = await retrieve_pages(stores.rag_conn, stores.rag_provider, question, top_k=PAGES_TOP_K)
    # Reuses RAG_MIN_SCORE (Sprint 3 brief: "min-score reuse RAG_MIN_SCORE")
    # rather than a separate pages-specific threshold -- one tuning knob,
    # not two, until real query traffic shows pages need a different bar.
    return [h for h in hits if h.score >= Config.RAG_MIN_SCORE]
