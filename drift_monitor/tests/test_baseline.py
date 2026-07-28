import pytest

from drift_monitor.baseline import BaselineManifest, sha256_text
from drift_monitor.page_manifest import WatchedPage
from drift_monitor.tests.conftest import FIXTURES_DIR, FakeGitHubClient, read_fixture_bytes


def _fixture_page() -> WatchedPage:
    return WatchedPage(
        slug="sample-page", repo_path="src/sample-page.html", source_url="https://ciphex.io/sample-page"
    )


def test_seed_from_kb_source_populates_manifest(isolated_dirs):
    manifest = BaselineManifest()
    manifest.load()
    manifest.seed_from_kb_source(
        kb_source_dir=str(FIXTURES_DIR / "kb_source"), pages=[_fixture_page()]
    )

    assert manifest.slugs() == ["sample-page"]
    entry = manifest.get("sample-page")
    assert entry.repo_path == "src/sample-page.html"
    assert entry.tracked_ref == "main"
    text = manifest.get_text("sample-page")
    assert "support@ciphex.io" in text
    assert entry.sha256 == sha256_text(text)


def test_manifest_save_and_load_roundtrip(isolated_dirs):
    manifest = BaselineManifest()
    manifest.load()
    manifest.set_page("sample-page", "src/sample-page.html", "hello world", seeded_from="test")
    manifest.save()

    reloaded = BaselineManifest().load()
    assert reloaded.get("sample-page").sha256 == manifest.get("sample-page").sha256
    assert reloaded.get_text("sample-page") == "hello world"


@pytest.mark.asyncio
async def test_reseed_from_repo_uses_own_normalizer(isolated_dirs):
    html = read_fixture_bytes("repo_checkout", "src", "sample-page.html")
    fake_client = FakeGitHubClient(file_contents={"src/sample-page.html": html})

    manifest = BaselineManifest()
    manifest.load()
    await manifest.reseed_from_repo(fake_client, pages=[_fixture_page()])

    assert "support@ciphex.io" in manifest.get_text("sample-page")
    assert manifest.get("sample-page").seeded_from.startswith("repo:")
