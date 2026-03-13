from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()

DEFAULT_EXTENSIONS = [".py", ".ts", ".tsx", ".js", ".go", ".rs", ".md", ".txt"]


class Document(BaseModel):
    """A document loaded from a source."""

    content: str
    metadata: dict[str, Any] = {}


async def load_git_repo(
    repo_path: str,
    extensions: list[str] | None = None,
) -> list[Document]:
    """Recursively load source files from a git repository.

    Filters by file extension and skips common non-source directories.
    """
    exts = set(extensions or DEFAULT_EXTENSIONS)
    root = Path(repo_path)

    if not root.exists():
        raise FileNotFoundError(f"Repository not found: {repo_path}")

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv",
                 ".next", "dist", "build", ".eggs", ".tox"}

    def _walk() -> list[Document]:
        docs: list[Document] = []
        for fpath in root.rglob("*"):
            if fpath.is_dir():
                continue

            # Skip files in excluded directories
            if any(part in skip_dirs for part in fpath.parts):
                continue

            if fpath.suffix not in exts:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                if content.strip():
                    docs.append(Document(
                        content=content,
                        metadata={
                            "file_path": str(fpath.relative_to(root)),
                            "extension": fpath.suffix,
                            "line_count": content.count("\n") + 1,
                            "source_type": "git",
                            "repo_path": str(root),
                        },
                    ))
            except (OSError, PermissionError) as exc:
                logger.warning("loader.git.skip_file", path=str(fpath), error=str(exc))

        return docs

    docs = await asyncio.to_thread(_walk)
    logger.info("loader.git", repo=repo_path, files=len(docs))
    return docs
