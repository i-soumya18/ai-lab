"""File Agent — file system operations with safety boundaries.

Capabilities:
  - List files in safe directories
  - Read file contents
  - Diff two files
  - Ingest files into RAG (ChromaDB) collection

All write/delete operations require prior approval via the approval queue.
Reads are unrestricted within SAFE_READ_DIRS.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import aiofiles
import structlog

from agents.base_agent import AgentResult, AgentTask, AgentTaskType, BaseAgent

logger = structlog.get_logger()

# Absolute paths the agent is allowed to read from
SAFE_READ_DIRS: list[str] = [
    "/app/data",
    "/app/watched",
    "/app/outputs",
    "/app/templates",
]

# Agents may only write to this directory
SAFE_WRITE_DIR = "/app/outputs"


def _is_safe_read(path: str) -> bool:
    """Return True if the path is inside a permitted read directory."""
    p = Path(path).resolve()
    return any(p.is_relative_to(Path(d)) for d in SAFE_READ_DIRS)


def _is_safe_write(path: str) -> bool:
    """Return True if the path is inside the permitted write directory."""
    p = Path(path).resolve()
    return p.is_relative_to(Path(SAFE_WRITE_DIR))


class FileAgent(BaseAgent):
    """Handles file system operations with read/write safety boundaries."""

    name: str = "file_agent"
    model: str = "nemotron-3-super:cloud"

    def __init__(
        self,
        ollama_client: Any,
        chroma_client: Any = None,
        embedder: Any = None,
    ) -> None:
        self._ollama = ollama_client
        self._chroma = chroma_client
        self._embedder = embedder

    async def run(self, task: AgentTask) -> AgentResult:
        """Dispatch to the appropriate file operation based on task.context['action'].

        Context keys:
            action: "list" | "read" | "diff" | "ingest" | "summarize"
            path: file or directory path
            path_b: second path for diff (only for "diff" action)
            collection: ChromaDB collection name (for "ingest")
        """
        action = task.context.get("action")
        path = task.context.get("path", "")

        # Goal tasks often provide only a natural-language instruction.
        # Infer a safe write action for "save/write file" intents.
        if action is None:
            inferred = self._infer_action_and_path(task.instruction)
            action = inferred["action"]
            if not path:
                path = inferred["path"]

        if action == "list":
            return await self._list_files(task, path)
        elif action == "read":
            return await self._read_file(task, path)
        elif action == "diff":
            path_b = task.context.get("path_b", "")
            return await self._diff_files(task, path, path_b)
        elif action == "ingest":
            collection = task.context.get("collection", "documents")
            return await self._ingest_file(task, path, collection)
        elif action == "summarize":
            return await self._summarize_file(task, path)
        elif action == "write":
            content = task.context.get("content", "")
            return await self._write_file(task, path, content)
        else:
            return AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                success=False,
                output="",
                model_used=self.model,
                error=f"Unknown file action: {action}",
            )

    def _infer_action_and_path(self, instruction: str) -> dict[str, str]:
        text = instruction.lower()
        if any(k in text for k in ["write", "save", "export", "store"]) and "file" in text:
            filename = "output.txt"
            match = re.search(
                r"(?:named|called|filename|file name)\s+['\"]?([A-Za-z0-9._-]+)",
                instruction,
                flags=re.IGNORECASE,
            )
            if match:
                filename = match.group(1)
            return {"action": "write", "path": str(Path(SAFE_WRITE_DIR) / filename)}
        if any(k in text for k in ["list", "show files", "directory"]):
            return {"action": "list", "path": SAFE_READ_DIRS[0]}
        return {"action": "read", "path": ""}

    async def _list_files(self, task: AgentTask, path: str) -> AgentResult:
        """List files in a safe directory."""
        if not _is_safe_read(path):
            return AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                success=False,
                output="",
                model_used=self.model,
                error=f"Path not in allowed read directories: {path}",
            )
        try:
            entries = await asyncio.to_thread(lambda: list(Path(path).iterdir()))
            file_list = [
                {"name": e.name, "is_dir": e.is_dir(), "size": e.stat().st_size if e.is_file() else 0}
                for e in sorted(entries)
            ]
            output = "\n".join(
                f"{'[DIR]' if f['is_dir'] else f['size']:>8} {f['name']}" for f in file_list
            )
            return AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                success=True,
                output=output,
                artifacts=[{"type": "file_list", "files": file_list}],
                steps_taken=1,
                model_used=self.model,
            )
        except Exception as exc:
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model, error=str(exc),
            )

    async def _read_file(self, task: AgentTask, path: str) -> AgentResult:
        """Read and return file contents."""
        if not _is_safe_read(path):
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model,
                error=f"Path not in allowed read directories: {path}",
            )
        try:
            async with aiofiles.open(path, encoding="utf-8", errors="replace") as f:
                content = await f.read()
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=True,
                output=content, steps_taken=1, model_used=self.model,
                sources=[path],
            )
        except Exception as exc:
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model, error=str(exc),
            )

    async def _diff_files(self, task: AgentTask, path_a: str, path_b: str) -> AgentResult:
        """Compare two files and return unified diff."""
        for p in [path_a, path_b]:
            if not _is_safe_read(p):
                return AgentResult(
                    task_id=task.task_id, agent_name=self.name, success=False,
                    output="", model_used=self.model,
                    error=f"Path not in allowed read directories: {p}",
                )
        try:
            import difflib
            async with aiofiles.open(path_a, encoding="utf-8", errors="replace") as f:
                lines_a = (await f.read()).splitlines(keepends=True)
            async with aiofiles.open(path_b, encoding="utf-8", errors="replace") as f:
                lines_b = (await f.read()).splitlines(keepends=True)
            diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=path_a, tofile=path_b))
            diff_text = "".join(diff) or "Files are identical."
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=True,
                output=diff_text, steps_taken=1, model_used=self.model,
            )
        except Exception as exc:
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model, error=str(exc),
            )

    async def _ingest_file(self, task: AgentTask, path: str, collection: str) -> AgentResult:
        """Ingest a file into a ChromaDB RAG collection."""
        if not _is_safe_read(path):
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model,
                error=f"Path not in allowed read directories: {path}",
            )
        if self._chroma is None or self._embedder is None:
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model,
                error="Chroma client or embedder not available for ingestion.",
            )
        try:
            from rag.ingestion import ingest_file
            chunk_count = await ingest_file(
                path=path,
                collection_name=collection,
                chroma_client=self._chroma,
                embedder=self._embedder,
            )
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=True,
                output=f"Ingested {chunk_count} chunks from {path} into collection '{collection}'.",
                artifacts=[{"type": "rag_ingest", "path": path, "collection": collection,
                            "chunk_count": chunk_count}],
                steps_taken=1, model_used=self.model, sources=[path],
            )
        except Exception as exc:
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model, error=str(exc),
            )

    async def _summarize_file(self, task: AgentTask, path: str) -> AgentResult:
        """Read a file and produce an LLM summary."""
        read_result = await self._read_file(task, path)
        if not read_result.success:
            return read_result
        content = read_result.output[:8000]  # cap input to LLM
        prompt = f"Summarize the following file content in 3-5 bullet points:\n\n{content}"
        response = await self._ollama.generate(
            model=self.model,
            prompt=prompt,
        )
        summary = response
        return AgentResult(
            task_id=task.task_id, agent_name=self.name, success=True,
            output=summary, steps_taken=2, model_used=self.model, sources=[path],
        )

    async def _write_file(self, task: AgentTask, path: str, content: str) -> AgentResult:
        """Write text content to /app/outputs only."""
        if not path:
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model, error="Missing output file path.",
            )
        if not _is_safe_write(path):
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model,
                error=f"Path not in allowed write directory: {path}",
            )
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            text = content if content else f"Generated by file agent.\n\nInstruction: {task.instruction}\n"
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(text)
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=True,
                output=f"Wrote file: {path}",
                artifacts=[{"type": "file_write", "path": path, "bytes": len(text.encode('utf-8'))}],
                steps_taken=1, model_used=self.model, sources=[path],
            )
        except Exception as exc:
            return AgentResult(
                task_id=task.task_id, agent_name=self.name, success=False,
                output="", model_used=self.model, error=str(exc),
            )
