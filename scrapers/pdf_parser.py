from typing import Dict, Any
import PyPDF2
from .base_scraper import BaseScraper
from utils.logger import setup_logger
from config.constants import WHITEPAPER_SECTIONS

logger = setup_logger()

class PDFParser(BaseScraper):
    def __init__(self, pdf_path: str = "data/training/whitepaper.pdf"):
        self.pdf_path = pdf_path

    async def process(self) -> Dict[str, Any]:
        """
        Main processing method that fetches and organizes whitepaper content
        """
        try:
            raw_data = await self.fetch()
            if await self.validate(raw_data):
                return raw_data
            return {}
        except Exception as e:
            logger.error(f"Error processing whitepaper: {e}")
            return {}

    async def fetch(self) -> Dict[str, Any]:
        """Extract text from PDF and organize by sections"""
        try:
            with open(self.pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                sections = {}
                current_section = None
                current_text = []

                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    
                    # Split text into lines for processing
                    lines = text.split('\n')
                    for line in lines:
                        # Check if line starts a new section
                        for section_num, section_title in WHITEPAPER_SECTIONS.items():
                            if line.strip().startswith(section_num):
                                # Save previous section if exists
                                if current_section:
                                    sections[current_section] = '\n'.join(current_text)
                                current_section = section_title
                                current_text = [line]
                                break
                        else:
                            if current_section:
                                current_text.append(line)

                # Add final section
                if current_section and current_text:
                    sections[current_section] = '\n'.join(current_text)

                return sections

        except FileNotFoundError:
            logger.error(f"Whitepaper not found at {self.pdf_path}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")
            return {}

    async def validate(self, data: Dict[str, Any]) -> bool:
        """
        Validate the parsed whitepaper data
        """
        if not isinstance(data, dict):
            return False
        
        # Check if we have content for key sections
        required_sections = [
            "1.0 Introduction",
            "2.0 Tokenomics",
            "3.0 Community Management"
        ]
        
        return all(
            any(section in key for key in data.keys())
            for section in required_sections
        )
