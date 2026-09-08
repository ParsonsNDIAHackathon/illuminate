"""Shared HTTP client with a descriptive User-Agent (SEC requires one), a
per-host politeness delay, and an on-disk JSON cache. The cache doubles as the
seed fixture store so the demo graph can be rebuilt offline."""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import socket
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


_SECRET_PARAMS = {
    "access_key", "access_token", "api_key", "api_token", "apikey",
    "authorization", "client_secret", "credential", "key", "key_id",
    "password", "secret", "signature", "token",
}


def scrub(url: str) -> str:
    """Remove credential query parameters so neither the cache key nor the stored
    URL ever carries a key (fixtures are committed)."""
    try:
        u = httpx.URL(url).copy_with(userinfo=None)
        params = [(k, v) for k, v in u.params.multi_items() if k.lower() not in _SECRET_PARAMS]
        return str(u.copy_with(query=None).copy_merge_params(params)) if params else str(u.copy_with(query=None))
    except (TypeError, ValueError):
        return "[invalid-url]"


def _key(method: str, url: str, body: Any) -> str:
    h = hashlib.sha1(f"{method} {scrub(url)} {json.dumps(body, sort_keys=True) if body is not None else ''}".encode()).hexdigest()
    return h


async def _throttle(host: str) -> None:
    """Per-host politeness delay; SEC and GDELT rate-limit hard."""
    delay = _delays.get(host, 0.0)
    if not delay:
        return
    wait = _last_call.get(host, 0) + delay - time.time()
    if wait > 0:
        await asyncio.sleep(wait)
    _last_call[host] = time.time()


class HttpError(Exception):
    def __init__(self, status: int, url: str, text: str = ""):
        # Upstream bodies and credential query parameters are never safe error
        # material. Callers receive only a scrubbed destination and status.
        super().__init__(f"HTTP {status} for {scrub(url)}")
        self.status = status


def _public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
    )


async def ensure_public_http_url(url: str) -> httpx.URL:
    """Reject local/private destinations before server-side document fetches."""
    try:
        parsed = httpx.URL(url)
        if parsed.scheme not in ("http", "https") or not parsed.host or parsed.userinfo:
            raise ValueError
        if parsed.host.lower() == "localhost" or parsed.host.lower().endswith((".local", ".internal")):
            raise ValueError
        try:
            if not _public_ip(parsed.host):
                raise ValueError
        except ValueError as exc:
            # It was an IP literal and was not public.
            try:
                ipaddress.ip_address(parsed.host)
            except ValueError:
                pass
            else:
                raise HttpError(0, url) from exc
        loop = asyncio.get_running_loop()
        infos = await loop.run_in_executor(
            None, lambda: socket.getaddrinfo(parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                            type=socket.SOCK_STREAM)
        )
        if not infos or any(not _public_ip(info[4][0]) for info in infos):
            raise ValueError
        return parsed
    except HttpError:
        raise
    except (OSError, TypeError, ValueError):
        raise HttpError(0, url) from None


async def probe_source(url: str, *, params: dict | None = None, headers: dict | None = None,
                       timeout: float = 8.0, max_bytes: int = 4096) -> None:
    """Make one bounded, non-cached GET used only for connector diagnostics."""
    req = httpx.Request("GET", url, params=params)
    full = str(req.url)
    await _throttle(req.url.host or "")
    hdrs = {
        "User-Agent": settings.illuminate_user_agent,
        "Accept": "*/*",
        "Range": f"bytes=0-{max_bytes - 1}",
        **(headers or {}),
    }
    # Redirects are deliberately not followed: automatic redirect handling can
    # buffer an unbounded intermediate body before exposing the final stream.
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream("GET", full, headers=hdrs) as response:
            if response.status_code < 200 or response.status_code >= 300:
                # Never read an upstream error body into memory or the exception.
                raise HttpError(response.status_code, full)
            read = 0
            async for chunk in response.aiter_raw(chunk_size=min(1024, max_bytes)):
                read += len(chunk)
                if read >= max_bytes:
                    break


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
    await _throttle(req.url.host or "")
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


# Documents are archival — a filing or an article does not change once published — so they
# are cached far longer than API responses, as bytes plus a sidecar holding the content type.
DOC_TTL = 30 * 86400
MAX_DOC_BYTES = 8 * 1024 * 1024


async def fetch_document(url: str, *, ttl: float = DOC_TTL, timeout: float = 60.0,
                         max_bytes: int = MAX_DOC_BYTES) -> dict:
    """GET any document. Returns {url, content_type, body: bytes, retrieved_at, truncated}.

    Unlike fetch_json/fetch_text this makes no assumption about the payload: the caller
    dispatches on content_type. The download stops at MAX_DOC_BYTES so a stray link to a
    large binary cannot exhaust memory. Every cache read, request, and redirect
    first passes the public-network destination policy.
    """
    parsed = await ensure_public_http_url(url)
    max_bytes = max(1, min(int(max_bytes), MAX_DOC_BYTES))
    key = _key("GET", url, None)
    blob = cache_dir() / f"{key}.doc"
    meta = cache_dir() / f"{key}.doc.json"
    if ttl > 0 and blob.exists() and meta.exists():
        try:
            m = json.loads(meta.read_text())
            if _read_only_cache or time.time() - m.get("_ts", 0) < ttl:
                cached_url = m.get("url") or url
                await ensure_public_http_url(cached_url)
                return {"url": cached_url, "content_type": m.get("content_type", ""), "body": blob.read_bytes(),
                        "retrieved_at": m.get("_ts"), "truncated": m.get("truncated", False)}
        except HttpError:
            if not _read_only_cache:
                blob.unlink(missing_ok=True)
                meta.unlink(missing_ok=True)
            raise
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            if not _read_only_cache:
                blob.unlink(missing_ok=True)
                meta.unlink(missing_ok=True)
            raise HttpError(0, url) from None
    if _read_only_cache:
        raise HttpError(0, url, "not in fixture cache (offline mode)")
    await _throttle(parsed.host or "")
    hdrs = {"User-Agent": settings.illuminate_user_agent, "Accept": "*/*"}
    chunks: list[bytes] = []
    size = 0
    truncated = False
    current = str(parsed)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for redirects in range(4):
            await ensure_public_http_url(current)
            async with client.stream("GET", current, headers=hdrs) as r:
                if r.is_redirect:
                    if redirects == 3 or not r.headers.get("location"):
                        raise HttpError(r.status_code, current)
                    current = str(r.url.join(r.headers["location"]))
                    continue
                if r.status_code >= 400:
                    raise HttpError(r.status_code, current)
                ctype = (r.headers.get("content-type") or "application/octet-stream").strip().lower()
                final = str(r.url)
                async for chunk in r.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= max_bytes:
                        truncated = True
                        break
                break
    body = b"".join(chunks)[:max_bytes]
    now = time.time()
    if ttl > 0:
        try:
            blob.write_bytes(body)
            meta.write_text(json.dumps({"_ts": now, "url": scrub(final), "content_type": ctype, "truncated": truncated}))
        except Exception:
            pass
    return {
        "url": scrub(final),
        "content_type": ctype,
        "body": body,
        "retrieved_at": now,
        "truncated": truncated,
        "x_frame_options": r.headers.get("x-frame-options"),
        "content_security_policy": r.headers.get("content-security-policy"),
    }
