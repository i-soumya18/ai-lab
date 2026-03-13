"""Structured activity logger — appends every significant event to PostgreSQL.

All subsystems (GoalExecutor, FileAgent, ApprovalQueue) call `log_event()`
to build a complete, queryable audit trail in the `activity_log` table.

Event type conventions:
    goal.created / goal.started / goal.completed / goal.failed / goal.cancelled
    goal.step.started / goal.step.completed / goal.step.failed
    approval.requested / approval.approved / approval.denied / approval.timeout
    agent.run / agent.error
    file.read / file.write / file.delete / file.ingest
    system.kill_switch.activated / system.kill_switch.deactivated
"""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def log_event(
    db: AsyncSession,
    event_type: str,
    description: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one event to the activity_log table.

    Args:
        db: SQLAlchemy async session.
        event_type: Dot-notation event name, e.g. "goal.started".
        description: Human-readable summary of what happened.
        entity_type: Optional category of the entity, e.g. "goal", "agent".
        entity_id: Optional identifier of the specific entity (UUID string, name).
        payload: Optional structured data to attach to the log entry.
    """
    import json

    payload_json = json.dumps(payload or {})
    try:
        await db.execute(
            text(
                "INSERT INTO activity_log "
                "(event_type, entity_type, entity_id, description, payload) "
                "VALUES (:event_type, :entity_type, :entity_id, :description, "
                "CAST(:payload AS jsonb))"
            ),
            {
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "description": description,
                "payload": payload_json,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.error("activity_logger.error", event_type=event_type, error=str(exc))
        await db.rollback()
