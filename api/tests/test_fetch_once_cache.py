import asyncio
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
import os
import threading
import time

import httpx
import pytest
from fastapi import HTTPException

from illuminate.config import settings
from illuminate.connectors import http
from illuminate.routers import fetch_cache as cache_router
from illuminate import fetch_cache_db


def _multiprocess_fetch(cache_url, marker, queue):
    from pydantic import SecretStr

    settings.illuminate_fetch_cache_url = cache_url
    settings.illuminate_fetch_cache_token = SecretStr("test-service-token")
    settings.illuminate_fetch_cache_required = True
    settings.illuminate_fetch_cache_wait_s = 5
    settings.illuminate_fetch_cache_lease_s = 2
    identity, document = http.canonical_request_identity(
        "process-source", "GET", "https://source.test/process", None, "json",
    )

    async def producer():
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, b"upstream\n")
        finally:
            os.close(descriptor)
        await asyncio.sleep(0.2)
        return _produced(b'{"process":"shared"}')

    try:
        record, hit = asyncio.run(http._shared_fetch(identity, document, producer))
        queue.put((record["payload"], hit))
    except Exception as exc:
        queue.put(("error", type(exc).__name__))


class _ProtocolHandler(BaseHTTPRequestHandler):
    authority = None

    def log_message(self, *_args):
        pass

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(length))
        authority = self.authority
        with authority["lock"]:
            now = time.time()
            if self.path.endswith("/claim"):
                if authority["record"]:
                    response = {"state": "complete", "record": authority["record"]}
                elif authority["owner"] and authority["lease_until"] >= now:
                    response = {
                        "state": "waiting", "owner": None,
                        "lease_until": authority["lease_until"],
                    }
                else:
                    authority["fence"] += 1
                    authority["owner"] = "http-owner"
                    authority["lease_until"] = now + body["lease_s"]
                    response = {
                        "state": "claimed", "owner": authority["owner"],
                        "fence": authority["fence"],
                        "lease_until": authority["lease_until"],
                    }
                status = 200
            elif self.path.endswith("/renew"):
                authority["lease_until"] = now + body["lease_s"]
                response, status = {"lease_until": authority["lease_until"]}, 200
            elif self.path.endswith("/publish"):
                if body["owner"] != authority["owner"] or body["fence"] != authority["fence"]:
                    response, status = {"detail": "lost"}, 409
                else:
                    authority["record"] = {
                        **body["record"], "namespace": body["namespace"],
                        "identity": body["identity"], "first_retrieved_at": now,
                    }
                    authority["owner"] = None
                    response, status = authority["record"], 200
            else:
                authority["owner"] = "cooldown"
                authority["lease_until"] = now + body["retry_after_s"]
                response, status = {}, 200
        encoded = json.dumps(response).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class _Response:
    def __init__(self, status: int, data=None):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "cache error",
                request=httpx.Request("POST", "https://cache.test"),
                response=httpx.Response(self.status_code),
            )


class _Authority:
    def __init__(self):
        self.record = None
        self.owner = None
        self.lease_until = 0.0
        self.fence = 0
        self.lock = asyncio.Lock()
        self.claims = 0

    async def post(self, url, *, json, headers):
        async with self.lock:
            if url.endswith("/claim"):
                self.claims += 1
                if self.record:
                    return _Response(200, {"state": "complete", "record": dict(self.record)})
                now = time.time()
                if self.owner and self.lease_until >= now:
                    return _Response(200, {
                        "state": "waiting", "owner": None, "lease_until": self.lease_until,
                    })
                self.owner = "owner-1"
                self.fence += 1
                self.lease_until = now + json["lease_s"]
                return _Response(200, {
                    "state": "claimed", "owner": self.owner, "fence": self.fence,
                    "lease_until": self.lease_until,
                })
            if url.endswith("/renew"):
                if json["owner"] != self.owner or json["fence"] != self.fence:
                    return _Response(409)
                self.lease_until = time.time() + json["lease_s"]
                return _Response(200, {"lease_until": self.lease_until})
            if url.endswith("/publish"):
                if json["owner"] != self.owner or json["fence"] != self.fence:
                    return _Response(409)
                if self.record is None:
                    self.record = {
                        **json["record"], "namespace": json["namespace"],
                        "identity": json["identity"], "first_retrieved_at": time.time(),
                    }
                self.owner = None
                return _Response(200, dict(self.record))
            if url.endswith("/release"):
                self.owner = "cooldown"
                self.lease_until = time.time() + json["retry_after_s"]
                return _Response(204)
        return _Response(404)


class _Client:
    authority = None

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, url, **kwargs):
        return await self.authority.post(url, **kwargs)


def _produced(payload=b'{"ok":true}'):
    return {
        "payload": payload,
        "final_url": "https://source.test/data",
        "content_type": "application/json",
        "truncated": False,
    }


def test_canonical_identity_is_stable_and_contains_no_credentials():
    first, doc = http.canonical_request_identity(
        "Source", "get",
        "HTTPS://EXAMPLE.test:443/path?b=2&api_key=super-secret&a=1",
        {"z": 1, "password": "body-secret", "nested": {"b": 2, "a": 1}},
        "json", headers={"Authorization": "Bearer hidden"},
    )
    second, _ = http.canonical_request_identity(
        "source", "GET",
        "https://example.test/path?a=1&api_key=super-secret&b=2",
        {"nested": {"a": 1, "b": 2}, "password": "body-secret", "z": 1},
        "json", headers={"Authorization": "Bearer hidden"},
    )
    assert first == second
    encoded = json.dumps(doc)
    assert "super-secret" not in encoded
    assert "body-secret" not in encoded
    assert "Bearer hidden" not in encoded
    assert doc["url"] == "https://example.test/path?a=1&b=2"


def test_credential_scopes_and_contract_versions_are_isolated(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(
        settings, "illuminate_fetch_cache_scope_key", SecretStr("stable-project-key"),
    )
    common = ("sam", "GET", "https://source.test/data?api_key={}", None, "json")
    key_a, _ = http.canonical_request_identity(*(
        common[0], common[1], common[2].format("a"), common[3], common[4],
    ))
    key_b, _ = http.canonical_request_identity(*(
        common[0], common[1], common[2].format("b"), common[3], common[4],
    ))
    version_b, _ = http.canonical_request_identity(
        "sam", "GET", "https://source.test/data?api_key=a", None, "json", contract="v2",
    )
    assert len({key_a, key_b, version_b}) == 3


def test_credential_scope_uses_explicit_project_key_across_sessions(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(
        settings, "illuminate_fetch_cache_scope_key", SecretStr("stable-project-key"),
    )
    first, _ = http.canonical_request_identity(
        "source", "GET", "https://source.test/data?api_key=credential", None, "json",
    )
    monkeypatch.setattr(settings, "session_secret", SecretStr("different-process-key"))
    second, _ = http.canonical_request_identity(
        "source", "GET", "https://source.test/data?api_key=credential", None, "json",
    )
    assert first == second


async def test_concurrent_callers_make_one_upstream_request(monkeypatch):
    authority = _Authority()
    _Client.authority = authority
    monkeypatch.setattr(http.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", "https://cache.test")
    monkeypatch.setattr(settings, "illuminate_fetch_cache_wait_s", 2)
    identity, doc = http.canonical_request_identity(
        "source", "GET", "https://source.test/data", None, "json",
    )
    calls = 0

    async def producer():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return _produced()

    results = await asyncio.gather(*[
        http._shared_fetch(identity, doc, producer) for _ in range(8)
    ])
    assert calls == 1
    assert [hit for _, hit in results].count(False) == 1
    assert all(record["payload"] == b'{"ok":true}' for record, _ in results)

    # A new client/process lifetime still reuses the durable immutable record.
    record, hit = await http._shared_fetch(identity, doc, producer)
    assert hit is True
    assert calls == 1
    assert authority.record["content_hash"] == hashlib.sha256(b'{"ok":true}').hexdigest()


async def test_first_success_is_never_replaced(monkeypatch):
    authority = _Authority()
    _Client.authority = authority
    monkeypatch.setattr(http.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", "https://cache.test")
    identity, doc = http.canonical_request_identity(
        "source", "GET", "https://source.test/data", None, "json",
    )
    first, _ = await http._shared_fetch(identity, doc, lambda: asyncio.sleep(0, result=_produced(b"first")))
    second, hit = await http._shared_fetch(identity, doc, lambda: asyncio.sleep(0, result=_produced(b"changed")))
    assert first["payload"] == second["payload"] == b"first"
    assert hit is True


async def test_malformed_record_and_cache_outage_fail_closed(monkeypatch):
    authority = _Authority()
    identity, doc = http.canonical_request_identity(
        "source", "GET", "https://source.test/data", None, "json",
    )
    authority.record = {
        "identity": identity,
        "payload_b64": base64.b64encode(b"tampered").decode(),
        "content_hash": "wrong",
    }
    _Client.authority = authority
    monkeypatch.setattr(http.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", "https://cache.test")
    called = False

    async def producer():
        nonlocal called
        called = True
        return _produced()

    with pytest.raises(http.HttpError):
        await http._shared_fetch(identity, doc, producer)
    assert called is False

    class _Down(_Client):
        async def post(self, *_args, **_kwargs):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(http.httpx, "AsyncClient", _Down)
    with pytest.raises(http.HttpError):
        await http._shared_fetch(identity, doc, producer)
    assert called is False


async def test_abandoned_lease_can_be_reclaimed(monkeypatch):
    authority = _Authority()
    authority.owner = "dead-process"
    authority.lease_until = time.time() - 1
    _Client.authority = authority
    monkeypatch.setattr(http.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", "https://cache.test")
    identity, doc = http.canonical_request_identity(
        "source", "GET", "https://source.test/data", None, "json",
    )
    record, hit = await http._shared_fetch(
        identity, doc, lambda: asyncio.sleep(0, result=_produced()),
    )
    assert hit is False
    assert record["payload"] == b'{"ok":true}'


async def test_cache_service_fails_closed_without_authentication(monkeypatch):
    monkeypatch.setattr(settings, "illuminate_fetch_cache_authority_enabled", True)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_token", None)
    monkeypatch.setattr(settings, "session_secret", None)
    with pytest.raises(HTTPException) as error:
        await cache_router._authorize(None)
    assert error.value.status_code == 503

    from pydantic import SecretStr
    monkeypatch.setattr(settings, "illuminate_fetch_cache_token", SecretStr("service-secret"))
    with pytest.raises(HTTPException) as error:
        await cache_router._authorize("Bearer wrong")
    assert error.value.status_code == 401
    monkeypatch.setattr(cache_router.fetch_cache, "_schema_ready", True)
    await cache_router._authorize("Bearer service-secret")


async def test_cache_authority_blocks_claims_until_schema_recovers(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "illuminate_fetch_cache_authority_enabled", True)
    monkeypatch.setattr(
        settings, "illuminate_fetch_cache_token", SecretStr("service-secret"),
    )
    monkeypatch.setattr(cache_router.fetch_cache, "_schema_ready", False)
    attempts = 0

    async def initialize():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("store unavailable")
        cache_router.fetch_cache._schema_ready = True

    monkeypatch.setattr(cache_router.fetch_cache, "ensure_schema", initialize)
    with pytest.raises(HTTPException) as error:
        await cache_router._authorize("Bearer service-secret")
    assert error.value.status_code == 503
    await cache_router._authorize("Bearer service-secret")
    assert attempts == 2


def test_cache_storage_requires_managed_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="managed"):
        fetch_cache_db._database_url()


def test_cache_record_rejects_hash_mismatch_oversize_and_secret_url():
    payload = b"safe"
    request = {
        "source": "source", "method": "GET", "url": "https://source.test/data",
        "body": None, "representation": "text", "contract": "test-v1",
        "credential_scope": None,
    }
    request_json = json.dumps(request, sort_keys=True, separators=(",", ":"))
    identity = hashlib.sha256(request_json.encode()).hexdigest()
    base = {
        "source": "source",
        "request": request_json,
        "final_url": "https://source.test/data",
        "content_type": "text/plain",
        "truncated": False,
        "content_hash": hashlib.sha256(payload).hexdigest(),
        "payload_b64": base64.b64encode(payload).decode(),
    }
    assert cache_router.CacheRecord(**base)
    assert cache_router.PublishRequest(
        namespace="test", identity=identity, owner="owner", fence=1, record=base,
    )
    with pytest.raises(ValueError):
        cache_router.PublishRequest(
            namespace="test", identity="0" * 64, owner="owner", fence=1, record=base,
        )
    secret_body = {**request, "body": {"password": "must-not-persist"}}
    secret_json = json.dumps(secret_body, sort_keys=True, separators=(",", ":"))
    with pytest.raises(ValueError):
        cache_router.PublishRequest(
            namespace="test", identity=hashlib.sha256(secret_json.encode()).hexdigest(),
            owner="owner", fence=1, record={**base, "request": secret_json},
        )
    with pytest.raises(ValueError):
        cache_router.CacheRecord(**{**base, "content_hash": "0" * 64})
    with pytest.raises(ValueError):
        cache_router.CacheRecord(**{
            **base, "final_url": "https://source.test/data?api_key=secret",
        })
    with pytest.raises(ValueError):
        cache_router.CacheRecord(**{
            **base, "payload_b64": "A" * (cache_router.MAX_CACHE_PAYLOAD_B64 + 1),
        })


async def test_long_fetch_renews_lease(monkeypatch):
    authority = _Authority()
    _Client.authority = authority
    monkeypatch.setattr(http.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", "https://cache.test")
    monkeypatch.setattr(settings, "illuminate_fetch_cache_lease_s", 1)
    identity, doc = http.canonical_request_identity(
        "source", "GET", "https://source.test/slow", None, "json",
    )

    async def slow_producer():
        await asyncio.sleep(1.1)
        return _produced()

    record, hit = await http._shared_fetch(identity, doc, slow_producer)
    assert hit is False
    assert record["payload"] == b'{"ok":true}'
    assert authority.record is not None


def test_separate_processes_share_one_atomic_first_writer(tmp_path):
    authority = {
        "record": None, "owner": None, "lease_until": 0.0, "fence": 0,
        "lock": threading.Lock(),
    }
    _ProtocolHandler.authority = authority
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ProtocolHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    marker = str(tmp_path / "upstream-calls")
    url = f"http://127.0.0.1:{server.server_port}"
    processes = [
        context.Process(target=_multiprocess_fetch, args=(url, marker, queue))
        for _ in range(4)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        results = [queue.get(timeout=2) for _ in processes]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert (tmp_path / "upstream-calls").read_text().splitlines() == ["upstream"]
    assert [hit for _, hit in results].count(False) == 1
    assert all(payload == b'{"process":"shared"}' for payload, _ in results), results


async def test_required_cache_never_uses_operational_local_file(tmp_path, monkeypatch):
    url = "https://example.test/required"
    http.set_cache_dir(tmp_path)
    path = tmp_path / f"{http._key('GET', url, None)}.json"
    path.write_text(json.dumps({"_ts": time.time(), "body": {"origin": "local"}}))
    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", None)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_required", True)
    with http.retrieval_context("operational_live") as trace:
        with pytest.raises(http.HttpError):
            await http.fetch_json("GET", url)
    assert trace[-1]["source_status"] == "error"


def test_shared_hit_requires_complete_canonical_envelope():
    identity, document = http.canonical_request_identity(
        "source", "GET", "https://source.test/data", None, "json",
    )
    payload = b"{}"
    valid = {
        "namespace": settings.illuminate_fetch_cache_namespace,
        "identity": identity,
        "source": "source",
        "request": json.dumps(document, sort_keys=True, separators=(",", ":")),
        "first_retrieved_at": time.time(),
        "final_url": "https://source.test/data",
        "content_type": "application/json",
        "truncated": False,
        "content_hash": hashlib.sha256(payload).hexdigest(),
        "payload_b64": base64.b64encode(payload).decode(),
    }
    assert http._validate_shared_record(
        valid, identity, document, settings.illuminate_fetch_cache_namespace,
    ) == payload
    for field in ("namespace", "request", "first_retrieved_at", "final_url"):
        malformed = dict(valid)
        malformed.pop(field)
        with pytest.raises(http.HttpError):
            http._validate_shared_record(
                malformed, identity, document, settings.illuminate_fetch_cache_namespace,
            )