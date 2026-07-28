from drift_monitor.state import FindingsState, PollState


def test_findings_state_dedup_roundtrip(isolated_dirs):
    state = FindingsState().load()
    assert state.seen("sample-page", "abc123") is False

    state.record("sample-page", "abc123", report_path="/tmp/report.md")
    assert state.seen("sample-page", "abc123") is True
    assert state.seen("sample-page", "different-fingerprint") is False
    assert state.entry("sample-page", "abc123")["report_path"] == "/tmp/report.md"

    state.save()
    reloaded = FindingsState().load()
    assert reloaded.seen("sample-page", "abc123") is True


def test_findings_state_scoped_per_slug(isolated_dirs):
    state = FindingsState().load()
    state.record("page-a", "fp1", report_path="a.md")
    assert state.seen("page-a", "fp1") is True
    assert state.seen("page-b", "fp1") is False  # same fingerprint, different page


def test_poll_state_persists_last_checked(isolated_dirs):
    state = PollState().load()
    assert state.get_last_checked() is None

    state.set_last_checked("2026-07-28T00:00:00Z")
    state.save()

    reloaded = PollState().load()
    assert reloaded.get_last_checked() == "2026-07-28T00:00:00Z"
