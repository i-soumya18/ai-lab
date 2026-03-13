"""Human-in-the-loop approval queue for sensitive agent actions.

Before any sensitive action (file write, shell exec, etc.) an ApprovalRequest
is created in PostgreSQL. The GoalExecutor then polls until the user resolves it
via the API, or until the timeout elapses.

Usage:
    approval_id = await request_approval(
        db, goal_id="...", task_step=2,
        action_type="file_write",
        action_description="Write summary.md to /app/outputs/",
        action_payload={"path": "/app/outputs/summary.md", "size_bytes": 1024},
    )
    approved = await await_approval(db, redis, approval_id, timeout_seconds=300)
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from safety.activity_logger import log_event
from safety.kill_switch import is_killed

logger = structlog.get_logger()


class ActionType(str, Enum):
    """Categories of actions that require user approval."""

    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    SHELL_EXEC = "shell_exec"
    WEB_REQUEST = "web_request"
    MEMORY_WRITE = "memory_write"
    GOAL_START = "goal_start"
    EXTERNAL_CALL = "external_call"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"


async def request_approval(
    db: AsyncSession,
    action_type: str,
    action_description: str,
    action_payload: dict[str, Any],
    goal_id: str | UUID | None = None,
    task_step: int | None = None,
) -> str:
    """Insert a pending approval request and return its UUID string."""
    approval_id = str(uuid.uuid4())
    payload_json = json.dumps(action_payload)
    goal_id_str = str(goal_id) if goal_id else None

    await db.execute(
        text(
            "INSERT INTO approval_requests "
            "(id, goal_id, task_step, action_type, action_description, action_payload, status) "
            "VALUES (:id, CAST(:goal_id AS uuid), :task_step, :action_type, "
            ":action_description, CAST(:payload AS jsonb), 'pending')"
        ),
        {
            "id": approval_id,
            "goal_id": goal_id_str,
            "task_step": task_step,
            "action_type": action_type,
            "action_description": action_description,
            "payload": payload_json,
        },
    )
    await db.commit()

    await log_event(
        db,
        event_type="approval.requested",
        description=f"Approval requested: {action_description}",
        entity_type="approval",
        entity_id=approval_id,
        payload={"action_type": action_type, "goal_id": goal_id_str, "task_step": task_step},
    )

    logger.info(
        "approval.requested",
        approval_id=approval_id,
        action_type=action_type,
        goal_id=goal_id_str,
    )
    return approval_id


async def resolve_approval(
    db: AsyncSession,
    approval_id: str,
    approved: bool,
    resolved_by: str = "user",
) -> bool:
    """Set an approval request to approved or denied.

    Returns True if the record was found and updated.
    """
    status = ApprovalStatus.APPROVED.value if approved else ApprovalStatus.DENIED.value
    now = datetime.now(timezone.utc)

    result = await db.execute(
        text(
            "UPDATE approval_requests SET status=:status, resolved_at=:now, resolved_by=:by "
            "WHERE id=:id AND status='pending' "
            "RETURNING id"
        ),
        {"status": status, "now": now, "by": resolved_by, "id": approval_id},
    )
    await db.commit()

    updated = result.fetchone() is not None
    if updated:
        event = "approval.approved" if approved else "approval.denied"
        await log_event(
            db,
            event_type=event,
            description=f"Approval {status} by {resolved_by}: {approval_id}",
            entity_type="approval",
            entity_id=approval_id,
        )
        logger.info("approval.resolved", approval_id=approval_id, status=status)
    else:
        logger.warning("approval.not_found_or_already_resolved", approval_id=approval_id)
    return updated


async def await_approval(
    db_session_factory: Any,
    redis: Any,
    approval_id: str,
    timeout_seconds: int = 300,
) -> bool:
    """Poll until the approval is resolved or timeout elapses.

    Checks the kill switch on every poll. Returns True if approved, False if
    denied, timed out, or the kill switch was activated.

    Args:
        db_session_factory: Callable that returns a new async DB session per poll.
        redis: Async Redis client for kill switch checks.
        approval_id: UUID string of the approval request to watch.
        timeout_seconds: Maximum wait time before auto-denying.

    Returns:
        True if the action was approved, False otherwise.
    """
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    poll_interval = 2.0

    while asyncio.get_running_loop().time() < deadline:
        # Kill switch check
        if await is_killed(redis):
            logger.warning("approval.killed", approval_id=approval_id)
            return False

        # Check current status — open a short-lived session per iteration
        async with db_session_factory() as db:
            row = await db.execute(
                text("SELECT status FROM approval_requests WHERE id=:id"),
                {"id": approval_id},
            )
            record = row.fetchone()
        if record:
            status = record[0]
            if status == ApprovalStatus.APPROVED.value:
                return True
            if status == ApprovalStatus.DENIED.value:
                return False

        await asyncio.sleep(poll_interval)

    # Timeout — mark the request as timed out
    async with db_session_factory() as db:
        await db.execute(
            text(
                "UPDATE approval_requests SET status='timeout', resolved_at=NOW() "
                "WHERE id=:id AND status='pending'"
            ),
            {"id": approval_id},
        )
        await db.commit()
        await log_event(
            db,
            event_type="approval.timeout",
            description=f"Approval request timed out after {timeout_seconds}s: {approval_id}",
            entity_type="approval",
            entity_id=approval_id,
        )
    logger.warning("approval.timeout", approval_id=approval_id, timeout_s=timeout_seconds)
    return False
