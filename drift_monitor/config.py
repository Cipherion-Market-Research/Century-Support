"""Environment-driven configuration for the content drift monitor (WP-7a).

Mirrors kpi_sync/config.py's and pubs_rag/config.py's convention: every
external endpoint, credential, and tunable is an env var with a sane
default, never a bare literal in calling code.
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


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_list(key: str, default: tuple) -> tuple:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return tuple(default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


class Config:
    # --- Enable / kill switches ---
    # Master switch: when false, main.py's scheduler loops no-op (used to
    # kill the whole service without a redeploy).
    CONTENT_ENABLED = _env_bool("DRIFT_CONTENT_ENABLED", True)
    # Shadow mode (default) writes a markdown report only. PR mode prepares
    # one consolidated PR body but still never calls the GitHub API to
    # actually open it except through the injected gh_pr wrapper.
    OPEN_PRS = _env_bool("DRIFT_OPEN_PRS", False)
    # Optional notification stub for shadow-mode reports (WP-7a brief:
    # "writes a markdown drift report ... and (if configured) a
    # notification stub"). Off by default -- no notification channel has
    # been specified by the owner; when off, notify.py only logs.
    NOTIFY_ENABLED = _env_bool("DRIFT_NOTIFY_ENABLED", False)

    # --- ciphex-website GitHub source (mirrors pubs_rag/config.py naming) ---
    GITHUB_REPO_OWNER = _env("DRIFT_GITHUB_REPO_OWNER", "Cipherion-Market-Research")
    GITHUB_REPO_NAME = _env("DRIFT_GITHUB_REPO_NAME", "ciphex-website")
    # TRACKED_REF is the only ref this service ever reads. It is
    # deliberately not sourced from an env override: every commits-API
    # query and every raw-content fetch is pinned to this single constant
    # so a misconfigured env var can never point the monitor at a
    # non-main branch (which could carry unreleased/sensitive content that
    # must never enter a drift report or a proposed facts.yaml edit, even
    # as "evidence"). If the tracked branch ever needs to change, that is a
    # deliberate code change + review, not a deploy-time env flip.
    TRACKED_REF = "main"
    GITHUB_API_BASE_URL = _env("DRIFT_GITHUB_API_BASE_URL", "https://api.github.com")
    GITHUB_RAW_BASE_URL = _env("DRIFT_GITHUB_RAW_BASE_URL", "https://raw.githubusercontent.com")
    # Optional -- raises the commits-API rate limit from 60/hr to 5000/hr.
    # Never required for correctness; the poller works unauthenticated.
    GITHUB_TOKEN = _env("DRIFT_GITHUB_TOKEN", "")

    # Repo source pages this service watches. All are HTML entry files
    # under src/ in ciphex-website (confirmed pattern -- see
    # pubs_rag/config.py's PUBLICATION_INDEX_PATHS for the two publication
    # pages; the same src/<slug>.html convention holds for every other
    # page in data/kb_source/inventory.json).
    WATCHED_PATH_PREFIX = _env("DRIFT_WATCHED_PATH_PREFIX", "src/")
    WATCHED_PATH_SUFFIX = _env("DRIFT_WATCHED_PATH_SUFFIX", ".html")
    SITE_BASE_URL = _env("DRIFT_SITE_BASE_URL", "https://ciphex.io")

    # --- Corpus seed (baseline bootstrap; see data/kb_source/inventory.json) ---
    KB_SOURCE_DIR = _env("DRIFT_KB_SOURCE_DIR", "data/kb_source")

    # --- facts.yaml (read-only; this service never writes it -- C4) ---
    FACTS_YAML_PATH = _env("DRIFT_FACTS_YAML_PATH", "facts.yaml")

    # --- Cadence ---
    # Default nightly commits-API poll (docs/BUILD_HANDOFF.md WP-7a: "Scheduled
    # runs (env-cadence, default nightly)").
    POLL_INTERVAL_S = _env_int("DRIFT_POLL_INTERVAL_S", 24 * 60 * 60)
    PARITY_INTERVAL_S = _env_int("DRIFT_PARITY_INTERVAL_S", 7 * 24 * 60 * 60)  # weekly

    # Three sentinel pages for the live-vs-repo parity probe (§ brief).
    PARITY_SENTINEL_SLUGS = _env_list(
        "DRIFT_PARITY_SENTINEL_SLUGS", ("index", "ciphex-token", "ecosystem-publications")
    )

    # --- HTTP client behavior ---
    HTTP_TIMEOUT_S = _env_float("DRIFT_HTTP_TIMEOUT_S", 20.0)
    RETRY_MAX_ATTEMPTS = _env_int("DRIFT_RETRY_MAX_ATTEMPTS", 4)
    RETRY_BASE_DELAY_S = _env_float("DRIFT_RETRY_BASE_DELAY_S", 1.0)
    RETRY_MAX_DELAY_S = _env_float("DRIFT_RETRY_MAX_DELAY_S", 30.0)

    # --- Local storage (this service's own paths; no Redis/Postgres) ---
    BASELINE_DIR = _env("DRIFT_BASELINE_DIR", "drift_monitor/baselines")
    STATE_DIR = _env("DRIFT_STATE_DIR", "drift_monitor/state")
    REPORTS_DIR = _env("DRIFT_REPORTS_DIR", "drift_monitor/reports")

    # --- Health endpoint ---
    HEALTH_HOST = _env("DRIFT_HEALTH_HOST", "0.0.0.0")
    HEALTH_PORT = _env_int("PORT", _env_int("DRIFT_HEALTH_PORT", 8082))

    LOG_LEVEL = _env("DRIFT_LOG_LEVEL", "INFO")
