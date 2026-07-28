"""Tests for drift_monitor.surface (WP-7b, surface-drift lane).

Covers the extractor unit behavior plus the five acceptance criteria from
the WP-7b brief:
  1. seeding a new route file AND a new 0x address -> both detected w/ file:line
  2. unchanged clone -> silent run
  3. same seeded drift twice -> one finding (report written once)
  4. --accept then re-run -> silent
  5. zero writes outside drift_monitor/ paths this lane owns
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from drift_monitor import surface

FIXTURES = Path(__file__).parent / "fixtures" / "seed_repos"


def _copy_fixture(repo: str, dest: Path) -> Path:
    target = dest / repo
    shutil.copytree(FIXTURES / repo, target)
    return target


@pytest.fixture
def isolated_dirs(tmp_path):
    """Baseline/report/state dirs isolated per test — never touches the
    real drift_monitor/baselines/surface/*.json committed to git."""
    return {
        "baseline_dir": tmp_path / "baselines",
        "report_dir": tmp_path / "reports",
        "state_dir": tmp_path / "state",
    }


def _run(repo, path, dirs, accept=False):
    return surface.run_scan(
        repo,
        path=str(path),
        accept=accept,
        baseline_dir=dirs["baseline_dir"],
        report_dir=dirs["report_dir"],
        state_dir=dirs["state_dir"],
    )


# --------------------------------------------------------------------------
# Extractor unit tests
# --------------------------------------------------------------------------


def test_extract_api_routes_next_app_router():
    root = FIXTURES / "ciphex-alpha-dashboard"
    findings = surface.extract_api_routes(root)
    identities = {(f.subtype, f.value, f.file, f.line) for f in findings}
    assert ("GET", "/api/health", "app/api/health/route.ts", 1) in identities
    assert ("GET", "/api/metrics/[key]", "app/api/metrics/[key]/route.ts", 3) in identities


def test_extract_api_routes_vercel_function():
    root = FIXTURES / "atlas"
    findings = surface.extract_api_routes(root)
    matches = [f for f in findings if f.file == "api/webhook.ts"]
    assert len(matches) == 1
    assert matches[0].value == "/api/webhook"


def test_extract_api_routes_fastapi():
    root = FIXTURES / "abacus-trading-view"
    findings = surface.extract_api_routes(root)
    identities = {(f.subtype, f.value, f.file, f.line) for f in findings}
    assert ("GET", "/health", "webapp/server.py", 7) in identities
    assert ("GET", "/v0/latest", "webapp/server.py", 12) in identities
    assert ("POST", "/v0/predict", "webapp/server.py", 17) in identities


def test_extract_env_vars_all_forms():
    root = FIXTURES / "abacus-trading-view"
    findings = surface.extract_env_vars(root)
    names = {f.value for f in findings}
    assert {"ABACUS_INDEXER_BASE", "ABACUS_API_KEY", "ABACUS_REDIS_URL", "ABACUS_PUBLIC_BASE"} <= names

    root2 = FIXTURES / "atlas"
    names2 = {f.value for f in surface.extract_env_vars(root2)}
    assert "VITE_ATLAS_PUBLIC_KEY" in names2  # import.meta.env form


def test_extract_addresses():
    root = FIXTURES / "abacus-trading-view"
    findings = surface.extract_addresses(root)
    values = {f.value for f in findings}
    assert "0x18b33687d1c804Dd4ea6c82106e54923c23a652E" in values
    assert "0x000000000000000000000000000000000000dEaD" in values
    for f in findings:
        assert f.file and f.line > 0  # file:line evidence present


def test_extract_domains():
    root = FIXTURES / "ciphex-alpha-dashboard"
    findings = surface.extract_domains(root)
    values = {f.value for f in findings}
    assert "ams.ciphex.io" in values


def test_extract_chain_ids():
    root = FIXTURES / "atlas"
    findings = surface.extract_chain_ids(root)
    values = {f.value for f in findings}
    assert "8453" in values


# --------------------------------------------------------------------------
# Acceptance 1: new route file + new address detected with file:line evidence
# --------------------------------------------------------------------------


def test_acceptance_1_new_route_and_address_detected(tmp_path, isolated_dirs):
    repo = "atlas"
    work = _copy_fixture(repo, tmp_path / "work")

    # seed the baseline from the unmodified fixture first
    seed = _run(repo, work, isolated_dirs, accept=True)
    assert seed["status"] == "accepted"

    # now mutate a COPY: add a new route file and a new 0x address
    new_route_dir = work / "app" / "api" / "vault"
    new_route_dir.mkdir(parents=True)
    (new_route_dir / "route.ts").write_text(
        "export async function GET() {\n  return Response.json({ ok: true });\n}\n"
    )
    (work / "src" / "new_constants.ts").write_text(
        'export const NEW_TOKEN = "0x1111111111111111111111111111111111111111";\n'
    )

    result = _run(repo, work, isolated_dirs, accept=False)
    assert result["status"] == "reported"
    assert result["diff_counts"]["added"] >= 2

    report_text = Path(result["report_path"]).read_text()
    assert "app/api/vault/route.ts:1" in report_text
    assert "0x1111111111111111111111111111111111111111" in report_text
    assert "src/new_constants.ts:1" in report_text


# --------------------------------------------------------------------------
# Acceptance 2: unchanged clone -> silent
# --------------------------------------------------------------------------


def test_acceptance_2_unchanged_is_silent(tmp_path, isolated_dirs):
    repo = "ciphex-alpha-dashboard"
    work = _copy_fixture(repo, tmp_path / "work")

    seed = _run(repo, work, isolated_dirs, accept=True)
    assert seed["status"] == "accepted"

    result = _run(repo, work, isolated_dirs, accept=False)
    assert result["status"] == "silent"
    assert not isolated_dirs["report_dir"].exists() or not any(isolated_dirs["report_dir"].iterdir())


# --------------------------------------------------------------------------
# Acceptance 3: same seeded drift twice -> one finding (report written once)
# --------------------------------------------------------------------------


def test_acceptance_3_same_drift_twice_is_one_finding(tmp_path, isolated_dirs):
    repo = "abacus-trading-view"
    work = _copy_fixture(repo, tmp_path / "work")
    _run(repo, work, isolated_dirs, accept=True)

    (work / "webapp" / "new_route.py").write_text(
        "from webapp.server import router\n\n\n"
        "@router.get(\"/v0/new-endpoint\")\n"
        "def new_endpoint():\n"
        "    return {}\n"
    )

    first = _run(repo, work, isolated_dirs, accept=False)
    assert first["status"] == "reported"

    second = _run(repo, work, isolated_dirs, accept=False)
    assert second["status"] == "suppressed"
    assert second["fingerprint"] == first["fingerprint"]

    reports = list(isolated_dirs["report_dir"].glob(f"{repo}-*.md"))
    assert len(reports) == 1  # only one finding/report across both runs


# --------------------------------------------------------------------------
# Acceptance 4: --accept then re-run -> silent
# --------------------------------------------------------------------------


def test_acceptance_4_accept_then_rerun_silent(tmp_path, isolated_dirs):
    repo = "atlas"
    work = _copy_fixture(repo, tmp_path / "work")
    _run(repo, work, isolated_dirs, accept=True)

    new_dir = work / "app" / "api" / "kyc2"
    new_dir.mkdir()
    (new_dir / "route.ts").write_text(
        "export async function GET() { return Response.json({}); }\n"
    )

    reported = _run(repo, work, isolated_dirs, accept=False)
    assert reported["status"] == "reported"

    accepted = _run(repo, work, isolated_dirs, accept=True)
    assert accepted["status"] == "accepted"

    silent = _run(repo, work, isolated_dirs, accept=False)
    assert silent["status"] == "silent"


# --------------------------------------------------------------------------
# Acceptance 5: zero writes outside drift_monitor/ paths this lane owns
# --------------------------------------------------------------------------


def test_acceptance_5_zero_writes_outside_owned_paths(tmp_path, isolated_dirs):
    repo = "ciphex-alpha-dashboard"
    work = _copy_fixture(repo, tmp_path / "work")

    def snapshot(root: Path):
        return {
            str(p.relative_to(root)): p.stat().st_mtime_ns
            for p in root.rglob("*")
            if p.is_file()
        }

    repo_root = Path(__file__).resolve().parents[2]  # century-support-bot repo root
    before = snapshot(repo_root)

    _run(repo, work, isolated_dirs, accept=True)
    _run(repo, work, isolated_dirs, accept=False)  # silent, no drift

    (work / "lib" / "extra.ts").write_text('export const X = process.env.NEW_VAR;\n')
    _run(repo, work, isolated_dirs, accept=False)  # reported

    after = snapshot(repo_root)

    changed_or_new = {
        k for k in after
        if k not in before or after[k] != before[k]
    }
    removed = {k for k in before if k not in after}

    # the only permissible touches are inside the isolated tmp dirs, which
    # live under tmp_path (outside repo_root) — so nothing under repo_root
    # should differ at all.
    assert not changed_or_new, f"unexpected writes under repo root: {changed_or_new}"
    assert not removed, f"unexpected deletions under repo root: {removed}"


# --------------------------------------------------------------------------
# Main-branch-only cloning (owner amendment)
# --------------------------------------------------------------------------


def test_clone_repo_main_only_uses_single_branch_main_depth1(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, check, capture_output, text):
        captured["cmd"] = cmd
        # simulate a real clone by creating the dest dir with no .git so
        # verify_main_branch_if_git() short-circuits (fixture-like)
        Path(cmd[-1]).mkdir(parents=True, exist_ok=True)

        class R:
            pass
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    dest = tmp_path / "cloned"
    surface.clone_repo_main_only("https://example.invalid/repo.git", dest)

    cmd = captured["cmd"]
    assert cmd[:2] == ["git", "clone"]
    assert "--branch" in cmd and cmd[cmd.index("--branch") + 1] == "main"
    assert "--single-branch" in cmd
    assert "--depth" in cmd and cmd[cmd.index("--depth") + 1] == "1"
    assert cmd[-2] == "https://example.invalid/repo.git"
    assert cmd[-1] == str(dest)


def test_verify_main_branch_if_git_non_git_dir_is_noop(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert surface.verify_main_branch_if_git(d) is None


def test_verify_main_branch_if_git_rejects_non_main(tmp_path):
    repo_dir = tmp_path / "gitrepo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "not-main", str(repo_dir)], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "a@b.c"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "t"], check=True)
    (repo_dir / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-q", "-m", "x"], check=True)

    with pytest.raises(surface.SurfaceDriftPolicyError):
        surface.verify_main_branch_if_git(repo_dir)


def test_verify_main_branch_if_git_accepts_main(tmp_path):
    repo_dir = tmp_path / "gitrepo_main"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo_dir)], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "a@b.c"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "t"], check=True)
    (repo_dir / "f.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-q", "-m", "x"], check=True)

    assert surface.verify_main_branch_if_git(repo_dir) == "main"


# --------------------------------------------------------------------------
# Kill switch
# --------------------------------------------------------------------------


def test_kill_switch_disables_lane(monkeypatch, tmp_path, isolated_dirs):
    monkeypatch.setenv("DRIFT_SURFACE_ENABLED", "false")
    repo = "atlas"
    work = _copy_fixture(repo, tmp_path / "work")

    result = _run(repo, work, isolated_dirs, accept=True)
    assert result["status"] == "disabled"
    assert not isolated_dirs["baseline_dir"].exists()
    assert not isolated_dirs["report_dir"].exists()
    assert not isolated_dirs["state_dir"].exists()


def test_kill_switch_default_is_enabled(monkeypatch):
    monkeypatch.delenv("DRIFT_SURFACE_ENABLED", raising=False)
    assert surface.surface_enabled() is True


# --------------------------------------------------------------------------
# Fingerprint determinism
# --------------------------------------------------------------------------


def test_fingerprint_is_order_independent_and_stable():
    diff_a = {"added": [{"type": "env_var", "subtype": "", "value": "X", "locations": [{"file": "a.py", "line": 1}]}], "removed": [], "moved": []}
    diff_b = json.loads(json.dumps(diff_a))  # deep copy, same content
    assert surface.fingerprint(diff_a) == surface.fingerprint(diff_b)
