"""WP-7c: global maintenance-mode switch, live-bot side.

Covers the hard requirements from the rollback ledger: flag set -> holding
message on both handlers with zero LLM/FAQ/command processing; flag absent
-> normal processing; a Redis error fails open (never blocks serving).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from telegram import Update, Message, User, Chat, Bot
from telegram.ext import ContextTypes

from core.command_handler import BotCommandHandler
from core.message_handler import BotMessageHandler
from utils.maintenance import MAINTENANCE_KEY, get_maintenance_message


def _make_update_and_context(text: str, chat_type: str = "private"):
    bot = MagicMock(spec=Bot)
    bot.username = "CiphexHelpBot"

    message = MagicMock(spec=Message)
    message.text = text
    message.entities = []
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = message
    update.effective_user = MagicMock(spec=User, id=123, first_name="TestUser", is_bot=False)
    update.effective_chat = MagicMock(spec=Chat, type=chat_type)

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = bot
    return update, context


def _cache_manager_with_redis_get(return_value=None, side_effect=None):
    cache_manager = MagicMock()
    cache_manager.redis = MagicMock()
    cache_manager.redis.get = AsyncMock(return_value=return_value, side_effect=side_effect)
    return cache_manager


def _cache_manager_maintenance_check_errors_other_keys_ok():
    """A Redis double that raises ONLY on the maintenance key -- every other
    key (faq_data, whitepaper_sections, ...) behaves as if simply unset, so
    a maintenance-check failure doesn't masquerade as a whole-Redis outage
    for the rest of the handler's unrelated lookups."""
    cache_manager = MagicMock()
    cache_manager.redis = MagicMock()

    async def _get(key):
        if key == MAINTENANCE_KEY:
            raise ConnectionError("redis unreachable")
        return None

    cache_manager.redis.get = AsyncMock(side_effect=_get)
    return cache_manager


# ─────────────────────────── get_maintenance_message ───────────────────────────


@pytest.mark.asyncio
async def test_get_maintenance_message_absent_key_returns_none():
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    assert await get_maintenance_message(redis) is None


@pytest.mark.asyncio
async def test_get_maintenance_message_custom_value_returned_verbatim():
    redis = MagicMock()
    redis.get = AsyncMock(return_value="Scheduled downtime until 3pm UTC.")
    assert await get_maintenance_message(redis) == "Scheduled downtime until 3pm UTC."


@pytest.mark.asyncio
async def test_get_maintenance_message_empty_value_falls_back_to_default():
    redis = MagicMock()
    redis.get = AsyncMock(return_value="")
    message = await get_maintenance_message(redis)
    assert message is not None
    assert "support@ciphex.io" in message


@pytest.mark.asyncio
async def test_get_maintenance_message_fails_open_on_redis_error():
    redis = MagicMock()
    redis.get = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    assert await get_maintenance_message(redis) is None


@pytest.mark.asyncio
async def test_get_maintenance_message_none_client_returns_none():
    assert await get_maintenance_message(None) is None


# ───────────────────────────── BotMessageHandler ─────────────────────────────


@pytest.mark.asyncio
async def test_handle_message_replies_with_holding_message_when_maintenance_set():
    update, context = _make_update_and_context("tell me about tokenomics")
    cache_manager = _cache_manager_with_redis_get(return_value="Down for maintenance.")
    db_manager = MagicMock()

    handler = BotMessageHandler(db_manager, cache_manager)
    handler.ai_handler.generate_response = AsyncMock(side_effect=AssertionError("LLM must not be called"))

    await handler.handle_message(update, context)

    update.message.reply_text.assert_awaited_once_with("Down for maintenance.", parse_mode="Markdown")
    db_manager.store_conversation.assert_not_called()


@pytest.mark.asyncio
async def test_handle_message_normal_processing_when_maintenance_absent():
    update, context = _make_update_and_context("random unmatched gibberish query")
    cache_manager = _cache_manager_with_redis_get(return_value=None)
    db_manager = MagicMock()
    db_manager.store_conversation = AsyncMock()
    db_manager.get_recent_conversations = AsyncMock(return_value=[])

    handler = BotMessageHandler(db_manager, cache_manager)
    handler.ai_handler.generate_response = AsyncMock(return_value="an AI answer")

    await handler.handle_message(update, context)

    # Falls through to the AI path -- proves maintenance mode isn't
    # short-circuiting normal processing when the flag is absent.
    handler.ai_handler.generate_response.assert_awaited()


@pytest.mark.asyncio
async def test_handle_message_fails_open_on_redis_error_and_processes_normally():
    update, context = _make_update_and_context("random unmatched gibberish query")
    cache_manager = _cache_manager_maintenance_check_errors_other_keys_ok()
    db_manager = MagicMock()
    db_manager.store_conversation = AsyncMock()
    db_manager.get_recent_conversations = AsyncMock(return_value=[])

    handler = BotMessageHandler(db_manager, cache_manager)
    handler.ai_handler.generate_response = AsyncMock(return_value="an AI answer")

    await handler.handle_message(update, context)

    handler.ai_handler.generate_response.assert_awaited()


# ───────────────────────────── BotCommandHandler ─────────────────────────────


@pytest.mark.asyncio
async def test_handle_command_replies_with_holding_message_when_maintenance_set():
    update, context = _make_update_and_context("/price")
    cache_manager = _cache_manager_with_redis_get(return_value="Down for maintenance.")
    db_manager = MagicMock()

    handler = BotCommandHandler(db_manager, cache_manager)
    handler._handle_price = AsyncMock(side_effect=AssertionError("command must not dispatch"))

    await handler.handle_command(update, context)

    update.message.reply_text.assert_awaited_once_with("Down for maintenance.", parse_mode="Markdown")
    handler._handle_price.assert_not_called()


@pytest.mark.asyncio
async def test_handle_command_dispatches_normally_when_maintenance_absent():
    update, context = _make_update_and_context("/price")
    cache_manager = _cache_manager_with_redis_get(return_value=None)
    db_manager = MagicMock()

    handler = BotCommandHandler(db_manager, cache_manager)
    handler._handle_price = AsyncMock()

    await handler.handle_command(update, context)

    handler._handle_price.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_command_fails_open_on_redis_error_and_dispatches_normally():
    update, context = _make_update_and_context("/price")
    cache_manager = _cache_manager_with_redis_get(side_effect=ConnectionError("down"))
    db_manager = MagicMock()

    handler = BotCommandHandler(db_manager, cache_manager)
    handler._handle_price = AsyncMock()

    await handler.handle_command(update, context)

    handler._handle_price.assert_awaited_once()
