"""PR-mode content preparation (DRIFT_OPEN_PRS=true): builds ONE
consolidated PR body covering every not-yet-reported finding from a poll
batch. This module only builds strings/dataclasses -- it never calls
GitHub. Actual PR creation is gh_pr.py's job, and only main.py wires the
two together when the flag is on.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from drift_monitor.config import Config
from drift_monitor.drift_check import PageFinding


@dataclass
class PullRequestPreview:
    title: str
    body: str
    branch_name: str
    findings: list = field(default_factory=list)  # the PageFindings included


def _facts_yaml_patch_snippet(finding: PageFinding) -> str:
    """A readable (not machine-applied) YAML-ish snippet showing the
    proposed edit -- the actual facts.yaml edit is always a
    human-reviewed PR per C4; this is evidence for that review, not a
    diff to be auto-applied."""
    lines = []
    for edit in finding.proposed_edits:
        proposed = edit.proposed_value if edit.proposed_value is not None else "# AMBIGUOUS -- manual review required"
        lines.append(f"{edit.fact_key}:")
        lines.append(f"  value: {proposed}")
        lines.append(f"  # was: {edit.current_value!r}")
        lines.append(f"  # verified_on: <fill in — reviewer must re-verify against source_url>")
        lines.append(f"  # source_url: {edit.source_url}")
    return "\n".join(lines)


def build_pr_preview(findings: list, branch_name: str = "drift/content-update") -> PullRequestPreview:
    """`findings` is the list of NEW (non-duplicate) PageFinding objects
    from one poll batch. Returns a single consolidated preview; callers
    only invoke this when Config.OPEN_PRS is true."""
    total_edits = sum(len(f.proposed_edits) for f in findings)
    total_unmapped = sum(f.unmapped_hunk_count for f in findings)
    slugs = ", ".join(f.slug for f in findings)

    title = f"Content drift: {len(findings)} page(s) changed on ciphex-website ({Config.TRACKED_REF})"

    body_parts = [
        f"Automated content-drift proposal (WP-7a). Pages affected: {slugs}.",
        f"Proposed facts.yaml edits: {total_edits}. Unmapped hunks (human review): {total_unmapped}.",
        "",
        "**This PR never auto-applies facts.yaml edits.** Every proposed value below "
        "must be re-verified by a human reviewer against its source_url before merge "
        "(C4: 'The file changes only by PR reviewed by the project owner').",
        "",
    ]

    for finding in findings:
        body_parts.extend(
            [
                f"## {finding.slug}",
                f"Repo path: `{finding.repo_path}` (ref: `{Config.TRACKED_REF}`) — fingerprint `{finding.fingerprint}`",
                "",
                "### Evidence diff",
                "```diff",
                finding.unified_diff,
                "```",
                "",
            ]
        )
        if finding.proposed_edits:
            body_parts.extend(
                [
                    "### Proposed facts.yaml edits",
                    "```yaml",
                    _facts_yaml_patch_snippet(finding),
                    "```",
                    "",
                ]
            )
        if finding.unmapped_hunk_count:
            body_parts.append(
                f"_{finding.unmapped_hunk_count} additional hunk(s) touched no known fact — "
                "flagged for manual review, no edit proposed._"
            )
            body_parts.append("")
        body_parts.append(
            "Refreshed baseline for this page is included in this PR's baseline manifest update."
        )
        body_parts.append("")

    return PullRequestPreview(
        title=title, body="\n".join(body_parts), branch_name=branch_name, findings=list(findings)
    )
