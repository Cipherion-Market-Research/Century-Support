from typing import Dict, Any, List
from .base_scraper import BaseScraper
from utils.logger import setup_logger
from config.constants import COMPOSITE_SECTIONS
import re
import os

logger = setup_logger()

class CompositeDocumentParser(BaseScraper):
    def __init__(self, file_path: str = None):
        self.file_path = file_path or "data/llm_composite.md"

    async def fetch(self) -> str:
        """Read content from the composite markdown file."""
        try:
            logger.debug(f"Attempting to read composite document from: {self.file_path}")
            if not os.path.exists(self.file_path):
                logger.error(f"Composite document not found at: {self.file_path}")
                return ""
            
            with open(self.file_path, "r", encoding="utf-8") as file:
                content = file.read()
                logger.info(f"Successfully read composite document ({len(content)} chars)")
                return content
        except Exception as e:
            logger.error(f"Error reading composite document: {e}")
            return ""

    async def process(self) -> Dict[str, Any]:
        """Process the composite document and extract structured content."""
        try:
            raw_text = await self.fetch()
            if not raw_text:
                return {}
            
            sections = self._extract_sections(raw_text)
            return sections
        except Exception as e:
            logger.error(f"Error processing composite document: {e}")
            return {}

    def _extract_sections(self, text: str) -> Dict[str, str]:
        """Extract content for each section based on markdown headers."""
        sections = {}
        for i, section_name in enumerate(COMPOSITE_SECTIONS):
            start_pattern = f"## {re.escape(section_name)}"
            
            # Determine the end pattern (next section header or end of file)
            if i + 1 < len(COMPOSITE_SECTIONS):
                next_section_name = COMPOSITE_SECTIONS[i+1]
                end_pattern = f"## {re.escape(next_section_name)}"
            else:
                end_pattern = None

            # Search for the start of the section
            start_match = re.search(start_pattern, text, re.MULTILINE)
            if not start_match:
                logger.warning(f"Section not found: {section_name}")
                continue

            start_pos = start_match.end()

            # Search for the end of the section
            if end_pattern:
                end_match = re.search(end_pattern, text[start_pos:], re.MULTILINE)
                end_pos = end_match.start() + start_pos if end_match else len(text)
            else:
                end_pos = len(text)
            
            content = text[start_pos:end_pos].strip()
            sections[section_name] = self._clean_content(content)
            
        return sections

    def _clean_content(self, content: str) -> str:
        """Clean and format section content."""
        # Removes markdown headers and extra whitespace
        cleaned = re.sub(r'###\s.*', '', content)
        cleaned = ' '.join(cleaned.split())
        return cleaned.strip()

    async def validate(self, data: Dict[str, Any]) -> bool:
        """Validate the parsed composite document data."""
        try:
            if not isinstance(data, dict) or not data:
                logger.error("Validation failed: Data is not a valid dictionary or is empty.")
                return False

            # Check for the presence of required sections
            for section in COMPOSITE_SECTIONS:
                if section not in data:
                    logger.error(f"Missing required section: {section}")
                    return False
                # Optional: Check for minimum content length
                if len(data[section]) < 20:
                    logger.warning(f"Section content may be too short: {section}")

            return True
        except Exception as e:
            logger.error(f"Error validating composite document data: {e}")
            return False