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
												"You are Century Assistant, an AI assistant for the Ciphex crypto project. "
												"You have access to the following data:\n"
												f"{context}\n"  # This includes price, stats, etc.
												"Base your answers on the above data and the project's documentation. "
												"Use links provided and the whitepaper sections when relevant. "
												"Format answers with bullet points, emojis, and short paragraphs."
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
          
