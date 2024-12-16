import PyPDF2
from typing import Dict, Any
from .base_scraper import BaseScraper
from utils.logger import setup_logger
from config.constants import WHITEPAPER_SECTIONS

logger = setup_logger()

class PDFParser(BaseScraper):
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path

    async def fetch(self) -> Dict[str, Any]:
        """Extract text from PDF"""
        try:
            with open(self.pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                sections = {}

                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    sections[f"page_{page_num + 1}"] = text

                return self._organize_sections(sections)
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")
            return {}

    def _organize_sections(self, raw_sections: Dict[str, str]) -> Dict[str, Any]:
        combined_text = "\n".join(raw_sections.values())
        
        organized = {}
        for section_name in WHITEPAPER_SECTIONS:
            start_idx = combined_text.lower().find(section_name)
            if start_idx != -1:
                next_section_idx = len(combined_text)
                for other_section in WHITEPAPER_SECTIONS:
                    if other_section == section_name:
                        continue
                    idx = combined_text.lower().find(other_section, start_idx+1)
                    if idx != -1 and idx < next_section_idx:
                        next_section_idx = idx
                section_text = combined_text[start_idx:next_section_idx]
                organized[section_name.lower()] = section_text.strip()
            else:
                organized[section_name.lower()] = "Not found in whitepaper"
        
        return organized


    async def validate(self, data: Dict[str, Any]) -> bool:
        """Validate PDF data"""
        return bool(data and isinstance(data, dict))
