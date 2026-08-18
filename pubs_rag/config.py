"""Environment-driven configuration for the publications RAG service (WP-4).

Mirrors kpi_sync/config.py's convention: every external endpoint, credential,
and tunable is an env var with a sane default, never a bare literal in
calling code.
"""
import os


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # --- Postgres / pgvector ---
    POSTGRES_DSN = _env("PUBS_RAG_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5433/pubs_rag")

    # --- Embeddings ---
    # "openai" is the production provider (matches the rest of the codebase's
    # use of OpenAI in core/ai_handler.py). "local" is a dependency-free,
    # deterministic hashing-trick provider used in tests/offline dev so the
    # suite never needs a live API key or network access. Both providers
    # emit EMBEDDING_DIM-length vectors so the pgvector column never has to
    # change shape when swapping providers.
    EMBEDDING_PROVIDER = _env("PUBS_RAG_EMBEDDING_PROVIDER", "openai")
    EMBEDDING_MODEL = _env("PUBS_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIM = _env_int("PUBS_RAG_EMBEDDING_DIM", 1536)
    OPENAI_API_KEY = _env("OPENAI_API_KEY", "")

    # --- Chunking ---
    CHUNK_SIZE_WORDS = _env_int("PUBS_RAG_CHUNK_SIZE_WORDS", 220)
    CHUNK_OVERLAP_WORDS = _env_int("PUBS_RAG_CHUNK_OVERLAP_WORDS", 40)

    # --- Corpus seed (initial ingestion inputs; see data/kb_source/inventory.json) ---
    KB_SOURCE_DIR = _env("PUBS_RAG_KB_SOURCE_DIR", "data/kb_source")

    # --- ciphex-website GitHub webhook ---
    GITHUB_WEBHOOK_SECRET = _env("PUBS_RAG_GITHUB_WEBHOOK_SECRET", "")
    GITHUB_REPO_OWNER = _env("PUBS_RAG_GITHUB_REPO_OWNER", "Cipherion-Market-Research")
    GITHUB_REPO_NAME = _env("PUBS_RAG_GITHUB_REPO_NAME", "ciphex-website")
    GITHUB_REPO_BRANCH = _env("PUBS_RAG_GITHUB_REPO_BRANCH", "main")
    GITHUB_API_BASE_URL = _env("PUBS_RAG_GITHUB_API_BASE_URL", "https://raw.githubusercontent.com")
    # ciphex-website is a private repo -- unauthenticated raw-content fetches
    # 404 in production (it only ever worked locally via the owner's stored
    # credentials). Set to a fine-grained PAT scoped read-only to this repo;
    # attached as `Authorization: Bearer <token>` on every raw-content fetch.
    # Never logged -- only its presence/absence is (see webhook.py, main.py).
    GITHUB_TOKEN = _env("PUBS_RAG_GITHUB_TOKEN", "")

    # The publication index page(s) to fetch and parse (source, not the
    # built site — see site_parser.py for why: they're server-rendered
    # multi-page-app entry HTML with data-slug/data-title/data-date/data-pdf
    # attributes baked in at build time, so a GitHub raw fetch gets the same
    # metadata a headless browser would get from the live site, without
    # needing one).
    #
    # Per the approved "Telegram & GitHub Bot Parameter Requirements"
    # (2026-08-18): the only approved knowledge sources are (a) the main
    # website crawl and (b) Internal Updates. The Insights & Publications
    # section (src/insights-and-publications.html) is strictly excluded --
    # see SERVE_INSIGHTS_AND_PUBLICATIONS below -- so it is deliberately
    # NOT listed here; only src/internal-updates.html is fetched/parsed.
    # Overridable because this page has already been renamed once on the
    # website repo (ecosystem-updates -> internal-updates, 2026-07-28); the
    # next rename should be an env change, not a code change.
    PUBLICATION_INDEX_PATHS = tuple(
        p.strip()
        for p in _env(
            "PUBS_RAG_PUBLICATION_INDEX_PATHS",
            "src/internal-updates.html",
        ).split(",")
        if p.strip()
    )
    PDF_ASSET_PATH_PREFIX = _env("PUBS_RAG_PDF_ASSET_PATH_PREFIX", "public/assets/documents/")
    SITE_BASE_URL = _env("PUBS_RAG_SITE_BASE_URL", "https://ciphex.io")

    # --- HTTP client ---
    HTTP_TIMEOUT_S = _env_int("PUBS_RAG_HTTP_TIMEOUT_S", 20)

    # --- Corpus policy (owner decision, Bot Parameter Requirements, 2026-08-18) ---
    # Per the approved "Telegram & GitHub Bot Parameter Requirements", the
    # bot's approved knowledge sources are ONLY (a) the main website crawl
    # and (b) Internal Updates (announcements & official press releases,
    # the ecosystem-update-* documents on ciphex.io/internal-updates).
    #
    # THE ENTIRE INSIGHTS & PUBLICATIONS SECTION IS EXCLUDED. This
    # supersedes the earlier "ungated-only" policy (2026-08-17, D-3), which
    # allowed the small set of public "Legacy Contributor Publications" PDFs
    # through: those legacy publications are now OUT too, regardless of
    # gating status. Nothing listed on ciphex.io/insights-and-publications
    # may be indexed, retrieved, referenced, quoted, or summarized by the
    # bot. SERVE_INSIGHTS_AND_PUBLICATIONS gates this at the page/section
    # level in site_parser.py: with the insights-and-publications page
    # already removed from PUBLICATION_INDEX_PATHS above, this is
    # belt-and-suspenders in case that index path ever reappears (e.g. an
    # env override, or a future code change that re-adds it).
    SERVE_INSIGHTS_AND_PUBLICATIONS = _env_bool("PUBS_RAG_SERVE_INSIGHTS_AND_PUBLICATIONS", False)

    # Independent, narrower defense: even for pages that ARE approved
    # sources, never ingest a document whose PDF path looks like a gated
    # teaser/preview asset rather than the real, publicly-resolvable PDF
    # (see site_parser._is_public_pdf_path). Originally written for
    # insights-and-publications' wallet-gated (SIWE) document registry
    # (GET /api/library after wallet sign-in, never present in the
    # server-rendered HTML this service reads); kept as a general safeguard
    # now that that page is excluded outright by the flag above.
    SERVE_GATED_DOCUMENTS = _env_bool("PUBS_RAG_SERVE_GATED_DOCUMENTS", False)

    # --- Serving quarantine (WP-7c) ---
    # retrieval.retrieve() filters documents.approved=false by default (an
    # explicit include_unapproved=True lets admin tooling/tests see
    # everything). Kill switch: setting this false disables the filter
    # entirely (retrieval serves regardless of approval state) -- mirrors
    # kpi_sync's KPI_SYNC_ABACUS_ENABLED-style on/off pattern.
    QUARANTINE_ENABLED = _env_bool("PUBS_RAG_QUARANTINE_ENABLED", True)

    # --- Health / webhook server ---
    HEALTH_HOST = _env("PUBS_RAG_HEALTH_HOST", "0.0.0.0")
    HEALTH_PORT = _env_int("PORT", _env_int("PUBS_RAG_HEALTH_PORT", 8081))

    LOG_LEVEL = _env("PUBS_RAG_LOG_LEVEL", "INFO")
