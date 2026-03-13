from __future__ import annotations

import time
from typing import Any

import structlog
from pydantic import BaseModel

from agents.base_agent import AgentResult, AgentTask, BaseAgent
from agents.tools.memory_tools import memory_search
from agents.tools.web_search import web_search, url_scrape
from models.ollama_client import OllamaClient

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a Research Agent specialized in information gathering and synthesis.
Your job is to collect accurate, relevant information and produce structured summaries.

Rules:
- Always cite your sources
- Distinguish between facts and speculation
- If information is unavailable, say so clearly
- Structure output with clear sections: Summary, Key Findings, Sources
- Do not fabricate statistics or company data"""


class ResearchOutput(BaseModel):
    """Structured output from the Research Agent."""

    summary: str
    key_findings: list[str]
    sources: list[str]
    confidence: float
    gaps: list[str]


class ResearchAgent(BaseAgent):
    """Collects, synthesizes, and summarizes information from multiple sources."""

    name = "research"
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
        """Execute a research task."""
        start = time.monotonic()
        steps = 0
        all_sources: list[str] = []
        context_parts: list[str] = []

        # Step 1: Search the web
        steps += 1
        search_results = await web_search(task.instruction, max_results=5)
        for r in search_results:
            context_parts.append(f"Source: {r.title} ({r.url})\n{r.snippet}")
            all_sources.append(r.url)

        # Step 2: Search memory if available
        if self._chroma and self._embedder:
            steps += 1
            memories = await memory_search(
                query=task.instruction,
                chroma_client=self._chroma,
                embedder=self._embedder,
                collection="research",
            )
            for m in memories:
                context_parts.append(f"From memory: {m.content}")

        # Step 3: Synthesize with LLM
        steps += 1
        research_context = "\n\n".join(context_parts) if context_parts else "No external data found."
        memory_context = "\n".join(task.memory_context) if task.memory_context else ""

        prompt = f"""Research the following topic and provide a comprehensive analysis.

Topic: {task.instruction}

Available research data:
{research_context}

{f"Previous relevant context: {memory_context}" if memory_context else ""}

Provide your response with these sections:
1. **Summary** - Brief overview
2. **Key Findings** - Bullet points of important findings
3. **Sources** - Where the information came from
4. **Confidence Level** - How confident you are (high/medium/low)
5. **Information Gaps** - What couldn't be found"""

        response = await self._ollama.generate(
            model=self.model,
            prompt=prompt,
            system=SYSTEM_PROMPT,
            temperature=0.5,
        )

        elapsed = int((time.monotonic() - start) * 1000)

        return AgentResult(
            task_id=task.task_id,
            agent_name=self.name,
            success=True,
            output=response,
            sources=all_sources,
            steps_taken=steps,
            duration_ms=elapsed,
            model_used=self.model,
        )
