# core/message_handler.py
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config.constants import BOT_RESPONSES, WHITEPAPER_MAP
from utils.logger import setup_logger
from .ai_handler import AIHandler
from utils.db_manager import DatabaseManager
from utils.cache_manager import CacheManager
from thefuzz import fuzz, process  # Added for fuzzy matching

logger = setup_logger(__name__)

class BotMessageHandler:
    def __init__(self, db_manager: DatabaseManager, cache_manager: CacheManager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.ai_handler = AIHandler(cache_manager)
        self.logger = setup_logger(__name__)  # Removed module-level logger duplication
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.logger.info("handle_message triggered")
        try:
            message = update.message.text
            user_id = update.effective_user.id

            self.logger.debug(f"Received message from user {user_id}: {message}")

            # Check if bot is mentioned or in private chat
            if not self._should_process_message(update, context):
                self.logger.info(f"Should process returned False for user {user_id}, message: {message}")
                return

            self.logger.info(f"Processing message from user {user_id}: {message}")

            await update.message.reply_text(BOT_RESPONSES["thinking"], parse_mode="Markdown")

            # Get context from recent messages
            chat_context = await self._get_chat_context(user_id)
            self.logger.debug(f"Chat context for user {user_id}: {chat_context}")

            # Fetch cached data for whitepaper and FAQ
            faq_data_str = await self.cache_manager.redis.get("faq_data")
            faq_data = json.loads(faq_data_str) if faq_data_str else {}
            if faq_data:
                self.logger.debug(f"Fetched faq_data from cache: {len(faq_data)} entries")
            else:
                self.logger.warning("faq_data not found in cache or empty")

            whitepaper_str = await self.cache_manager.redis.get("whitepaper_sections")
            whitepaper_data = json.loads(whitepaper_str) if whitepaper_str else {}
            self.logger.debug(f"Whitepaper data keys: {list(whitepaper_data.keys()) if whitepaper_data else 'No data'}")

            user_msg_lower = message.lower()

            # Fuzzy Matching for FAQ
            if faq_data:
                faq_questions = list(faq_data.keys())
                match, score = process.extractOne(user_msg_lower, faq_questions, scorer=fuzz.token_sort_ratio)
                similarity_threshold = 80  # Adjust based on desired sensitivity

                self.logger.debug(f"Fuzzy match result: '{match}' with score {score}")

                if score >= similarity_threshold:
                    response = faq_data[match]
                    self.logger.info(f"FAQ matched: '{match}' with score {score}")
                    await self.db_manager.store_conversation(user_id, message, response)
                    await update.message.reply_text(response)
                    return
                else:
                    self.logger.info(f"No significant FAQ match found (score: {score}). Proceeding to whitepaper or AI.")

            # Check Whitepaper sections
            matched_section = None
            for keyword, section_name in WHITEPAPER_MAP.items():
                if keyword in user_msg_lower:
                    matched_section = section_name.lower()
                    break

            if matched_section and matched_section in whitepaper_data:
                section_text = whitepaper_data.get(matched_section, "No info found.")
                response_text = f"{section_text}\n\nCheck out [Ciphex Whitepaper](https://ciphex.io/whitepaper.pdf) for more details!"
                self.logger.debug(f"Response text for whitepaper section '{matched_section}': {response_text[:100]}...")
                await self.db_manager.store_conversation(user_id, message, response_text)
                await update.message.reply_text(response_text[:4000], parse_mode="Markdown")
                return

            # Fallback to AI
            context_data = f"Whitepaper Sections: {whitepaper_data}\nFAQ: {faq_data}\n{chat_context}"
            self.logger.debug(f"Context data for AI: {context_data[:200]}...")
            response = await self.ai_handler.generate_response(message, context_data)
            self.logger.debug(f"AI response: {response[:100]}...")
            await self.db_manager.store_conversation(user_id, message, response)
            await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await update.message.reply_text(BOT_RESPONSES["error"], parse_mode="Markdown")


    def _should_process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        self.logger.debug(f"Chat: {update.effective_chat.type}, Text: {update.message.text}, Bot Username: {context.bot.username}")

        if update.effective_chat.type == "private":
            self.logger.debug("Private chat detected.")
            return True

        if update.message.entities:
            self.logger.debug(f"Entities found: {update.message.entities}")
            for entity in update.message.entities:
                if entity.type == "mention":
                    mention_text = update.message.text[entity.offset:entity.offset + entity.length]
                    self.logger.debug(f"Mention Text: {mention_text.lower()} vs @{context.bot.username.lower()}")
                    if mention_text.lower() == f"@{context.bot.username.lower()}":
                        self.logger.debug("Mention matches bot username.")
                        return True
                    mention_str = f"@{context.bot.username.lower()}"
                    if mention_str in update.message.text.lower():
                        self.logger.debug("Substring fallback match for mention found.")
                        return True

            self.logger.debug("No mention detected and not a private chat.")
            return False
        else:
            # No entities at all
            # For group chats, we only respond if mentioned or private, so no mention = no process.
            self.logger.debug("No entities in a group, not processing.")
            return False

    async def _get_chat_context(self, user_id: int) -> str:
        """Get recent chat context for user"""
        try:
            whitepaper_str = await self.cache_manager.redis.get("whitepaper_sections")
            whitepaper_data = json.loads(whitepaper_str) if whitepaper_str else {}
            recent_messages = await self.db_manager.get_recent_conversations(user_id)
            context_str = "\n".join(
                [
                    f"User: {m['message']}\nBot: {m['response']}"
                    for m in recent_messages[-3:]
                ]
            )
            self.logger.debug(f"Recent chat context for user {user_id}: {context_str}")
            return context_str
        except Exception as e:
            self.logger.error(f"Error getting chat context for user {user_id}: {e}", exc_info=True)
            return ""
