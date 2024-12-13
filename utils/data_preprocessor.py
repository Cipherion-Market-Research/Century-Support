import re
from typing import Dict, Any
from utils.logger import setup_logger

logger = setup_logger()


class DataPreprocessor:
    @staticmethod
    def clean_text(text: str) -> str:
        """Clean and normalize text"""
        try:
            # Remove extra whitespace
            text = re.sub(r"\s+", " ", text)
            # Remove special characters
            text = re.sub(r"[^\w\s\.\,\!\?]", "", text)
            return text.strip()
        except Exception as e:
            logger.error(f"Error cleaning text: {e}")
            return text

    @staticmethod
    def format_for_training(data: Dict[str, Any]) -> str:
        """Format data for AI training"""
        try:
            formatted = []
            for section, content in data.items():
                if isinstance(content, str):
                    formatted.append(f"### {section.upper()}\n{content}\n")
            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"Error formatting data: {e}")
            return ""

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 1000) -> list:
        """Split text into smaller chunks for processing"""
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
