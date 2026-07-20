"""Environment-driven configuration for the Tier-1 KPI sync service.

Every upstream URL is a config knob, not a literal — the Abacus Indexer in
particular is a raw ALB hostname today (OQ-4: no stable subdomain exists
yet), so its scheme+host+path are assembled from three separate env vars
rather than a hardcoded string, and the whole base URL can still be
overridden wholesale with KPI_SYNC_ABACUS_BASE_URL when a subdomain lands.
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
    REDIS_URL = _env("REDIS_URL", "redis://localhost:6379")

    # --- Tier-1 HTTP feeds ---
    CLAIM_API_URL = _env("KPI_SYNC_CLAIM_API_URL", "https://claim.ciphex.io/api/presale")
    CLAIM_API_INTERVAL_S = _env_int("KPI_SYNC_CLAIM_API_INTERVAL_S", 15 * 60)

    AMS_BASE_URL = _env("KPI_SYNC_AMS_BASE_URL", "https://ams.ciphex.io")
    AMS_MARKETING_STATS_PATH = _env(
        "KPI_SYNC_AMS_MARKETING_STATS_PATH", "/api/ciphex-data/marketing-stats"
    )
    AMS_MARKETING_INTERVAL_S = _env_int("KPI_SYNC_AMS_MARKETING_INTERVAL_S", 15 * 60)

    AMS_KEY_METRICS_PATH = _env("KPI_SYNC_AMS_KEY_METRICS_PATH", "/api/ciphex-data/key-metrics")
    AMS_PUBLIC_METRICS_PATH = _env(
        "KPI_SYNC_AMS_PUBLIC_METRICS_PATH", "/api/ciphex-data/public-metrics"
    )
    AMS_PUBLIC_CHARTS_PATH = _env(
        "KPI_SYNC_AMS_PUBLIC_CHARTS_PATH", "/api/ciphex-data/public-charts"
    )
    AMS_KEYMETRICS_INTERVAL_S = _env_int("KPI_SYNC_AMS_KEYMETRICS_INTERVAL_S", 30 * 60)

    # ams.ciphex.io enforces 10 req/min server-side (x-ratelimit-* headers
    # confirm it); the poller's own budget is kept strictly under that so
    # a slow response or retry never trips the upstream limit.
    AMS_RATE_LIMIT_PER_MIN = _env_int("KPI_SYNC_AMS_RATE_LIMIT_PER_MIN", 8)

    # --- Abacus Indexer (OQ-4: raw ALB hostname, no stable subdomain yet) ---
    # KPI_SYNC_ABACUS_BASE_URL overrides everything below in one shot once a
    # stable subdomain (e.g. index.ciphex.io) exists. Until then the scheme
    # defaults to plain http because the ALB's TLS cert is issued for a
    # different host (api.ciphex.io) and does not cover its own hostname —
    # verifying TLS against the wrong name is not a substitute for a real
    # cert, so this talks to the ALB the way it is actually being served.
    ABACUS_SCHEME = _env("KPI_SYNC_ABACUS_SCHEME", "http")
    ABACUS_HOST = _env(
        "KPI_SYNC_ABACUS_HOST",
        "live-price-production-alb-1621087159.ca-central-1.elb.amazonaws.com",
    )
    ABACUS_PATH_PREFIX = _env("KPI_SYNC_ABACUS_PATH_PREFIX", "/indexer")
    ABACUS_BASE_URL = _env(
        "KPI_SYNC_ABACUS_BASE_URL", f"{ABACUS_SCHEME}://{ABACUS_HOST}{ABACUS_PATH_PREFIX}"
    )
    ABACUS_LATEST_PATH = _env("KPI_SYNC_ABACUS_LATEST_PATH", "/v0/latest")
    ABACUS_INTERVAL_S = _env_int("KPI_SYNC_ABACUS_INTERVAL_S", 60)

    # --- On-chain reads ---
    BASE_RPC_URL = _env("KPI_SYNC_BASE_RPC_URL", "https://mainnet.base.org")
    ETH_RPC_URL = _env("KPI_SYNC_ETH_RPC_URL", "https://ethereum.publicnode.com")
    PRESALE_CONTRACT_ADDRESS = _env(
        "KPI_SYNC_PRESALE_CONTRACT_ADDRESS", "0xE8E53D687b1b806Da21a2D7DA73Ff56a34e07A49"
    )
    CPX_ETH_CONTRACT_ADDRESS = _env(
        "KPI_SYNC_CPX_ETH_CONTRACT_ADDRESS", "0x18b33687d1c804Dd4ea6c82106e54923c23a652E"
    )
    ONCHAIN_INTERVAL_S = _env_int("KPI_SYNC_ONCHAIN_INTERVAL_S", 5 * 60)
    # When the presale isn't active, back off the on-chain poller to this
    # much slower cadence instead of hammering the RPC every 5 min for
    # nothing (§WP-3 spec: "5 min while a round runs").
    ONCHAIN_IDLE_INTERVAL_S = _env_int("KPI_SYNC_ONCHAIN_IDLE_INTERVAL_S", 30 * 60)

    # --- Envelope / staleness defaults (C3) ---
    DEFAULT_TTL_S = _env_int("KPI_SYNC_DEFAULT_TTL_S", 3600)
    DEFAULT_STALE_AFTER_S = _env_int("KPI_SYNC_DEFAULT_STALE_AFTER_S", 1800)

    # --- HTTP client behavior ---
    HTTP_TIMEOUT_S = _env_float("KPI_SYNC_HTTP_TIMEOUT_S", 10.0)
    RETRY_MAX_ATTEMPTS = _env_int("KPI_SYNC_RETRY_MAX_ATTEMPTS", 4)
    RETRY_BASE_DELAY_S = _env_float("KPI_SYNC_RETRY_BASE_DELAY_S", 1.0)
    RETRY_MAX_DELAY_S = _env_float("KPI_SYNC_RETRY_MAX_DELAY_S", 30.0)

    # --- Health endpoint ---
    HEALTH_HOST = _env("KPI_SYNC_HEALTH_HOST", "0.0.0.0")
    HEALTH_PORT = _env_int("PORT", _env_int("KPI_SYNC_HEALTH_PORT", 8080))

    LOG_LEVEL = _env("KPI_SYNC_LOG_LEVEL", "INFO")
