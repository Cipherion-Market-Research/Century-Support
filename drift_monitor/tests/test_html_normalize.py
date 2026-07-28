from drift_monitor.html_normalize import extract_body_text, normalize_plain_text
from drift_monitor.tests.conftest import read_fixture_bytes


def test_extract_body_text_strips_chrome_and_keeps_copy():
    html = read_fixture_bytes("repo_checkout", "src", "sample-page.html").decode("utf-8")
    text = extract_body_text(html)

    assert "chrome, must be stripped" not in text  # <script> content gone
    assert "Home | Token | Contact" not in text  # <nav> gone
    assert "Copyright 2026 Ciphex" not in text  # <footer> gone
    assert "support@ciphex.io" in text
    assert "481,454,298" in text


def test_extract_body_text_is_deterministic():
    html = read_fixture_bytes("repo_checkout", "src", "sample-page.html").decode("utf-8")
    assert extract_body_text(html) == extract_body_text(html)


def test_extract_body_text_collapses_whitespace():
    html = "<html><body><p>a   b\t\tc</p></body></html>"
    assert extract_body_text(html) == "a b c"


def test_normalize_plain_text_drops_blank_lines():
    # Blank lines carry no factual content and are dropped entirely (not
    # collapsed to one) -- this makes the line-level diff robust to pure
    # paragraph-spacing changes, which would otherwise flag as noise.
    text = "line one\n\n\n\nline two"
    assert normalize_plain_text(text) == "line one\nline two"
