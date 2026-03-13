from __future__ import annotations

import time
from typing import Any

import structlog
from pydantic import BaseModel

from agents.base_agent import AgentResult, AgentTask, BaseAgent
from agents.tools.file_tools import csv_analyze, file_read, json_parse
from models.ollama_client import OllamaClient

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are a Data Analysis Agent specialized in extracting insights from structured data.

Rules:
- Always describe the shape and structure of data before analyzing it
- Report actual numbers, not vague descriptions
- Highlight anomalies and outliers explicitly
- Keep statistical jargon minimal — speak plainly
- Never fabricate data points — only report what the data shows"""


class DataOutput(BaseModel):
    """Structured output from the Data Agent."""

    dataset_description: str
    key_statistics: dict[str, Any]
    insights: list[str]
    anomalies: list[str]
    recommendations: list[str]
    chart_suggestions: list[str]


class DataAgent(BaseAgent):
    """Analyzes structured data, generates insights, and identifies patterns."""

    name = "data"
    model = "nemotron-3-super:cloud"

    def __init__(self, ollama_client: OllamaClient) -> None:
        self._ollama = ollama_client

    async def run(self, task: AgentTask) -> AgentResult:
        """Execute a data analysis task."""
        start = time.monotonic()
        steps = 0
        context_parts: list[str] = []

        # Step 1: Analyze file if provided
        file_path = task.context.get("file_path")
        if file_path:
            steps += 1
            if file_path.endswith(".csv"):
                summary = await csv_analyze(file_path)
                context_parts.append(
                    f"Dataset: {file_path}\n"
                    f"Shape: {summary.shape}\n"
                    f"Columns: {summary.columns}\n"
                    f"Data types: {summary.dtypes}\n"
                    f"Null counts: {summary.null_counts}\n"
                    f"Statistics: {summary.statistics}\n"
                    f"Sample rows: {summary.sample_rows}"
                )
            elif file_path.endswith(".json"):
                data = await json_parse(file_path)
                context_parts.append(f"JSON data from {file_path}:\n{data}")
            else:
                content = await file_read(file_path)
                context_parts.append(f"File content from {file_path}:\n{content[:5000]}")

        # Step 2: Analyze with LLM
        steps += 1
        data_context = "\n\n".join(context_parts) if context_parts else "No data file provided."

        prompt = f"""Analyze the following data and provide insights.

Task: {task.instruction}

Data:
{data_context}

Provide:
1. Dataset description (shape, structure)
2. Key statistics
3. Top insights and patterns
4. Any anomalies or outliers
5. Recommendations
6. Suggested visualizations"""

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
