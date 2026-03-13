"""Approvals API router — list and resolve pending approval requests.

Endpoints:
    GET    /api/v1/approvals/              list pending approvals
    POST   /api/v1/approvals/{id}/approve  approve an action
    POST   /api/v1/approvals/{id}/deny     deny an action
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from api.dependencies import get_db
from safety.approval_queue import resolve_approval

logger = structlog.get_logger()
router = APIRouter()


@router.get("/")
async def list_approvals(
    status: str = "pending",
    limit: int = 20,
    db=Depends(get_db),
) -> dict:
    """List approval requests, defaulting to pending ones."""
    result = await db.execute(
        text(
            "SELECT id, goal_id, task_step, action_type, action_description, "
            "action_payload, status, requested_at, resolved_at, resolved_by "
            "FROM approval_requests WHERE status=:status "
            "ORDER BY requested_at DESC LIMIT :limit"
        ),
        {"status": status, "limit": limit},
    )
    rows = result.fetchall()
    items = [
        {
            "id": str(row.id),
            "goal_id": str(row.goal_id) if row.goal_id else None,
            "task_step": row.task_step,
            "action_type": row.action_type,
            "action_description": row.action_description,
            "action_payload": row.action_payload,
            "status": row.status,
            "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
            "resolved_by": row.resolved_by,
        }
        for row in rows
    ]
    return {"data": items, "error": None}


@router.post("/{approval_id}/approve")
async def approve_action(approval_id: str, db=Depends(get_db)) -> dict:
    """Approve a pending action request."""
    updated = await resolve_approval(db, approval_id, approved=True)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Approval request not found or already resolved: {approval_id}",
        )
    return {"data": {"approval_id": approval_id, "approved": True}, "error": None}


@router.post("/{approval_id}/deny")
async def deny_action(approval_id: str, db=Depends(get_db)) -> dict:
    """Deny a pending action request."""
    updated = await resolve_approval(db, approval_id, approved=False)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"Approval request not found or already resolved: {approval_id}",
        )
    return {"data": {"approval_id": approval_id, "denied": True}, "error": None}
