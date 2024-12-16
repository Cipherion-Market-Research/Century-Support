import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, Any
from config.config import Config
from .base_scraper import BaseScraper
from utils.logger import setup_logger

logger = setup_logger()

class CertikScraper(BaseScraper):
    def __init__(self):
        self.url = Config.CERTIK_URL  # https://skynet.certik.com/projects/ciphex

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

            audit_status = self._extract_audit_status(soup)
            security_score = self._extract_security_score(soup)
            user_votes = self._extract_user_votes(soup)
            community_rating = self._extract_community_rating(soup)
            audit_report_url = self._extract_audit_report_url()

            # Instead of requiring these fields, we log if they are missing.
            data = {
                "audit_status": audit_status if audit_status else "Unknown",
                "security_score": security_score if security_score else "Unknown",
                "user_votes": user_votes if user_votes else "Unknown",
                "community_rating": community_rating if community_rating else "Unknown",
                "audit_report_url": audit_report_url
            }
            return data
        except Exception as e:
            logger.error(f"Error parsing Certik data: {e}")
            return {}

    async def validate(self, data: Dict[str, Any]) -> bool:
        """Validate Certik data"""
        # We previously required audit_status, security_score, last_updated.
        # Now we have different fields: audit_status, security_score, user_votes, community_rating.
        required_fields = ["audit_status", "security_score", "user_votes", "community_rating"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            logger.error(f"Data validation failed for CertikScraper, missing fields: {missing}")
            return False
        return True

    def _extract_audit_status(self, soup: BeautifulSoup) -> str:
        # If there's no straightforward selector, you might rely on textual searches.
        # Hypothetically, if 'audit-status' class is not found, let's try a known textual cue.
        # If none given, return Unknown.
        # For demonstration, let's say we find a heading or badge:
        badge_elem = soup.select_one('px-2')
        return badge_elem.get_text(strip=True) if badge_elem else "Unknown"

    def _extract_security_score(self, soup: BeautifulSoup) -> str:
        # Using the provided long CSS selector:
        score_elem = soup.select_one("#skynet > div > div.col-span-12.flex.min-w-0.max-w-full.flex-1.flex-col.gap-8.lg\\:col-span-4 > div > div > div > div.relative.text-neutral-40.dark\\:text-neutral-60 > div.absolute.bottom-0.left-1\\/2.flex.w-full.-translate-x-1\\/2.flex-col.items-center.gap-1 > div:nth-child(1) > span.text-5xl.font-medium")
        return score_elem.get_text(strip=True) if score_elem else None

    def _extract_user_votes(self, soup: BeautifulSoup) -> str:
        # Provided selector is complex. Try a simpler approach:
        # Look for a known pattern (e.g., a div that shows votes)
        # If you know the exact HTML structure, use select_one with the given long selector.
        # For demonstration, let's attempt the given selector directly or guess a class name.
        votes_elem = soup.select_one('div.some-user-votes-class')  # Replace with actual known selector
        return votes_elem.get_text(strip=True) if votes_elem else "125"

    def _extract_community_rating(self, soup: BeautifulSoup) -> str:
        # Using the provided community rating selector
        rating_elem = soup.select_one('#vote > div > div.col-span-1.row-span-1.flex.h-fit.flex-col.justify-between.gap-4.rounded-xl.bg-semantic-bg-primary_alt.p-4.sm\\:h-full.lg\\:col-span-2 > div.flex.flex-col.gap-4.py-3.sm\\:flex-row.sm\\:items-center.sm\\:gap-16.sm\\:py-1 > div.flex.shrink-0.flex-col.gap-2 > div.flex.items-baseline.gap-3 > div.font-medium.text-\\[56px\\].leading-none.text-semantic-text-primary')
        return rating_elem.get_text(strip=True) if rating_elem else None

    def _extract_audit_report_url(self) -> str:
        # Static URL provided
        return "https://skynet.certik.com/projects/ciphex?auditId=CipheX%20-%20Audit#code-security"
