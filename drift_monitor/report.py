"""Shadow-mode markdown drift report writer (drift_monitor/reports/).

SHADOW MODE is the default (DRIFT_OPEN_PRS=false): this module is the
entire output of a shadow-mode run. It never touches facts.yaml or
GitHub -- it only writes a file under drift_monitor/reports/ for a human
to read.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from drift_monitor.config import Config
from drift_monitor.drift_check import PageFinding


def render_report_markdown(finding: PageFinding) -> str:
    lines = [
        f"# Content drift report: {finding.slug}",
        "",
        f"- Repo path: `{finding.repo_path}` (ref: `{Config.TRACKED_REF}`)",
        f"- Detected at: {finding.detected_at}",
        f"- Fingerprint: `{finding.fingerprint}`",
        f"- Mapped fact edits proposed: {len(finding.proposed_edits)}",
        f"- Unmapped hunks (no known fact touched): {finding.unmapped_hunk_count}",
        "",
        "## Evidence diff",
        "",
        "```diff",
        finding.unified_diff,
        "```",
        "",
    ]

    if finding.proposed_edits:
        lines.append("## Proposed facts.yaml edits")
        lines.append("")
        for edit in finding.proposed_edits:
            proposed = edit.proposed_value if edit.proposed_value is not None else "AMBIGUOUS — manual review required"
            lines.extend(
                [
                    f"### `{edit.fact_key}`",
                    "",
                    f"- Current value: `{edit.current_value}` (verified_on {edit.verified_on}, source: {edit.source_url})",
                    f"- Proposed value: `{proposed}`",
                    "",
                ]
            )

    if finding.unmapped_hunk_count:
        lines.extend(
            [
                "## Unmapped changes",
                "",
                f"{finding.unmapped_hunk_count} hunk(s) in this diff touched no known fact.yaml value. "
                "These are flagged for human review only -- no fact edit is proposed for them.",
                "",
            ]
        )

    lines.append(
        "---\n_This report is informational only (SHADOW MODE). It never mutates "
        "facts.yaml; see docs/CONTRACTS.md C4._"
    )
    return "\n".join(lines)


def report_filename(finding: PageFinding) -> str:
    ts = finding.detected_at.replace(":", "").replace("-", "")
    short_fp = finding.fingerprint[:12]
    return f"{ts}-{finding.slug}-{short_fp}.md"


def write_shadow_report(finding: PageFinding, reports_dir: Optional[str] = None) -> Path:
    directory = Path(reports_dir if reports_dir is not None else Config.REPORTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / report_filename(finding)
    path.write_text(render_report_markdown(finding), encoding="utf-8")
    return path
