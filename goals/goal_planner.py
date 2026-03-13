from __future__ import annotations

import json
import re
from typing import Any

import structlog

from goals.models import GoalTask

logger = structlog.get_logger()


class GoalPlanner:
    """LLM-powered goal decomposition — breaks a user goal into ordered GoalTask steps."""

    _SYSTEM_PROMPT = (
        "You are a planning assistant. Given a goal, decompose it into 3-7 ordered "
        "executable steps. Each step must have: step_number (int), task_type "
        "(one of: research, coding, data, writing, file, goal_plan, general), "
        "instruction (string), depends_on (list of step numbers), "
        "requires_approval (bool). "
        "Return ONLY a valid JSON array of step objects. No prose."
    )

    def __init__(self, ollama_client: Any) -> None:
        self._ollama = ollama_client

    async def plan(self, title: str, description: str = "") -> list[GoalTask]:
        """Decompose a goal into GoalTask steps using the LLM.

        Returns a list of GoalTask instances in step order.
        Raises ValueError if the LLM response cannot be parsed.
        """
        user_message = f"Goal: {title}\n\nDetails: {description or title}"
        response = await self._ollama.chat(
            model=self._ollama.default_model,
            messages=[
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.2,
        )
        raw = response

        # Extract JSON array from response
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            raise ValueError(f"GoalPlanner: LLM returned no JSON array. Raw: {raw[:300]}")

        try:
            steps_data: list[dict] = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(f"GoalPlanner: Failed to parse JSON: {exc}") from exc

        tasks: list[GoalTask] = []
        for i, step in enumerate(steps_data):
            tasks.append(
                GoalTask(
                    step_number=step.get("step_number", i + 1),
                    task_type=step.get("task_type", "general"),
                    instruction=step.get("instruction", ""),
                    depends_on=step.get("depends_on", []),
                    requires_approval=step.get("requires_approval", False),
                )
            )

        if not tasks:
            raise ValueError("GoalPlanner: LLM returned empty task list.")

        logger.info("goal_planner.planned", title=title, steps=len(tasks))
        return tasks
