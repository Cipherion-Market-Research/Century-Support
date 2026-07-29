"""WP-7b — Surface drift scanner (ADVISORY-ONLY, permanent).

Weekly-cadence lane that runs deterministic, regex-based extractors over the
three product repos (ciphex-alpha-dashboard, atlas, abacus-trading-view) and
diffs the result against an accepted baseline manifest (kept on disk under
`baselines/surface/`, not tracked in git -- see
`drift_monitor/baselines/.gitignore` -- since those three repos are private
and their baselines enumerate private API routes/file paths). It NEVER calls an
LLM, NEVER auto-mutates facts.yaml / kpi_sync config / any poller, and the
only way a baseline moves is the explicit `--accept` CLI flag.

Ownership (WP-7b): this file, `surface_*.py` helpers, `baselines/surface/*`,
and `tests/test_surface*.py`. Everything else under `drift_monitor/` belongs
to the sibling WP-7a (content lane) — do not assume this module owns it.

Main-branch-only rule: every clone this module performs is `git clone
--branch main --single-branch --depth 1 <url> <dest>` — no other ref is
ever fetched or read, and non-main content must never reach a report or
baseline. See `MAIN_BRANCH_CLONE_ARGS` / `verify_main_branch_if_git`. Now
committed at `docs/BUILD_HANDOFF.md` (WP-7 section, commit cfe80d7) — an
earlier revision of this docstring flagged the rule as owner-instructed but
undocumented; that gap has since been closed and independently verified.

The three source repos are PRIVATE. Production cloning requires
`GITHUB_TOKEN`; the URL is built as
`https://x-access-token:${GITHUB_TOKEN}@github.com/<REPO_ORG>/<repo>.git`
(still main-branch-only/single-branch/depth-1). See `default_clone_url`.
If `DRIFT_SURFACE_ENABLED` is true and neither `--path` nor a usable token
is available, this fails loud with `SurfaceDriftConfigError` rather than
silently reporting nothing. The token and the credentialed URL are never
logged or persisted anywhere (baselines, reports, stdout, exceptions) —
see `_redact_secret` / `sanitize_url`; local `--path` mode never touches a
token at all.

Run as a self-contained module:

    python -m drift_monitor.surface --repo atlas --path /path/to/local/clone
    GITHUB_TOKEN=... python -m drift_monitor.surface --repo atlas   # production
    python -m drift_monitor.surface --repo atlas --url https://example/atlas.git
    python -m drift_monitor.surface --repo atlas --path ... --accept
    GITHUB_TOKEN=... python -m drift_monitor.surface --all          # all 3 repos

Kill switch: DRIFT_SURFACE_ENABLED=false disables the entire lane (default
true) — no reads beyond the check, no writes, exit 0.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# Paths owned by this lane
# --------------------------------------------------------------------------

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_BASELINE_DIR = PACKAGE_DIR / "baselines" / "surface"
DEFAULT_REPORT_DIR = PACKAGE_DIR / "reports" / "surface"
DEFAULT_STATE_DIR = PACKAGE_DIR / "state" / "surface"
DEFAULT_STATE_FILE = "state.json"

# The three product repos this lane watches (weekly cadence). They are
# private GitHub repos under this org; production cloning requires
# GITHUB_TOKEN (see default_clone_url / GITHUB_TOKEN_ENV below). Local
# --path fixtures/checkouts stay token-free.
DEFAULT_REPOS = ("ciphex-alpha-dashboard", "atlas", "abacus-trading-view")
REPO_ORG = "Cipherion-Market-Research"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"

# --------------------------------------------------------------------------
# Main-branch-only cloning (+ token auth for private repos)
# --------------------------------------------------------------------------

MAIN_BRANCH_CLONE_ARGS = ("--branch", "main", "--single-branch", "--depth", "1")

# Matches the credentialed-URL form we construct AND the form git itself
# echoes back in clone error messages, so both can be scrubbed the same way.
_TOKEN_URL_RE = re.compile(r"https://x-access-token:[^@\s]+@")


class SurfaceDriftPolicyError(RuntimeError):
    """Raised when a scan target would violate the main-branch-only rule."""


class SurfaceDriftConfigError(RuntimeError):
    """Raised when the lane is enabled but not usably configured (e.g. no
    GITHUB_TOKEN and no local --path override for a private source repo).
    This is meant to fail loud — callers must not swallow it into a silent
    'nothing to report' status."""


class SurfaceDriftCloneError(RuntimeError):
    """Wraps a failed `git clone` with the credentialed URL/token scrubbed
    out of the message. Never construct this directly with unredacted text
    — always go through `_redact_secret`."""


def _redact_secret(text: str, secret: Optional[str] = None) -> str:
    """Scrub a GitHub token and/or the credentialed clone URL out of `text`.
    Used for both the token value (defense in depth against verbose
    credential-helper output) and the structural `x-access-token:...@`
    pattern git itself echoes into clone error messages."""
    if secret:
        text = text.replace(secret, "***")
    text = _TOKEN_URL_RE.sub("https://x-access-token:***@", text)
    return text


def default_clone_url(repo: str) -> str:
    """Production clone URL for one of the three private product repos.
    Requires GITHUB_TOKEN — raises SurfaceDriftConfigError (fail loud) if
    unset, since there is no other way to read a private repo without a
    local --path override."""
    token = os.getenv(GITHUB_TOKEN_ENV)
    if not token:
        raise SurfaceDriftConfigError(
            f"{GITHUB_TOKEN_ENV} is not set and no local --path override was "
            f"given for {repo!r} — the source repos are private, so a token "
            "is required to clone them. Set GITHUB_TOKEN or pass --path."
        )
    return f"https://x-access-token:{token}@github.com/{REPO_ORG}/{repo}.git"


def sanitize_url(url: Optional[str]) -> Optional[str]:
    """Redacted form of a clone URL, safe to persist in a baseline manifest
    or print. Never store/print a raw `url` that may carry a token."""
    if url is None:
        return None
    return _redact_secret(url)


def clone_repo_main_only(url: str, dest: Path, secret: Optional[str] = None) -> Path:
    """Shallow-clone `url` into `dest`, main branch only, single branch.

    Never fetches or checks out any other ref. Raises SurfaceDriftPolicyError
    if, after cloning, the checked-out branch is not `main` (defensive check
    in case a remote's clone behavior ever deviates).

    `secret` (if the caller has the raw token) is scrubbed from any error
    text alongside the structural `x-access-token:...@` pattern — git
    itself echoes the remote URL into `fatal: ...` messages, so failures
    here are caught and redacted before they ever reach a log or exception
    that might be printed/reported.
    """
    cmd = ["git", "clone", *MAIN_BRANCH_CLONE_ARGS, url, str(dest)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        redacted_cmd = [_redact_secret(part, secret) for part in cmd]
        redacted_stderr = _redact_secret(exc.stderr or "", secret)
        raise SurfaceDriftCloneError(
            f"git clone failed (exit {exc.returncode}): {redacted_cmd} — {redacted_stderr}"
        ) from None
    verify_main_branch_if_git(dest)
    return dest


def verify_main_branch_if_git(path: Path) -> Optional[str]:
    """If `path` is a git checkout, assert it is on `main`. Returns branch
    name or None if `path` is not a git repo (e.g. a synthetic test fixture,
    which has nothing to verify since no ref was ever read)."""
    path = Path(path)
    if not (path / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip()
    if branch != "main":
        raise SurfaceDriftPolicyError(
            f"refusing to scan non-main ref {branch!r} at {path} "
            "(main-branch-only rule)"
        )
    return branch


# --------------------------------------------------------------------------
# Kill switch
# --------------------------------------------------------------------------


def surface_enabled() -> bool:
    val = os.getenv("DRIFT_SURFACE_ENABLED", "true").strip().lower()
    return val not in {"0", "false", "no", "off"}


# --------------------------------------------------------------------------
# Extractors (deterministic, regex-only — no LLM calls anywhere here)
# --------------------------------------------------------------------------

EXCLUDED_DIR_NAMES = {
    ".git", "node_modules", ".next", ".vercel", "dist", "build", "venv",
    ".venv", "__pycache__", ".turbo", "coverage", ".pytest_cache", "out",
    ".cache", ".DS_Store",
}
TEXT_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".json", ".env",
    ".yaml", ".yml", ".md", ".txt", ".toml", ".cfg", ".ini",
}
MAX_FILE_BYTES = 2_000_000  # skip anything larger (binaries, lockfiles, etc.)

_APP_ROUTE_METHOD_RE = re.compile(
    r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\b"
    r"|export\s+const\s+(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s*="
)
_FASTAPI_ROUTE_RE = re.compile(
    r"@[\w.]+\.(get|post|put|delete|patch|options|head)\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_ENV_PATTERNS = [
    re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"import\.meta\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"os\.environ\.get\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\.getenv\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
]
_ADDRESS_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_CIPHEX_DOMAIN_RE = re.compile(
    r"(?<![\w.-])([a-zA-Z0-9][a-zA-Z0-9.-]*ciphex\.io)\b", re.IGNORECASE
)
_URL_DOMAIN_RE = re.compile(r"https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")
_CHAIN_ID_RE = re.compile(
    r"chain[_-]?id\s*[:=]\s*['\"]?(0x[0-9a-fA-F]+|\d+)['\"]?", re.IGNORECASE
)


@dataclasses.dataclass(frozen=True)
class Finding:
    type: str      # api_route | env_var | address | domain | chain_id
    subtype: str   # http method, "url_host"/"literal", "" , ""
    value: str     # route path, var name, address, domain, chain id
    file: str      # posix-relative path from repo root
    line: int

    def identity(self):
        return (self.type, self.subtype, self.value)

    def to_dict(self):
        return dataclasses.asdict(self)


def _iter_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix not in TEXT_EXTENSIONS and p.name not in {".env", ".env.example"}:
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p


def _read_lines(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return text.splitlines()


def _relpath(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _next_app_route_url(root: Path, path: Path) -> Optional[str]:
    rel = _relpath(root, path)
    marker = "app/api/"
    idx = rel.find(marker)
    if idx == -1 or not path.name.startswith("route."):
        return None
    sub = rel[idx + len("app/") : rel.rfind("/")]  # e.g. "api/users/[id]"
    return "/" + sub


def _vercel_fn_url(root: Path, path: Path) -> Optional[str]:
    rel = _relpath(root, path)
    if "app/api/" in rel:
        return None
    m = re.search(r"(^|/)api/", rel)
    if not m or path.suffix not in {".ts", ".js", ".tsx", ".jsx"}:
        return None
    without_ext = rel[: -len(path.suffix)]
    # index.ts under a dir maps to the dir itself
    if without_ext.endswith("/index"):
        without_ext = without_ext[: -len("/index")]
    return "/" + without_ext


def extract_api_routes(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_source_files(root):
        if path.suffix == ".py":
            for lineno, line in enumerate(_read_lines(path), start=1):
                for m in _FASTAPI_ROUTE_RE.finditer(line):
                    method = m.group(1).upper()
                    url = m.group(2)
                    findings.append(
                        Finding("api_route", method, url, _relpath(root, path), lineno)
                    )
            continue

        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue

        app_url = _next_app_route_url(root, path)
        if app_url is not None:
            for lineno, line in enumerate(_read_lines(path), start=1):
                for m in _APP_ROUTE_METHOD_RE.finditer(line):
                    method = m.group(1) or m.group(2)
                    findings.append(
                        Finding("api_route", method, app_url, _relpath(root, path), lineno)
                    )
            continue

        fn_url = _vercel_fn_url(root, path)
        if fn_url is not None:
            findings.append(
                Finding("api_route", "ANY", fn_url, _relpath(root, path), 1)
            )
    return findings


def extract_env_vars(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_source_files(root):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"}:
            continue
        for lineno, line in enumerate(_read_lines(path), start=1):
            for pattern in _ENV_PATTERNS:
                for m in pattern.finditer(line):
                    findings.append(
                        Finding("env_var", "", m.group(1), _relpath(root, path), lineno)
                    )
    return findings


def extract_addresses(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_source_files(root):
        for lineno, line in enumerate(_read_lines(path), start=1):
            for m in _ADDRESS_RE.finditer(line):
                findings.append(
                    Finding("address", "", m.group(0), _relpath(root, path), lineno)
                )
    return findings


def extract_domains(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_source_files(root):
        for lineno, line in enumerate(_read_lines(path), start=1):
            for m in _CIPHEX_DOMAIN_RE.finditer(line):
                findings.append(
                    Finding("domain", "literal", m.group(1).lower(), _relpath(root, path), lineno)
                )
            for m in _URL_DOMAIN_RE.finditer(line):
                host = m.group(1).lower()
                if "ciphex.io" in host:
                    continue  # already captured above, avoid double-count
                findings.append(
                    Finding("domain", "url_host", host, _relpath(root, path), lineno)
                )
    return findings


def extract_chain_ids(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_source_files(root):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".env"}:
            continue
        for lineno, line in enumerate(_read_lines(path), start=1):
            for m in _CHAIN_ID_RE.finditer(line):
                findings.append(
                    Finding("chain_id", "", m.group(1), _relpath(root, path), lineno)
                )
    return findings


def scan_repo(root: Path) -> list[Finding]:
    root = Path(root)
    all_findings: list[Finding] = []
    all_findings += extract_api_routes(root)
    all_findings += extract_env_vars(root)
    all_findings += extract_addresses(root)
    all_findings += extract_domains(root)
    all_findings += extract_chain_ids(root)
    all_findings.sort(key=lambda f: (f.type, f.subtype, f.value, f.file, f.line))
    return all_findings


# --------------------------------------------------------------------------
# Baseline manifests
# --------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _group_by_identity(findings: list[Finding]) -> dict:
    grouped: dict = {}
    for f in findings:
        key = f.identity()
        entry = grouped.setdefault(
            key, {"type": f.type, "subtype": f.subtype, "value": f.value, "locations": []}
        )
        entry["locations"].append({"file": f.file, "line": f.line})
    return grouped


def _manifest_findings(findings: list[Finding]) -> list[dict]:
    grouped = _group_by_identity(findings)
    out = list(grouped.values())
    out.sort(key=lambda e: (e["type"], e["subtype"], e["value"]))
    return out


def write_baseline(baseline_path: Path, repo: str, source_path: Path,
                    findings: list[Finding], url: Optional[str] = None) -> dict:
    # Never persist a raw token/credentialed URL into a committed baseline.
    safe_url = sanitize_url(url)
    manifest = {
        "repo": repo,
        "generated_at": _now_iso(),
        "source": {
            "path": str(source_path),
            "url": safe_url,
            "clone_args": list(MAIN_BRANCH_CLONE_ARGS) if safe_url else None,
        },
        "findings": _manifest_findings(findings),
    }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return manifest


def load_baseline(baseline_path: Path) -> dict:
    if not baseline_path.exists():
        return {"repo": baseline_path.stem, "findings": []}
    return json.loads(baseline_path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Diff + fingerprint
# --------------------------------------------------------------------------


def diff_findings(baseline_entries: list[dict], current_findings: list[Finding]) -> dict:
    current_grouped = _manifest_findings(current_findings)
    baseline_map = {(e["type"], e["subtype"], e["value"]): e for e in baseline_entries}
    current_map = {(e["type"], e["subtype"], e["value"]): e for e in current_grouped}

    added = [current_map[k] for k in sorted(current_map) if k not in baseline_map]
    removed = [baseline_map[k] for k in sorted(baseline_map) if k not in current_map]

    moved = []
    for k in sorted(current_map):
        if k[0] != "api_route" or k not in baseline_map:
            continue
        old_files = {loc["file"] for loc in baseline_map[k]["locations"]}
        new_files = {loc["file"] for loc in current_map[k]["locations"]}
        if old_files and new_files and old_files.isdisjoint(new_files):
            moved.append({
                "type": k[0], "subtype": k[1], "value": k[2],
                "old_locations": baseline_map[k]["locations"],
                "new_locations": current_map[k]["locations"],
            })

    return {"added": added, "removed": removed, "moved": moved}


def diff_is_empty(diff: dict) -> bool:
    return not diff["added"] and not diff["removed"] and not diff["moved"]


def fingerprint(diff: dict) -> str:
    canonical = json.dumps(diff, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# State (suppress-until-resolved)
# --------------------------------------------------------------------------


def load_state(state_dir: Path) -> dict:
    state_path = Path(state_dir) / DEFAULT_STATE_FILE
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_state(state_dir: Path, state: dict) -> None:
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / DEFAULT_STATE_FILE).write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def clear_state(state_dir: Path, repo: str) -> None:
    state = load_state(state_dir)
    if repo in state:
        del state[repo]
        save_state(state_dir, state)


# --------------------------------------------------------------------------
# Report rendering
# --------------------------------------------------------------------------


def _format_locations(locations: list[dict]) -> str:
    return ", ".join(f"`{loc['file']}:{loc['line']}`" for loc in locations)


def render_report(repo: str, diff: dict, fp: str, source_path: Path,
                   main_branch_verified: Optional[str]) -> str:
    branch_note = repr(main_branch_verified) if main_branch_verified else "N/A (local, non-git fixture)"
    lines = [
        f"# Surface drift report — {repo}",
        "",
        f"- Scanned at: {_now_iso()}",
        f"- Source: `{source_path}`",
        f"- Clone policy: `git clone {' '.join(MAIN_BRANCH_CLONE_ARGS)}` "
        f"(main-branch-only; verified branch = {branch_note})",
        f"- Fingerprint: `{fp}`",
        "- Lane: ADVISORY-ONLY — this report never mutates facts.yaml, kpi_sync "
        "config, or any poller. A human must action it.",
        "",
    ]

    def section(title, items, render_item):
        lines.append(f"## {title} ({len(items)})")
        if not items:
            lines.append("_none_")
        else:
            for item in items:
                lines.append(render_item(item))
        lines.append("")

    section(
        "New", diff["added"],
        lambda e: f"- **{e['type']}** `{e['subtype']} {e['value']}`".rstrip()
        + f" — {_format_locations(e['locations'])}",
    )
    section(
        "Removed", diff["removed"],
        lambda e: f"- **{e['type']}** `{e['subtype']} {e['value']}`".rstrip()
        + f" — last seen at {_format_locations(e['locations'])}",
    )
    section(
        "Renamed / moved", diff["moved"],
        lambda e: f"- **{e['type']}** `{e['subtype']} {e['value']}`".rstrip()
        + f" — was {_format_locations(e['old_locations'])}, now {_format_locations(e['new_locations'])}",
    )

    return "\n".join(lines) + "\n"


def write_report(report_dir: Path, repo: str, markdown: str) -> Path:
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"{repo}-{ts}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


_TOKEN_CAPTURE_RE = re.compile(r"https://x-access-token:([^@\s]+)@")


def _extract_token_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = _TOKEN_CAPTURE_RE.search(url)
    return m.group(1) if m else None


def resolve_path(repo: str, path: Optional[str], url: Optional[str]):
    """Returns (work_path, cleanup_dir_or_None, resolved_url_or_None).

    Priority: explicit local --path (token-free, used for tests/fixtures and
    the scratchpad re-seed) > explicit --url (caller-supplied, e.g. CI/tests)
    > production default — a private-repo HTTPS URL built from GITHUB_TOKEN.
    The production default raises SurfaceDriftConfigError (fail loud) if
    GITHUB_TOKEN is unset, per the private-repo owner amendment: there is no
    silent/degraded path here, only local --path or a working token.
    """
    if path:
        return Path(path), None, None
    if url:
        tmp = Path(tempfile.mkdtemp(prefix=f"surface-drift-{repo}-"))
        clone_repo_main_only(url, tmp, secret=_extract_token_from_url(url))
        return tmp, tmp, url
    prod_url = default_clone_url(repo)  # raises SurfaceDriftConfigError if no token
    tmp = Path(tempfile.mkdtemp(prefix=f"surface-drift-{repo}-"))
    clone_repo_main_only(prod_url, tmp, secret=os.getenv(GITHUB_TOKEN_ENV))
    return tmp, tmp, prod_url


def count_by_type(findings: list[Finding]) -> dict:
    counts: dict = {}
    for f in findings:
        counts[f.type] = counts.get(f.type, 0) + 1
    return counts


def run_scan(
    repo: str,
    path: Optional[str] = None,
    url: Optional[str] = None,
    accept: bool = False,
    baseline_dir: Path = DEFAULT_BASELINE_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    state_dir: Path = DEFAULT_STATE_DIR,
) -> dict:
    if not surface_enabled():
        return {"status": "disabled", "repo": repo}

    work_path, cleanup_dir, resolved_url = resolve_path(repo, path, url)
    try:
        branch = verify_main_branch_if_git(work_path)
        current = scan_repo(work_path)
        baseline_path = Path(baseline_dir) / f"{repo}.json"

        if accept:
            manifest = write_baseline(baseline_path, repo, work_path, current, resolved_url)
            clear_state(state_dir, repo)
            return {
                "status": "accepted",
                "repo": repo,
                "baseline_path": str(baseline_path),
                "counts": count_by_type(current),
                "total_findings": len(manifest["findings"]),
            }

        baseline = load_baseline(baseline_path)
        diff = diff_findings(baseline.get("findings", []), current)

        if diff_is_empty(diff):
            clear_state(state_dir, repo)
            return {"status": "silent", "repo": repo}

        fp = fingerprint(diff)
        state = load_state(state_dir)
        prior = state.get(repo)

        if prior and prior.get("fingerprint") == fp:
            prior["last_seen"] = _now_iso()
            state[repo] = prior
            save_state(state_dir, state)
            return {
                "status": "suppressed",
                "repo": repo,
                "fingerprint": fp,
                "report_path": prior.get("report_path"),
            }

        markdown = render_report(repo, diff, fp, work_path, branch)
        report_path = write_report(report_dir, repo, markdown)
        state[repo] = {
            "fingerprint": fp,
            "first_seen": (prior or {}).get("first_seen", _now_iso()),
            "last_seen": _now_iso(),
            "report_path": str(report_path),
        }
        save_state(state_dir, state)
        return {
            "status": "reported",
            "repo": repo,
            "fingerprint": fp,
            "report_path": str(report_path),
            "diff_counts": {
                "added": len(diff["added"]),
                "removed": len(diff["removed"]),
                "moved": len(diff["moved"]),
            },
        }
    finally:
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _env_url_for(repo: str) -> Optional[str]:
    key = "DRIFT_SURFACE_URL_" + re.sub(r"[^A-Za-z0-9]+", "_", repo).upper()
    return os.getenv(key)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m drift_monitor.surface",
        description=__doc__.splitlines()[0],
    )
    p.add_argument("--repo", help="repo name (one of: %s)" % ", ".join(DEFAULT_REPOS))
    p.add_argument("--all", action="store_true", help="run all DEFAULT_REPOS (needs GITHUB_TOKEN, --url/DRIFT_SURFACE_URL_<REPO>, or local fixture dirs)")
    p.add_argument("--path", help="local directory to scan (test fixtures / pre-cloned checkout) — token-free")
    p.add_argument("--url", help="git URL to shallow-clone (main branch only); overrides the GITHUB_TOKEN production default")
    p.add_argument("--accept", action="store_true", help="rewrite the baseline from the current scan")
    p.add_argument("--baseline-dir", default=str(DEFAULT_BASELINE_DIR))
    p.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    p.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    return p


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    if not surface_enabled():
        print("DRIFT_SURFACE_ENABLED is false — surface drift lane disabled, no action taken.")
        return 0

    baseline_dir = Path(args.baseline_dir)
    report_dir = Path(args.report_dir)
    state_dir = Path(args.state_dir)

    repos = list(DEFAULT_REPOS) if args.all else [args.repo]
    if not args.all and not args.repo:
        print("error: --repo NAME or --all is required", file=sys.stderr)
        return 2

    exit_code = 0
    for repo in repos:
        url = args.url or _env_url_for(repo)
        path = args.path
        try:
            result = run_scan(
                repo, path=path, url=url, accept=args.accept,
                baseline_dir=baseline_dir, report_dir=report_dir, state_dir=state_dir,
            )
        except (ValueError, SurfaceDriftPolicyError, SurfaceDriftConfigError, SurfaceDriftCloneError) as exc:
            # exc's message is already redacted (see _redact_secret /
            # SurfaceDriftCloneError) — safe to print verbatim. Fail loud:
            # non-zero exit, no silent "nothing to report" status.
            print(f"[{repo}] error: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        print(f"[{repo}] {result['status']}" + (
            f" -> {result.get('report_path')}" if result.get("report_path") else ""
        ))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
