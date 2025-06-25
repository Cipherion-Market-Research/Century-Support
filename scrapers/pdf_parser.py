from typing import Dict, Any
import PyPDF2
from .base_scraper import BaseScraper
from utils.logger import setup_logger
from config.constants import COMPOSITE_SECTIONS
import re

logger = setup_logger()

class PDFParser(BaseScraper):
    def __init__(self, pdf_path: str = "data/training/whitepaper.pdf"):
        self.pdf_path = pdf_path

    async def process(self) -> Dict[str, Any]:
        """Process the whitepaper and extract structured content"""
        try:
            raw_text = await self.fetch()
            if not raw_text:
                return {}
            
            sections = {}
            for section_name in COMPOSITE_SECTIONS:
                # Note: The logic for PDF section extraction will need to be adapted
                # to the new document structure. This is a placeholder for now.
                content = await self._extract_section_content(raw_text, section_name)
                if content:
                    sections[section_name] = content
                
            return sections
        except Exception as e:
            logger.error(f"Error processing whitepaper: {e}")
            return {}

    async def fetch(self) -> str:
        """Extract text from PDF and return as plain text"""
        try:
            with open(self.pdf_path, "rb") as file:
                pdf_reader = PyPDF2.PdfReader(file)
                full_text = []

                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    full_text.append(text)

                return "\n".join(full_text)

        except FileNotFoundError:
            logger.error(f"Whitepaper not found at {self.pdf_path}")
            return ""
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")
            return ""

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

    async def _extract_section_content(self, text: str, section_num: str) -> str:
        """Extract content for a specific section number"""
        try:
            # Build more precise section patterns based on whitepaper format
            section_start = f"{section_num}\\s+[A-Za-z].*?\\n"  # Matches section header
            next_section = f"\\d+\\.\\d+\\s+[A-Za-z]"  # Matches next section number
            
            # Find section start
            start_match = re.search(section_start, text, re.MULTILINE)
            if not start_match:
                logger.warning(f"No start match found for section {section_num}")
                return ""
            
            start_pos = start_match.start()
            
            # Find next section or end of text
            next_match = re.search(next_section, text[start_pos + 1:], re.MULTILINE)
            end_pos = (next_match.start() + start_pos + 1) if next_match else len(text)
            
            # Extract content
            content = text[start_pos:end_pos]
            
            # Clean the content
            return self._clean_section_content(content)
            
        except Exception as e:
            logger.error(f"Error extracting section {section_num}: {e}")
            return ""

    def _clean_section_content(self, content: str) -> str:
        """Clean and format section content"""
        try:
            # Split into lines
            lines = content.split('\n')
            cleaned_lines = []
            
            for line in lines:
                # Skip page numbers and headers
                if re.match(r'^\d+\s*Page\s*\|', line) or line.strip() == '':
                    continue
                
                # Skip table of contents style lines
                if re.match(r'^\.+\d+$', line):
                    continue
                
                # Clean whitespace
                line = ' '.join(line.split())
                
                if line:
                    cleaned_lines.append(line)
            
            # Join lines and clean up
            cleaned = ' '.join(cleaned_lines)
            
            # Remove section number from start
            cleaned = re.sub(r'^\d+\.\d+\s+', '', cleaned)
            
            # Fix spacing
            cleaned = re.sub(r'\s+', ' ', cleaned)
            
            return cleaned.strip()
            
        except Exception as e:
            logger.error(f"Error cleaning content: {e}")
            return content
