# tests/test_handlers.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, Message, User, Chat, Bot
from telegram.ext import ContextTypes
from core.message_handler import BotMessageHandler
from config.constants import BOT_RESPONSES

@pytest.fixture
def mock_bot():
    bot = MagicMock(spec=Bot)
    bot.username = "CiphexHelpBot"
    return bot

@pytest.fixture
def mock_message(mock_bot):
    message = MagicMock(spec=Message)
    message._bot = mock_bot
    message.reply_text = AsyncMock()
    return message

@pytest.mark.asyncio
async def test_start_command(mock_bot, mock_message):
    # Setup
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User, id=123, first_name="TestUser", is_bot=False)
    update.message = mock_message
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = mock_bot

    # Initialize handler
    db_manager = MagicMock()
    cache_manager = MagicMock()
    handler = BotMessageHandler(db_manager, cache_manager)

    # Execute
    await handler.handle_start(update, context)

    # Assert
    mock_message.reply_text.assert_called_once()

@pytest.mark.asyncio
async def test_help_command(mock_bot, mock_message):
    # Setup
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User, id=123, first_name="TestUser", is_bot=False)
    update.message = mock_message
    update.message.text = "/help"
    
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = mock_bot

    # Initialize handler
    db_manager = MagicMock()
    cache_manager = MagicMock()
    handler = BotMessageHandler(db_manager, cache_manager)

    # Execute
    await handler.handle_help(update, context)

    # Assert
    mock_message.reply_text.assert_called_once_with(BOT_RESPONSES["help"])

@pytest.mark.asyncio
async def test_message_handling_with_mention(mock_bot, mock_message):
    # Setup
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User, id=123)
    update.message = mock_message
    update.message.text = "@CenturySupport Tell me about tokenomics"
    
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = mock_bot

    db_manager = MagicMock()
    cache_manager = MagicMock()
    handler = BotMessageHandler(db_manager, cache_manager)
    
    # Execute
    await handler.handle_message(update, context)
    
    # Assert
    assert mock_message.reply_text.call_count >= 1
