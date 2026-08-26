"""Offline tests for scripts/harvest_pages.py -- the committed website-pages
harvester (Sprint 3). No network, no git, no database: pure extraction,
scope-computation, and inventory-merge functions only.

scripts/ is a plain script directory (no __init__.py), so the module is
loaded by file path rather than via `import scripts.harvest_pages` -- keeps
this test independent of whatever import-mode pytest happens to be using
for the rest of the suite.
"""
import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "harvest_pages.py"
_spec = importlib.util.spec_from_file_location("harvest_pages", _SCRIPT_PATH)
harvest_pages = importlib.util.module_from_spec(_spec)
# Registered in sys.modules before exec: the module defines dataclasses,
# and the dataclass machinery looks itself up via sys.modules[cls.__module__].
sys.modules["harvest_pages"] = harvest_pages
_spec.loader.exec_module(harvest_pages)


# ─────────────────────────── HTML -> markdown extraction (parser) ───────────────────────────


def test_extract_page_pulls_title_and_main_text_only():
    html = """
    <html><head><title>Ciphex | Example</title></head>
    <body>
      <site-nav></site-nav>
      <main id="main-content">
        <h1>Ciphex Example</h1>
        <p>First paragraph of body copy.</p>
        <div class="tc"><div class="tc-name">Kevin O&rsquo;Brien</div></div>
      </main>
      <site-footer></site-footer>
    </body></html>
    """
    title, paragraphs = harvest_pages.extract_page(html)
    assert title == "Ciphex | Example"
    assert paragraphs == ["Ciphex Example", "First paragraph of body copy.", "Kevin O’Brien"]


def test_extract_page_drops_script_and_style_even_inside_main():
    html = """
    <html><head><title>T</title></head>
    <body><main id="main-content">
      <script>var x = "<b>not real content</b>";</script>
      <style>.tc { color: red; }</style>
      <p>Real paragraph.</p>
    </main></body></html>
    """
    _, paragraphs = harvest_pages.extract_page(html)
    assert paragraphs == ["Real paragraph."]


def test_extract_page_ignores_content_outside_main():
    html = """
    <html><head><title>T</title></head>
    <body>
      <nav><p>Nav link text -- must never appear in output.</p></nav>
      <main id="main-content"><p>In scope.</p></main>
      <footer><p>Footer text -- must never appear in output.</p></footer>
    </body></html>
    """
    _, paragraphs = harvest_pages.extract_page(html)
    assert paragraphs == ["In scope."]


def test_extract_page_merges_inline_tags_into_one_paragraph():
    html = """
    <html><head><title>T</title></head>
    <body><main id="main-content">
      <h2><span>One Capital Ecosystem Shaping the Future of </span><em>Intelligent Digital Capital Markets</em></h2>
    </main></body></html>
    """
    _, paragraphs = harvest_pages.extract_page(html)
    assert paragraphs == ["One Capital Ecosystem Shaping the Future of Intelligent Digital Capital Markets"]


def test_extract_page_collapses_internal_whitespace():
    html = """
    <html><head><title>T</title></head>
    <body><main id="main-content">
      <p>
        Multi
        line    text
        with     extra spaces
      </p>
    </main></body></html>
    """
    _, paragraphs = harvest_pages.extract_page(html)
    assert paragraphs == ["Multi line text with extra spaces"]


def test_extract_page_no_main_yields_no_paragraphs():
    html = "<html><head><title>T</title></head><body><p>Not inside main.</p></body></html>"
    title, paragraphs = harvest_pages.extract_page(html)
    assert title == "T"
    assert paragraphs == []


def test_render_markdown_shape_matches_target_frontmatter():
    md = harvest_pages.render_markdown(
        title="Ciphex | Example",
        source_url="https://ciphex.io/example",
        fetched_date="2026-08-26",
        paragraphs=["First paragraph.", "Second paragraph."],
    )
    assert md.startswith("<!--\nsource_url: https://ciphex.io/example\n")
    assert "fetched: 2026-08-26" in md
    assert "page_title: Ciphex | Example" in md
    assert "\n# Ciphex | Example\n\n" in md
    assert "First paragraph.\n\nSecond paragraph." in md
    # Public repo: no AI/coding-assistant vendor references anywhere,
    # including harvested content headers. Same obfuscated-pattern
    # approach as .github/workflows/provenance-guard.yml, so this
    # assertion doesn't itself trip that CI scan.
    import re

    vendor_pattern = re.compile("cl" + "aude|anthr" + "opic", re.IGNORECASE)
    assert not vendor_pattern.search(md)


# ─────────────────────────── page scope (sitemap-parity formula reuse) ───────────────────────────


def test_compute_harvest_scope_matches_sitemap_parity_formula(monkeypatch):
    from drift_monitor.config import Config as DriftConfig

    monkeypatch.setattr(DriftConfig, "KNOWN_NOINDEX_SLUGS", frozenset({"contribute", "hidden-page"}))
    monkeypatch.setattr(DriftConfig, "EXCLUDED_SLUGS", frozenset({"insights-and-publications"}))

    sitemap_slugs = ["index", "ciphex-token", "insights-and-publications", "404"]
    scope = harvest_pages.compute_harvest_scope(sitemap_slugs)

    # sitemap ∪ noindex − excluded − utility pages
    assert scope == sorted({"index", "ciphex-token", "contribute", "hidden-page"})
    assert "insights-and-publications" not in scope  # EXCLUDED_SLUGS
    assert "404" not in scope  # utility page, always dropped


def test_compute_harvest_scope_drops_utility_slugs_even_if_noindex_ever_grew_to_include_them(monkeypatch):
    from drift_monitor.config import Config as DriftConfig

    monkeypatch.setattr(DriftConfig, "KNOWN_NOINDEX_SLUGS", frozenset({"unavailable"}))
    monkeypatch.setattr(DriftConfig, "EXCLUDED_SLUGS", frozenset())

    scope = harvest_pages.compute_harvest_scope(["index"])
    assert "unavailable" not in scope


# ─────────────────────────── inventory upsert ───────────────────────────


def test_upsert_inventory_entry_replaces_existing_page_in_place():
    inventory = [
        {"kind": "page", "slug": "index", "title": "old"},
        {"kind": "pdf", "slug": "some-pdf", "title": "unrelated"},
    ]
    updated = harvest_pages.upsert_inventory_entry(inventory, {"kind": "page", "slug": "index", "title": "new"})
    assert updated[0] == {"kind": "page", "slug": "index", "title": "new"}
    assert updated[1] == {"kind": "pdf", "slug": "some-pdf", "title": "unrelated"}  # untouched
    assert len(updated) == 2  # replaced, not appended


def test_upsert_inventory_entry_appends_new_page():
    inventory = [{"kind": "page", "slug": "index", "title": "old"}]
    updated = harvest_pages.upsert_inventory_entry(inventory, {"kind": "page", "slug": "community", "title": "new"})
    assert len(updated) == 2
    assert updated[1]["slug"] == "community"


def test_upsert_inventory_entry_never_touches_pdf_entries_with_same_slug_string():
    # A "page" entry and a "pdf" entry could theoretically share a slug --
    # upsert must key on (kind == "page", slug), never slug alone.
    inventory = [{"kind": "pdf", "slug": "index", "title": "pdf entry"}]
    updated = harvest_pages.upsert_inventory_entry(inventory, {"kind": "page", "slug": "index", "title": "page entry"})
    assert len(updated) == 2
    kinds = {e["kind"] for e in updated}
    assert kinds == {"pdf", "page"}


def test_source_url_for_slug():
    assert harvest_pages.source_url_for_slug("index", "https://ciphex.io") == "https://ciphex.io/"
    assert harvest_pages.source_url_for_slug("leadership-team", "https://ciphex.io") == "https://ciphex.io/leadership-team"
