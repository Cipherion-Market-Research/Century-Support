import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, Any
from config.config import Config
from .base_scraper import BaseScraper
from utils.logger import setup_logger

logger = setup_logger()


class CertikScraper(BaseScraper):
    def __init__(self):
        self.url = Config.CERTIK_URL

    async def fetch(self) -> Dict[str, Any]:
        """Fetch Certik audit data"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url) as response:
                    if response.status == 200:
                        html = await response.text()
                        return self._parse_certik_data(html)
            return {}
        except Exception as e:
            logger.error(f"Error fetching Certik data: {e}")
            return {}

    def _parse_certik_data(self, html: str) -> Dict[str, Any]:
        """Parse Certik HTML content"""
        try:
            soup = BeautifulSoup(html, "html.parser")
            # Implement specific parsing logic based on Certik's HTML structure
            return {
                "audit_status": self._extract_audit_status(soup),
                "security_score": self._extract_security_score(soup),
                "last_updated": self._extract_last_updated(soup),
            }
        except Exception as e:
            logger.error(f"Error parsing Certik data: {e}")
            return {}

    async def validate(self, data: Dict[str, Any]) -> bool:
        """Validate Certik data"""
        required_fields = ["audit_status", "security_score", "last_updated"]
        return all(field in data for field in required_fields)

    def _extract_audit_status(self, soup: BeautifulSoup) -> str:
        # Example: Find an element with class "audit-status"
        status_elem = soup.find(class_="audit-status")
        return status_elem.get_text(strip=True) if status_elem else "Unknown"

    def _extract_security_score(self, soup: BeautifulSoup) -> str:
        score_elem = soup.find(class_="security-score")
        return score_elem.get_text(strip=True) if score_elem else "Unknown"

    def _extract_last_updated(self, soup: BeautifulSoup) -> str:
        updated_elem = soup.find(class_="last-updated")
        return updated_elem.get_text(strip=True) if updated_elem else "Unknown"
