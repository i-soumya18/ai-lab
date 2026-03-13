"""Goal Planner Agent — wraps GoalPlanner into the BaseAgent interface.

Accepts a planning task and returns an AgentResult where `artifacts`
contains the decomposed GoalTask list as serialized JSON.
"""
from __future__ import annotations

from typing import Any

import structlog

from agents.base_agent import AgentResult, AgentTask, AgentTaskType, BaseAgent
from goals.goal_planner import GoalPlanner

logger = structlog.get_logger()


class GoalPlannerAgent(BaseAgent):
    """Decomposes a user goal into executable GoalTask steps."""

    name: str = "goal_planner"
    model: str = "nemotron-3-super:cloud"

    def __init__(self, ollama_client: Any) -> None:
        self._planner = GoalPlanner(ollama_client=ollama_client)

    async def run(self, task: AgentTask) -> AgentResult:
        """Plan the goal described in task.instruction.

        Expects task.context to have optional keys:
            - "title": goal title (falls back to instruction[:80])
            - "description": full goal description (falls back to instruction)
        """
        title = task.context.get("title", task.instruction[:80])
        description = task.context.get("description", task.instruction)

        tasks = await self._planner.plan(title=title, description=description)
        tasks_dicts = [t.model_dump() for t in tasks]

        summary_lines = [f"{t.step_number}. [{t.task_type}] {t.instruction}" for t in tasks]
        summary = "\n".join(summary_lines)

        return AgentResult(
            task_id=task.task_id,
            agent_name=self.name,
            success=True,
            output=f"Goal decomposed into {len(tasks)} tasks:\n{summary}",
            artifacts=[{"type": "goal_plan", "tasks": tasks_dicts}],
            steps_taken=1,
            model_used=self.model,
        )
