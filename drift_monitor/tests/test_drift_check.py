"""Core acceptance-line tests for WP-7a:

  (1) a seeded fake edit in a local website-checkout fixture produces a
      correct proposed fact edit with evidence diff.
  (2) an unchanged fixture produces zero output.
"""
from drift_monitor.drift_check import detect_page_drift
from drift_monitor.html_normalize import extract_body_text
from drift_monitor.tests.conftest import read_fixture_bytes


def _normalized(name: str) -> str:
    html = read_fixture_bytes("repo_checkout", "src", name).decode("utf-8")
    return extract_body_text(html)


def test_seeded_fake_edit_produces_correct_proposed_fact_edit(facts_store):
    baseline_text = _normalized("sample-page.html")
    edited_text = _normalized("sample-page-edited.html")

    finding = detect_page_drift("sample-page", "src/sample-page.html", baseline_text, edited_text, facts_store)

    assert finding is not None
    # Evidence diff must show the actual before/after text.
    assert "-Contact support at support@ciphex.io" in finding.unified_diff
    assert "+Contact support at help@ciphex.io" in finding.unified_diff

    # Correct proposed fact edit: identity.support_email, old -> new.
    matched = [e for e in finding.proposed_edits if e.fact_key == "identity.support_email"]
    assert len(matched) == 1
    edit = matched[0]
    assert edit.current_value == "support@ciphex.io"
    assert edit.proposed_value == "help@ciphex.io"
    assert edit.source_url == "https://ciphex.io/contact"

    # The new "rewards dashboard" sentence touches no fact -> unmapped.
    assert finding.unmapped_hunk_count >= 1


def test_unchanged_fixture_produces_zero_output(facts_store):
    baseline_text = _normalized("sample-page.html")
    same_text = _normalized("sample-page.html")

    finding = detect_page_drift("sample-page", "src/sample-page.html", baseline_text, same_text, facts_store)

    assert finding is None
