from telegram import Update
from telegram.ext import ContextTypes
from config.constants import BOT_RESPONSES
from utils.logger import setup_logger
from .ai_handler import AIHandler
from utils.db_manager import DatabaseManager
from utils.cache_manager import CacheManager
import json

logger = setup_logger()


class BotMessageHandler:
    def __init__(self, db_manager: DatabaseManager, cache_manager: CacheManager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.ai_handler = AIHandler(cache_manager)
        self.logger = setup_logger(__name__)

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        await update.message.reply_text(BOT_RESPONSES["welcome"], parse_mode="Markdown")
        self.logger.info(f"Handled /start command from user {update.effective_user.id}")

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command."""
        await update.message.reply_text(BOT_RESPONSES["help"], parse_mode="Markdown")
        self.logger.info(f"Handled /help command from user {update.effective_user.id}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command messages"""
        try:
            message = update.message.text
            user_id = update.effective_user.id

            # Check if bot is mentioned or in private chat
            if not self._should_process_message(update, context):
                return

            await update.message.reply_text(BOT_RESPONSES["thinking"], parse_mode="Markdown")

            # Get context from recent messages
            chat_context = await self._get_chat_context(user_id)

            # Add near response generation:
            whitepaper_sections = await self.cache_manager.redis.get("whitepaper_sections")
            if whitepaper_sections:
                whitepaper_sections = json.loads(whitepaper_sections)
            else:
                whitepaper_sections = {}

            # Also fetch FAQ if stored (similarly)
            faq_data = await self.cache_manager.redis.get("faq_data")
            faq_data = json.loads(faq_data) if faq_data else {}

            # Add to context
            context_data = f"Whitepaper Sections: {whitepaper_sections}\nFAQ: {faq_data}"
            response = await self.ai_handler.generate_response(message, context_data)

            # Generate AI response
            response = await self.ai_handler.generate_response(message, chat_context)

            # Store conversation
            await self.db_manager.store_conversation(user_id, message, response)

            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(BOT_RESPONSES["error"], parse_mode="Markdown")

    def _should_process_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        """Determine if message should be processed"""
        # Process if in private chat
        if update.effective_chat.type == "private":
            return True

        # Process if bot is mentioned
        if context.bot.username.lower() in update.message.text.lower():
            return True

        return False

    async def _get_chat_context(self, user_id: int) -> str:
        """Get recent chat context for user"""
        recent_messages = await self.db_manager.get_recent_conversations(user_id)
        return "\n".join(
            [
                f"User: {m['message']}\nBot: {m['response']}"
                for m in recent_messages[-3:]
            ]
        )
