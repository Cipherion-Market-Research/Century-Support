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

    async def _fetch_ciphex_stats(self, html: str) -> dict:
        """
        Parse the ciphex.io main page HTML to extract community/token stats.
        This is an example. You must identify actual HTML elements and classes/ids from ciphex.io.
        """
        soup = BeautifulSoup(html, "html.parser")
        
        contributions_elem = soup.find(id="total_contributions")
        if contributions_elem:
            total_contributions = contributions_elem.get_text(strip=True)
        else:
            total_contributions = "Unknown"

        tokens_elem = soup.find(id="total_allocated")
        tokens_allocated = tokens_elem.get_text(strip=True) if tokens_elem else "Unknown"

        return {
            "total_contributions": total_contributions,
            "tokens_allocated": tokens_allocated,
        }

    async def fetch(self) -> Dict[str, Any]:
        """Fetch website content"""
        results = {}
        try:
            # Fetch the main page once
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url) as response:
                    if response.status == 200:
                        html = await response.text()
                        ciphex_stats = await self._fetch_ciphex_stats(html)
                        results["ciphex_stats"] = ciphex_stats
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
        # Now we expect 'ciphex_stats' as a key:
        return "ciphex_stats" in data and isinstance(data["ciphex_stats"], dict)