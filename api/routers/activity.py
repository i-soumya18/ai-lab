"""Activity log router — read-only access to the audit trail.

Endpoints:
    GET    /api/v1/activity/       paginated activity log
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text

from api.dependencies import get_db

logger = structlog.get_logger()
router = APIRouter()


@router.get("/")
async def list_activity(
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db=Depends(get_db),
) -> dict:
    """Return paginated activity log entries, newest first.

    Optional filters: entity_type, entity_id, event_type.
    """
    conditions = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if entity_type:
        conditions.append("entity_type=:entity_type")
        params["entity_type"] = entity_type
    if entity_id:
        conditions.append("entity_id=:entity_id")
        params["entity_id"] = entity_id
    if event_type:
        conditions.append("event_type LIKE :event_type")
        params["event_type"] = f"{event_type}%"

    where = " AND ".join(conditions)
    result = await db.execute(
        text(
            f"SELECT id, event_type, entity_type, entity_id, description, payload, created_at "
            f"FROM activity_log WHERE {where} "
            f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        ),
        params,
    )
    items = [
        {
            "id": str(row.id),
            "event_type": row.event_type,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "description": row.description,
            "payload": row.payload,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in result.fetchall()
    ]
    return {"data": items, "error": None}
