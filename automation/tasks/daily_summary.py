from __future__ import annotations

import asyncio

import structlog

from automation.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="automation.daily_summary", bind=True, max_retries=2)
def daily_summary_task(self) -> dict:
    """Celery task: summarize the past 24 hours of conversation history."""
    return asyncio.run(_run_daily_summary())


async def _run_daily_summary() -> dict:
    """Core logic for the daily summary task."""
    from datetime import datetime, timedelta, timezone

    from api.config import get_settings
    from models.ollama_client import OllamaClient

    settings = get_settings()
    ollama = OllamaClient(base_url=settings.ollama_base_url)

    # In a full implementation: query PostgreSQL for yesterday's conversations
    # and summarize them. For now, record a placeholder summary.
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)

    prompt = (
        f"Generate a brief daily AI assistant activity summary for "
        f"{yesterday.strftime('%Y-%m-%d')}. "
        "Keep it to 3-5 bullet points covering topics discussed, files ingested, "
        "and agents run."
    )

    try:
        summary = await ollama.generate(
            model=settings.default_model,
            prompt=prompt,
            system="You are a concise assistant providing daily activity summaries.",
            temperature=0.3,
        )
        logger.info("daily_summary.complete", date=yesterday.date().isoformat())
        return {"success": True, "summary": summary, "date": yesterday.date().isoformat()}
    except Exception as exc:
        logger.error("daily_summary.failed", error=str(exc))
        return {"success": False, "error": str(exc)}
    finally:
        await ollama.close()
