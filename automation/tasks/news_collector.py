from __future__ import annotations

import asyncio

import structlog

from automation.celery_app import celery_app

logger = structlog.get_logger()

# RSS feeds to collect (all offline-accessible public feeds)
DEFAULT_FEEDS = [
    "https://hnrss.org/frontpage",          # Hacker News
    "https://feeds.arstechnica.com/arstechnica/index",   # Ars Technica
    "https://rss.slashdot.org/Slashdot/slashdotMain",   # Slashdot
]


@celery_app.task(name="automation.news_collector", bind=True, max_retries=1)
def news_collector_task(self, feeds: list[str] | None = None) -> dict:
    """Celery task: scrape RSS feeds and ingest headlines into the 'news' RAG collection."""
    return asyncio.run(
        _collect_news(feeds or DEFAULT_FEEDS)
    )


async def _collect_news(feeds: list[str]) -> dict:
    """Fetch RSS feeds and store results in ChromaDB via RAG ingestion."""
    import httpx
    from bs4 import BeautifulSoup

    articles: list[str] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for feed_url in feeds:
            try:
                resp = await client.get(
                    feed_url,
                    headers={"User-Agent": "AILab/1.0 (RSS collector)"},
                )
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml-xml")

                for item in soup.find_all("item")[:10]:
                    title = item.find("title")
                    desc = item.find("description")
                    link = item.find("link")

                    if title:
                        text = f"Title: {title.get_text()}"
                        if desc:
                            text += f"\nSummary: {BeautifulSoup(desc.get_text(), 'html.parser').get_text()[:500]}"
                        if link:
                            text += f"\nURL: {link.get_text()}"
                        articles.append(text)

            except Exception as exc:
                logger.warning("news_collector.feed_failed", url=feed_url, error=str(exc))

    logger.info("news_collector.complete", articles=len(articles))

    if articles:
        try:
            import json
            import pathlib
            import datetime
            out_dir = pathlib.Path("/app/outputs/news")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{datetime.date.today()}.json"
            out_file.write_text(json.dumps(articles, ensure_ascii=False))
            logger.info("news_collector.articles_saved", path=str(out_file), count=len(articles))
        except Exception as exc:
            logger.warning("news_collector.save_failed", error=str(exc))

    return {"success": True, "articles_collected": len(articles)}
