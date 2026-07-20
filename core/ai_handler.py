import openai
import asyncio
from typing import Optional
from config.config import Config
from utils.cache_manager import CacheManager
from utils.logger import setup_logger

logger = setup_logger(__name__)


class AIHandler:
    def __init__(self, cache_manager: CacheManager):
        openai.api_key = Config.OPENAI_API_KEY
        self.cache_manager = cache_manager

    async def generate_response(
        self, prompt: str, context: str = "", style: str = "informative"
    ) -> str:
        """Generate AI response with optional context"""
        try:
            # Add whitepaper context for better responses
            whitepaper_data = await self.cache_manager.redis.get("whitepaper_sections")
            if whitepaper_data:
                context = f"{whitepaper_data}\n\n{context}"

            # Check cache first
            cache_key = f"{prompt}:{context}"
            cached_response = await self.cache_manager.get_cached_response(cache_key)
            if cached_response:
                return cached_response

            # Prepare messages for AI
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are CipheX Help Bot, the official CipheX (CPX) project assistant for the CipheX Telegram Channel. "
                        "Your role is to answer questions accurately using only the provided context data (whitepaper sections, "
                        "FAQ entries, KPI data, etc.). "
                        "You must never solicit purchases: do not tell users they should buy CPX, do not frame buying as "
                        "recommended, and do not suppress or omit risk disclaimers when discussing price, returns, or investment decisions. "
                        "Cryptocurrency assets carry regulatory and market risk that varies by jurisdiction; when a user asks "
                        "about buying, price, or returns, note that this is not financial advice and rules vary by region. "
                        "NEVER reference 'training data' in responses; instead, just answer factually. "
                        "If a user asks about token claiming, direct them to claim.ciphex.io to access their claiming dashboard. "
                        "For queries about vesting schedules, lockups, tokenomics, or roadmap, refer to relevant whitepaper "
                        "sections or FAQ data if available; never invent numbers. "
                        "If the context does not contain the answer, say you don't know and point the user to the official "
                        "site (ciphex.io) rather than guessing. "
                        "Keep answers concise. Provide at most 2 bullet points if listing advice. "
                        "Avoid repeating the same advice multiple times. "
                        "If the user corrects you during the conversation, adjust your response accordingly, "
                        "but do not permanently alter your standard approach. "
                        "Use markdown formatting for the response. "
                        "Use links and emojis where appropriate to make the response engaging, without overstating claims."
                    )
                }
            ]

            if context:
                messages.append({"role": "system", "content": f"Context: {context}"})

            messages.append({"role": "user", "content": prompt})

            # Generate response
            response = await openai.ChatCompletion.acreate(
                model=Config.MODEL,
                messages=messages,
                max_tokens=Config.MAX_TOKENS,
                temperature=Config.TEMPERATURE,
            )

            response_text = response.choices[0].message.content

            # Cache response
            await self.cache_manager.cache_response(cache_key, response_text)

            return response_text

        except Exception as e:
            logger.error(f"Error in AI response generation: {e}")
            return "I'm having trouble generating a response. Please try again later."
          
