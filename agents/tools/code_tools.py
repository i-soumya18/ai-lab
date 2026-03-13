from __future__ import annotations

import asyncio
import shlex
import subprocess
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()

# Allowlisted commands for shell execution
ALLOWED_COMMANDS = ["git log", "git diff", "git show", "python -m py_compile",
                    "git status", "git branch"]


class CodeChunk(BaseModel):
    """A chunk of code from semantic search."""

    file_path: str
    content: str
    metadata: dict[str, Any] = {}
    score: float = 0.0


async def code_search(
    query: str,
    repo_collection: str,
    chroma_client: Any,
    embedder: Any,
    top_k: int = 5,
) -> list[CodeChunk]:
    """Semantic search over an ingested codebase in ChromaDB."""
    from rag.retriever import Retriever

    retriever = Retriever(chroma_client=chroma_client, embedder=embedder)
    results = await retriever.search(query=query, collection=repo_collection, top_k=top_k)

    chunks = []
    for r in results:
        chunks.append(CodeChunk(
            file_path=r.get("metadata", {}).get("file_path", "unknown"),
            content=r["content"],
            metadata=r.get("metadata", {}),
            score=r.get("score", 0.0),
        ))

    return chunks


async def git_read(repo_path: str, file_path: str) -> str:
    """Read a file from a git repository."""
    full_path = Path(repo_path) / file_path
    if not full_path.exists():
        raise FileNotFoundError(f"File not found: {full_path}")

    return full_path.read_text(encoding="utf-8", errors="replace")


async def shell_safe(command: str) -> str:
    """Execute a shell command from the allowlist only.

    Security: Never executes arbitrary commands. Only allowed commands
    can be run to prevent injection attacks.
    """
    # Check if command starts with an allowed prefix
    cmd_parts = shlex.split(command)

    def _prefix_matches(parts: list[str], allowed: str) -> bool:
        allowed_parts = allowed.split()
        return parts[:len(allowed_parts)] == allowed_parts

    is_allowed = any(_prefix_matches(cmd_parts, allowed) for allowed in ALLOWED_COMMANDS)
    if not is_allowed:
        raise PermissionError(
            f"Command not allowed: {command}. Allowed: {ALLOWED_COMMANDS}"
        )

    def _run() -> str:
        result = subprocess.run(
            cmd_parts,
            shell=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return output

    output = await asyncio.to_thread(_run)
    logger.info("code_tools.shell_safe", command=command, output_len=len(output))
    return output
