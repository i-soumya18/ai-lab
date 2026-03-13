"""Pydantic models for the Goal system.

Goals are long-horizon user intentions decomposed into ordered agent tasks.
All state is persisted in PostgreSQL. The `tasks` field is stored as JSONB
inside the `goals` table row (always read/written as a unit).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GoalStatus(str, Enum):
    """Lifecycle states for a goal."""

    PENDING = "pending"
    PLANNING = "planning"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GoalTaskStatus(str, Enum):
    """Lifecycle states for a single task within a goal."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class GoalTask(BaseModel):
    """One executable step within a goal."""

    step_number: int
    task_type: str  # maps to AgentTaskType value: research|coding|data|writing|file|goal_plan
    instruction: str
    depends_on: list[int] = Field(default_factory=list)
    requires_approval: bool = False
    status: GoalTaskStatus = GoalTaskStatus.PENDING
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    approval_id: str | None = None


class Goal(BaseModel):
    """A persistent, multi-step user goal."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    status: GoalStatus = GoalStatus.PENDING
    tasks: list[GoalTask] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateGoalRequest(BaseModel):
    """API request body for creating a new goal."""

    title: str
    description: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    auto_run: bool = False  # if True, immediately start execution after planning


class GoalSummary(BaseModel):
    """Lightweight goal summary for list endpoints."""

    id: str
    title: str
    description: str
    status: GoalStatus
    task_count: int
    completed_tasks: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
