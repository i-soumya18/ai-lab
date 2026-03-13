"""Goal CRUD operations backed by PostgreSQL.

All goal state, including the task list, is stored in a single `goals` row.
The `tasks` column is JSONB, loaded and saved as a Python list[GoalTask].
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from goals.models import Goal, GoalStatus, GoalSummary, GoalTask, GoalTaskStatus

logger = structlog.get_logger()


def _row_to_goal(row: Any) -> Goal:
    """Convert a SQLAlchemy row to a Goal model."""
    tasks_data = row.tasks if isinstance(row.tasks, list) else json.loads(row.tasks or "[]")
    tasks = [GoalTask(**t) if isinstance(t, dict) else t for t in tasks_data]
    context_data = row.context if isinstance(row.context, dict) else json.loads(row.context or "{}")
    return Goal(
        id=str(row.id),
        title=row.title,
        description=row.description,
        status=row.status,
        tasks=tasks,
        context=context_data,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class GoalManager:
    """Manages goal persistence in PostgreSQL."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        title: str,
        description: str = "",
        context: dict[str, Any] | None = None,
        tasks: list[GoalTask] | None = None,
    ) -> Goal:
        """Insert a new goal row and return the Goal model."""
        goal_id = str(uuid.uuid4())
        tasks_json = json.dumps([t.model_dump() for t in (tasks or [])])
        context_json = json.dumps(context or {})

        await self._db.execute(
            text(
                "INSERT INTO goals (id, title, description, status, tasks, context) "
                "VALUES (CAST(:id AS uuid), :title, :description, :status, "
                "CAST(:tasks AS jsonb), CAST(:context AS jsonb))"
            ),
            {
                "id": goal_id,
                "title": title,
                "description": description,
                "status": GoalStatus.PENDING.value,
                "tasks": tasks_json,
                "context": context_json,
            },
        )
        await self._db.commit()
        logger.info("goal.created", goal_id=goal_id, title=title)
        return await self.get(goal_id)  # type: ignore[return-value]

    async def get(self, goal_id: str) -> Goal | None:
        """Fetch a single goal by ID."""
        result = await self._db.execute(
            text("SELECT * FROM goals WHERE id=CAST(:id AS uuid)"),
            {"id": goal_id},
        )
        row = result.fetchone()
        return _row_to_goal(row) if row else None

    async def list_goals(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GoalSummary]:
        """Return a paginated list of goal summaries."""
        if status:
            result = await self._db.execute(
                text(
                    "SELECT id, title, description, status, tasks, created_at, updated_at "
                    "FROM goals WHERE status=:status ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"status": status, "limit": limit, "offset": offset},
            )
        else:
            result = await self._db.execute(
                text(
                    "SELECT id, title, description, status, tasks, created_at, updated_at "
                    "FROM goals ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
        summaries = []
        for row in result.fetchall():
            tasks_data = row.tasks if isinstance(row.tasks, list) else json.loads(row.tasks or "[]")
            completed = sum(1 for t in tasks_data if t.get("status") == GoalTaskStatus.COMPLETED.value)
            summaries.append(GoalSummary(
                id=str(row.id),
                title=row.title,
                description=row.description,
                status=row.status,
                task_count=len(tasks_data),
                completed_tasks=completed,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ))
        return summaries

    async def update_status(self, goal_id: str, status: GoalStatus) -> None:
        """Update goal status and updated_at timestamp."""
        now = datetime.now(timezone.utc)
        await self._db.execute(
            text(
                "UPDATE goals SET status=:status, updated_at=:now WHERE id=CAST(:id AS uuid)"
            ),
            {"status": status.value, "now": now, "id": goal_id},
        )
        await self._db.commit()
        logger.info("goal.status_updated", goal_id=goal_id, status=status.value)

    async def save_tasks(self, goal_id: str, tasks: list[GoalTask]) -> None:
        """Overwrite the tasks JSONB array for a goal (load-modify-save pattern)."""
        now = datetime.now(timezone.utc)
        tasks_json = json.dumps([t.model_dump() for t in tasks])
        await self._db.execute(
            text(
                "UPDATE goals SET tasks=CAST(:tasks AS jsonb), updated_at=:now "
                "WHERE id=CAST(:id AS uuid)"
            ),
            {"tasks": tasks_json, "now": now, "id": goal_id},
        )
        await self._db.commit()

    async def update_task_result(
        self,
        goal_id: str,
        step_number: int,
        result: dict[str, Any],
        status: GoalTaskStatus,
        error: str | None = None,
        approval_id: str | None = None,
    ) -> None:
        """Update a single task's result within the goal's JSONB tasks array."""
        goal = await self.get(goal_id)
        if goal is None:
            logger.error("goal.not_found_for_task_update", goal_id=goal_id)
            return
        for task in goal.tasks:
            if task.step_number == step_number:
                task.result = result
                task.status = status
                task.error = error
                if approval_id:
                    task.approval_id = approval_id
                break
        await self.save_tasks(goal_id, goal.tasks)

    async def get_interrupted_goals(self) -> list[str]:
        """Return IDs of goals that were RUNNING when the system last shut down."""
        result = await self._db.execute(
            text("SELECT id FROM goals WHERE status='running'"),
        )
        return [str(row.id) for row in result.fetchall()]
