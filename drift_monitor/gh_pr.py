"""`gh`-CLI wrapper for actually opening the consolidated PR built by
pr_preview.py.

This module is dependency-injected: main.py's orchestrator receives a
callable/object satisfying `PrCreator` and only invokes it when
Config.OPEN_PRS is true. It is NEVER imported or exercised by the test
suite -- the acceptance line "PR mode never fires with the flag off" and
the "no live network in tests" rule both mean the real
`subprocess.run(["gh", ...])` call below must not run under pytest. Tests
cover pr_preview.py's pure string-building instead, and a NoOpPrCreator
double stands in wherever an orchestrator needs *a* PrCreator without
actually creating anything.
"""
from __future__ import annotations

import subprocess
from typing import Protocol

from drift_monitor.pr_preview import PullRequestPreview


class PrCreator(Protocol):
    def create_pr(self, preview: PullRequestPreview) -> dict: ...


class NoOpPrCreator:
    """Safe default: records what it would have done, creates nothing.
    Used whenever Config.OPEN_PRS is false, and any place tests need a
    PrCreator without touching gh_pr's real implementation."""

    def __init__(self):
        self.calls: list = []

    def create_pr(self, preview: PullRequestPreview) -> dict:
        self.calls.append(preview)
        return {"created": False, "reason": "DRIFT_OPEN_PRS is false (shadow mode)"}


class GhCliPrCreator:
    """Real implementation -- shells out to the `gh` CLI. Only ever
    constructed/called from main.py's live orchestrator path, gated on
    Config.OPEN_PRS. No test in this package's suite calls create_pr() on
    this class.

    Ops note (docs/BUILD_HANDOFF.md HITL policy matrix, "All lanes" row):
    the `gh` CLI's own auth token is expected to be a fine-grained token
    scoped to this repo only, with PR-create permission and nothing more
    (no merge, no admin) -- drift PRs can never auto-merge. That scoping
    is a deployment/credential concern (whatever `gh auth login` or
    GH_TOKEN is configured with in the Railway environment), not
    something this class enforces in code.
    """

    def __init__(self, base_branch: str = "main", repo: str = ""):
        self.base_branch = base_branch
        self.repo = repo

    def create_pr(self, preview: PullRequestPreview) -> dict:  # pragma: no cover -- never called in tests
        cmd = [
            "gh",
            "pr",
            "create",
            "--title",
            preview.title,
            "--body",
            preview.body,
            "--base",
            self.base_branch,
            "--head",
            preview.branch_name,
        ]
        if self.repo:
            cmd.extend(["--repo", self.repo])
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return {
            "created": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
