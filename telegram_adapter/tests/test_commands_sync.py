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

from telegram_adapter.commands import COMMAND_NAMES

century_core_registry = pytest.importorskip(
    "century_core.commands.registry",
    reason="century_core not installed in this test environment -- parity check skipped",
)


def test_command_names_match_century_core_registry():
    assert COMMAND_NAMES == frozenset(century_core_registry.HANDLERS.keys())
