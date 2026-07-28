"""Fail-loud startup requirement (owner directive, 2026-07-28): verified
live via unauthenticated `curl` that api.github.com/repos/
Cipherion-Market-Research/ciphex-website and its raw-content path both
404 without a token (control request to a known-public repo returned
200 in the same check, ruling out a connectivity problem). A poll loop
started without DRIFT_GITHUB_TOKEN would silently 404 every cycle
instead of detecting drift -- main.check_startup_requirements() refuses
to let that happen when the content-drift lane is enabled.
"""
import pytest

from drift_monitor import main as main_module
from drift_monitor.config import Config
from drift_monitor.main import StartupConfigError, check_startup_requirements


def test_fails_when_enabled_and_token_missing(monkeypatch):
    monkeypatch.setattr(Config, "CONTENT_ENABLED", True)
    monkeypatch.setattr(Config, "GITHUB_TOKEN", "")
    with pytest.raises(StartupConfigError):
        check_startup_requirements()


def test_passes_when_enabled_and_token_present(monkeypatch):
    monkeypatch.setattr(Config, "CONTENT_ENABLED", True)
    monkeypatch.setattr(Config, "GITHUB_TOKEN", "ghp_fake_test_token_value")
    check_startup_requirements()  # must not raise


def test_disabled_never_requires_a_token(monkeypatch):
    monkeypatch.setattr(Config, "CONTENT_ENABLED", False)
    monkeypatch.setattr(Config, "GITHUB_TOKEN", "")
    check_startup_requirements()  # must not raise -- kill switch wins


def test_error_message_names_the_env_var_but_never_a_token_value(monkeypatch):
    monkeypatch.setattr(Config, "CONTENT_ENABLED", True)
    monkeypatch.setattr(Config, "GITHUB_TOKEN", "")

    with pytest.raises(StartupConfigError) as exc_info:
        check_startup_requirements()

    message = str(exc_info.value)
    assert "DRIFT_GITHUB_TOKEN" in message  # names the env var to set
    assert "ghp_" not in message  # never echoes a token-shaped value


@pytest.mark.asyncio
async def test_serve_raises_before_binding_anything_when_misconfigured(monkeypatch, isolated_dirs):
    monkeypatch.setattr(Config, "CONTENT_ENABLED", True)
    monkeypatch.setattr(Config, "GITHUB_TOKEN", "")

    with pytest.raises(StartupConfigError):
        await main_module.serve()
