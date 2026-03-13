from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from automation.scheduler import add_job, get_scheduler

logger = structlog.get_logger()
router = APIRouter()


# ── Request / Response Models ────────────────────────────────────────────────

class ScheduleRequest(BaseModel):
    """Request body for creating a new scheduled automation job."""

    name: str
    schedule: str  # "interval:<seconds>" or "cron:<expression>"
    task_type: str  # "daily_summary" | "news_collector" | "monitor"
    config: dict[str, Any] = {}


class ScheduleResponse(BaseModel):
    """Response for a schedule creation."""

    data: dict[str, Any] | None = None
    error: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/schedule", response_model=ScheduleResponse)
async def create_schedule(body: ScheduleRequest) -> ScheduleResponse:
    """Create a new scheduled automation job."""
    if not body.name.strip():
        return ScheduleResponse(data=None, error="Job name cannot be empty")

    allowed_tasks = {"daily_summary", "news_collector", "monitor"}
    if body.task_type not in allowed_tasks:
        return ScheduleResponse(
            data=None,
            error=f"Unknown task type. Allowed: {sorted(allowed_tasks)}",
        )

    try:
        scheduler = get_scheduler()
        if not scheduler.running:
            scheduler.start()

        job_id = add_job(
            scheduler=scheduler,
            task_type=body.task_type,
            schedule=body.schedule,
            config=body.config,
        )

        return ScheduleResponse(
            data={"job_id": job_id, "name": body.name, "schedule": body.schedule,
                  "task_type": body.task_type},
            error=None,
        )
    except Exception as exc:
        logger.error("automation.schedule_failed", error=str(exc))
        return ScheduleResponse(data=None, error=str(exc))


@router.get("/jobs")
async def list_jobs() -> dict:
    """List all registered scheduled jobs."""
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        })
    return {"data": jobs, "error": None}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Remove a scheduled job by ID."""
    scheduler = get_scheduler()
    try:
        scheduler.remove_job(job_id)
        return {"data": {"removed": job_id}, "error": None}
    except Exception as exc:
        return {"data": None, "error": str(exc)}


@router.post("/jobs/{job_id}/run")
async def trigger_job_now(job_id: str) -> dict:
    """Immediately trigger a scheduled job (one-shot, out of schedule)."""
    scheduler = get_scheduler()
    try:
        scheduler.modify_job(job_id, next_run_time=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ))
        return {"data": {"triggered": job_id}, "error": None}
    except Exception as exc:
        return {"data": None, "error": str(exc)}
