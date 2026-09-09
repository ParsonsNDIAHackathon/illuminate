"""Read-only recent GDELT coverage for the geographic map."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from datetime import datetime, timezone
from asyncio import sleep
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..connectors.gdelt import DOC
from ..connectors.http import HttpError, fetch_json, read_cached_json

router = APIRouter(prefix="/api/news", tags=["news"])
_lock = asyncio.Lock()


# Queries have separate persistent entries in the shared HTTP cache. A failed refresh
# never replaces a good response, and the original retrieval time is retained.
NEWS_TTL = 15 * 60
NEWS_MAX_STALE = 7 * 86400
_retry_after: OrderedDict[tuple[str, str], float] = OrderedDict()


def _valid(result) -> bool:
    return isinstance(result, dict) and isinstance(result.get("articles"), list)


def _response(result, query, timespan, fetched_at, *, cached=False, stale=False):
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
    return {"articles": articles, "query": query, "timespan": timespan,
            "cached": cached, "stale": stale,
            "fetched_at": datetime.fromtimestamp(fetched_at, timezone.utc).isoformat(),
            "notice": "GDELT is unavailable. Showing the last saved results; coverage may be out of date." if stale else None}


@router.get("")
async def search_news(
    query: str = Query("(conflict OR earthquake OR flood OR protest)", min_length=2, max_length=250),
    timespan: Literal["24h", "3d", "7d"] = "24h",
):
    query = query.strip()
    if len(query) < 2:
        raise HTTPException(422, "Enter a news topic with at least two characters.")
    params = {"query": query, "mode": "artlist", "format": "json",
              "maxrecords": 250, "timespan": timespan, "sort": "datedesc"}
    key = (query, timespan)
    async with _lock:
        saved = read_cached_json("GET", DOC, params=params, max_age=NEWS_MAX_STALE)
        if saved and not _valid(saved["body"]):
            saved = None
        if saved:
            fresh = time.time() - saved["_ts"] < NEWS_TTL
            if fresh or time.time() < _retry_after.get(key, 0):
                return _response(saved["body"], query, timespan, saved["_ts"], cached=True, stale=not fresh)
        try:
            for attempt in range(2):
                try:
                    result = await fetch_json("GET", DOC, params=params, ttl=NEWS_TTL, timeout=20, validate=_valid)
                    break
                except HttpError as exc:
                    # A saved response is a better fallback than making the user wait
                    # through another rate-limited request.
                    if saved or exc.status != 429 or attempt:
                        raise
                    await sleep(6)
            if not _valid(result):
                raise HTTPException(502, "GDELT returned an invalid response. Try again shortly.")
        except (HttpError, httpx.RequestError, HTTPException) as exc:
            if saved:
                _retry_after[key] = time.time() + 60
                _retry_after.move_to_end(key)
                while len(_retry_after) > 256:
                    _retry_after.popitem(last=False)
                return _response(saved["body"], query, timespan, saved["_ts"], cached=True, stale=True)
            if isinstance(exc, HTTPException):
                raise
            if isinstance(exc, httpx.RequestError):
                raise HTTPException(504, "GDELT did not respond. Try again shortly.") from exc
            if exc.status == 429:
                raise HTTPException(503, "GDELT is rate limiting requests. Try again in a minute.") from exc
            raise HTTPException(502, "GDELT is temporarily unavailable. Try again shortly.") from exc
        _retry_after.pop(key, None)
        stored = read_cached_json("GET", DOC, params=params, max_age=NEWS_TTL)
        return _response(result, query, timespan, stored["_ts"] if stored else time.time())


# Keep /api/news as the GDELT-only endpoint for existing consumers.
from ..connectors.web_news import search_web_news
from ..connectors.news_locations import locate_articles
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import re


def _article_key(article):
    parts = urlsplit(article['url'])
    params = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith('utm_') and k.lower() not in ('gclid', 'fbclid')]
    url = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip('/'), urlencode(sorted(params)), ''))
    headline = re.sub(r'[^\w]+', ' ', article.get('title', '').casefold()).strip()
    domain = article.get('domain', '').casefold().removeprefix('www.')
    return url, (domain, headline) if domain and headline else None


def merge_articles(groups):
    articles, urls, titles = [], {}, {}
    for group in groups:
        for original in group:
            article = dict(original)
            url, title = _article_key(article)
            existing = urls.get(url)
            if existing is None and title:
                existing = titles.get(title)
            if existing is not None:
                existing['providers'] = list(dict.fromkeys(existing['providers'] + article['providers']))
                if article.get('published_at'):
                    existing['published_at'] = article['published_at']
            else:
                articles.append(article)
                existing = article
            urls[url] = existing
            if title:
                titles[title] = existing
    def timestamp(a):
        try:
            value = a.get('published_at') or a.get('seendate') or ''
            return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
        except ValueError:
            return 0
    return sorted(articles, key=timestamp, reverse=True)


@router.get('/search')
async def search_all_news(
    query: str = Query('(conflict OR earthquake OR flood OR protest)', min_length=2, max_length=250),
    timespan: Literal['24h', '3d', '7d'] = '24h',
):
    query = query.strip()
    if len(query) < 2:
        raise HTTPException(422, 'Enter a news topic with at least two characters.')
    results = await asyncio.gather(
        asyncio.wait_for(search_news(query, timespan), timeout=25),
        asyncio.wait_for(search_web_news(query, timespan), timeout=15),
        return_exceptions=True,
    )
    sources, groups, notices = [], [], []
    for name, result in zip(('GDELT', 'Google News'), results):
        if isinstance(result, BaseException):
            sources.append({'name': name, 'status': 'unavailable'})
            notices.append(f'{name} is unavailable; its results may be missing.')
            continue
        stale = result.get('stale', False)
        fetched = result.get('fetched_at') or datetime.fromtimestamp(result['_ts'], timezone.utc).isoformat()
        sources.append({'name': name, 'status': 'stale' if stale else 'ok', 'cached': result.get('cached', False), 'fetched_at': fetched})
        if stale:
            notices.append(f'{name} is unavailable; showing its saved results from {fetched}.')
        groups.append([{**a, 'provider': name, 'providers': [name]} for a in result['articles']])
    if not groups:
        raise HTTPException(503, 'Both news sources are unavailable. Try again shortly.')
    articles = await asyncio.to_thread(locate_articles, merge_articles(groups))
    return {'articles': articles, 'query': query, 'timespan': timespan,
            'sources': sources, 'stale': any(s['status'] == 'stale' for s in sources),
            'notice': ' '.join(notices) or None}
