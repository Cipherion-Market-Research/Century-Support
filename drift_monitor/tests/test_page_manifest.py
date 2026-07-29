from pathlib import Path

from drift_monitor.page_manifest import load_watched_pages, repo_path_for_slug
from drift_monitor.tests.conftest import FIXTURES_DIR

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_repo_path_for_slug_uses_src_prefix_and_html_suffix():
    assert repo_path_for_slug("ciphex-token") == "src/ciphex-token.html"
    assert repo_path_for_slug("index") == "src/index.html"


def test_load_watched_pages_from_fixture_inventory():
    pages = load_watched_pages(kb_source_dir=str(FIXTURES_DIR / "kb_source"))
    assert len(pages) == 1
    page = pages[0]
    assert page.slug == "sample-page"
    assert page.repo_path == "src/sample-page.html"
    assert page.source_url == "https://ciphex.io/sample-page"


def test_load_watched_pages_from_real_kb_source_only_includes_pages():
    pages = load_watched_pages(kb_source_dir=str(REPO_ROOT / "data" / "kb_source"))
    slugs = {p.slug for p in pages}
    assert "ciphex-token" in slugs
    # Renamed from ecosystem-publications in the website repo's 2026-07-28
    # restructure (PR #100).
    assert "insights-and-publications" in slugs
    # PDFs are WP-4's concern, not this service's.
    assert "2026-phase-iii-optimization-summary" not in slugs
    assert all(p.repo_path.startswith("src/") and p.repo_path.endswith(".html") for p in pages)
