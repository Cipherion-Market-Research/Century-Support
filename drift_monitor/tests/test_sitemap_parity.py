from drift_monitor.config import Config
from drift_monitor.sitemap_parity import (
    EXCLUDED_PRESENT,
    NEW_PAGE,
    REMOVED_PAGE,
    check_sitemap_parity,
    compute_expected_tracked,
    render_sitemap_parity_report_markdown,
    write_sitemap_parity_report,
)


def test_compute_expected_tracked_unions_noindex_and_subtracts_excluded():
    sitemap_slugs = {"index", "about", "insights-and-publications"}

    expected = compute_expected_tracked(sitemap_slugs)

    # known-noindex pages are pulled in even though absent from the sitemap
    for slug in Config.KNOWN_NOINDEX_SLUGS:
        assert slug in expected
    # excluded sections are dropped even though present in the sitemap
    assert "insights-and-publications" not in expected
    assert "index" in expected
    assert "about" in expected


def test_parity_check_no_drift_when_tracked_matches_expected():
    sitemap_slugs = {"index", "about"}
    tracked_slugs = compute_expected_tracked(sitemap_slugs)

    findings = check_sitemap_parity(sitemap_slugs, tracked_slugs)

    assert findings == []


def test_parity_check_flags_new_page_present_in_sitemap_but_not_tracked():
    sitemap_slugs = {"index", "about", "new-restructured-page"}
    tracked_slugs = {"index", "about"} | set(Config.KNOWN_NOINDEX_SLUGS)

    findings = check_sitemap_parity(sitemap_slugs, tracked_slugs)

    new_findings = [f for f in findings if f.kind == NEW_PAGE]
    assert any(f.slug == "new-restructured-page" for f in new_findings)


def test_parity_check_flags_new_page_for_known_noindex_slug_not_yet_tracked():
    sitemap_slugs = {"index", "about"}
    tracked_slugs = {"index", "about"}  # none of the noindex pages tracked yet

    findings = check_sitemap_parity(sitemap_slugs, tracked_slugs)

    new_slugs = {f.slug for f in findings if f.kind == NEW_PAGE}
    assert new_slugs == set(Config.KNOWN_NOINDEX_SLUGS)


def test_parity_check_flags_removed_page_no_longer_in_expected_scope():
    sitemap_slugs = {"index"}
    tracked_slugs = {"index", "retired-page"} | set(Config.KNOWN_NOINDEX_SLUGS)

    findings = check_sitemap_parity(sitemap_slugs, tracked_slugs)

    removed = [f for f in findings if f.kind == REMOVED_PAGE]
    assert len(removed) == 1
    assert removed[0].slug == "retired-page"


def test_parity_check_flags_excluded_present_when_sitemap_has_excluded_slug():
    sitemap_slugs = {"index", "insights-and-publications"}
    tracked_slugs = {"index"} | set(Config.KNOWN_NOINDEX_SLUGS)

    findings = check_sitemap_parity(sitemap_slugs, tracked_slugs)

    excluded = [f for f in findings if f.kind == EXCLUDED_PRESENT]
    assert len(excluded) == 1
    assert excluded[0].slug == "insights-and-publications"
    # excluded slugs must never also produce a new/removed finding for
    # themselves -- they're not part of expected_tracked either way.
    assert not any(f.slug == "insights-and-publications" and f.kind != EXCLUDED_PRESENT for f in findings)


def test_finding_fingerprint_is_stable_and_kind_scoped():
    sitemap_slugs = {"index", "orphaned-page"}
    tracked_slugs = {"index"} | set(Config.KNOWN_NOINDEX_SLUGS)

    findings_a = check_sitemap_parity(sitemap_slugs, tracked_slugs)
    findings_b = check_sitemap_parity(sitemap_slugs, tracked_slugs)

    fp_by_slug_a = {(f.kind, f.slug): f.fingerprint for f in findings_a}
    fp_by_slug_b = {(f.kind, f.slug): f.fingerprint for f in findings_b}
    assert fp_by_slug_a == fp_by_slug_b  # deterministic given the same (kind, slug)


def test_render_and_write_sitemap_parity_report(tmp_path):
    sitemap_slugs = {"index", "new-page"}
    tracked_slugs = {"index"} | set(Config.KNOWN_NOINDEX_SLUGS)
    findings = check_sitemap_parity(sitemap_slugs, tracked_slugs)

    md = render_sitemap_parity_report_markdown(findings)
    assert "sitemap_new_page" in md
    assert "new-page" in md

    path = write_sitemap_parity_report(findings, reports_dir=str(tmp_path))
    assert path.exists()
    assert path.read_text(encoding="utf-8") == md
