"""Command list registered with Telegram via `setMyCommands`.

Deliberately hardcoded (name, description) pairs rather than an import of
century_core.commands.registry: this package deploys as its own Railway
service with its own root directory (see railway.json's symlink-shim start
command), so century_core's source tree is not present in the deployed
image. The two lists must still match -- that parity is enforced by
tests/test_commands_sync.py, which imports century_core directly. That
test only ever runs inside this monorepo's own dev/CI checkout, never
inside the deployed adapter image.
"""

TELEGRAM_COMMANDS = [
    ("price", "CPX price info"),
    ("ca", "Contract addresses"),
    ("claim", "Token claiming portal"),
    ("audit", "Security audit status"),
    ("stats", "Claim portal stats"),
    ("publications", "Recent Ciphex publications"),
    ("help", "Show available commands"),
    ("start", "Welcome message"),
]

COMMAND_NAMES = frozenset(name for name, _ in TELEGRAM_COMMANDS)
