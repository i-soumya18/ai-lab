from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import structlog

import redis as sync_redis

from automation.celery_app import celery_app

logger = structlog.get_logger()


def _get_redis_client():
    """Create a synchronous Redis client for Celery task context."""
    from api.config import get_settings
    s = get_settings()
    return sync_redis.from_url(s.redis_url)


@celery_app.task(name="automation.monitor", bind=True, max_retries=1)
def monitor_task(self, targets: list[dict[str, str]]) -> dict:
    """Celery task: check URLs for content changes.

    Each target is a dict: {"url": "...", "name": "..."}
    Compares SHA-256 hash of page content to detect changes.
    """
    return asyncio.run(_run_monitor(targets))


async def _run_monitor(targets: list[dict[str, str]]) -> dict:
    """Check each target URL for content changes using in-memory hash store."""
    import httpx
    from bs4 import BeautifulSoup

    redis_client = _get_redis_client()

    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for target in targets:
            url = target.get("url", "")
            name = target.get("name", url)

            if not url:
                continue

            try:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "AILab/1.0 (site monitor)"},
                )
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "lxml")
                for el in soup(["script", "style", "nav", "footer"]):
                    el.decompose()
                text = soup.get_text(separator=" ", strip=True)

                current_hash = hashlib.sha256(text.encode()).hexdigest()
                previous_hash_bytes = redis_client.get(f"monitor:hash:{url}")
                previous_hash = previous_hash_bytes.decode() if previous_hash_bytes else None
                changed = previous_hash is not None and previous_hash != current_hash
                redis_client.set(f"monitor:hash:{url}", current_hash)

                results.append({
                    "name": name,
                    "url": url,
                    "changed": changed,
                    "hash": current_hash[:16] + "...",
                })

                if changed:
                    logger.info("monitor.change_detected", name=name, url=url)

            except Exception as exc:
                logger.warning("monitor.check_failed", url=url, error=str(exc))
                results.append({"name": name, "url": url, "changed": False, "error": str(exc)})

    return {"success": True, "results": results}
