from telegram import Update
from telegram.ext import ContextTypes
from config.constants import BOT_RESPONSES, WHITEPAPER_MAP
from utils.logger import setup_logger
from .ai_handler import AIHandler
from utils.db_manager import DatabaseManager
from utils.cache_manager import CacheManager
import json

logger = setup_logger(__name__)

class BotMessageHandler:
    def __init__(self, db_manager: DatabaseManager, cache_manager: CacheManager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.ai_handler = AIHandler(cache_manager)
        self.logger = setup_logger(__name__)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command messages (fallback/AI)"""
        try:
            message = update.message.text
            user_id = update.effective_user.id

            # Check if bot is mentioned or in private chat
            if not self._should_process_message(update, context):
                return

            await update.message.reply_text(BOT_RESPONSES["thinking"], parse_mode="Markdown")

            # Get context from recent messages
            chat_context = await self._get_chat_context(user_id)

            # Fetch cached data for whitepaper and FAQ
            whitepaper_sections = await self.cache_manager.redis.get("whitepaper_sections")
            if whitepaper_sections:
                whitepaper_sections = json.loads(whitepaper_sections)
            else:
                whitepaper_sections = {}

            faq_data_str = await self.cache_manager.redis.get("faq_data")
            faq_data = json.loads(faq_data_str) if faq_data_str else {}

            user_msg_lower = message.lower()

            # Check FAQ first
            for q, a in faq_data.items():
                # A simple substring check (improve with regex or fuzzy match if needed)
                if q in user_msg_lower:
                    await self.db_manager.store_conversation(user_id, message, a)
                    await update.message.reply_text(a)
                    return

            whitepaper_str = await self.cache_manager.redis.get("whitepaper_sections")
            whitepaper_data = json.loads(whitepaper_str) if whitepaper_str else {}

            for keyword, section_name in WHITEPAPER_MAP.items():
                if keyword in user_msg_lower:
                    section_text = whitepaper_data.get(section_name.lower(), "No info found.")
                    # Add promotional stance about CipheX
                    response_text = section_text + "\n\nCheck out [Ciphex Whitepaper](https://ciphex.io/whitepaper.pdf) for more details!"
                    await self.db_manager.store_conversation(user_id, message, response_text)
                    await update.message.reply_text(response_text[:4000], parse_mode="Markdown")
                    return

            # Fallback to AI
            context_data = f"Whitepaper Sections: {whitepaper_data}\nFAQ: {faq_data}\n{chat_context}"
            response = await self.ai_handler.generate_response(message, context_data)
            await self.db_manager.store_conversation(user_id, message, response)
            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(BOT_RESPONSES["error"], parse_mode="Markdown")

    def _should_process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        # Process if in private chat or if bot is mentioned
        if update.effective_chat.type == "private":
            return True
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
