import asyncio
import hashlib
import aiohttp
import json
from datetime import datetime
from typing import Dict, Any
from config.config import Config
from utils.logger import setup_logger

logger = setup_logger()


class DataSyncer:
    def __init__(self, db_manager, cache_manager):
        self.db_manager = db_manager
        self.cache_manager = cache_manager
        self.is_syncing = False
        self.last_sync = None

    async def start_periodic_sync(self):
        """Start periodic data synchronization"""
        while True:
            try:
                await self.sync_all()
                await asyncio.sleep(Config.SYNC_INTERVAL_HOURS * 3600)
            except Exception as e:
                logger.error(f"Error in periodic sync: {e}")
                await asyncio.sleep(Config.RETRY_DELAY_SECONDS)

    async def sync_website(self):
        from scrapers.website_scraper import WebsiteScraper
        scraper = WebsiteScraper()
        data = await scraper.process()
        return data  # data should contain "ciphex_stats"

    async def sync_certik(self):
        from scrapers.certik_scraper import CertikScraper
        scraper = CertikScraper()
        data = await scraper.process()
        return data  # should contain audit_status, security_score, last_updated

    async def sync_pdf(self):
        # If you want to parse the PDF whitepaper each time:
        from scrapers.pdf_parser import PDFParser
        parser = PDFParser(pdf_path="data/training/whitepaper.pdf")
        data = await parser.process()
        return data

    async def sync_presale_stats(self):
        url = "https://ciphex.io/api/presale"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Validate data if needed
                        await self.cache_manager.update_data({"ciphex_stats": data})
                        return data
                    else:
                        logger.error(f"Failed to fetch presale stats: {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"Error fetching presale stats: {e}")
            return {}

    async def sync_all(self):
        """Synchronize all data sources"""
        if self.is_syncing:
            return

        self.is_syncing = True
        try:
            # Sync PDF data
            pdf_data = await self.sync_pdf()
            if pdf_data and self._is_data_valid(pdf_data):
                # Serialize the entire pdf_data dictionary
                serialized_data = json.dumps(pdf_data)
                # Store under the single key "whitepaper_sections"
                await self.cache_manager.redis.set("whitepaper_sections", serialized_data)
                logger.info("Whitepaper sections successfully stored in Redis under 'whitepaper_sections'.")
            else:
                logger.error("Failed to parse or validate whitepaper data.")

            # Sync presale stats
            presale_data = await self.sync_presale_stats()

            # Update cache and database
            await self._update_data_stores(pdf_data, presale_data)

            self.last_sync = datetime.now()
            logger.info("Data sync completed successfully")

        except Exception as e:
            logger.error(f"Error in sync_all: {e}")
        finally:
            self.is_syncing = False

    async def _update_data_stores(self, *data_sets):
        try:
            for data in data_sets:
                if data and self._is_data_valid(data):
                    await self.cache_manager.update_data(data)
                # Remove call to db_manager.store_data(data) if not needed:
                # If you want to store historical data in MongoDB, implement db_manager.store_data(data)
                # Otherwise, just skip it.
        except Exception as e:
            logger.error(f"Error updating data stores: {e}")

    def _is_data_valid(self, data: Dict[str, Any]) -> bool:
        """Validate data before storing"""
        return bool(data and isinstance(data, dict))

    async def sync_faq_data(self):
        """
        Sync FAQ data from file to Redis cache
        """
        try:
            # Read FAQ data from file
            with open('data/training/faq.json', 'r') as f:
                faq_data = json.load(f)
            
            # Store in Redis with expiration
            await self.cache_manager.redis.set(
                'faq_data',
                json.dumps(faq_data),
                ex=3600  # 1 hour expiration
            )
            logger.info("FAQ data synced successfully")
        except Exception as e:
            logger.error(f"Error syncing FAQ data: {e}")
