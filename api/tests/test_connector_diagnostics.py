import asyncio
import json

import httpx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from illuminate.connectors.base import diagnostic_failure
from illuminate.connectors.http import HttpError
from illuminate.connectors import http as connector_http
from illuminate.connectors.registry import REGISTRY, get_connector
from illuminate.connectors import registry
from illuminate.routers import connectors as connector_router


def test_every_registry_connector_has_a_connectivity_check():
    assert REGISTRY
    for connector in REGISTRY:
        assert callable(connector.check_connectivity)
        if connector.name not in ("openai", "websearch"):
            assert connector.diagnostic_url


def test_diagnostic_failures_are_small_and_allowlisted():
    for category in ("missing_credentials", "authentication", "rate_limited", "timeout", "unavailable"):
        result = diagnostic_failure(category)
        assert set(result) == {"ok", "status", "detail"}
        assert result["ok"] is False
        assert result["status"] == category


def test_probe_source_streams_at_most_the_byte_limit(monkeypatch):
    chunks_read = 0

    class CountingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal chunks_read
            for _ in range(20):
                chunks_read += 1
                yield b"x" * 1024

    def handler(request):
        assert request.headers["range"] == "bytes=0-4095"
        return httpx.Response(200, stream=CountingStream())

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        connector_http.httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_client(*args, transport=httpx.MockTransport(handler), **kwargs),
    )
    asyncio.run(connector_http.probe_source("https://source.test/status", max_bytes=4096))
    assert chunks_read == 4


def test_probe_source_does_not_read_upstream_error_body(monkeypatch):
    body_read = False

    class ErrorStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal body_read
            body_read = True
            yield b"sensitive raw response"

    def handler(request):
        return httpx.Response(503, stream=ErrorStream())

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        connector_http.httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_client(*args, transport=httpx.MockTransport(handler), **kwargs),
    )
    try:
        asyncio.run(connector_http.probe_source("https://source.test/status"))
        assert False, "expected HttpError"
    except HttpError as error:
        assert error.status == 503
    assert body_read is False


def test_probe_source_does_not_follow_or_read_large_redirects(monkeypatch):
    redirect_body_read = False

    class RedirectStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal redirect_body_read
            redirect_body_read = True
            for _ in range(20):
                yield b"x" * 1024

    def handler(request):
        return httpx.Response(
            302,
            headers={"Location": "https://source.test/final"},
            stream=RedirectStream(),
        )

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        connector_http.httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_client(*args, transport=httpx.MockTransport(handler), **kwargs),
    )
    try:
        asyncio.run(connector_http.probe_source("https://source.test/redirect"))
        assert False, "expected HttpError"
    except HttpError as error:
        assert error.status == 302
    assert redirect_body_read is False


def test_registry_probes_are_single_bounded_reads_and_substitute_keys(monkeypatch):
    calls = []

    async def probe(url, **kwargs):
        calls.append((url, kwargs))

    monkeypatch.setattr(connector_http, "probe_source", probe)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, name: "stored-secret")
    for connector in REGISTRY:
        if connector.name in ("openai", "websearch"):
            continue
        calls.clear()
        result = asyncio.run(connector.check_connectivity("diagnostic-test"))
        assert result["ok"] is True
        assert len(calls) == 1
        _, options = calls[0]
        assert options["timeout"] == 8
        assert options["max_bytes"] == 4096
        assert options["params"] is None or "$credential" not in options["params"].values()


def test_route_handles_unknown_connector():
    app = FastAPI()
    app.include_router(connector_router.router)

    async def check():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/connectors/not-registered/test", headers={"X-User": "diagnostic-test"})
        assert response.status_code == 404
        assert response.json() == {"detail": "unknown connector"}

    asyncio.run(check())


def test_route_enforces_credentials_without_running_probe(monkeypatch):
    connector = get_connector("sam")
    called = False

    async def should_not_run(user):
        nonlocal called
        called = True

    monkeypatch.setattr(connector, "check_connectivity", should_not_run)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, name: None)
    result = asyncio.run(connector_router.test_connector("sam", "diagnostic-test"))
    assert result["status"] == "missing_credentials"
    assert called is False


def test_route_returns_selected_connector_success(monkeypatch):
    connector = get_connector("usaspending")

    async def succeeds(user):
        return {"ok": True, "status": "available", "detail": "Source is available"}

    monkeypatch.setattr(connector, "check_connectivity", succeeds)
    result = asyncio.run(connector_router.test_connector("usaspending", "diagnostic-test"))
    assert result == {"ok": True, "status": "available", "detail": "Source is available"}


def test_openai_diagnostic_preserves_safe_model_availability(monkeypatch):
    async def key_works(user):
        return {"ok": True, "models": 4, "strong_available": True, "fast_available": False}

    monkeypatch.setattr(registry, "check_key", key_works)
    result = asyncio.run(get_connector("openai").check_connectivity("diagnostic-test"))
    assert result == {
        "ok": True,
        "status": "available",
        "detail": "OpenAI is available",
        "diagnostics": {"models": 4, "strong_available": True, "fast_available": False},
    }


def test_websearch_uses_openai_compatible_diagnostic(monkeypatch):
    async def key_works(user):
        return {"ok": True, "models": 1, "strong_available": True, "fast_available": True}

    monkeypatch.setattr(registry, "check_key", key_works)
    result = asyncio.run(get_connector("websearch").check_connectivity("diagnostic-test"))
    assert result["ok"] is True
    assert result["status"] == "available"
    assert result["diagnostics"]["models"] == 1


def test_openai_failures_are_normalized_by_route(monkeypatch):
    connector = get_connector("openai")

    async def check():
        results = []
        for status in (401, 429):
            async def key_fails(user, status=status):
                return {"ok": False, "error": HttpError(status, "https://models.test", "raw-secret")}

            monkeypatch.setattr(registry, "check_key", key_fails)
            monkeypatch.setattr(connector_router.vault(), "get", lambda user, name: "configured")
            results.append(await connector_router.test_connector("openai", "diagnostic-test"))
        return results

    results = asyncio.run(check())
    assert [result["status"] for result in results] == ["authentication", "rate_limited"]
    assert "raw-secret" not in json.dumps(results)


def test_route_sanitizes_auth_quota_timeout_and_upstream_failures(monkeypatch):
    connector = get_connector("usaspending")
    secret = "credential-and-raw-upstream-body"

    async def run(error):
        async def fails(user):
            raise error

        monkeypatch.setattr(connector, "check_connectivity", fails)
        return await connector_router.test_connector("usaspending", "diagnostic-test")

    async def check_all():
        results = []
        for error in (
            HttpError(401, f"https://source.test/?api_key={secret}", secret),
            HttpError(429, "https://source.test/quota", secret),
            asyncio.TimeoutError(secret),
            RuntimeError(secret),
        ):
            results.append(await run(error))
        return results

    results = asyncio.run(check_all())
    assert [result["status"] for result in results] == [
        "authentication", "rate_limited", "timeout", "unavailable",
    ]
    encoded = json.dumps(results)
    assert secret not in encoded
    assert "source.test" not in encoded