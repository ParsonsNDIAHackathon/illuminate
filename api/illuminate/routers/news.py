"""Read-only recent GDELT coverage for the geographic map."""
from __future__ import annotations

import asyncio
from typing import Literal
from calendar import monthrange
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..connectors.gdelt import DOC
from ..connectors.http import HttpError, fetch_json, gdelt_status

router = APIRouter(prefix="/api/news", tags=["news"])
_lock = asyncio.Lock()


def search_windows(timespan: str, now: datetime | None = None) -> list[dict]:
    """Sample every quarter of a long search; DOC artlist caps each window at 3 months."""
    if timespan in ("7d", "1m", "3m"):
        return [{"timespan": timespan, "maxrecords": 250}]
    now = now or datetime.now(timezone.utc)
    # Stable five-minute boundaries allow repeated searches to use the HTTP cache.
    end = now.replace(minute=now.minute // 5 * 5, second=0, microsecond=0)
    count = 4
    def months_ago(months: int) -> datetime:
        year, month = divmod(end.year * 12 + end.month - 1 - months, 12)
        return end.replace(year=year, month=month + 1, day=min(end.day, monthrange(year, month + 1)[1]))
    return [{"startdatetime": months_ago((i + 1) * 3).strftime("%Y%m%d%H%M%S"),
             "enddatetime": months_ago(i * 3).strftime("%Y%m%d%H%M%S"),
             "maxrecords": 250 // count + (1 if i < 250 % count else 0)}
            for i in range(count)]


@router.get("")
async def search_news(
    query: str = Query("(conflict OR earthquake OR flood OR protest)", min_length=2, max_length=250),
    timespan: Literal["7d", "1m", "3m", "12m"] = "7d",
):
    if len(query.strip()) < 2:
        raise HTTPException(422, "Enter a news topic with at least two characters.")
    try:
        async with _lock:
            all_articles = []
            for window in search_windows(timespan):
                result = await fetch_json("GET", DOC, params={
                    "query": query.strip(), "mode": "artlist", "format": "json",
                    "sort": "datedesc", **window,
                }, ttl=300, timeout=20)
                if not isinstance(result, dict) or not isinstance(result.get("articles"), list):
                    raise HTTPException(502, "GDELT returned an invalid response. Try again shortly.")
                all_articles.extend(result["articles"])
    except HttpError as exc:
        if exc.status == 429:
            raise HTTPException(503, "GDELT is currently refusing requests (HTTP 429).",
                                headers={"Retry-After": str(exc.retry_after or 60)}) from exc
        raise HTTPException(502, "GDELT is temporarily unavailable. Try again shortly.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(504, "GDELT did not respond. Try again shortly.") from exc
    articles = []
    seen = set()
    for article in all_articles:
        if not isinstance(article, dict):
            continue
        url = article.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        articles.append({key: article.get(key) or "" for key in ("url", "title", "seendate", "domain", "language")})
    articles.sort(key=lambda article: article["seendate"], reverse=True)
    return {"articles": articles, "query": query.strip(), "timespan": timespan}


@router.get("/status")
async def news_status():
    return gdelt_status()
