from typing import Dict, Any
from .base_scraper import BaseScraper
from utils.logger import setup_logger
from config.constants import WHITEPAPER_SECTIONS
import re

logger = setup_logger()

class WhitepaperParser(BaseScraper):
    def __init__(self, file_path: str = "data/training/whitepaper.txt"):
        self.file_path = file_path

    async def fetch(self) -> str:
        """Read whitepaper from plaintext file"""
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                return file.read()
        except FileNotFoundError:
            logger.error(f"Whitepaper not found at {self.file_path}")
            return ""
        except Exception as e:
            logger.error(f"Error reading whitepaper: {e}")
            return "" 

    async def process(self) -> Dict[str, Any]:
        """Process the whitepaper and extract structured content"""
        try:
            raw_text = await self.fetch()
            if not raw_text:
                return {}
            
            sections = {}
            for section_num in WHITEPAPER_SECTIONS.keys():
                content = await self._extract_section_content(raw_text, section_num)
                if content:
                    sections[WHITEPAPER_SECTIONS[section_num]] = content
                
            return sections
        except Exception as e:
            logger.error(f"Error processing whitepaper: {e}")
            return {}

    async def _extract_section_content(self, text: str, section_num: str) -> str:
        """Extract content for a specific section number"""
        try:
            section_start = f"{section_num}\\s+[A-Za-z].*?\\n"
            next_section = f"\\d+\\.\\d+\\s+[A-Za-z]"
            
            start_match = re.search(section_start, text, re.MULTILINE)
            if not start_match:
                logger.warning(f"No start match found for section {section_num}")
                return ""
            
            start_pos = start_match.start()
            next_match = re.search(next_section, text[start_pos + 1:], re.MULTILINE)
            end_pos = (next_match.start() + start_pos + 1) if next_match else len(text)
            
            content = text[start_pos:end_pos]
            return self._clean_section_content(content)
            
        except Exception as e:
            logger.error(f"Error extracting section {section_num}: {e}")
            return ""

    def _clean_section_content(self, content: str) -> str:
        """Clean and format section content"""
        try:
            lines = content.split('\n')
            cleaned_lines = []
            
            for line in lines:
                if re.match(r'^\d+\s*Page\s*\|', line) or line.strip() == '':
                    continue
                if re.match(r'^\.+\d+$', line):
                    continue
                
                line = ' '.join(line.split())
                if line:
                    cleaned_lines.append(line)
            
            cleaned = ' '.join(cleaned_lines)
            cleaned = re.sub(r'^\d+\.\d+\s+', '', cleaned)
            cleaned = re.sub(r'\s+', ' ', cleaned)
            
            return cleaned.strip()
            
        except Exception as e:
            logger.error(f"Error cleaning content: {e}")
            return content 

    async def validate(self, data: Dict[str, Any]) -> bool:
        """Validate the parsed whitepaper data"""
        try:
            if not isinstance(data, dict):
                return False
            
            # Check required sections
            required_sections = [
                "Introduction",
                "The CipheX Ecosystem",
                "The Origin of CipheX",
                "Autonomous Market Trading"
            ]
            
            # Verify content quality
            for section in required_sections:
                if section not in data:
                    logger.error(f"Missing required section: {section}")
                    return False
                if len(data[section]) < 50:  # Minimum content length
                    logger.error(f"Section too short: {section}")
                    return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error validating whitepaper data: {e}")
            return False 