from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


# ── Shared Data Models ───────────────────────────────────────────────────────

class AgentTaskType(str, Enum):
    """Types of tasks agents can handle."""

    RESEARCH = "research"
    CODING = "coding"
    DATA = "data"
    WRITING = "writing"
    GENERAL = "general"
    FILE = "file"
    GOAL_PLAN = "goal_plan"


class AgentTask(BaseModel):
    """Input contract for all agents."""

    task_id: str = ""
    task_type: AgentTaskType = AgentTaskType.GENERAL
    instruction: str
    context: dict[str, Any] = {}
    memory_context: list[str] = []
    max_steps: int = 10
    timeout_seconds: int = 120

    def model_post_init(self, __context: Any) -> None:
        """Auto-generate task_id if not provided."""
        if not self.task_id:
            self.task_id = str(uuid.uuid4())


class AgentResult(BaseModel):
    """Output contract for all agents."""

    task_id: str
    agent_name: str
    success: bool
    output: str
    artifacts: list[dict[str, Any]] = []
    sources: list[str] = []
    steps_taken: int = 0
    duration_ms: int = 0
    model_used: str = ""
    error: str | None = None


# ── Base Agent ───────────────────────────────────────────────────────────────

class BaseAgent(ABC):
    """Abstract base class for all agents.

    Subclasses must implement `run()`. The `execute()` method wraps
    `run()` with timeout enforcement, kill-switch checking, and logging.
    """

    name: str = "base"
    model: str = "nemotron-3-super:cloud"

    @abstractmethod
    async def run(self, task: AgentTask) -> AgentResult:
        """Execute the agent's core logic. Must be implemented by subclasses."""
        ...

    async def execute(self, task: AgentTask, redis: Any = None) -> AgentResult:
        """Run the agent with kill-switch check, timeout enforcement, and logging.

        Args:
            task: The task to execute.
            redis: Optional async Redis client. When provided, the kill switch
                   is checked before executing. If active, returns an error result
                   immediately without running the agent.
        """
        # Kill switch check before starting
        if redis is not None:
            from safety.kill_switch import is_killed
            if await is_killed(redis):
                logger.warning("agent.killed_before_start", agent=self.name, task_id=task.task_id)
                return AgentResult(
                    task_id=task.task_id,
                    agent_name=self.name,
                    success=False,
                    output="",
                    model_used=self.model,
                    error="Aborted: system kill switch is active.",
                )

        start = time.monotonic()

        try:
            result = await asyncio.wait_for(
                self.run(task),
                timeout=task.timeout_seconds,
            )
        except asyncio.TimeoutError:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error("agent.timeout", agent=self.name, task_id=task.task_id,
                         timeout=task.timeout_seconds)
            result = AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                success=False,
                output="",
                duration_ms=elapsed,
                model_used=self.model,
                error=f"Agent timed out after {task.timeout_seconds} seconds",
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error("agent.error", agent=self.name, task_id=task.task_id,
                         error=str(exc))
            result = AgentResult(
                task_id=task.task_id,
                agent_name=self.name,
                success=False,
                output="",
                duration_ms=elapsed,
                model_used=self.model,
                error=str(exc),
            )

        # Ensure duration is set
        if result.duration_ms == 0:
            result.duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "agent.complete",
            agent=self.name,
            task_id=task.task_id,
            success=result.success,
            duration_ms=result.duration_ms,
        )

        return result
