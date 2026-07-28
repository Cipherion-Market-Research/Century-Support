import logging

from drift_monitor.config import Config
from drift_monitor.drift_check import PageFinding
from drift_monitor.notify import notify_new_finding


def test_notify_is_noop_when_disabled(monkeypatch, caplog):
    monkeypatch.setattr(Config, "NOTIFY_ENABLED", False)
    finding = PageFinding(slug="sample-page", repo_path="src/sample-page.html", fingerprint="fp", unified_diff="d")

    with caplog.at_level(logging.INFO, logger="drift_monitor.notify"):
        notify_new_finding(finding, "report.md")

    assert caplog.records == []


def test_notify_logs_when_enabled(monkeypatch, caplog):
    monkeypatch.setattr(Config, "NOTIFY_ENABLED", True)
    finding = PageFinding(slug="sample-page", repo_path="src/sample-page.html", fingerprint="fp", unified_diff="d")

    with caplog.at_level(logging.INFO, logger="drift_monitor.notify"):
        notify_new_finding(finding, "report.md")

    assert len(caplog.records) == 1
    assert "drift finding" in caplog.records[0].getMessage()
    assert caplog.records[0].slug == "sample-page"
