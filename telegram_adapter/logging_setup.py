"""Structured (JSON-lines) logging, mirroring kpi_sync/logging_setup.py's
shape so operators reading Railway logs get one consistent format across
services."""
import json
import logging
import sys
from datetime import datetime, timezone

_EXTRA_FIELDS = ("event", "chat_ref", "user_ref", "status", "attempt", "port")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    # httpx logs every request URL at INFO, and Telegram Bot API URLs embed
    # the bot token -- keep it at WARNING so the token never reaches logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
