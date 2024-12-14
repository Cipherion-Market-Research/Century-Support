# utils/db_manager.py
import motor.motor_asyncio
from config.config import Config
from utils.logger import setup_logger
from datetime import datetime

logger = setup_logger(__name__)


class DatabaseManager:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(Config.MONGODB_URI)
        self.db = self.client["ciphex_db"]

    async def store_conversation(self, user_id, message, response):
        try:
            await self.db.conversations.insert_one(
                {
                    "user_id": user_id,
                    "message": message,
                    "response": response,
                    "timestamp": datetime.utcnow(),
                }
            )
        except Exception as e:
            logger.error(f"Error storing conversation: {e}")

    async def get_recent_conversations(self, user_id, limit=3):
        try:
            cursor = (
                self.db.conversations.find({"user_id": user_id})
                .sort("timestamp", -1)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            logger.error(f"Error fetching conversations: {e}")
            return []

    async def update_data(self, data: dict):
        # Store each key-value pair
        for k, v in data.items():
            await self.redis.set(k, v)