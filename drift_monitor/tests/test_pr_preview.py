"""pr_preview.py is pure string-building -- no network, no gh CLI. These
tests never import/exercise gh_pr's real subprocess path."""
from drift_monitor.drift_check import PageFinding, ProposedFactEdit
from drift_monitor.pr_preview import build_pr_preview


def _finding(fact_key="identity.support_email", proposed="help@ciphex.io") -> PageFinding:
    return PageFinding(
        slug="sample-page",
        repo_path="src/sample-page.html",
        fingerprint="abc123",
        unified_diff="-support@ciphex.io\n+help@ciphex.io",
        proposed_edits=[
            ProposedFactEdit(
                fact_key=fact_key,
                current_value="support@ciphex.io",
                proposed_value=proposed,
                source_url="https://ciphex.io/contact",
                verified_on="2026-07-20",
            )
        ],
        unmapped_hunk_count=1,
    )


def test_build_pr_preview_consolidates_multiple_findings():
    preview = build_pr_preview([_finding(), _finding(fact_key="tokenomics.burn_cycle_1_cpx")])
    assert "2" in preview.title or "sample-page" in preview.title
    assert "identity.support_email" in preview.body
    assert "tokenomics.burn_cycle_1_cpx" in preview.body
    assert "never auto-applies facts.yaml" in preview.body
    assert preview.branch_name


def test_build_pr_preview_includes_evidence_diff_and_ambiguous_marker():
    preview = build_pr_preview([_finding(proposed=None)])
    assert "-support@ciphex.io" in preview.body
    assert "AMBIGUOUS" in preview.body


def test_build_pr_preview_notes_unmapped_hunks():
    preview = build_pr_preview([_finding()])
    assert "manual review" in preview.body
