"""Local state under drift_monitor/state/: dedup of already-reported
findings (by fingerprint) and the commits-API poll cursor.

File-based (this service has no Redis/Postgres of its own) with
atomic-replace writes, same pattern as baseline.py's manifest.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from drift_monitor.config import Config


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp_path.replace(path)


class FindingsState:
    """Tracks which (slug, fingerprint) pairs already have a live report,
    so the same seeded drift, detected again on a subsequent poll, yields
    exactly one finding rather than a duplicate (WP-7a acceptance line 3)."""

    def __init__(self, state_dir: Optional[str] = None):
        self.path = Path(state_dir if state_dir is not None else Config.STATE_DIR) / "findings_state.json"
        self._data: dict = {}

    def load(self) -> "FindingsState":
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {}
        return self

    def save(self) -> None:
        _atomic_write_json(self.path, self._data)

    def seen(self, slug: str, fingerprint: str) -> bool:
        return fingerprint in self._data.get(slug, {})

    def record(self, slug: str, fingerprint: str, *, report_path: str, status: str = "shadow") -> None:
        self._data.setdefault(slug, {})[fingerprint] = {
            "first_seen": utcnow_iso(),
            "report_path": report_path,
            "status": status,
        }

    def entry(self, slug: str, fingerprint: str) -> Optional[dict]:
        return self._data.get(slug, {}).get(fingerprint)


class PollState:
    """Tracks the commits-API poll cursor (last commit timestamp checked
    per watched path) across process restarts."""

    def __init__(self, state_dir: Optional[str] = None):
        self.path = Path(state_dir if state_dir is not None else Config.STATE_DIR) / "poll_state.json"
        self._data: dict = {}

    def load(self) -> "PollState":
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        else:
            self._data = {}
        return self

    def save(self) -> None:
        _atomic_write_json(self.path, self._data)

    def get_last_checked(self) -> Optional[str]:
        return self._data.get("last_checked_at")

    def set_last_checked(self, iso_ts: str) -> None:
        self._data["last_checked_at"] = iso_ts

    def get_last_commit_sha(self) -> Optional[str]:
        return self._data.get("last_commit_sha")

    def set_last_commit_sha(self, sha: str) -> None:
        self._data["last_commit_sha"] = sha
