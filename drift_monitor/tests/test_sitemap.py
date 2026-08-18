import pytest

from drift_monitor.sitemap import (
    SitemapFetchError,
    fetch_sitemap_slugs,
    parse_sitemap_xml,
    slug_from_loc,
)
from drift_monitor.tests.conftest import FakeSitemapFetcher, read_fixture_bytes

SITEMAP_URL = "https://ciphex.io/sitemap.xml"


def test_slug_from_loc_root_is_index():
    assert slug_from_loc("https://ciphex.io/") == "index"
    assert slug_from_loc("https://ciphex.io") == "index"


def test_slug_from_loc_path_component():
    assert slug_from_loc("https://ciphex.io/about") == "about"
    assert slug_from_loc("https://ciphex.io/insights-and-publications") == "insights-and-publications"


def test_parse_sitemap_xml_fixture_has_eleven_urls():
    xml_bytes = read_fixture_bytes("sitemap.xml")
    slugs = parse_sitemap_xml(xml_bytes)

    assert len(slugs) == 11
    assert "index" in slugs
    assert "insights-and-publications" in slugs
    assert "about" in slugs


def test_parse_sitemap_xml_rejects_malformed_document():
    with pytest.raises(SitemapFetchError):
        parse_sitemap_xml(b"<urlset><url><loc>not closed")


@pytest.mark.asyncio
async def test_fetch_sitemap_slugs_uses_injected_fetcher():
    xml_bytes = read_fixture_bytes("sitemap.xml")
    fetcher = FakeSitemapFetcher({SITEMAP_URL: xml_bytes})

    slugs = await fetch_sitemap_slugs(fetcher, url=SITEMAP_URL)

    assert fetcher.calls == [SITEMAP_URL]
    assert "index" in slugs
    assert len(slugs) == 11


@pytest.mark.asyncio
async def test_fetch_sitemap_slugs_wraps_fetch_failure():
    fetcher = FakeSitemapFetcher(error=ConnectionError("unreachable"))

    with pytest.raises(SitemapFetchError):
        await fetch_sitemap_slugs(fetcher, url=SITEMAP_URL)


@pytest.mark.asyncio
async def test_fetch_sitemap_slugs_defaults_to_config_url():
    # No `url=` passed -- must fall back to drift_monitor.sitemap's own
    # bound Config.SITEMAP_URL (asserted against the same reference the
    # module itself reads, rather than re-importing Config here, which
    # would risk picking up a different class object if some other test
    # in the suite has reloaded drift_monitor.config -- see test_config.py).
    from drift_monitor import sitemap as sitemap_module

    default_url = sitemap_module.Config.SITEMAP_URL
    xml_bytes = read_fixture_bytes("sitemap.xml")
    fetcher = FakeSitemapFetcher({default_url: xml_bytes})

    slugs = await fetch_sitemap_slugs(fetcher)

    assert fetcher.calls == [default_url]
    assert len(slugs) == 11
