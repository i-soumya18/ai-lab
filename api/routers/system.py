"""System control router — kill switch and status.

Endpoints:
    POST   /api/v1/system/kill      activate kill switch
    POST   /api/v1/system/resume    deactivate kill switch
    GET    /api/v1/system/status    system state summary
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from api.dependencies import get_db, get_redis
from safety.kill_switch import activate, deactivate, is_killed

logger = structlog.get_logger()
router = APIRouter()


@router.post("/kill")
async def kill_system(request: Request, redis=Depends(get_redis)) -> dict:
    """Activate the kill switch — all running goals will abort at their next step."""
    await activate(redis)
    # Also cancel all running goal tasks immediately
    executor = getattr(request.app.state, "goal_executor", None)
    if executor:
        for goal_id in list(executor._running.keys()):
            await executor.cancel(goal_id)
    return {"data": {"kill_switch": True, "message": "Kill switch activated."}, "error": None}


@router.post("/resume")
async def resume_system(redis=Depends(get_redis)) -> dict:
    """Deactivate the kill switch — goals can be restarted."""
    await deactivate(redis)
    return {"data": {"kill_switch": False, "message": "Kill switch deactivated."}, "error": None}


@router.get("/status")
async def system_status(request: Request, redis=Depends(get_redis), db=Depends(get_db)) -> dict:
    """Return current system state: kill switch, running goals, pending approvals."""
    killed = await is_killed(redis)

    executor = getattr(request.app.state, "goal_executor", None)
    running_count = executor.running_count() if executor else 0

    result = await db.execute(
        text("SELECT COUNT(*) FROM approval_requests WHERE status='pending'")
    )
    pending_approvals = result.scalar() or 0

    goal_result = await db.execute(
        text("SELECT status, COUNT(*) as cnt FROM goals GROUP BY status")
    )
    goal_counts = {row.status: row.cnt for row in goal_result.fetchall()}

    return {
        "data": {
            "kill_switch_active": killed,
            "running_goals": running_count,
            "pending_approvals": pending_approvals,
            "goal_counts": goal_counts,
        },
        "error": None,
    }
