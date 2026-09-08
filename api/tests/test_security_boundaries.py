from __future__ import annotations

import json
import socket
import time
from types import SimpleNamespace

import httpx as httpx_lib
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from illuminate import main, mcp_server
from illuminate.connectors import http
from illuminate.content import document
from illuminate.mcp_server import AuthenticatedMCP
from illuminate.routers import graph
from illuminate.tools import handlers


async def _echo_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_network_mcp_fails_closed_and_checks_bearer(monkeypatch):
    app = FastAPI()
    app.mount("/", AuthenticatedMCP(_echo_app))

    monkeypatch.setattr("illuminate.mcp_server.settings.illuminate_mcp_http_token", None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/")).status_code == 503

    monkeypatch.setattr(
        "illuminate.mcp_server.settings.illuminate_mcp_http_token",
        SecretStr("test-only-token"),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/")).status_code == 401
        assert (await client.post("/", headers={"Authorization": "Bearer test-only-token"})).status_code == 204


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost/private",
        "http://127.0.0.1/private",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/private",
    ],
)
async def test_document_fetch_rejects_non_public_destinations(url):
    with pytest.raises(http.HttpError):
        await http.ensure_public_http_url(url)


async def _content_endpoint(monkeypatch, url: str):
    async def fake_read(*args, **kwargs):
        return [{"artifact": {"id": "art_security", "url": url, "kind": "document"}}]

    monkeypatch.setattr(graph.db, "read", fake_read)
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        return await client.get("/api/artifacts/art_security/content")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/private",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/private",
])
async def test_content_endpoint_never_probes_blocked_literal(monkeypatch, url):
    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("blocked destination reached the HTTP client")

    monkeypatch.setattr(http.httpx, "AsyncClient", UnexpectedClient)
    response = await _content_endpoint(monkeypatch, url)
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["frameable"] is False


async def test_content_endpoint_never_probes_private_dns_destination(monkeypatch):
    monkeypatch.setattr(
        http.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.30.40", 80)),
        ],
    )

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("private DNS destination reached the HTTP client")

    monkeypatch.setattr(http.httpx, "AsyncClient", UnexpectedClient)
    response = await _content_endpoint(monkeypatch, "http://private-dns.security-test/document")
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["frameable"] is False


async def test_content_endpoint_blocks_public_to_private_redirect(monkeypatch):
    hits: list[str] = []
    real_client = http.httpx.AsyncClient

    monkeypatch.setattr(
        http.socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
        ],
    )

    def respond(request: httpx_lib.Request) -> httpx_lib.Response:
        hits.append(str(request.url))
        return httpx_lib.Response(302, headers={"Location": "http://127.0.0.1/private"})

    transport = httpx_lib.MockTransport(respond)
    monkeypatch.setattr(
        http.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )
    response = await _content_endpoint(
        monkeypatch,
        "http://public.security-test/security-boundary-public-to-private-20260908",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["frameable"] is False
    assert hits == ["http://public.security-test/security-boundary-public-to-private-20260908"]


@pytest.mark.parametrize("cached_url", [
    "http://127.0.0.1/private",
    "not a valid URL",
])
async def test_document_cache_rejects_and_evicts_unsafe_final_url(monkeypatch, tmp_path, cached_url):
    public_url = "http://public-cache.security-test/document"
    key = http._key("GET", public_url, None)
    blob = tmp_path / f"{key}.doc"
    meta = tmp_path / f"{key}.doc.json"
    blob.write_bytes(b"legacy private response")
    meta.write_text(json.dumps({
        "_ts": time.time(),
        "url": cached_url,
        "content_type": "text/plain",
        "truncated": False,
    }))
    monkeypatch.setattr(http, "_cache_dir", tmp_path)
    monkeypatch.setattr(http, "_read_only_cache", False)
    monkeypatch.setattr(
        http.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80)),
        ],
    )

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("unsafe cache entry fell through to a network fetch")

    monkeypatch.setattr(http.httpx, "AsyncClient", UnexpectedClient)
    with pytest.raises(http.HttpError):
        await http.fetch_document(public_url)
    assert not blob.exists()
    assert not meta.exists()


def test_http_errors_remove_credential_query_and_body():
    error = http.HttpError(
        403,
        "https://example.test/data?access_token=secret-value&item=1",
        "credential-bearing upstream body",
    )
    message = str(error)
    assert "secret-value" not in message
    assert "credential-bearing" not in message
    assert "item=1" in message
    assert "user:password" not in str(http.HttpError(0, "https://user:password@example.test/private"))


async def test_discover_suppliers_survives_model_and_mcp_projections(monkeypatch):
    payload = {
        "job_id": "job_1",
        "program": {"id": "program_1", "name": "Program"},
        "search": {"keywords": ["V-22"], "agency": "Navy"},
        "status": "queued",
        "note": "Discovery queued.",
        "raw": {"restricted": "must not pass"},
    }
    result = handlers.ToolResult(ok=True, data=payload)
    model_payload = json.loads(result.for_model("discover_suppliers"))
    assert model_payload["data"] == {key: payload[key] for key in ("job_id", "program", "search", "status", "note")}

    async def fake_dispatch(*args, **kwargs):
        return result

    monkeypatch.setattr(mcp_server, "dispatch", fake_dispatch)
    mcp_result = await mcp_server._call_tool(
        None,
        SimpleNamespace(name="discover_suppliers", arguments={}),
    )
    mcp_payload = json.loads(mcp_result.content[0].text)
    assert mcp_payload["data"] == model_payload["data"]
    assert "restricted" not in mcp_result.content[0].text


async def test_human_evidence_is_staged_after_write_approval(monkeypatch):
    async def approve(*args, **kwargs):
        return SimpleNamespace(
            status="executed",
            request_id="req_test",
            reason=None,
            result={"counters": {}},
        )

    monkeypatch.setattr(handlers.gate, "request", approve)
    result = await handlers.attach_evidence(
        handlers.ToolContext(source="ui"),
        "ent_subject",
        "mention",
        "https://example.test/evidence",
    )
    assert result.ok
    assert result.data["status"] == "staged"
    assert "c.status='staged'" in result.cypher
    assert "c.status='committed'" not in result.cypher


async def test_artifact_detail_uses_raw_only_for_server_side_summary(monkeypatch):
    async def fake_read(*args, **kwargs):
        return [{"artifact": {"id": "art_1", "kind": "record"}, "about": [], "claims": []}]

    monkeypatch.setattr(graph.db, "read", fake_read)
    monkeypatch.setattr(graph, "find_raw", lambda *args: [{"body": {"restricted": "value"}}])
    monkeypatch.setattr(graph, "summarize", lambda artifact, raw: {"shape": "safe"})

    result = await graph.artifact_detail("art_1")
    assert "raw" not in result
    assert result["summary"] == {"shape": "safe"}


async def test_unknown_raw_payload_does_not_survive_real_summary(monkeypatch):
    async def fake_read(*args, **kwargs):
        return [{"artifact": {"id": "art_1", "kind": "record"}, "about": [], "claims": []}]

    marker = "must-remain-server-side"
    monkeypatch.setattr(graph.db, "read", fake_read)
    monkeypatch.setattr(graph, "find_raw", lambda *args: [{"body": {"private": marker}}])
    result = await graph.artifact_detail("art_1")
    assert marker not in str(result)


async def test_claim_list_limits_are_validated_before_database_access():
    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        assert (await client.get("/api/claims", params={"limit": 0})).status_code == 422
        assert (await client.get("/api/claims/source-records", params={"limit": 501})).status_code == 422