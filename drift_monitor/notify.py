"""Optional notification stub for shadow-mode reports (WP-7a brief:
shadow mode writes a markdown report "and (if configured) a notification
stub"). No notification channel (Slack/email/etc.) has been specified by
the owner, so the only implementation today is a structured log line,
gated by Config.NOTIFY_ENABLED (default off). This keeps the interface in
place for a future channel without inventing one that doesn't exist.
"""
from __future__ import annotations

from drift_monitor.config import Config
from drift_monitor.drift_check import PageFinding
from drift_monitor.logging_setup import get_logger

logger = get_logger("drift_monitor.notify")


def notify_new_finding(finding: PageFinding, report_path: str) -> None:
    if not Config.NOTIFY_ENABLED:
        return
    logger.info(
        "content drift finding ready for review",
        extra={
            "event": "notify_finding",
            "slug": finding.slug,
            "fingerprint": finding.fingerprint,
            "path": report_path,
        },
    )
