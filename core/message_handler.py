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
        """
        Main message handler. Checks for FAQ or Whitepaper matches—
        if found, provides a summarized (more conversational) answer.
        Falls back to the general GPT AI if no matches are found.
        """
        self.logger.info("handle_message triggered")
        try:
            # Basic info about user and message
            message = (update.message.text or "").strip().lower()
            user_id = update.effective_user.id

            # Quick user mention or private chat check
            if not self._should_process_message(update, context):
                self.logger.info("Skipping message as bot not mentioned or not in private chat.")
                return

            self.logger.info(f"Processing user {user_id} message: {message}")
            await update.message.reply_text(BOT_RESPONSES["thinking"], parse_mode="Markdown")

            # Get all data sources
            faq_data_str = await self.cache_manager.redis.get("faq_data")
            faq_data = json.loads(faq_data_str) if faq_data_str else {}
            
            # Split compound questions and gather all relevant information
            response_parts = []
            
            # Define common topic keywords
            topics = {
                "presale": ["presale", "pre-sale", "pre sale", "when start", "launch"],
                "supply": ["supply", "total supply", "max supply", "token supply"],
                "staking": ["staking", "stake", "rewards"],
                "join": ["join", "how to join", "participate", "how do i"],
                "minimum": ["minimum", "min purchase", "smallest amount"]
            }

            # Check each topic in the message
            for topic, keywords in topics.items():
                if any(keyword in message for keyword in keywords):
                    if topic == "presale":
                        response_parts.append(BOT_RESPONSES["presale_info"])
                    elif topic == "supply":
                        response_parts.append(
                            "**Token Supply Information:**\n"
                            "• Maximum Supply: 1.5 billion CPX Tokens\n"
                            "• Deflationary Model: Supply aims to reduce by ~95% over 10 years\n"
                            "• PreSale Allocation: 142,738,450 CPX tokens"
                        )
                    elif topic == "staking":
                        response_parts.append(
                            "**Staking Program:**\n"
                            "• Options: 6, 12, or 24-month terms\n"
                            "• Returns: Based on 10-year US Treasury yield plus premium\n"
                            "• Launch: Program starts after presale completion\n"
                            "• Rewards: Paid in unrestricted CPX tokens"
                        )
                    elif topic == "join":
                        response_parts.append(
                            "**How to Join CipheX:**\n"
                            "1. Prepare a self-custodial wallet (MetaMask, Trust Wallet, or WalletConnect)\n"
                            "2. Have USDT, USDC, or ETH ready for purchase\n"
                            "3. Visit [ciphex.io](https://ciphex.io) when presale launches (Jan 24, 2025)\n"
                            "4. Connect your wallet and complete your purchase\n"
                            "5. Minimum purchase: 2,000 CPX tokens\n\n"
                            "After purchase, you'll become a CipheX Community Member with voting rights after the presale is complete!"
                        )

            if response_parts:
                # Combine all relevant information
                final_response = "\n\n".join(response_parts)
                
                # Add a separator between different topics if multiple
                if len(response_parts) > 1:
                    final_response = final_response.replace("\n\n", "\n\n---\n\n")
                
                await update.message.reply_text(
                    final_response[:4000],  # Telegram message limit
                    parse_mode="Markdown"
                )
                return

            # If no specific topics matched, fall back to fuzzy matching and AI
            # Build chat context from recent DB logs (for GPT fallback, if needed)
            chat_context = await self._get_chat_context(user_id)

            # Pull FAQ data from Redis
            faq_data_str = await self.cache_manager.redis.get("faq_data")
            faq_data = json.loads(faq_data_str) if faq_data_str else {}

            # Pull Whitepaper data from Redis
            whitepaper_str = await self.cache_manager.redis.get("whitepaper_sections")
            whitepaper_data = json.loads(whitepaper_str) if whitepaper_str else {}

            # Check for presale-related keywords first
            presale_keywords = ["presale", "pre-sale", "pre sale", "when start", "when launch"]
            if any(keyword in message for keyword in presale_keywords):
                await update.message.reply_text(
                    BOT_RESPONSES["presale_info"],
                    parse_mode="Markdown"
                )
                return

            # 1) Attempt fuzzy match for FAQ
            matched_faq, faq_score = self._fuzzy_match_faq(message, faq_data)
            similarity_threshold = 80

            if matched_faq and faq_score >= similarity_threshold:
                original_faq_answer = faq_data[matched_faq]
                # Summarize the matched FAQ text
                summarized_answer = await self._summarize_text(
                    original_faq_answer,
                    user_query=message,
                    source_label="FAQ"
                )
                # Store & respond
                await self.db_manager.store_conversation(user_id, message, summarized_answer)
                await update.message.reply_text(summarized_answer, parse_mode="Markdown")
                return

            # 2) Attempt a whitepaper match (partial or direct map)
            matched_section = None

            # The existing approach: check if any keyword in WHITEPAPER_MAP is in the user message
            for keyword, wp_section_name in WHITEPAPER_MAP.items():
                if keyword in message:
                    matched_section = wp_section_name.lower()
                    break

            if matched_section and matched_section in whitepaper_data:
                original_wp_text = whitepaper_data[matched_section]
                # Summarize the matched Whitepaper text
                summarized_wp = await self._summarize_text(
                    original_wp_text,
                    user_query=message,
                    source_label="whitepaper"
                )
                # Optionally append a “read more” snippet
                response_text = (
                    f"{summarized_wp}\n\n"
                    "Check out https://ciphex.io/whitepaper for more details!"
                )

                # Store & respond
                await self.db_manager.store_conversation(user_id, message, response_text)
                await update.message.reply_text(response_text[:4000], parse_mode="Markdown")
                return

            # 3) Fallback to AI if no direct FAQ or Whitepaper match
            context_data = (
                f"Whitepaper Sections: {whitepaper_data}\n\n"
                f"FAQ: {faq_data}\n\n"
                f"{chat_context}"
            )
            self.logger.debug(f"Context data for AI: {context_data[:200]}...")
            ai_response = await self.ai_handler.generate_response(message, context_data)

            # Store & respond
            await self.db_manager.store_conversation(user_id, message, ai_response)
            await update.message.reply_text(ai_response, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            await update.message.reply_text(BOT_RESPONSES["error"], parse_mode="Markdown")

    def _should_process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Determine if the bot should process this message. We respond
        if it's a private chat or if we are explicitly mentioned in a group.
        """
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
        """
        Retrieve up to the last few interactions for GPT fallback context.
        """
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
    
    def _fuzzy_match_faq(self, user_message: str, faq_dict: dict):
        """
        Enhanced fuzzy matching with exact keyword prioritization
        Returns (best_match_key, score)
        """
        if not faq_dict:
            return None, 0
        # Priority keywords that should trigger specific FAQ entries
        priority_matches = {
            "price": "What is the starting price in USD?",
            "starting price": "What is the starting price in USD?",
            "token price": "What is the starting price in USD",
            "how much": "What is the starting price in USD?",
            # Add presale related priority matches
            "presale": "When does the presale start?",
            "when presale": "When does the presale start?",
            "when does presale": "When does the presale start?"
        }
        # Check for priority keyword matches first
        user_msg_lower = user_message.lower()
        for keyword, faq_question in priority_matches.items():
            if keyword in user_msg_lower and faq_question in faq_dict:
                return faq_question, 100  # Perfect match score
        # If no priority match, proceed with regular fuzzy matching
        faq_questions = list(faq_dict.keys())
        best_match, best_score = process.extractOne(
            user_message, 
            faq_questions, 
            scorer=fuzz.token_sort_ratio
        )
        return best_match, best_score

    async def _summarize_text(self, original_text: str, user_query: str, source_label: str) -> str:
        """
        Summarize or rephrase text in a more conversational style
        using your AIHandler. 
        source_label can be 'FAQ', 'whitepaper', or any future data source.
        """
        # You could tailor your prompt for each source_label if needed.
        prompt = (
            "You are CipheX Help Bot. Please rephrase or summarize the text below in a concise, "
            "friendly tone. Retain all essential information, but deliver it in a natural, "
            "user-friendly format.\n\n"
            f"Source: {source_label}\n"
            f"Original Text:\n{original_text}\n\n"
            f"User Query:\n{user_query}\n"
        )

        # Provide some minimal context so GPT knows the situation
        context_data = (
            f"We have an answer from {source_label}. "
            "Convert it into an engaging user-facing response with Markdown formatting. "
            "Feel free to use bullet points or emojis if relevant."
        )

        # Call AI handler to get summarized text
        summarized_answer = await self.ai_handler.generate_response(prompt, context_data)
        return summarized_answer.strip()