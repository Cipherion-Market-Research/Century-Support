"""Only NoOpPrCreator (the safe default) is exercised here.
GhCliPrCreator.create_pr -- the real `gh` CLI / subprocess path -- is
never called anywhere in this test suite by design (WP-7a brief: "PR
mode never fires with the flag off"; the real PR-creation path is only
reachable from main.py's live orchestrator, gated on Config.OPEN_PRS)."""
from drift_monitor.gh_pr import NoOpPrCreator
from drift_monitor.pr_preview import build_pr_preview
from drift_monitor.drift_check import PageFinding


def test_noop_pr_creator_records_but_creates_nothing():
    finding = PageFinding(slug="sample-page", repo_path="src/sample-page.html", fingerprint="fp", unified_diff="diff")
    preview = build_pr_preview([finding])

    creator = NoOpPrCreator()
    result = creator.create_pr(preview)

    assert result["created"] is False
    assert creator.calls == [preview]
