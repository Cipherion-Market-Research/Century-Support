"""Environment-driven configuration for Century Core (WP-5).

Mirrors the `_env`/`_env_int` convention from kpi_sync/config.py and
pubs_rag/config.py.
"""
import os


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return float(raw)


class Config:
    # --- Redis: the C3 KPI store this service reads (written by kpi_sync) ---
    REDIS_URL = _env("REDIS_URL", "redis://localhost:6379")

    # --- facts.yaml (C4) ---
    FACTS_PATH = _env("CENTURY_CORE_FACTS_PATH", "facts.yaml")

    # --- Publications RAG (pubs_rag) ---
    PUBS_RAG_POSTGRES_DSN = _env(
        "PUBS_RAG_POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5433/pubs_rag"
    )

    # --- Guarded LLM ---
    # "openai" is production (modern SDK, replaces the bot's legacy
    # openai==0.27.8). "stub" is a deterministic, network-free provider for
    # tests — same pluggable-provider pattern pubs_rag/embeddings.py uses.
    LLM_PROVIDER = _env("CENTURY_CORE_LLM_PROVIDER", "openai")
    LLM_MODEL = _env("CENTURY_CORE_LLM_MODEL", "gpt-4o-mini")
    OPENAI_API_KEY = _env("OPENAI_API_KEY", "")

    # --- Q&A retrieval tuning ---
    RAG_TOP_K = _env_int("CENTURY_CORE_RAG_TOP_K", 4)
    RAG_MIN_SCORE = _env_float("CENTURY_CORE_RAG_MIN_SCORE", 0.05)

    # --- Server ---
    # "::" (dual-stack) is required, not optional: Railway's healthcheck
    # probes over IPv4, but private-network traffic from the channel
    # adapters arrives over IPv6 (railway.internal resolves to AAAA).
    # An IPv4-only 0.0.0.0 bind passes healthchecks yet is unreachable
    # from the adapters. Linux binds "::" dual-stack by default.
    HOST = _env("CENTURY_CORE_HOST", "::")
    PORT = _env_int("PORT", _env_int("CENTURY_CORE_PORT", 8082))
    LOG_LEVEL = _env("CENTURY_CORE_LOG_LEVEL", "INFO")

    # --- "I don't know" fallback link (C4: unknown -> official link) ---
    OFFICIAL_SITE_URL = "https://ciphex.io"

    # --- Sprint-1 owner ruling: Abacus Indexer KPIs are internal-only and
    # must never reach a user-facing response, even though C3 lists
    # abacus_index as a valid source. Enforced in kpi_reader.py. ---
    # onchain_base added 2026-07-30: reads a deprecated legacy contract
    # (owner ruling -- the contribute page is source of truth).
    BLOCKED_KPI_SOURCES = frozenset({"abacus_index", "onchain_base"})

    # --- Broadcast queue (no channel adapters exist yet — WP-6 is Sprint 3;
    # broadcasts are durably queued here for adapters to consume later) ---
    BROADCAST_QUEUE_KEY = _env("CENTURY_CORE_BROADCAST_QUEUE_KEY", "century:broadcasts")

    # --- Servable-facts exclusion (owner rulings, 2026-08-17) ---
    # These keys exist in facts.yaml for historical/scam-verification/audit
    # purposes only and must never be servable to a user, in a command
    # response OR a Q&A search hit: contracts.base_presale and
    # contracts.cpx_token_base are the deprecated/non-Ethereum chain data
    # (CPX is ERC-20 on Ethereum mainnet only -- Base is never presented as
    # a legitimate deployment); links.claim_portal_legacy_redirect is the
    # old presale.ciphex.io domain ("presale" is banned vocabulary with no
    # exemptions); round-terms.new_round_price_usd is a CPX price figure
    # (the bot must never output a CPX price -- it is not listed, TBD).
    # Enforced in qa/facts_search.py.
    BLOCKED_FACT_KEYS = frozenset(
        {
            "contracts.base_presale",
            "contracts.cpx_token_base",
            "links.claim_portal_legacy_redirect",
            "round-terms.new_round_price_usd",
        }
    )

    # --- Global maintenance-mode switch (WP-7c rollback ledger) ---
    # Un-prefixed on purpose: the live Telegram bot's own copy of this
    # default (utils/maintenance.py) reads the same env var so one setting
    # produces one consistent holding message everywhere.
    MAINTENANCE_DEFAULT_MESSAGE = _env(
        "MAINTENANCE_DEFAULT_MESSAGE",
        "We're currently updating our information. Please check back shortly "
        "— for urgent issues contact support@ciphex.io.",
    )
