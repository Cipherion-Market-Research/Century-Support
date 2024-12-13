from abc import ABC, abstractmethod
from typing import Any, Dict
from utils.logger import setup_logger

logger = setup_logger()


class BaseScraper(ABC):
    @abstractmethod
    async def fetch(self) -> Dict[str, Any]:
        """Fetch data from source"""
        pass

    @abstractmethod
    async def validate(self, data: Dict[str, Any]) -> bool:
        """Validate fetched data"""
        pass

    async def process(self) -> Dict[str, Any]:
        """Process and validate data"""
        try:
            data = await self.fetch()
            if await self.validate(data):
                return data
            logger.error("Data validation failed")
            return {}
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            return {}
