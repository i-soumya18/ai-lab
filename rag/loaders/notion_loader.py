from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel

from rag.loaders.git_loader import Document

logger = structlog.get_logger()


async def load_notion_export(export_dir: str) -> list[Document]:
    """Load Notion exported markdown/HTML files from a directory.

    Notion exports are typically a directory tree of markdown files
    with optional embedded images and subpages.
    """
    root = Path(export_dir)
    if not root.exists():
        raise FileNotFoundError(f"Notion export directory not found: {export_dir}")

    exts = {".md", ".html", ".txt"}

    def _walk() -> list[Document]:
        docs: list[Document] = []
        for fpath in root.rglob("*"):
            if fpath.is_dir() or fpath.suffix not in exts:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    # Extract a title from the filename (Notion format: "Title hash.md")
                    name = fpath.stem
                    # Remove Notion's hash suffix if present
                    parts = name.rsplit(" ", 1)
                    title = parts[0] if len(parts) > 1 and len(parts[1]) == 32 else name

                    docs.append(Document(
                        content=content,
                        metadata={
                            "file_path": str(fpath.relative_to(root)),
                            "title": title,
                            "extension": fpath.suffix,
                            "source_type": "notion",
                        },
                    ))
            except (OSError, PermissionError) as exc:
                logger.warning("loader.notion.skip_file", path=str(fpath), error=str(exc))

        return docs

    docs = await asyncio.to_thread(_walk)
    logger.info("loader.notion", directory=export_dir, files=len(docs))
    return docs
