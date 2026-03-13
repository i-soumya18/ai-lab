from __future__ import annotations

from celery import Celery

from api.config import get_settings

settings = get_settings()

# Create the Celery application — uses Redis as both broker and result backend
celery_app = Celery(
    "ailab",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "automation.tasks.daily_summary",
        "automation.tasks.news_collector",
        "automation.tasks.monitor",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=110,   # soft limit: raises SoftTimeLimitExceeded
    task_time_limit=125,         # hard kill after this many seconds
)
