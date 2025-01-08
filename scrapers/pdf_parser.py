from typing import Dict, Any
import PyPDF2
from .base_scraper import BaseScraper
from utils.logger import setup_logger
from config.constants import WHITEPAPER_SECTIONS
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
            for section_num in WHITEPAPER_SECTIONS.keys():
                content = await self._extract_section_content(raw_text, section_num)
                if content:
                    sections[WHITEPAPER_SECTIONS[section_num]] = content
                
            return sections
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

    async def _extract_section_content(self, text: str, section_num: str) -> str:
        """Extract content for a specific section number"""
        try:
            # Build the section pattern
            next_section_pattern = self._get_next_section_pattern()
            section_pattern = f"{section_num}\\s+.*?(?={next_section_pattern})"
            
            # Search for content with DOTALL flag to match across lines
            content = re.search(section_pattern, text, re.DOTALL)
            if content:
                raw_content = content.group(0)
                return self._clean_section_content(raw_content)
            
            logger.warning(f"No content found for section {section_num}")
            return ""
            
        except Exception as e:
            logger.error(f"Error extracting section {section_num}: {e}")
            return ""

    def _get_next_section_pattern(self) -> str:
        """
        Generate regex pattern to find the next section boundary
        Returns a pattern that matches any section number format (e.g., 1.0, 1.1, 2.0, etc.)
        """
        return r"\d+\.\d+\s+[A-Za-z]|\Z"  # Matches next section number or end of text

    def _clean_section_content(self, content: str) -> str:
        """
        Clean and format the extracted section content
        - Removes extra whitespace
        - Fixes line breaks
        - Removes page numbers and headers
        - Preserves important formatting
        """
        try:
            # Remove page numbers and headers
            lines = content.split('\n')
            cleaned_lines = []
            for line in lines:
                # Skip page numbers and headers
                if re.match(r'^\d+\s*Page\s*\|', line):
                    continue
                # Skip empty lines
                if not line.strip():
                    continue
                # Clean up whitespace
                cleaned_line = ' '.join(line.split())
                cleaned_lines.append(cleaned_line)

            # Join lines with proper spacing
            cleaned_content = ' '.join(cleaned_lines)
            
            # Remove section number from start
            cleaned_content = re.sub(r'^\d+\.\d+\s+', '', cleaned_content)
            
            # Fix any double spaces
            cleaned_content = re.sub(r'\s+', ' ', cleaned_content)
            
            return cleaned_content.strip()
        except Exception as e:
            logger.error(f"Error cleaning section content: {e}")
            return content  # Return original content if cleaning fails
