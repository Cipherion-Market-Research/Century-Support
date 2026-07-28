import importlib

from drift_monitor.config import Config


def test_defaults_are_safe():
    assert Config.CONTENT_ENABLED is True
    assert Config.OPEN_PRS is False  # shadow mode is the default (WP-7a brief)
    assert Config.NOTIFY_ENABLED is False


def test_tracked_ref_cannot_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("DRIFT_GITHUB_REPO_BRANCH", "some-other-branch")
    import drift_monitor.config as config_module

    importlib.reload(config_module)
    try:
        assert config_module.Config.TRACKED_REF == "main"
    finally:
        importlib.reload(config_module)  # restore a clean module state for later tests


def test_open_prs_env_flag_true(monkeypatch):
    monkeypatch.setenv("DRIFT_OPEN_PRS", "true")
    import drift_monitor.config as config_module

    importlib.reload(config_module)
    try:
        assert config_module.Config.OPEN_PRS is True
    finally:
        monkeypatch.delenv("DRIFT_OPEN_PRS", raising=False)
        importlib.reload(config_module)


def test_watched_path_and_cadence_defaults():
    assert Config.WATCHED_PATH_PREFIX == "src/"
    assert Config.WATCHED_PATH_SUFFIX == ".html"
    assert Config.POLL_INTERVAL_S == 24 * 60 * 60  # nightly default
    assert Config.PARITY_INTERVAL_S == 7 * 24 * 60 * 60  # weekly default
    assert len(Config.PARITY_SENTINEL_SLUGS) == 3
