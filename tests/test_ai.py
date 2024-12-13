# tests/test_ai.py
import pytest
from unittest.mock import AsyncMock
from core.ai_handler import AIHandler
from config.config import Config

@pytest.mark.asyncio
async def test_ai_handler_with_cache():
    cache_manager = AsyncMock()
    cache_manager.get_cached_response = AsyncMock(return_value=None)
    cache_manager.cache_response = AsyncMock()

    ai_handler = AIHandler(cache_manager)

    # Mock OpenAI response
    import openai
    openai.ChatCompletion.acreate = AsyncMock(return_value=AsyncMock(choices=[AsyncMock(message=AsyncMock(content="AI Response"))]))

    response = await ai_handler.generate_response("What is CipheX?", "Context: roadmap")
    assert response == "AI Response"
    cache_manager.cache_response.assert_awaited_once()
