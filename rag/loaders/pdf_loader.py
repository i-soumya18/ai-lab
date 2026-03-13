from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

logger = structlog.get_logger()


async def load_pdf(file_path: str) -> list[str]:
    """Extract text from a PDF file, returning a list of page texts.

    Uses PyMuPDF (fitz) for reliable text extraction.
    """
    import fitz

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    def _extract() -> list[str]:
        pages: list[str] = []
        with fitz.open(str(path)) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    pages.append(text)
        return pages

    pages = await asyncio.to_thread(_extract)
    logger.info("loader.pdf", path=file_path, pages=len(pages))
    return pages
