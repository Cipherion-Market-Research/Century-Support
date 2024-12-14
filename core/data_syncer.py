import asyncio
from datetime import datetime
import hashlib
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

    async def sync_all(self):
        """Synchronize all data sources"""
        if self.is_syncing:
            return

        self.is_syncing = True
        try:
            # Sync website data
            website_data = await self.sync_website()

            # Sync Certik data
            certik_data = await self.sync_certik()

            # Sync PDF data
            pdf_data = await self.sync_pdf()

            # Update cache and database
            await self._update_data_stores(website_data, certik_data, pdf_data)

            self.last_sync = datetime.now()
            logger.info("Data sync completed successfully")

        except Exception as e:
            logger.error(f"Error in sync_all: {e}")
        finally:
            self.is_syncing = False

    async def _update_data_stores(self, *data_sets):
        """Update cache and database with new data"""
        try:
            for data in data_sets:
                if data and self._is_data_valid(data):
                    await self.cache_manager.update_data(data)
                    await self.db_manager.store_data(data)
        except Exception as e:
            logger.error(f"Error updating data stores: {e}")

    def _is_data_valid(self, data: Dict[str, Any]) -> bool:
        """Validate data before storing"""
        return bool(data and isinstance(data, dict))
