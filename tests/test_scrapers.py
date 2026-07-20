# tests/test_scrapers.py
import pytest
from scrapers.pdf_parser import PDFParser

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
