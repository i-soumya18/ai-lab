from __future__ import annotations

import time
from typing import Any

import structlog
from pydantic import BaseModel

from agents.base_agent import AgentResult, AgentTask, BaseAgent
from agents.tools.file_tools import file_write
from models.ollama_client import OllamaClient

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a Writing Agent specialized in producing clear, professional written content.

Rules:
- Always use the input context — never fabricate information
- Structure documents with clear headings, sections, and flow
- Match the requested tone (professional, casual, technical)
- Produce complete documents, not outlines (unless an outline is requested)
- Cite sources when provided by Research or Data agents
- Output in Markdown format unless another format is specified"""


class WritingOutput(BaseModel):
    """Structured output from the Writing Agent."""

    title: str
    content: str
    word_count: int
    sections: list[str]
    output_file: str | None = None


class WritingAgent(BaseAgent):
    """Produces well-structured written content: reports, docs, summaries, articles."""

    name = "writing"
    model = "nemotron-3-super:cloud"

    def __init__(self, ollama_client: OllamaClient) -> None:
        self._ollama = ollama_client

    async def run(self, task: AgentTask) -> AgentResult:
        """Execute a writing task."""
        start = time.monotonic()
        steps = 0
        artifacts: list[dict[str, Any]] = []

        # Build context from upstream agents (research, data)
        context_parts: list[str] = []

        research_context = task.context.get("research_output")
        if research_context:
            context_parts.append(f"Research findings:\n{research_context}")

        data_context = task.context.get("data_output")
        if data_context:
            context_parts.append(f"Data analysis:\n{data_context}")

        memory_context = "\n".join(task.memory_context) if task.memory_context else ""
        if memory_context:
            context_parts.append(f"Relevant past context:\n{memory_context}")

        # Generate with LLM
        steps += 1
        input_context = "\n\n".join(context_parts) if context_parts else "No additional context provided."

        prompt = f"""Write the following content.

Task: {task.instruction}

Available context and data:
{input_context}

Write a complete, well-structured document in Markdown format.
Include a title, clear sections, and a conclusion if appropriate."""

        response = await self._ollama.generate(
            model=self.model,
            prompt=prompt,
            system=SYSTEM_PROMPT,
            temperature=0.7,
        )

        # Optionally save to file
        output_path = task.context.get("output_file")
        if output_path:
            steps += 1
            await file_write(output_path, response)
            artifacts.append({"type": "file", "path": output_path})

        elapsed = int((time.monotonic() - start) * 1000)

        return AgentResult(
            task_id=task.task_id,
            agent_name=self.name,
            success=True,
            output=response,
            artifacts=artifacts,
            steps_taken=steps,
            duration_ms=elapsed,
            model_used=self.model,
        )
