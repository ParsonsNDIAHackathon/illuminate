"""Shared HTTP client with a descriptive User-Agent (SEC requires one), a
per-host politeness delay, and an on-disk JSON cache. The cache doubles as the
seed fixture store so the demo graph can be rebuilt offline."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import settings

_last_call: dict[str, float] = {}
_delays = {"efts.sec.gov": 0.15, "data.sec.gov": 0.15, "www.sec.gov": 0.15, "api.gdeltproject.org": 5.5, "littlesis.org": 0.5, "api.gleif.org": 0.2, "api.usaspending.gov": 0.2}
_cache_dir: Path | None = None
_read_only_cache = False


def set_cache_dir(p: Path | None, read_only: bool = False) -> None:
    global _cache_dir, _read_only_cache
    _cache_dir = p
    _read_only_cache = read_only
    if p:
        p.mkdir(parents=True, exist_ok=True)


def cache_dir() -> Path:
    global _cache_dir
    if _cache_dir is None:
        _cache_dir = settings.data_dir / "http_cache"
        _cache_dir.mkdir(parents=True, exist_ok=True)
    return _cache_dir


_SECRET_PARAMS = {"api_key", "api_token", "token", "apikey", "key"}


def scrub(url: str) -> str:
    """Remove credential query parameters so neither the cache key nor the stored
    URL ever carries a key (fixtures are committed)."""
    u = httpx.URL(url)
    params = [(k, v) for k, v in u.params.multi_items() if k.lower() not in _SECRET_PARAMS]
    return str(u.copy_with(query=None).copy_merge_params(params)) if params else str(u.copy_with(query=None))


def _key(method: str, url: str, body: Any) -> str:
    h = hashlib.sha1(f"{method} {scrub(url)} {json.dumps(body, sort_keys=True) if body is not None else ''}".encode()).hexdigest()
    return h


class HttpError(Exception):
    def __init__(self, status: int, url: str, text: str = ""):
        super().__init__(f"HTTP {status} for {url}: {text[:200]}")
        self.status = status


async def fetch_json(method: str, url: str, *, params: dict | None = None, json_body: Any = None, headers: dict | None = None,
                     ttl: float = 7 * 86400, timeout: float = 30.0) -> Any:
    """GET/POST returning parsed JSON, with cache. ttl<=0 disables caching."""
    req = httpx.Request(method, url, params=params)
    full = str(req.url)
    key = _key(method, full, json_body)
    path = cache_dir() / f"{key}.json"
    if ttl > 0 and path.exists():
        try:
            doc = json.loads(path.read_text())
            if _read_only_cache or time.time() - doc.get("_ts", 0) < ttl:
                return doc["body"]
        except Exception:
            pass
    if _read_only_cache:
        raise HttpError(0, full, "not in fixture cache (offline mode)")
    host = req.url.host or ""
    delay = _delays.get(host, 0.0)
    if delay:
        wait = _last_call.get(host, 0) + delay - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call[host] = time.time()
    hdrs = {"User-Agent": settings.illuminate_user_agent, "Accept": "application/json", **(headers or {})}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.request(method, full, json=json_body, headers=hdrs)
    if r.status_code >= 400:
        raise HttpError(r.status_code, full, r.text)
    try:
        body = r.json()
    except Exception:
        raise HttpError(r.status_code, full, "non-JSON response")
    if ttl > 0:
        try:
            path.write_text(json.dumps({"_ts": time.time(), "url": scrub(full), "body": body}))
        except Exception:
            pass
    return body


async def fetch_text(url: str, *, ttl: float = 86400, timeout: float = 60.0, headers: dict | None = None) -> str:
    key = _key("GET", url, None)
    path = cache_dir() / f"{key}.txt"
    if ttl > 0 and path.exists() and (_read_only_cache or time.time() - path.stat().st_mtime < ttl):
        return path.read_text()
    if _read_only_cache:
        raise HttpError(0, url, "not in fixture cache (offline mode)")
    hdrs = {"User-Agent": settings.illuminate_user_agent, **(headers or {})}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r = await client.get(url, headers=hdrs)
    if r.status_code >= 400:
        raise HttpError(r.status_code, url, r.text)
    if ttl > 0:
        path.write_text(r.text)
    return r.text
