"""Goals API router — CRUD and execution control for persistent goals.

Endpoints:
    GET    /api/v1/goals/          list goals
    POST   /api/v1/goals/          create + plan goal
    GET    /api/v1/goals/{id}      goal detail
    POST   /api/v1/goals/{id}/run      start/resume execution
    POST   /api/v1/goals/{id}/pause    pause (cancel asyncio task)
    POST   /api/v1/goals/{id}/cancel   cancel permanently
    GET    /api/v1/goals/{id}/stream   SSE stream of goal progress
"""
from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.dependencies import get_db, get_redis
from goals.goal_manager import GoalManager
from goals.goal_planner import GoalPlanner
from goals.models import CreateGoalRequest, GoalStatus

logger = structlog.get_logger()
router = APIRouter()


@router.get("/")
async def list_goals(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db=Depends(get_db),
) -> dict:
    """List all goals, optionally filtered by status."""
    manager = GoalManager(db)
    summaries = await manager.list_goals(status=status, limit=limit, offset=offset)
    return {"data": [s.model_dump() for s in summaries], "error": None}


@router.post("/")
async def create_goal(body: CreateGoalRequest, request: Request, db=Depends(get_db)) -> dict:
    """Create a new goal and automatically decompose it into tasks using the LLM.

    If auto_run=true in the body, also starts execution immediately.
    """
    planner = GoalPlanner(ollama_client=request.app.state.ollama_client)

    try:
        tasks = await planner.plan(title=body.title, description=body.description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    manager = GoalManager(db)
    goal = await manager.create(
        title=body.title,
        description=body.description,
        context=body.context,
        tasks=tasks,
    )

    if body.auto_run:
        executor = request.app.state.goal_executor
        await executor.start(goal.id)

    return {"data": goal.model_dump(), "error": None}


@router.get("/{goal_id}")
async def get_goal(goal_id: str, db=Depends(get_db)) -> dict:
    """Get full goal detail including all task steps and their results."""
    manager = GoalManager(db)
    goal = await manager.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"Goal not found: {goal_id}")
    return {"data": goal.model_dump(), "error": None}


@router.post("/{goal_id}/run")
async def run_goal(goal_id: str, request: Request, db=Depends(get_db)) -> dict:
    """Start or resume goal execution."""
    manager = GoalManager(db)
    goal = await manager.get(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail=f"Goal not found: {goal_id}")

    if goal.status in (GoalStatus.COMPLETED, GoalStatus.CANCELLED):
        raise HTTPException(status_code=400,
                            detail=f"Cannot run a {goal.status.value} goal.")

    executor = request.app.state.goal_executor
    started = await executor.start(goal_id)
    return {
        "data": {"goal_id": goal_id, "started": started},
        "error": None if started else "Goal is already running or max concurrency reached.",
    }


@router.post("/{goal_id}/pause")
async def pause_goal(goal_id: str, request: Request, db=Depends(get_db)) -> dict:
    """Pause a running goal by cancelling its asyncio task."""
    executor = request.app.state.goal_executor
    cancelled = await executor.cancel(goal_id)
    if not cancelled:
        # Not running — just mark paused in DB
        manager = GoalManager(db)
        await manager.update_status(goal_id, GoalStatus.PAUSED)
    return {"data": {"goal_id": goal_id, "paused": True}, "error": None}


@router.post("/{goal_id}/cancel")
async def cancel_goal(goal_id: str, request: Request, db=Depends(get_db)) -> dict:
    """Permanently cancel a goal."""
    executor = request.app.state.goal_executor
    await executor.cancel(goal_id)
    manager = GoalManager(db)
    await manager.update_status(goal_id, GoalStatus.CANCELLED)
    return {"data": {"goal_id": goal_id, "cancelled": True}, "error": None}


@router.get("/{goal_id}/stream")
async def stream_goal_events(goal_id: str, redis=Depends(get_redis)) -> StreamingResponse:
    """Stream goal progress events via Server-Sent Events.

    Subscribes to Redis pub/sub channel goal:{goal_id}:events.
    """
    channel = f"goal:{goal_id}:events"

    async def event_generator():
        yield "retry: 3000\n\n"  # tell browser to reconnect after 3s on disconnect
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    yield f"data: {data}\n\n"
                    # Stop streaming once goal reaches a terminal state
                    try:
                        parsed = json.loads(data)
                        if parsed.get("event") in (
                            "goal.completed", "goal.failed", "goal.cancelled"
                        ):
                            break
                    except (json.JSONDecodeError, AttributeError):
                        pass
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
