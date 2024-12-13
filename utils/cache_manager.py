# utils/cache_manager.py
import redis.asyncio as redis
from config.config import Config
from utils.logger import setup_logger

logger = setup_logger(__name__)

class CacheManager:
    def __init__(self):
        self.redis = None
        self._initialized = False

    async def init(self):
        if self._initialized:
            return
            
        try:
            self.redis = await redis.from_url(
                Config.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            self._initialized = True
        except Exception as e:
            logger.error(f"Redis initialization error: {e}")
            raise

    async def get_cached_response(self, key):
        try:
            value = await self.redis.get(key)
            if value:
                return value.decode("utf-8")
        except Exception as e:
            logger.error(f"Error getting cached response: {e}")
        return None

    async def cache_response(self, key, value):
        try:
            await self.redis.set(key, value, expire=Config.CACHE_EXPIRY)
        except Exception as e:
            logger.error(f"Error caching response: {e}")
