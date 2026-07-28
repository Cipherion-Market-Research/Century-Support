from pathlib import Path

from drift_monitor.drift_check import PageFinding, ProposedFactEdit
from drift_monitor.report import render_report_markdown, write_shadow_report


def _sample_finding() -> PageFinding:
    return PageFinding(
        slug="sample-page",
        repo_path="src/sample-page.html",
        fingerprint="abc123",
        unified_diff="-old line\n+new line",
        proposed_edits=[
            ProposedFactEdit(
                fact_key="identity.support_email",
                current_value="support@ciphex.io",
                proposed_value="help@ciphex.io",
                source_url="https://ciphex.io/contact",
                verified_on="2026-07-20",
            )
        ],
        unmapped_hunk_count=1,
    )


def test_render_report_markdown_contains_evidence_and_proposed_edit():
    md = render_report_markdown(_sample_finding())
    assert "sample-page" in md
    assert "-old line" in md
    assert "+new line" in md
    assert "identity.support_email" in md
    assert "help@ciphex.io" in md
    assert "SHADOW MODE" in md
    assert "Unmapped changes" in md


def test_write_shadow_report_creates_file(isolated_dirs):
    path = write_shadow_report(_sample_finding())
    assert Path(path).exists()
    assert path.suffix == ".md"
    assert "sample-page" in path.name
