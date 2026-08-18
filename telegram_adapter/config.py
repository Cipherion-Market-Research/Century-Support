"""Environment-driven configuration for the Telegram adapter.

Mirrors the `_env`/`_env_int` convention used by kpi_sync/config.py and
century_core/config.py.

Fail-loud rule (owner spec): TELEGRAM_TOKEN and CENTURY_CORE_URL are
required for every action (`serve`, `set-webhook`, `delete-webhook`);
`Config.validate()` raises immediately if either is missing. Nothing else
in this module registers a webhook or performs any network call by
itself -- that only ever happens when the owner explicitly runs the
`set-webhook` / `delete-webhook` CLI actions (see main.py).
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
    # --- Required (fail-loud) ---
    TELEGRAM_TOKEN = _env("TELEGRAM_TOKEN", "")
    CENTURY_CORE_URL = _env("CENTURY_CORE_URL", "")

    # --- Webhook security + registration ---
    # Validated (non-empty) on the webhook request path itself -- an empty
    # secret means every inbound request fails the secret_token check
    # closed, rather than open.
    TELEGRAM_WEBHOOK_SECRET = _env("TELEGRAM_WEBHOOK_SECRET", "")
    # Only required for the `set-webhook` CLI action (the externally
    # reachable HTTPS URL Telegram should POST updates to, e.g. the
    # Railway public domain + WEBHOOK_PATH). Never used by `serve`.
    TELEGRAM_WEBHOOK_URL = _env("TELEGRAM_WEBHOOK_URL", "")
    WEBHOOK_PATH = _env("TELEGRAM_WEBHOOK_PATH", "/telegram/webhook")

    # --- Server ---
    # Sync the Telegram command menu (setMyCommands) on every serve startup.
    # The menu persists on Telegram's servers as whatever was last
    # registered, so a deploy that changes TELEGRAM_COMMANDS silently ships
    # a stale menu until something re-registers it (observed live
    # 2026-08-18: /publications lingered in the menu after its removal
    # deployed). Idempotent, so per-boot sync is safe; webhook registration
    # itself stays a deliberate owner-run action (set-webhook CLI).
    SYNC_COMMANDS_ON_START = _env("TELEGRAM_SYNC_COMMANDS_ON_START", "true").lower() == "true"

    HOST = _env("TELEGRAM_ADAPTER_HOST", "0.0.0.0")
    PORT = _env_int("PORT", _env_int("TELEGRAM_ADAPTER_PORT", 8080))
    LOG_LEVEL = _env("TELEGRAM_ADAPTER_LOG_LEVEL", "INFO")

    # --- Century Core HTTP client ---
    CORE_HTTP_TIMEOUT_S = _env_float("TELEGRAM_ADAPTER_CORE_TIMEOUT_S", 10.0)
    CORE_RETRY_MAX_ATTEMPTS = _env_int("TELEGRAM_ADAPTER_CORE_RETRY_MAX_ATTEMPTS", 3)
    CORE_RETRY_BASE_DELAY_S = _env_float("TELEGRAM_ADAPTER_CORE_RETRY_BASE_DELAY_S", 0.5)

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.TELEGRAM_TOKEN:
            missing.append("TELEGRAM_TOKEN")
        if not cls.CENTURY_CORE_URL:
            missing.append("CENTURY_CORE_URL")
        if missing:
            raise RuntimeError(
                "telegram_adapter: missing required environment variable(s): "
                + ", ".join(missing)
            )
