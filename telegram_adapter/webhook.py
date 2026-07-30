"""aiohttp web app: the Telegram webhook endpoint + /health.

Owner ruling (webhook registration): this module only ever *serves* the
webhook route -- it never calls `setWebhook` itself. Registration is the
`set-webhook` CLI action in main.py, run by the owner by hand at cutover.

Error handling: the live bot (core/message_handler.py, core/command_handler.py)
has no top-level error handler -- an unhandled exception there just
propagates out of the PTB update-processing loop. This module's hard
requirement is the opposite: `_handle_update` below is the single place
every failure in translation/core-call/render/send funnels through, is
logged, and is turned into a safe response -- Telegram always gets a fast
200 so it doesn't retry-storm a transient failure, and the user gets
CORE_FAILURE_MESSAGE instead of silence when anything in the pipeline
breaks.
"""
import logging
from typing import Optional

import aiohttp
from aiohttp import web
from telegram import Bot

from telegram_adapter.bot_sender import send_plain_text, send_rendered_messages
from telegram_adapter.config import Config
from telegram_adapter.core_client import CORE_FAILURE_MESSAGE, post_message
from telegram_adapter.envelope import translate_update
from telegram_adapter.markdown import render_blocks

logger = logging.getLogger("telegram_adapter.webhook")


async def _handle_update(update: dict, *, bot: Bot, session: aiohttp.ClientSession) -> None:
    envelope = translate_update(update, bot_username=bot.username or "")
    if envelope is None:
        return  # mention-gating: silently ignored, never forwarded to core

    chat_id = int(envelope["chat_ref"])
    thread_id = int(envelope["thread_ref"]) if envelope["thread_ref"] is not None else None

    response_ir = await post_message(session, envelope)
    if response_ir is None:
        await send_plain_text(bot, chat_id=chat_id, thread_id=thread_id, text=CORE_FAILURE_MESSAGE)
        return

    messages = render_blocks(response_ir)
    await send_rendered_messages(bot, chat_id=chat_id, thread_id=thread_id, messages=messages)


def create_webhook_app(*, bot: Bot, session: aiohttp.ClientSession) -> web.Application:
    app = web.Application()

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def telegram_webhook(request: web.Request) -> web.Response:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if not Config.TELEGRAM_WEBHOOK_SECRET or secret != Config.TELEGRAM_WEBHOOK_SECRET:
            logger.warning("rejected webhook request: bad or missing secret token")
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)

        try:
            update = await request.json()
        except Exception:
            logger.warning("rejected webhook request: invalid JSON body")
            return web.json_response({"ok": False, "error": "invalid body"}, status=400)

        # Single funnel point for every failure downstream (translation,
        # the core POST, rendering, sending) -- see module docstring.
        try:
            await _handle_update(update, bot=bot, session=session)
        except Exception:
            logger.exception("unhandled error processing Telegram update")
            # Telegram still gets 200: an error here is ours to fix, not a
            # signal for Telegram to keep re-delivering the same update.

        return web.json_response({"ok": True})

    app.router.add_post(Config.WEBHOOK_PATH, telegram_webhook)
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    return app
