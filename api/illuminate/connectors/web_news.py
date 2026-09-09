"""Public Google News search RSS, normalized without fetching publisher articles."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import httpx

RSS_URL = 'https://news.google.com/rss/search'
TTL = 900
MAX_STALE = 7 * 86400
_cache: OrderedDict[tuple[str, str], dict] = OrderedDict()
_lock = asyncio.Lock()


def parse_feed(content: bytes, timespan: str, now: datetime) -> list[dict]:
    if len(content) > 2_000_000 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('Unsafe or oversized RSS')
    root = ET.fromstring(content)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('Invalid news RSS')
    cutoff = now - timedelta(days={'24h': 1, '3d': 3, '7d': 7}[timespan])
    articles = []
    for item in root.findall('./channel/item')[:100]:
        link = (item.findtext('link') or '').strip()
        source = item.find('source')
        publisher = (source.text or '').strip() if source is not None else ''
        domain = urlsplit(source.get('url', '')).hostname if source is not None else ''
        title = (item.findtext('title') or '').strip()
        if publisher and title.endswith(' - ' + publisher):
            title = title[:-len(' - ' + publisher)]
        if not title or urlsplit(link).scheme not in ('https', 'http') or not urlsplit(link).hostname:
            continue
        try:
            published = parsedate_to_datetime(item.findtext('pubDate') or '')
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if not cutoff <= published <= now + timedelta(minutes=5):
                continue
        except (ValueError, TypeError, OverflowError):
            continue  # Unknown dates cannot establish the requested time window.
        articles.append({'url': link, 'title': title, 'domain': domain or '', 'publisher': publisher,
                         'language': '', 'seendate': '', 'published_at': published.astimezone(timezone.utc).isoformat(),
                         'provider': 'Google News', 'providers': ['Google News']})
    return articles


async def search_web_news(query: str, timespan: str) -> dict:
    key = (query, timespan)
    async with _lock:
        saved = _cache.get(key)
        if saved and time.time() - saved['_ts'] < TTL:
            return {**saved, 'cached': True, 'stale': False}
        try:
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                async with client.stream('GET', RSS_URL, params={
                    'q': f'{query} when:{"1d" if timespan == "24h" else timespan}',
                    'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en',
                }, headers={'User-Agent': 'Illuminate/0.1 news search'}) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise ValueError('Oversized RSS')
            articles = parse_feed(bytes(body), timespan, datetime.now(timezone.utc))
        except (httpx.HTTPError, ET.ParseError, ValueError):
            if saved and time.time() - saved['_ts'] < MAX_STALE:
                return {**saved, 'cached': True, 'stale': True}
            raise
        result = {'articles': articles, '_ts': time.time(), 'cached': False, 'stale': False}
        _cache[key] = result
        _cache.move_to_end(key)
        while len(_cache) > 64:
            _cache.popitem(last=False)
        return result
