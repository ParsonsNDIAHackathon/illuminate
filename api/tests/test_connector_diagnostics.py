import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from illuminate.connectors.base import diagnostic_failure
from illuminate.connectors.http import HttpError, ProbeResponse
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
        assert request.method == "GET"
        assert request.content == b""
        assert request.headers["range"] == "bytes=0-4095"
        return httpx.Response(200, stream=CountingStream())

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        connector_http.httpx,
        "AsyncClient",
        lambda *args, **kwargs: original_client(*args, transport=httpx.MockTransport(handler), **kwargs),
    )
    response = asyncio.run(connector_http.probe_source("https://source.test/status", max_bytes=4096))
    assert chunks_read == 4
    assert len(response.body) == 4096


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
    success_bodies = {
        "sam": {
            "totalRecords": 1,
            "entityData": [{"entityRegistration": {"ueiSAM": registry._SAM_DIAGNOSTIC_UEI}}],
        },
        "market": {"c": 1, "t": 1},
        "opencorporates": {"results": {"companies": []}},
    }

    async def probe(url, **kwargs):
        calls.append((url, kwargs))
        connector_name = next(
            (name for name, (diagnostic_url, _) in registry._DIAGNOSTICS.items() if diagnostic_url == url),
            None,
        )
        body = success_bodies.get(connector_name, {})
        return ProbeResponse(200, json.dumps(body).encode(), "application/json")

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
        assert options["max_bytes"] == (65536 if connector.name == "sam" else 4096)
        assert options["params"] is None or "$credential" not in options["params"].values()
        if connector.name == "sam":
            assert options["params"]["ueiSAM"] == registry._SAM_DIAGNOSTIC_UEI
            assert "legalBusinessName" not in options["params"]


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("sam", {"message": "API key is not valid"}),
        ("market", {"error": "Invalid API key"}),
        ("opencorporates", {"error": {"message": "Invalid API token"}}),
    ],
)
def test_credentialed_http_connectors_reject_provider_auth_errors(monkeypatch, name, body):
    connector = get_connector(name)
    calls = []

    async def rejected_probe(url, **kwargs):
        calls.append((url, kwargs))
        return ProbeResponse(200, json.dumps(body).encode(), "application/json")

    monkeypatch.setattr(connector_http, "probe_source", rejected_probe)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, key_name: "do-not-expose-this-key")
    result = asyncio.run(connector_router.test_connector(name, "diagnostic-test"))

    assert result == diagnostic_failure("authentication")
    assert len(calls) == 1
    assert calls[0][1]["max_bytes"] == (65536 if name == "sam" else 4096)
    encoded = json.dumps(result)
    assert "do-not-expose-this-key" not in encoded
    assert "Invalid" not in encoded


def test_sam_rejects_nominal_success_with_no_known_entity(monkeypatch):
    connector = get_connector("sam")

    async def empty_probe(url, **kwargs):
        return ProbeResponse(
            200,
            b'{"totalRecords":0,"entityData":[]}',
            "application/json",
        )

    monkeypatch.setattr(connector_http, "probe_source", empty_probe)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, key_name: "bad-key")
    result = asyncio.run(connector_router.test_connector("sam", "diagnostic-test"))
    assert result == diagnostic_failure("authentication")


def test_sam_treats_provider_404_as_rejected_credential(monkeypatch):
    async def rejected_probe(url, **kwargs):
        raise HttpError(404, "https://api.sam.gov/entities?api_key=do-not-expose")

    monkeypatch.setattr(connector_http, "probe_source", rejected_probe)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, key_name: "bad-key")
    result = asyncio.run(connector_router.test_connector("sam", "diagnostic-test"))
    assert result == diagnostic_failure("authentication")


def test_keyless_connector_keeps_404_as_unavailable(monkeypatch):
    connector = get_connector("usaspending")

    async def missing_probe(url, **kwargs):
        raise HttpError(404, "https://api.usaspending.gov/missing")

    monkeypatch.setattr(connector_http, "probe_source", missing_probe)
    result = asyncio.run(connector_router.test_connector(connector.name, "diagnostic-test"))
    assert result == diagnostic_failure("unavailable")


@pytest.mark.parametrize(
    ("name", "body"),
    [
        (
            "sam",
            {
                "totalRecords": 1,
                "entityData": [{"entityRegistration": {"ueiSAM": registry._SAM_DIAGNOSTIC_UEI}}],
            },
        ),
        ("market", {"c": 196.25, "d": 1.5, "t": 1788890000}),
        ("opencorporates", {"results": {"companies": []}}),
    ],
)
def test_credentialed_http_connectors_accept_provider_successes(monkeypatch, name, body):
    connector = get_connector(name)

    async def successful_probe(url, **kwargs):
        return ProbeResponse(200, json.dumps(body).encode(), "application/json")

    monkeypatch.setattr(connector_http, "probe_source", successful_probe)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, key_name: "valid-key")
    result = asyncio.run(connector.check_connectivity("diagnostic-test"))
    assert result == {"ok": True, "status": "available", "detail": "Source is available"}


@pytest.mark.parametrize("name", ["openai", "websearch"])
def test_openai_backed_connectors_reject_invalid_keys(monkeypatch, name):
    calls = []

    async def key_rejected(url, **kwargs):
        calls.append((url, kwargs))
        return ProbeResponse(
            200,
            b'{"error":{"code":"invalid_api_key","message":"Incorrect API key: secret"}}',
            "application/json",
        )

    monkeypatch.setattr(registry, "probe_source", key_rejected)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, key_name: "configured")
    result = asyncio.run(connector_router.test_connector(name, "diagnostic-test"))
    assert result == diagnostic_failure("authentication")
    assert len(calls) == 1
    assert calls[0][1]["max_bytes"] == 65536
    assert calls[0][1]["headers"]["Authorization"] == "Bearer configured"
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("sam", b"<html>gateway page</html>"),
        ("market", b'{"unexpected":"response"}'),
        ("opencorporates", b"not-json"),
        ("openai", b'{"error":{"code":"unexpected"}}'),
        ("websearch", b"x" * 4096 + b"incorrect api key"),
    ],
)
def test_credentialed_connectors_do_not_accept_unknown_success_payloads(monkeypatch, name, body):
    async def unknown_probe(url, **kwargs):
        return ProbeResponse(200, body[:4096], "application/json")

    monkeypatch.setattr(connector_http, "probe_source", unknown_probe)
    monkeypatch.setattr(registry, "probe_source", unknown_probe)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, key_name: "configured")
    result = asyncio.run(connector_router.test_connector(name, "diagnostic-test"))
    assert result == diagnostic_failure("unavailable")


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("sam", b'{"totalRecords":0,"entityData":['),
        ("market", b'{"c":1,"t":'),
        ("opencorporates", b'{"results":{"companies":['),
        ("openai", b'{"object":"list","data":['),
        ("websearch", b'{"object":"list","data":['),
    ],
)
def test_credentialed_connectors_reject_truncated_success_envelopes(monkeypatch, name, body):
    async def truncated_probe(url, **kwargs):
        return ProbeResponse(200, body, "application/json")

    monkeypatch.setattr(connector_http, "probe_source", truncated_probe)
    monkeypatch.setattr(registry, "probe_source", truncated_probe)
    monkeypatch.setattr(connector_router.vault(), "get", lambda user, key_name: "configured")
    result = asyncio.run(connector_router.test_connector(name, "diagnostic-test"))
    assert result == diagnostic_failure("unavailable")


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
    body = {
        "object": "list",
        "data": [{"id": "gpt-5"}, {"id": "another-model"}, {"id": "third-model"}, {"id": "fourth-model"}],
    }

    async def key_works(url, **kwargs):
        return ProbeResponse(200, json.dumps(body).encode(), "application/json")

    monkeypatch.setattr(registry, "probe_source", key_works)
    monkeypatch.setattr(registry, "models", lambda user: ("gpt-5", "gpt-5-mini"))
    monkeypatch.setattr(registry.vault(), "get", lambda user, key_name: "configured")
    result = asyncio.run(get_connector("openai").check_connectivity("diagnostic-test"))
    assert result == {
        "ok": True,
        "status": "available",
        "detail": "OpenAI is available",
        "diagnostics": {"models": 4, "strong_available": True, "fast_available": False},
    }


def test_websearch_uses_openai_compatible_diagnostic(monkeypatch):
    body = {"object": "list", "data": [{"id": "shared-model"}]}

    async def key_works(url, **kwargs):
        return ProbeResponse(200, json.dumps(body).encode(), "application/json")

    monkeypatch.setattr(registry, "probe_source", key_works)
    monkeypatch.setattr(registry, "models", lambda user: ("shared-model", "shared-model"))
    monkeypatch.setattr(registry.vault(), "get", lambda user, key_name: "configured")
    result = asyncio.run(get_connector("websearch").check_connectivity("diagnostic-test"))
    assert result["ok"] is True
    assert result["status"] == "available"
    assert result["diagnostics"]["models"] == 1


def test_openai_failures_are_normalized_by_route(monkeypatch):
    connector = get_connector("openai")

    async def check():
        results = []
        for status in (401, 429):
            async def key_fails(url, status=status, **kwargs):
                raise HttpError(status, "https://models.test", "raw-secret")

            monkeypatch.setattr(registry, "probe_source", key_fails)
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