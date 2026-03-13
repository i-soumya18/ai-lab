from __future__ import annotations

from typing import Any

import structlog
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = structlog.get_logger()

# Singleton scheduler instance shared across the application
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return (or create) the global APScheduler instance."""
    global _scheduler

    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            executors={"default": AsyncIOExecutor()},
            job_defaults={"coalesce": False, "max_instances": 1},
            timezone="UTC",
        )
        _register_default_jobs(_scheduler)
        logger.info("scheduler.initialized")

    return _scheduler


def _register_default_jobs(scheduler: AsyncIOScheduler) -> None:
    """Register built-in scheduled jobs."""
    # Daily summary at 08:00 UTC every day
    scheduler.add_job(
        _run_daily_summary,
        trigger="cron",
        hour=8,
        minute=0,
        id="daily_summary",
        replace_existing=True,
    )

    # News collection every 4 hours
    scheduler.add_job(
        _run_news_collector,
        trigger="interval",
        hours=4,
        id="news_collector",
        replace_existing=True,
    )

    logger.info("scheduler.jobs_registered", count=2)


async def _run_daily_summary() -> None:
    """Dispatch the daily summary Celery task."""
    from automation.tasks.daily_summary import daily_summary_task
    daily_summary_task.delay()
    logger.info("scheduler.dispatched", task="daily_summary")


async def _run_news_collector() -> None:
    """Dispatch the news collector Celery task."""
    from automation.tasks.news_collector import news_collector_task
    news_collector_task.delay()
    logger.info("scheduler.dispatched", task="news_collector")


def add_job(
    scheduler: AsyncIOScheduler,
    task_type: str,
    schedule: str,
    config: dict[str, Any],
    job_id: str | None = None,
) -> str:
    """Add a new scheduled job dynamically.

    `schedule` is either:
    - "cron:<cron_expression>" e.g. "cron:0 9 * * 1"
    - "interval:<seconds>" e.g. "interval:3600"
    """
    import uuid

    if job_id is None:
        job_id = str(uuid.uuid4())

    if schedule.startswith("interval:"):
        seconds = int(schedule.split(":", 1)[1])
        trigger_args = {"trigger": "interval", "seconds": seconds}
    else:
        trigger_args = {"trigger": "cron"}
        # Parse cron expression
        if schedule.startswith("cron:"):
            cron_expr = schedule.split(":", 1)[1].strip()
            parts = cron_expr.split()
            fields = ["minute", "hour", "day", "month", "day_of_week"]
            for i, part in enumerate(parts[:5]):
                if part != "*":
                    trigger_args[fields[i]] = part

    async def _dispatch() -> None:
        logger.info("scheduler.custom_job_fired", job_id=job_id, task_type=task_type)
        from automation.celery_app import celery_app
        celery_app.send_task(f"automation.tasks.{task_type}", kwargs=config or {})

    scheduler.add_job(_dispatch, id=job_id, replace_existing=True, **trigger_args)
    logger.info("scheduler.job_added", job_id=job_id, task_type=task_type, schedule=schedule)
    return job_id
