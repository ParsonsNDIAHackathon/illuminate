"""Shared HTTP client with a descriptive User-Agent (SEC requires one), a
per-host politeness delay, and an on-disk JSON cache. The cache doubles as the
seed fixture store so the demo graph can be rebuilt offline."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import ipaddress
import json
import socket
import time
from pathlib import Path
from typing import Any, Iterator, Literal

import httpx

from ..config import settings

_last_call: dict[str, float] = {}
_delays = {"efts.sec.gov": 0.15, "data.sec.gov": 0.15, "www.sec.gov": 0.15, "api.gdeltproject.org": 5.5, "littlesis.org": 0.5, "api.gleif.org": 0.2, "api.usaspending.gov": 0.2}
_cache_dir: Path | None = None
_read_only_cache = False
_fixture_store = False

RetrievalMode = Literal["operational_live", "offline_fixture"]
_retrieval_mode: ContextVar[RetrievalMode] = ContextVar("retrieval_mode", default="operational_live")
_retrieval_trace: ContextVar[list[dict] | None] = ContextVar("retrieval_trace", default=None)
from dataclasses import dataclass


def set_cache_dir(p: Path | None, read_only: bool = False, *, fixture_store: bool = False) -> None:
    """Configure the process cache.

    ``fixture_store`` is deliberately independent of ``read_only``: an online
    fixture regeneration must not make committed fixtures an operational cache.
    """
    global _cache_dir, _read_only_cache, _fixture_store
    _cache_dir = p
    _read_only_cache = read_only
    _fixture_store = fixture_store
    _retrieval_mode.set("offline_fixture" if read_only else "operational_live")
    if p:
        p.mkdir(parents=True, exist_ok=True)


def cache_dir() -> Path:
    global _cache_dir
    if _cache_dir is None:
        _cache_dir = settings.data_dir / "http_cache"
        _cache_dir.mkdir(parents=True, exist_ok=True)
    return _cache_dir

@contextmanager
def retrieval_context(mode: RetrievalMode) -> Iterator[list[dict]]:
    """Select retrieval policy for one async task and collect truthful outcomes."""
    if mode not in ("operational_live", "offline_fixture"):
        raise ValueError(f"unknown retrieval mode {mode!r}")
    trace: list[dict] = []
    mode_token = _retrieval_mode.set(mode)
    trace_token = _retrieval_trace.set(trace)
    try:
        yield trace
    finally:
        _retrieval_trace.reset(trace_token)
        _retrieval_mode.reset(mode_token)
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

@dataclass(frozen=True)
class ProbeResponse:
    """Bounded diagnostic response; callers must never return its body."""
    status: int
    body: bytes
    content_type: str
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
                       timeout: float = 8.0, max_bytes: int = 4096) -> ProbeResponse:
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
            chunks: list[bytes] = []
            async for chunk in response.aiter_bytes(chunk_size=min(1024, max_bytes)):
                remaining = max_bytes - read
                chunks.append(chunk[:remaining])
                read += min(len(chunk), remaining)
                if read >= max_bytes:
                    break
            return ProbeResponse(
                status=response.status_code,
                body=b"".join(chunks),
                content_type=(response.headers.get("content-type") or "").lower(),
            )


async def fetch_json(method: str, url: str, *, params: dict | None = None, json_body: Any = None, headers: dict | None = None,
                     ttl: float = 7 * 86400, timeout: float = 30.0) -> Any:
    """GET/POST returning parsed JSON, with cache. ttl<=0 disables caching."""
    req = httpx.Request(method, url, params=params)
    full = str(req.url)
    key = _key(method, full, json_body)
    path = cache_dir() / f"{key}.json"
    stale_doc = None
    if ttl > 0 and path.exists() and _can_read_cache():
        try:
            doc = json.loads(path.read_text())
            age = max(0.0, time.time() - doc.get("_ts", 0))
            stale_doc = doc
            if _offline():
                _record("offline_fixture", full, age_s=age)
                return doc["body"]
            if age < ttl:
                _record("cached", full, age_s=age)
                return doc["body"]
        except Exception:
            pass
    if _offline():
        _record("fixture_miss", full)
        raise HttpError(0, full, "not in fixture cache (offline mode)")
    await _throttle(req.url.host or "")
    hdrs = {"User-Agent": settings.illuminate_user_agent, "Accept": "application/json", **(headers or {})}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.request(method, full, json=json_body, headers=hdrs)
        if r.status_code >= 400:
            raise HttpError(r.status_code, full, r.text)
        try:
            body = r.json()
        except Exception:
            raise HttpError(r.status_code, full, "non-JSON response")
    except Exception:
        age = _fallback_age(stale_doc.get("_ts", 0)) if stale_doc else None
        if age is not None:
            _record("stale_fallback", full, age_s=age)
            return stale_doc["body"]
        _record("error", full)
        raise
    if ttl > 0:
        try:
            path.write_text(json.dumps({"_ts": time.time(), "url": scrub(full), "body": body}))
        except Exception:
            pass
    _record("live", full, age_s=0)
    return body


async def fetch_text(url: str, *, ttl: float = 86400, timeout: float = 60.0, headers: dict | None = None) -> str:
    key = _key("GET", url, None)
    path = cache_dir() / f"{key}.txt"
    cached = path.exists() and _can_read_cache()
    age = max(0.0, time.time() - path.stat().st_mtime) if cached else None
    if ttl > 0 and cached and (_offline() or (age is not None and age < ttl)):
        _record("offline_fixture" if _offline() else "cached", url, age_s=age)
        return path.read_text()
    if _offline():
        _record("fixture_miss", url)
        raise HttpError(0, url, "not in fixture cache (offline mode)")
    hdrs = {"User-Agent": settings.illuminate_user_agent, **(headers or {})}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers=hdrs)
        if r.status_code >= 400:
            raise HttpError(r.status_code, url, r.text)
    except Exception:
        fallback_age = _fallback_age(path.stat().st_mtime) if cached else None
        if fallback_age is not None:
            _record("stale_fallback", url, age_s=fallback_age)
            return path.read_text()
        _record("error", url)
        raise
    if ttl > 0:
        path.write_text(r.text)
    _record("live", url, age_s=0)
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
    max_bytes = max(1, min(int(max_bytes), MAX_DOC_BYTES))
    key = _key("GET", url, None)
    blob = cache_dir() / f"{key}.doc"
    meta = cache_dir() / f"{key}.doc.json"
    cached_meta = None
    if ttl > 0 and blob.exists() and meta.exists() and _can_read_cache():
        try:
            m = json.loads(meta.read_text())
            cached_meta = m
            age = max(0.0, time.time() - m.get("_ts", 0))
            if _offline() or age < ttl:
                cached_url = m.get("url") or url
                await ensure_public_http_url(cached_url)
                _record("offline_fixture" if _offline() else "cached", cached_url, age_s=age)
                return {"url": cached_url, "content_type": m.get("content_type", ""), "body": blob.read_bytes(),
                        "retrieved_at": m.get("_ts"), "truncated": m.get("truncated", False)}
        except HttpError:
            if not _offline():
                blob.unlink(missing_ok=True)
                meta.unlink(missing_ok=True)
            raise
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            if not _offline():
                blob.unlink(missing_ok=True)
                meta.unlink(missing_ok=True)
    if _offline():
        _record("fixture_miss", url)
        raise HttpError(0, url, "not in fixture cache (offline mode)")
    parsed = await ensure_public_http_url(url)
    await _throttle(parsed.host or "")
    hdrs = {"User-Agent": settings.illuminate_user_agent, "Accept": "*/*"}
    chunks: list[bytes] = []
    size = 0
    truncated = False
    current = str(parsed)
    x_frame_options = None
    content_security_policy = None
    try:
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
                    x_frame_options = r.headers.get("x-frame-options")
                    content_security_policy = r.headers.get("content-security-policy")
                    async for chunk in r.aiter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= max_bytes:
                            truncated = True
                            break
                    break
    except Exception:
        age = _fallback_age(cached_meta.get("_ts", 0)) if cached_meta else None
        if age is not None:
            cached_url = cached_meta.get("url") or url
            await ensure_public_http_url(cached_url)
            _record("stale_fallback", cached_url, age_s=age)
            return {
                "url": cached_url,
                "content_type": cached_meta.get("content_type", ""),
                "body": blob.read_bytes(),
                "retrieved_at": cached_meta.get("_ts"),
                "truncated": cached_meta.get("truncated", False),
                "stale": True,
            }
        _record("error", current)
        raise
    body = b"".join(chunks)[:max_bytes]
    now = time.time()
    if ttl > 0:
        try:
            blob.write_bytes(body)
            meta.write_text(json.dumps({"_ts": now, "url": scrub(final), "content_type": ctype, "truncated": truncated}))
        except Exception:
            pass
    _record("live", final, age_s=0)
    return {
        "url": scrub(final),
        "content_type": ctype,
        "body": body,
        "retrieved_at": now,
        "truncated": truncated,
        "x_frame_options": x_frame_options,
        "content_security_policy": content_security_policy,
    }

def current_retrieval_mode() -> RetrievalMode:
    return _retrieval_mode.get()

def _record(status: str, url: str, *, age_s: float | None = None) -> None:
    trace = _retrieval_trace.get()
    if trace is not None:
        # Cache age describes the upstream response, not this ingestion.  Carry
        # its original observed time so graph writers never replace it with now.
        observed_at = time.time() - age_s if age_s is not None else time.time()
        trace.append({
            "source_status": status, "url": scrub(url), "cache_age_s": age_s,
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        })

def record_retrieval(status: str, url: str, *, age_s: float | None = None) -> None:
    """Record an outcome for connectors with specialized streaming clients."""
    _record(status, url, age_s=age_s)

def _can_read_cache() -> bool:
    mode = _retrieval_mode.get()
    return mode == "offline_fixture" or not _fixture_store

def _offline() -> bool:
    return _retrieval_mode.get() == "offline_fixture"

def _fallback_age(timestamp: float) -> float | None:
    try:
        age = max(0.0, time.time() - float(timestamp))
    except (TypeError, ValueError):
        return None
    return age if age <= settings.connector_cache_fallback_max_age_s else None
