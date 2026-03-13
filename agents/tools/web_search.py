from __future__ import annotations

from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup
from pydantic import BaseModel

logger = structlog.get_logger()


class SearchResult(BaseModel):
    """A single web search result."""

    title: str
    url: str
    snippet: str


async def web_search(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search the web using DuckDuckGo HTML scraping.

    No API key required. Falls back to empty results if network unavailable.
    """
    results: list[SearchResult] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AILab/1.0)"},
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            result_divs = soup.select(".result")

            for div in result_divs[:max_results]:
                title_el = div.select_one(".result__title a")
                snippet_el = div.select_one(".result__snippet")

                if title_el:
                    title = title_el.get_text(strip=True)
                    url = title_el.get("href", "")
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                    results.append(SearchResult(
                        title=title,
                        url=str(url),
                        snippet=snippet,
                    ))

    except Exception as exc:
        logger.warning("web_search.failed", query=query, error=str(exc))

    logger.info("web_search.complete", query=query, results=len(results))
    return results


async def url_scrape(url: str, max_chars: int = 5000) -> str:
    """Scrape and extract text content from a URL."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AILab/1.0)"},
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer"]):
                element.decompose()

            text = soup.get_text(separator="\n", strip=True)
            return text[:max_chars]

    except Exception as exc:
        logger.warning("url_scrape.failed", url=url, error=str(exc))
        return f"Failed to scrape URL: {exc}"
