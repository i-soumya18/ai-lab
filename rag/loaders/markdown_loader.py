from __future__ import annotations

from pathlib import Path

import aiofiles
import structlog

logger = structlog.get_logger()


async def load_markdown(file_path: str) -> str:
    """Read a markdown file and return its content."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Markdown file not found: {file_path}")

    async with aiofiles.open(str(path), mode="r", encoding="utf-8") as f:
        content = await f.read()

    logger.info("loader.markdown", path=file_path, chars=len(content))
    return content
