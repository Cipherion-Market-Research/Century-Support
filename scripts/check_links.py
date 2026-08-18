#!/usr/bin/env python3
"""CI check: every user-facing link the bot could ever serve actually
resolves. Production audit, 2026-08-18 found fact citations linking to the
literal string "internal://content-audit-2026-07-20" (fixed structurally --
see century_core/response_guard.py's link allowlist and qa/router.py) and
RAG citations linking two now-404 PDF urls. This script is the standing
regression check against link rot on top of that structural fix.

Checks the union of:
  - century_core.config.Config.ALLOWED_LINK_PREFIXES -- every prefix in
    that list is itself a real, directly-fetchable URL (a host root or a
    specific path), not just a pattern, so each is checked as-is.
  - Every https:// URL found in a facts.yaml fact's `value` field (e.g.
    links.* facts, whose value IS the URL shown to users).

HEAD each URL with a 10s timeout and a browser-ish User-Agent (some hosts
block the default bare-urllib UA even though the page works fine in a real
browser); falls back to GET if HEAD isn't supported (405/501, or a host
that just doesn't like HEAD). skynet.certik.com is a documented
pass-on-403: Cloudflare bot-blocks non-browser HTTP clients there, but the
page is confirmed fine in a real browser (see
century_core/config.py's ALLOWED_LINK_PREFIXES comment on links.certik_skynet).

Exits 0 (printing a short summary) on success; exits 1 and lists every
failing URL with its status code or error on failure.

Usage:
    python scripts/check_links.py
"""
from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from century_core.config import Config as CenturyCoreConfig  # noqa: E402
from facts_store import load_facts_file  # noqa: E402
from facts_store.loader import DEFAULT_FACTS_PATH  # noqa: E402

TIMEOUT_S = 10
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Cloudflare bot-blocks non-browser HTTP clients (curl, bare urllib) on
# this host with a 403, even though the page is fine in a real browser --
# confirmed manually during the 2026-08-17 website re-audit (see
# century_core/config.py's ALLOWED_LINK_PREFIXES comment on
# links.certik_skynet). Documented pass-on-403, not a silent skip: still
# attempted and still reported, just not treated as a failure at 403.
_PASS_ON_403_HOSTS = frozenset({"skynet.certik.com"})

_URL_RE = re.compile(r"https://\S+")


def _https_urls_from_facts(facts_path: Path) -> set[str]:
    facts_file = load_facts_file(facts_path)
    urls = set()
    for fact in facts_file.facts.values():
        # fact.value is a plain URL for links.* facts, but can also be a
        # dict (e.g. a contract's {"explorer_url": ..., "chain": ...})
        # or another non-string shape -- str() on any of those still
        # surfaces the URL text for the regex, just wrapped in Python's
        # repr punctuation, which the strip set below accounts for.
        for match in _URL_RE.findall(str(fact.value)):
            # Strip trailing punctuation a sentence -- or a dict/list
            # repr -- might have glued onto the URL (not part of it).
            urls.add(match.rstrip(".,;:)}]\"'"))
    return urls


def _urls_to_check() -> list[str]:
    urls = set(CenturyCoreConfig.ALLOWED_LINK_PREFIXES)
    urls |= _https_urls_from_facts(DEFAULT_FACTS_PATH)
    # "https://ciphex.io" (bare, no scheme suffix) is a prefix, not
    # necessarily a distinct fetchable URL from "https://ciphex.io/" --
    # both are kept; a HEAD/GET against either is a legitimate, separate
    # check of the same server.
    return sorted(u for u in urls if u.startswith("https://"))


def _check_url(url: str) -> tuple[bool, str]:
    """Returns (ok, detail). Tries HEAD first, falls back to GET on
    405/501 or a request that errors before a response is even received
    (some servers just don't implement HEAD cleanly)."""
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                status = response.status
                if status < 400:
                    return True, f"{method} {status}"
                if method == "HEAD" and status in (405, 501):
                    continue
                return False, f"{method} {status}"
        except urllib.error.HTTPError as exc:
            host = urlparse(url).hostname or ""
            if host in _PASS_ON_403_HOSTS and exc.code == 403:
                return True, f"{method} 403 (pass-on-403: {host} bot-blocks non-browser clients)"
            if method == "HEAD" and exc.code in (405, 501):
                continue
            return False, f"{method} {exc.code} {exc.reason}"
        except urllib.error.URLError as exc:
            if method == "HEAD":
                continue
            return False, f"{method} error: {exc.reason}"
        except TimeoutError:
            if method == "HEAD":
                continue
            return False, f"{method} timed out after {TIMEOUT_S}s"
    return False, "HEAD and GET both failed"


def main() -> int:
    urls = _urls_to_check()
    failures: list[tuple[str, str]] = []

    for url in urls:
        ok, detail = _check_url(url)
        print(f"{'OK  ' if ok else 'FAIL'} {url} -- {detail}")
        if not ok:
            failures.append((url, detail))

    print(f"\n{len(urls)} link(s) checked, {len(failures)} failure(s).")
    if failures:
        print("\nFailing links:", file=sys.stderr)
        for url, detail in failures:
            print(f"  {url} -- {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
