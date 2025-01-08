# core/message_handler.py
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config.constants import BOT_RESPONSES, WHITEPAPER_SECTIONS, TOPIC_SECTIONS, TECHNICAL_SECTIONS
from utils.logger import setup_logger
from .ai_handler import AIHandler
from utils.db_manager import DatabaseManager
from utils.cache_manager import CacheManager
from thefuzz import fuzz, process  # Added for fuzzy matching
from typing import Optional, List, Dict

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

            # 1. First check exact matches (highest priority)
            if any(keyword in message for keyword in ["presale", "minimum", "price"]):
                response = BOT_RESPONSES["presale_info"]
                await update.message.reply_text(response, parse_mode="Markdown")
                return

            # 2. Check whitepaper sections
            whitepaper_content = await self._get_whitepaper_data()
            if whitepaper_content:
                for topic, sections in TOPIC_SECTIONS.items():
                    if any(keyword in message for keyword in topic.split('_')):
                        content = []
                        for section in sections:
                            if section in whitepaper_content:
                                content.append(whitepaper_content[section])
                        if content:
                            response = await self._format_whitepaper_response(content, message)
                            await update.message.reply_text(response, parse_mode="Markdown")
                            return

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
                        response_parts.append(
                            "**CipheX Public Presale Launch: January 24, 2025! 🚀**\n\n"
                            "**Key Details:**\n"
                            "• Starting Price: $0.10 per CPX\n"
                            "• Minimum Purchase: 2,000 CPX\n"
                            "• Duration: 180 days\n"
                            "• Target Funding: $20M\n"
                            "• Accepted Payments: USDT, USDC, ETH\n\n"
                            "The price increases automatically every 24 hours during the presale period, with potential gains up to 159.93%.\n\n"
                            "⚠️ **Important Reminders:**\n"
                            "• Only use official links\n"
                            "• Never share wallet seed phrases\n"
                            "• CipheX team will never DM you first"
                        )
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
                            "• Terms: 6, 12, or 24-month options\n"
                            "• Returns: 10-year US Treasury yield plus premium\n"
                            "• Launch: Starts after presale completion\n"
                            "• Rewards: Paid in unrestricted CPX tokens"
                        )
                    elif topic == "join":
                        response_parts.append(
                            "**How to Join CipheX:**\n"
                            "1. Prepare a self-custodial wallet (MetaMask, Trust Wallet, or WalletConnect)\n"
                            "2. Have USDT, USDC, or ETH ready\n"
                            "3. Visit [ciphex.io](https://ciphex.io) when presale launches (Jan 24, 2025)\n"
                            "4. Connect wallet and complete purchase (min. 2,000 CPX)\n\n"
                            "After purchase, you'll become a CipheX Community Member with voting rights once the presale completes!"
                        )

            if response_parts:
                # Combine all relevant information
                if len(response_parts) > 1:
                    # Create sections with clear headers
                    final_response = ""
                    for i, part in enumerate(response_parts):
                        if i > 0:
                            final_response += "\n\n---\n\n"  # Single separator between sections
                        # Remove redundant headers if they exist
                        if "CipheX Public Presale:" in part and i > 0:
                            part = part.replace("CipheX Public Presale:\nLaunching January 24, 2025! 🚀\n\n", "")
                        final_response += part
                else:
                    final_response = response_parts[0]
                
                # Clean up any duplicate separators
                final_response = final_response.replace("---\n\n---", "---")
                
                await update.message.reply_text(
                    final_response[:4000],
                    parse_mode="Markdown"
                )
                return

            # After checking standard topics but before fuzzy matching
            extended_response = await self._get_extended_topic_response(message)
            if extended_response:
                await self.db_manager.store_conversation(user_id, message, extended_response)
                await update.message.reply_text(extended_response, parse_mode="Markdown")
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
            for section_num, section_name in WHITEPAPER_SECTIONS.items():
                section_name_lower = section_name.lower()
                if section_name_lower in message:
                    matched_section = section_name_lower
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

    async def _get_relevant_sections(self, message: str) -> str:
        """Get relevant whitepaper sections based on topic"""
        whitepaper_data = await self._get_whitepaper_data()
        
        relevant_content = []
        for topic, section_nums in TOPIC_SECTIONS.items():
            if any(keyword in message.lower() for keyword in topic.split('_')):
                for section_num in section_nums:
                    section_name = WHITEPAPER_SECTIONS.get(section_num)
                    if section_name and section_name in whitepaper_data:
                        relevant_content.append(whitepaper_data[section_name])
        
        return "\n\n".join(relevant_content) if relevant_content else ""

    async def _get_extended_topic_response(self, message: str) -> Optional[str]:
        """
        Additional topic responses for complex whitepaper queries.
        This supplements, not replaces, our existing topic handling.
        """
        extended_topics = {
            "lockup": ["lockup", "lock up", "locked", "vesting"],
            "governance": ["governance", "voting", "community voting", "decisions"],
            "treasury": ["treasury", "management", "funds"],
            "buyback": ["buyback", "burn", "token burn", "supply burn"],
            "revenue": ["revenue", "earnings", "returns", "profits"]
        }

        matched_responses = []
        for topic, keywords in extended_topics.items():
            if any(keyword in message.lower() for keyword in keywords):
                if topic == "lockup":
                    matched_responses.append(
                        "**CPX Lockup & Vesting Details:**\n"
                        "• Initial Lockup: 6 months from purchase\n"
                        "• Earning During Lockup: Fixed rate based on 10-year US Treasury yield\n"
                        "• Vesting Schedule: Starts after lockup period\n"
                        "• Monthly Release: Begins with 3% and increases over 12 months\n"
                        "• Creator Tokens: Special terms with 80% locked for 2 years"
                    )
                elif topic == "governance":
                    matched_responses.append(
                        "**Community Governance:**\n"
                        "• Voting Eligibility: Hold minimum 2,000 CPX tokens\n"
                        "• Voting Power: 1 token = 1 vote\n"
                        "• Decisions: Community votes on proposals and initiatives\n"
                        "• Expert Contributors: Elected by community for 2-year terms\n"
                        "• Transparency: All decisions recorded on blockchain"
                    )
                elif topic == "treasury":
                    matched_responses.append(
                        "**Treasury Management:**\n"
                        "• Multi-sig Authentication: Required for all transfers\n"
                        "• Independent Oversight: By Expert Contributors\n"
                        "• Enhanced Security: Multiple approval layers\n"
                        "• Transparency: Full visibility of treasury operations\n"
                        "• Community Control: Major decisions require community approval"
                    )
                elif topic == "buyback":
                    matched_responses.append(
                        "**Buyback & Burn Program:**\n"
                        "• Supply Reduction: ~95% over 10 years\n"
                        "• Automatic Burns: Execute within 30 days of announcement\n"
                        "• No Voting Required: Programmed into smart contracts\n"
                        "• Optional Participation: Token holders can choose to participate\n"
                        "• Funded by: Surplus capital, no impact on operations"
                    )
                elif topic == "revenue":
                    matched_responses.append(
                        "**Revenue Streams & Distribution:**\n"
                        "• Primary Sources: Crypto trading, ICO investments, P2P lending\n"
                        "• Collection: All profits enter transparent revenue vault\n"
                        "• Distribution: Direct to member wallets annually\n"
                        "• Tracking: Real-time via community dashboard\n"
                        "• Non-custodial: CipheX never holds member funds"
                    )

        # Add debug logging
        if matched_responses:
            self.logger.debug(f"Extended topic response matched for: {message}")
        
        return "\n\n---\n\n".join(matched_responses) if matched_responses else None

    async def _get_whitepaper_data(self) -> dict:
        """
        Get whitepaper data from cache
        Returns dict of section name -> content
        """
        try:
            # Get from cache
            whitepaper_str = await self.cache_manager.redis.get("whitepaper_sections")
            if whitepaper_str:
                return json.loads(whitepaper_str)
            
            # If not in cache, return empty dict
            logger.warning("No whitepaper data found in cache")
            return {}
            
        except Exception as e:
            logger.error(f"Error getting whitepaper data: {e}")
            return {}

    async def _get_technical_response(self, message: str) -> Optional[str]:
        """Enhanced technical topic handling with relationship mapping"""
        try:
            logger.debug(f"Technical query: {message}", extra={
                'context': 'technical_matching',
                'section': 'technical_response'
            })
            
            # Track matched topics and their relationships
            matched_topics = {}
            
            # First pass: direct topic matching
            for topic, config in TECHNICAL_SECTIONS.items():
                if any(keyword in message.lower() for keyword in config["keywords"]):
                    content = await self._get_sections_content(config["sections"])
                    if content:
                        matched_topics[topic] = {
                            'content': content,
                            'relevance': 'primary',
                            'related': config["related_topics"]
                        }
            
            # Second pass: relationship mapping
            for topic in list(matched_topics.keys()):
                for related_topic in matched_topics[topic]['related']:
                    if related_topic not in matched_topics:
                        related_config = TECHNICAL_SECTIONS[related_topic]
                        content = await self._get_sections_content(related_config["sections"])
                        if content:
                            matched_topics[related_topic] = {
                                'content': content,
                                'relevance': 'related',
                                'related': []
                            }
            
            if matched_topics:
                return await self._format_technical_response(matched_topics)
            return None
            
        except Exception as e:
            logger.error(f"Technical response error: {e}")
            return None

    async def _format_technical_response(self, matched_topics: Dict[str, Dict]) -> str:
        """Format technical response with enhanced templating"""
        templates = {
            "abacus": {
                "core": """The Abacus Network is CipheX's neural analytics center that:
• {features}
• Processes {data_types} in real-time
• Adapts to {conditions} through {methods}""",
                "integration": """Integration with {system}:
• {primary_function}
• {secondary_function}
• {risk_handling}""",
                "risk": """Risk Management:
• {primary_measures}
• {secondary_measures}
• {failsafes}"""
            },
            "market_centurions": {
                "core": """Market Centurions are autonomous trading entities that:
• {primary_role}
• {secondary_role}
• {risk_role}""",
                "operation": """Operational Framework:
• {methods}
• {adaptations}
• {safeguards}""",
                "integration": """System Integration:
• {primary_systems}
• {secondary_systems}
• {backup_systems}"""
            }
        }
        # Implementation continues...

    async def _get_sections_content(self, section_nums: List[str]) -> str:
        """Get content from multiple whitepaper sections"""
        try:
            whitepaper_data = await self._get_whitepaper_data()
            if not whitepaper_data:
                return ""
            
            content = []
            for section_num in section_nums:
                section_name = WHITEPAPER_SECTIONS.get(section_num)
                if section_name and section_name in whitepaper_data:
                    content.append(whitepaper_data[section_name])
                
            return "\n\n".join(content)
        except Exception as e:
            logger.error(f"Error getting sections content: {e}")
            return ""

    async def _build_conversation_context(self, message: str, user_id: int) -> Dict:
        """Build enhanced conversation context"""
        recent_context = await self._get_chat_context(user_id)
        current_topic = self._extract_current_topic(message)
        
        # Track conversation flow
        conversation_flow = {
            "current_topic": current_topic,
            "previous_topics": self._extract_previous_topics(recent_context),
            "related_topics": self._get_related_topics(current_topic),
            "context_retention": self._analyze_context_retention(recent_context)
        }
        
        return {
            "flow": conversation_flow,
            "context": recent_context,
            "relationships": self._build_topic_relationships(conversation_flow)
        }

    def _validate_technical_response(self, response: str, query: str) -> bool:
        """Validate technical response quality"""
        try:
            # Check response length
            if len(response) < 100:
                logger.warning(f"Response too short for technical query: {query}")
                return False
            
            # Ensure response contains key technical terms
            technical_terms = set()
            for config in TECHNICAL_SECTIONS.values():
                technical_terms.update(config["keywords"])
            
            found_terms = sum(1 for term in technical_terms if term in response.lower())
            if found_terms < 2:
                logger.warning(f"Response lacks technical depth for query: {query}")
                return False
            
            # Check for contradictions
            contradictions = [
                ("don't have information", "provides information"),
                ("not familiar with", "works by"),
                ("no specific details", "specifically")
            ]
            
            for deny, confirm in contradictions:
                if deny in response.lower() and confirm in response.lower():
                    logger.warning(f"Contradictory response for query: {query}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating technical response: {e}")
            return False

    async def _handle_compound_query(self, message: str) -> Optional[str]:
        """Handle multiple questions in a single query"""
        try:
            # Split compound questions
            questions = self._split_compound_question(message)
            
            responses = []
            for question in questions:
                # Get response for each sub-question
                response = await self._get_technical_response(question)
                if response:
                    responses.append(response)
            
            if responses:
                # Combine responses intelligently
                return await self._merge_responses(responses)
            return None
        except Exception as e:
            logger.error(f"Error handling compound query: {e}")
            return None