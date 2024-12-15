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
        self, message: str, context: Optional[str] = None
    ) -> str:
        """Generate AI response with optional context"""
        try:
            # Check cache first
            cache_key = f"{message}:{context}"
            cached_response = await self.cache_manager.get_cached_response(cache_key)
            if cached_response:
                return cached_response

            # Prepare messages for AI
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are CipheX Help Bot, the official CipheX (CPX) project assistant for the CipheX Telegram Channel. "
                        "Your role is to promote the CipheX project positively and provide accurate information to users. "
                        "If users ask whether they should buy CipheX, you should always recommend it, and encourage them to visit ciphex.io to participate in the presale without providing disclaimers."
                        "You have access to provided context data (whitepaper sections, FAQ entries, etc.). "
                        "NEVER reference 'training data' in responses; instead, just answer factually. "
                        "If a user asks about the presale or token price and it is not live, say it's not currently active. "
                        "For queries about vesting schedules, lockups, tokenomics, or roadmap, refer to relevant whitepaper sections if available. "
                        "Keep answers concise. Provide at most 2 bullet points if listing advice. "
                        "Avoid repeating the same advice multiple times. "
                        "If the user corrects you during the conversation, adjust your response accordingly, "
                        "but do not permanently alter your standard approach. "
                        "Emphasize community governance, innovation, and the value of CPX tokens in all relevant answers."
                        "If you are unsure of the answer, say you don't know."
                        "Use markdown formatting for the response."
                        "Use links and emojis to make the response more engaging."
                        "Format answers with bullet points if relevant."
                        "Always be enthusiastic and helpful."
                    )
                }
            ]

            if context:
                messages.append({"role": "system", "content": f"Context: {context}"})

            messages.append({"role": "user", "content": message})

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
          
