"""Read-only recent GDELT coverage for the geographic map."""
from __future__ import annotations

import asyncio
from asyncio import sleep
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..connectors.gdelt import DOC
from ..connectors.http import HttpError, fetch_json

router = APIRouter(prefix="/api/news", tags=["news"])
_lock = asyncio.Lock()


@router.get("")
async def search_news(
    query: str = Query("(conflict OR earthquake OR flood OR protest)", min_length=2, max_length=250),
    timespan: Literal["24h", "3d", "7d"] = "24h",
):
    if len(query.strip()) < 2:
        raise HTTPException(422, "Enter a news topic with at least two characters.")
    try:
        async with _lock:
            for attempt in range(2):
                try:
                    result = await fetch_json("GET", DOC, params={
                        "query": query.strip(), "mode": "artlist", "format": "json",
                        "maxrecords": 250, "timespan": timespan, "sort": "datedesc",
                    }, ttl=300, timeout=20)
                    break
                except HttpError as exc:
                    if exc.status != 429 or attempt:
                        raise
                    # One bounded retry, spaced beyond GDELT's five-second limit.
                    await sleep(6)
        if not isinstance(result, dict) or not isinstance(result.get("articles"), list):
            raise HTTPException(502, "GDELT returned an invalid response. Try again shortly.")
    except HttpError as exc:
        if exc.status == 429:
            raise HTTPException(503, "GDELT is rate limiting requests. Try again in a minute.") from exc
        raise HTTPException(502, "GDELT is temporarily unavailable. Try again shortly.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(504, "GDELT did not respond. Try again shortly.") from exc
    articles = []
    seen = set()
    for article in result["articles"]:
        if not isinstance(article, dict):
            continue
        url = article.get("url")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")) or url in seen:
            continue
        seen.add(url)
        articles.append({key: article.get(key) or "" for key in ("url", "title", "seendate", "domain", "language")})
    return {"articles": articles, "query": query.strip(), "timespan": timespan}
