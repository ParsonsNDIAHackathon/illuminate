import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from illuminate.main import app
from illuminate.routers import catalog


@pytest.fixture
def catalog_env(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog.settings, "illuminate_data_dir", tmp_path)
    monkeypatch.setattr(catalog.settings, "illuminate_public_url", "https://illuminate.example")
    monkeypatch.setattr(catalog.settings, "ndia_key", None)
    monkeypatch.setattr(catalog.settings, "ndia_catalog_operator_token", SecretStr("operator"))
    monkeypatch.setattr(catalog.settings, "ndia_catalog_contribution_path", "/api/test/contributions")
    monkeypatch.setattr(catalog.settings, "ndia_catalog_lookup_path", "/api/test/by-export/{export_id}/{export_version}")
    monkeypatch.setattr(catalog.settings, "ndia_catalog_status_path", "/api/test/contributions/{dataset_id}")
    monkeypatch.setattr(catalog.exports, "_sync_export_ledger", lambda: _async_value(7))


async def _async_value(value):
    return value


async def test_preview_and_confirmed_dry_run_are_schema_valid(catalog_env):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preview = await client.get("/api/catalog/ndia/preview")
        assert preview.status_code == 200
        body = preview.json()
        assert body["metadata"]["event_id"] == 3
        assert body["event"]["title"] == "NDIA Global Defense Hackathon / Main Event: Washington, DC"
        assert body["metadata"]["api_documentation"].endswith("/api/exports/v1/fields")
        assert body["metadata"]["schema_description"].endswith("/api/exports/v1/schema")
        assert body["schema_valid"] is True
        assert "server-only" not in json.dumps(body)

        missing_confirmation = await client.post("/api/catalog/ndia/submit", json={"dry_run": True})
        assert missing_confirmation.status_code == 422
        stale = await client.post("/api/catalog/ndia/submit", json={
            "confirm": True, "confirmation": "PUBLISH EVENT 3",
            "confirmation_token": "0" * 64, "dry_run": True,
        })
        assert stale.status_code == 409
        result = await client.post("/api/catalog/ndia/submit", json={
            "confirm": True, "confirmation": "PUBLISH EVENT 3",
            "confirmation_token": body["confirmation_token"], "dry_run": True,
        })
        assert result.status_code == 200
        assert result.json()["contribution_state"] == "validated_dry_run"
        assert not (tmp_path := catalog.settings.data_dir / "ndia-catalog.json").exists()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"confirm": False, "confirmation": "PUBLISH EVENT 3", "confirmation_token": "x" * 20},
        {"confirm": True, "confirmation": "publish", "confirmation_token": "x" * 20},
        {"confirm": True, "confirmation": "PUBLISH EVENT 3", "confirmation_token": "short"},
        {
            "confirm": True,
            "confirmation": "PUBLISH EVENT 3",
            "confirmation_token": "x" * 20,
            "unexpected": "server-only",
        },
    ],
)
async def test_malformed_submission_never_reaches_portal(catalog_env, monkeypatch, body):
    calls = []

    async def portal_request(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("malformed input must not reach the portal")

    monkeypatch.setattr(catalog, "_portal_request", portal_request)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/catalog/ndia/submit", json=body)
    assert response.status_code == 422
    assert calls == []
    assert "server-only" not in response.text


async def test_missing_credential_fails_safe(catalog_env):
    preview = await catalog._preview("local")
    with pytest.raises(catalog.HTTPException) as exc:
        await catalog.submit(catalog.SubmitRequest(
            confirm=True, confirmation="PUBLISH EVENT 3",
            confirmation_token=preview.confirmation_token, dry_run=False,
        ), "local", "operator")
    assert exc.value.status_code == 503
    assert "credential" in exc.value.detail
    assert not (catalog.settings.data_dir / "ndia-catalog.json").exists()


async def test_live_submission_requires_operator_authorization(catalog_env, monkeypatch):
    monkeypatch.setattr(catalog.settings, "ndia_key", SecretStr("server-only"))
    preview = await catalog._preview("local")
    request = catalog.SubmitRequest(
        confirm=True, confirmation="PUBLISH EVENT 3",
        confirmation_token=preview.confirmation_token, dry_run=False,
    )
    with pytest.raises(catalog.HTTPException) as exc:
        await catalog.submit(request, "local", None)
    assert exc.value.status_code == 403
    assert not (catalog.settings.data_dir / "ndia-catalog.json").exists()


async def test_submission_records_remote_identity_and_is_idempotent(catalog_env, monkeypatch):
    monkeypatch.setattr(catalog.settings, "ndia_key", SecretStr("server-only"))
    calls = []

    async def request(method, path, *, body=None, idempotency_key=None):
        calls.append((method, path, body))
        if method == "GET":
            return {}
        return {"dataset_id": "ds_123", "message": "Accepted", "status": "pending_review"}

    monkeypatch.setattr(catalog, "_portal_request", request)
    preview = await catalog._preview("local")
    request_body = catalog.SubmitRequest(
        confirm=True, confirmation="PUBLISH EVENT 3",
        confirmation_token=preview.confirmation_token, dry_run=False,
    )
    first = await catalog.submit(request_body, "local", "operator")
    second = await catalog.submit(request_body, "local", "operator")
    assert first.dataset_id == second.dataset_id == "ds_123"
    assert second.idempotent is True
    assert len(calls) == 2
    assert calls[1][2]["event_id"] == 3
    assert "server-only" not in json.dumps(calls)


async def test_status_refresh_and_safe_remote_errors(catalog_env, monkeypatch):
    path = catalog.settings.data_dir / "ndia-catalog.json"
    path.write_text(json.dumps({
        f"illuminate-insight-findings:{catalog.exports.VERSION}": {
            "dataset_id": "ds_123", "contribution_state": "pending_review",
            "message": "Accepted", "submitted_at": "2026-09-08T00:00:00Z",
        }
    }))
    monkeypatch.setattr(catalog.settings, "ndia_key", SecretStr("secret"))

    async def request(method, path, *, body=None, idempotency_key=None):
        return {"dataset_id": "ds_123", "contribution_state": "published", "message": "Published"}

    monkeypatch.setattr(catalog, "_portal_request", request)
    result = await catalog.status(refresh=True)
    assert result.contribution_state == "published"

    response = httpx.Response(403, request=httpx.Request("POST", "https://portal.example"))
    error = catalog._safe_portal_error(httpx.HTTPStatusError("no", request=response.request, response=response))
    assert error.status_code == 502
    assert "403" in error.detail


async def test_uncertain_remote_outcome_blocks_duplicate_retry(catalog_env, monkeypatch):
    monkeypatch.setattr(catalog.settings, "ndia_key", SecretStr("secret"))
    calls = []

    async def request(method, path, *, body=None, idempotency_key=None):
        calls.append(method)
        if method == "GET":
            if len(calls) > 2:
                raise catalog.HTTPException(502, "lookup unavailable")
            return {}
        raise catalog.HTTPException(504, "portal timed out")

    monkeypatch.setattr(catalog, "_portal_request", request)
    preview = await catalog._preview("local")
    body = catalog.SubmitRequest(
        confirm=True, confirmation="PUBLISH EVENT 3",
        confirmation_token=preview.confirmation_token, dry_run=False,
    )
    with pytest.raises(catalog.HTTPException) as first:
        await catalog.submit(body, "local", "operator")
    assert first.value.status_code == 504
    with pytest.raises(catalog.HTTPException) as retry:
        await catalog.submit(body, "local", "operator")
    assert retry.value.status_code == 409
    assert calls.count("POST") == 1