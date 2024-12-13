# tests/test_scrapers.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from scrapers.pdf_parser import PDFParser
from scrapers.website_scraper import WebsiteScraper

@pytest.mark.asyncio
async def test_pdf_parser():
    # Assume we have a dummy PDF with known text
    pdf_parser = PDFParser(pdf_path="data/training/whitepaper.pdf")

    # You might mock PyPDF2 if needed, but here let's assume the PDF exists and is correct.
    # For a real test, you'd have a known test PDF file and expected text.
    data = await pdf_parser.process()
    assert isinstance(data, dict)
    # Check that at least one page of text is extracted
    assert any("page_" in key for key in data.keys())

@pytest.mark.asyncio
async def test_website_scraper():
    # Mock aiohttp calls
    with patch("aiohttp.ClientSession.get") as mock_get:
        # Create async mock response with HTML containing our expected sections
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_html = """
        <html>
            <body>
                <div id="tokenomics">Tokenomics Content</div>
                <div id="roadmap">Roadmap Content</div>
                <div id="about">About Content</div>
            </body>
        </html>
        """
        mock_response.text = AsyncMock(return_value=mock_html)
        
        # Setup the context manager mock
        mock_get.return_value.__aenter__.return_value = mock_response

        scraper = WebsiteScraper()
        data = await scraper.fetch()
        
        # Verify the structure and content
        assert isinstance(data, dict)
        assert all(key in data for key in ['tokenomics', 'roadmap', 'about'])
        assert all(len(value.strip()) > 0 for value in data.values())
        
        # Verify only one call was made to the base URL
        mock_get.assert_called_once_with("https://ciphex.io")
