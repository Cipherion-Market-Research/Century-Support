"""PDF text extraction for the publications corpus.

The source PDFs are AES-encrypted with an empty user password (owner
password protects editing only; the empty user password still lets any
reader open/extract them, which is exactly why pypdf + cryptography rather
than legacy PyPDF2 are required here) — see docs/BUILD_HANDOFF.md WP-4.
"""
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass
class ExtractedPdf:
    text: str
    page_count: int


def extract_pdf_text(source: Union[str, Path, bytes]) -> ExtractedPdf:
    """Extract text from a PDF given a filesystem path or raw bytes (the
    latter used by the webhook path, which fetches PDFs from GitHub raw
    content straight into memory without touching disk)."""
    stream = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    reader = PdfReader(stream)
    if reader.is_encrypted:
        result = reader.decrypt("")
        if result == 0:
            raise PdfReadError(f"{source!r}: empty-password decrypt failed")

    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    return ExtractedPdf(text=text, page_count=len(reader.pages))
