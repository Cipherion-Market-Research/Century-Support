from typing import Any, Dict
import re
from utils.logger import setup_logger

logger = setup_logger()


class Validators:
    @staticmethod
    def is_valid_ethereum_address(address: str) -> bool:
        """Validate Ethereum address format"""
        try:
            return bool(re.match(r"^0x[a-fA-F0-9]{40}$", address))
        except Exception as e:
            logger.error(f"Error validating Ethereum address: {e}")
            return False

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Validate URL format"""
        try:
            pattern = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\$$\$$,]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
            return bool(re.match(pattern, url))
        except Exception as e:
            logger.error(f"Error validating URL: {e}")
            return False

    @staticmethod
    def validate_scraped_data(data: Dict[str, Any]) -> bool:
        """Validate scraped data structure"""
        try:
            if not isinstance(data, dict):
                return False
            return all(
                isinstance(k, str) and isinstance(v, (str, dict, list))
                for k, v in data.items()
            )
        except Exception as e:
            logger.error(f"Error validating scraped data: {e}")
            return False
