"""Entrypoint.

Three CLI actions:
  - `serve` (default): run the webhook server. Never registers a webhook
    or touches setMyCommands -- config is validated, nothing more.
  - `set-webhook`: owner-run cutover action. Registers the webhook URL +
    secret with Telegram, and calls setMyCommands from commands.py.
  - `delete-webhook`: owner-run rollback action.

`set-webhook` / `delete-webhook` are NEVER invoked automatically by
`serve` or by anything at import time -- see docs/CONTRACTS.md's adapter
scope and the delivery report's cutover runbook.
"""
import argparse
import asyncio
import os
import signal
import sys

# This file uses absolute `telegram_adapter.xxx` imports throughout so it
# runs both as `python -m telegram_adapter.main` from the repo root (local
# dev, tests) and via railway.json's symlink-shim start command, which
# makes Railway's per-service root directory importable as the
# `telegram_adapter` package without this file's own directory being on
# sys.path twice.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp
from aiohttp import web
from telegram import Bot, BotCommand

from telegram_adapter.commands import TELEGRAM_COMMANDS
from telegram_adapter.config import Config
from telegram_adapter.logging_setup import get_logger, setup_logging
from telegram_adapter.webhook import create_webhook_app

logger = get_logger("telegram_adapter.main")


async def _run_serve() -> None:
    Config.validate()
    if not Config.TELEGRAM_WEBHOOK_SECRET:
        logger.warning(
            "TELEGRAM_WEBHOOK_SECRET is not set -- every webhook request will be "
            "rejected (closed) until it is configured.",
            extra={"event": "missing_webhook_secret"},
        )

    async with Bot(token=Config.TELEGRAM_TOKEN) as bot:
        if Config.SYNC_COMMANDS_ON_START:
            # Menu-only sync -- never touches the webhook registration (that
            # remains the owner-run set-webhook action). A Telegram API
            # failure here must not block serving updates.
            try:
                await bot.set_my_commands(
                    [BotCommand(name, description) for name, description in TELEGRAM_COMMANDS]
                )
                logger.info(
                    "command menu synced", extra={"event": "commands_synced", "count": len(TELEGRAM_COMMANDS)}
                )
            except Exception:
                logger.exception("command menu sync failed; serving anyway", extra={"event": "commands_sync_failed"})
        async with aiohttp.ClientSession() as session:
            app = create_webhook_app(bot=bot, session=session)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, Config.HOST, Config.PORT)
            await site.start()
            logger.info(
                "telegram_adapter started", extra={"event": "startup", "port": Config.PORT}
            )

            loop = asyncio.get_running_loop()
            stop_event = asyncio.Event()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, stop_event.set)
                except NotImplementedError:
                    pass  # not available on every platform (e.g. Windows)

            await stop_event.wait()
            logger.info("shutting down", extra={"event": "shutdown"})
            await runner.cleanup()


async def _run_set_webhook() -> None:
    Config.validate()
    if not Config.TELEGRAM_WEBHOOK_URL:
        raise RuntimeError("TELEGRAM_WEBHOOK_URL must be set to run set-webhook.")
    if not Config.TELEGRAM_WEBHOOK_SECRET:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET must be set to run set-webhook.")

    async with Bot(token=Config.TELEGRAM_TOKEN) as bot:
        await bot.set_webhook(
            url=Config.TELEGRAM_WEBHOOK_URL,
            secret_token=Config.TELEGRAM_WEBHOOK_SECRET,
            allowed_updates=["message"],
        )
        await bot.set_my_commands(
            [BotCommand(name, description) for name, description in TELEGRAM_COMMANDS]
        )
    print(f"Webhook registered at {Config.TELEGRAM_WEBHOOK_URL}; command list set.")


async def _run_delete_webhook() -> None:
    Config.validate()
    async with Bot(token=Config.TELEGRAM_TOKEN) as bot:
        await bot.delete_webhook(drop_pending_updates=False)
    print("Webhook deleted.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="telegram_adapter")
    parser.add_argument(
        "action",
        nargs="?",
        default="serve",
        choices=["serve", "set-webhook", "delete-webhook"],
        help="serve (default): run the webhook server. set-webhook / "
        "delete-webhook: owner-run cutover actions -- never run automatically.",
    )
    args = parser.parse_args()

    setup_logging(Config.LOG_LEVEL)

    if args.action == "serve":
        asyncio.run(_run_serve())
    elif args.action == "set-webhook":
        asyncio.run(_run_set_webhook())
    elif args.action == "delete-webhook":
        asyncio.run(_run_delete_webhook())


if __name__ == "__main__":
    main()
