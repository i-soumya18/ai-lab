from __future__ import annotations

import time
from typing import Any

import structlog
from pydantic import BaseModel

from agents.base_agent import AgentResult, AgentTask, BaseAgent
from agents.tools.code_tools import code_search, shell_safe
from agents.tools.file_tools import file_read
from models.ollama_client import OllamaClient

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a Coding Agent with deep software engineering expertise.
You have access to a codebase through semantic search tools.

Rules:
- Always look up relevant code before answering code questions
- Produce working, tested code — never pseudocode unless asked
- Follow the language conventions of the existing codebase
- Explain your reasoning step by step
- Flag potential bugs or security issues you notice
- Never generate shell commands outside the safe allowlist"""


class CodeBlock(BaseModel):
    """A block of code produced by the Coding Agent."""

    language: str
    filename: str | None = None
    content: str
    description: str


class CodingOutput(BaseModel):
    """Structured output from the Coding Agent."""

    explanation: str
    code_blocks: list[CodeBlock]
    files_modified: list[str]
    tests: list[CodeBlock]
    warnings: list[str]


class CodingAgent(BaseAgent):
    """Understands codebases, answers code questions, generates and debugs code."""

    name = "coding"
    model = "nemotron-3-super:cloud"

    def __init__(
        self,
        ollama_client: OllamaClient,
        chroma_client: Any = None,
        embedder: Any = None,
    ) -> None:
        self._ollama = ollama_client
        self._chroma = chroma_client
        self._embedder = embedder

    async def run(self, task: AgentTask) -> AgentResult:
        """Execute a coding task."""
        start = time.monotonic()
        steps = 0
        context_parts: list[str] = []

        # Step 1: Search codebase if a repo collection is specified
        repo_collection = task.context.get("repo_collection")
        if repo_collection and self._chroma and self._embedder:
            steps += 1
            code_chunks = await code_search(
                query=task.instruction,
                repo_collection=repo_collection,
                chroma_client=self._chroma,
                embedder=self._embedder,
            )
            for chunk in code_chunks:
                context_parts.append(
                    f"File: {chunk.file_path}\n```\n{chunk.content}\n```"
                )

        # Step 2: Read specific file if provided
        target_file = task.context.get("file_path")
        if target_file:
            steps += 1
            try:
                content = await file_read(target_file)
                context_parts.append(f"File: {target_file}\n```\n{content}\n```")
            except FileNotFoundError:
                context_parts.append(f"File not found: {target_file}")

        # Step 3: Generate response with LLM
        steps += 1
        code_context = "\n\n".join(context_parts) if context_parts else "No codebase context available."

        prompt = f"""Task: {task.instruction}

Relevant code context:
{code_context}

Provide:
1. A clear explanation of your approach
2. Working code (not pseudocode)
3. Any tests if applicable
4. Any warnings about potential issues"""

        response = await self._ollama.generate(
            model=self.model,
            prompt=prompt,
            system=SYSTEM_PROMPT,
            temperature=0.3,
        )

        elapsed = int((time.monotonic() - start) * 1000)

        return AgentResult(
            task_id=task.task_id,
            agent_name=self.name,
            success=True,
            output=response,
            steps_taken=steps,
            duration_ms=elapsed,
            model_used=self.model,
        )
