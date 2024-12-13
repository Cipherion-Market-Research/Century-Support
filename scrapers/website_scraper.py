import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, Any
from config.config import Config
from .base_scraper import BaseScraper
from utils.logger import setup_logger

logger = setup_logger()


class WebsiteScraper(BaseScraper):
    def __init__(self):
        super().__init__()
        self.base_url = "https://ciphex.io"
        self.urls = Config.WEBSITE_URLS

    async def fetch(self) -> Dict[str, Any]:
        """Fetch website content"""
        results = {}
        try:
            # Fetch the main page once
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url) as response:
                    if response.status == 200:
                        html = await response.text()
                        # Parse sections from the main page
                        for section in self.urls.keys():
                            results[section] = self._parse_section(html, section)
                    else:
                        logger.error(f"Failed to fetch main page: {response.status}")
        except Exception as e:
            logger.error(f"Error fetching main page: {e}")
        return results

    def _parse_section(self, html: str, section: str) -> str:
        """Parse specific section content using section IDs"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Find the section by ID
            section_element = soup.find(id=section)
            if section_element:
                # Clean and return the section content
                return self._clean_content(section_element.get_text(strip=True))
            else:
                logger.warning(f"Section '{section}' not found in HTML")
                return ""
        except Exception as e:
            logger.error(f"Error parsing section {section}: {e}")
            return ""

    def _clean_content(self, content: str) -> str:
        """Clean and format the extracted content"""
        # Remove extra whitespace and normalize text
        return " ".join(content.split())

    async def validate(self, data: Dict[str, Any]) -> bool:
        """Validate website data"""
        return all(isinstance(v, str) and len(v.strip()) > 0 for v in data.values())
