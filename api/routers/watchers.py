"""Watchers router — manage filesystem paths to watch for changes.

Endpoints:
    GET    /api/v1/watchers/        list watched paths
    POST   /api/v1/watchers/        add a new watched path
    DELETE /api/v1/watchers/{id}    remove a watched path
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from api.dependencies import get_db

logger = structlog.get_logger()
router = APIRouter()


class AddWatcherRequest(BaseModel):
    """Request body for adding a new filesystem watcher."""

    path: str
    recursive: bool = True
    trigger_goal_template: str | None = None


@router.get("/")
async def list_watchers(db=Depends(get_db)) -> dict:
    """List all configured filesystem watchers."""
    result = await db.execute(
        text(
            "SELECT id, path, recursive, trigger_goal_template, enabled, created_at "
            "FROM watched_paths ORDER BY created_at DESC"
        )
    )
    items = [
        {
            "id": str(row.id),
            "path": row.path,
            "recursive": row.recursive,
            "trigger_goal_template": row.trigger_goal_template,
            "enabled": row.enabled,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in result.fetchall()
    ]
    return {"data": items, "error": None}


@router.post("/")
async def add_watcher(body: AddWatcherRequest, request: Request) -> dict:
    """Add a filesystem path to watch and register it with the file watcher."""
    file_watcher = getattr(request.app.state, "file_watcher", None)
    if file_watcher is None:
        raise HTTPException(status_code=503, detail="File watcher service not available.")

    success = await file_watcher.add_path(
        path=body.path,
        recursive=body.recursive,
        template=body.trigger_goal_template,
    )
    return {
        "data": {
            "path": body.path,
            "registered": success,
            "message": "Path registered." if success else "Path already watched or not found.",
        },
        "error": None,
    }


@router.delete("/{watcher_id}")
async def remove_watcher(watcher_id: str, request: Request, db=Depends(get_db)) -> dict:
    """Remove a filesystem watcher by its UUID."""
    result = await db.execute(
        text("SELECT path FROM watched_paths WHERE id=CAST(:id AS uuid)"),
        {"id": watcher_id},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Watcher not found: {watcher_id}")

    # Delete the DB record first
    await db.execute(
        text("DELETE FROM watched_paths WHERE id=CAST(:id AS uuid)"),
        {"id": watcher_id},
    )
    await db.commit()

    # Unregister from the live file watcher if running
    file_watcher = getattr(request.app.state, "file_watcher", None)
    if file_watcher:
        await file_watcher.remove_path(row.path)

    return {"data": {"watcher_id": watcher_id, "removed": True}, "error": None}
