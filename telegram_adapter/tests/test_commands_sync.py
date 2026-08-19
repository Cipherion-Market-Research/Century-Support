"""Parity check between this adapter's hardcoded TELEGRAM_COMMANDS (used
for setMyCommands) and century_core's actual command registry.

telegram_adapter deploys as its own Railway service (its own root
directory, per railway.json's symlink-shim start command) and never
imports century_core at runtime -- the two command lists are necessarily
maintained as separate literals. This test is the parity guarantee: it
imports century_core directly, which is only possible in this monorepo's
own dev/CI checkout (century_core's dependencies are not part of this
package's own requirements-dev.txt). It skips cleanly rather than failing
in a stripped-down environment where only telegram_adapter's own
requirements are installed.
"""
import pytest

from telegram_adapter.commands import COMMAND_NAMES, TELEGRAM_COMMANDS

century_core_registry = pytest.importorskip(
    "century_core.commands.registry",
    reason="century_core not installed in this test environment -- parity check skipped",
)


def test_command_names_match_century_core_registry():
    assert COMMAND_NAMES == frozenset(century_core_registry.HANDLERS.keys())


def test_command_order_matches_century_core_registry():
    # Telegram renders /help and the command menu in registration order --
    # a bare set-equality check (above) can't catch the two lists silently
    # drifting into different groupings/orderings, so pin sequence too.
    adapter_order = [name for name, _ in TELEGRAM_COMMANDS]
    registry_order = list(century_core_registry.HANDLERS.keys())
    assert adapter_order == registry_order


async def test_serve_startup_syncs_command_menu(monkeypatch):
    """SYNC_COMMANDS_ON_START (default true) registers the current command
    list with Telegram on every serve boot, so a deploy that changes
    TELEGRAM_COMMANDS can never ship a stale menu (live finding,
    2026-08-18: /publications lingered in the menu after its removal
    deployed). Webhook registration must NOT happen here."""
    import asyncio
    from unittest.mock import AsyncMock, patch

    from telegram_adapter import main as adapter_main
    from telegram_adapter.config import Config

    calls = {}

    class FakeBot:
        def __init__(self, token):
            calls["token"] = token
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def set_my_commands(self, commands):
            calls["commands"] = [(c.command, c.description) for c in commands]
            raise _StopServe()  # stop before the network server starts
        async def set_webhook(self, *a, **k):
            raise AssertionError("serve must never register a webhook")

    class _StopServe(BaseException):
        # BaseException so the serve loop's failure-tolerant except Exception
        # around the menu sync cannot swallow it
        pass

    monkeypatch.setattr(Config, "TELEGRAM_TOKEN", "test-token")
    monkeypatch.setattr(Config, "CENTURY_CORE_URL", "http://core.test")
    monkeypatch.setattr(Config, "TELEGRAM_WEBHOOK_SECRET", "s")
    monkeypatch.setattr(Config, "SYNC_COMMANDS_ON_START", True)
    with patch.object(adapter_main, "Bot", FakeBot):
        try:
            await adapter_main._run_serve()
        except _StopServe:
            pass
    from telegram_adapter.commands import TELEGRAM_COMMANDS
    assert calls["commands"] == list(TELEGRAM_COMMANDS)
