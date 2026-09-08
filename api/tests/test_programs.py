from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from neo4j.exceptions import ConstraintError
import pytest
from pydantic import ValidationError

from illuminate.routers import programs


@pytest.mark.asyncio
async def test_list_programs_filters_and_paginates(monkeypatch):
    calls = []

    async def fake_read(query, params):
        calls.append((query, params))
        return ([{"id": "prog_1", "name": "Radar", "source": "seed"}]
                if "RETURN p.id" in query else [{"total": 1}])

    monkeypatch.setattr(programs.db, "read", fake_read)
    result = await programs.list_programs(q="  Air   Force ", limit=10, offset=20)
    assert result["total"] == 1
    assert result["items"][0]["id"] == "prog_1"
    assert calls[0][1] == {"q": "air force", "q_norm": "air force", "limit": 10, "offset": 20}
    assert "p.kind = 'program'" in calls[0][0]


@pytest.mark.asyncio
async def test_create_program_normalizes_and_persists_manual_provenance(monkeypatch):
    captured = {}
    announced = {}

    async def fake_write(query, params):
        captured.update(query=query, params=params)
        return {"rows": [{"id": params["id"], "name": params["name"], "source": "manual"}]}

    async def fake_announce(ids, **metadata):
        announced.update(ids=ids, metadata=metadata)

    monkeypatch.setattr(programs.db, "write", fake_write)
    monkeypatch.setattr(programs.events, "announce", fake_announce)
    payload = programs.ProgramCreate(name="  Joint   Radar  ", agency="  DoD ", program_code=" JR-1 ")
    result = await programs.create_program(payload, "operator")
    assert result["name"] == "Joint Radar"
    assert captured["params"]["name_norm"] == "joint radar"
    assert captured["params"]["created_by"] == "operator"
    assert captured["params"]["id"].startswith("prog_")
    assert "method: 'user_entered'" in captured["query"]
    assert "program_code_norm: $program_code_norm" in captured["query"]
    assert announced == {
        "ids": [result["id"]],
        "metadata": {"reason": "program:create", "source": "ui"},
    }
    assert "$name" in captured["query"]


@pytest.mark.asyncio
async def test_create_program_rejects_duplicate_without_second_write(monkeypatch):
    calls = 0

    async def fake_write(query, params):
        nonlocal calls
        calls += 1
        return {"rows": []}

    monkeypatch.setattr(programs.db, "write", fake_write)
    with pytest.raises(HTTPException) as exc:
        await programs.create_program(programs.ProgramCreate(name="Existing program"), "local")
    assert exc.value.status_code == 409
    assert calls == 1


def test_create_program_rejects_invalid_payload():
    with pytest.raises(ValidationError):
        programs.ProgramCreate(name=" ")


def test_http_contract_rejects_invalid_payload_before_write(monkeypatch):
    async def should_not_write(*args, **kwargs):
        raise AssertionError("invalid requests must not write")

    monkeypatch.setattr(programs.db, "write", should_not_write)
    app = FastAPI()
    app.include_router(programs.router)
    response = TestClient(app).post("/api/programs", json={"name": " "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_database_uniqueness_conflict_maps_to_duplicate(monkeypatch):
    async def conflict(*args, **kwargs):
        raise ConstraintError("duplicate")

    monkeypatch.setattr(programs.db, "write", conflict)
    with pytest.raises(HTTPException) as exc:
        await programs.create_program(programs.ProgramCreate(name="Concurrent program"), "local")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_program_database_failures_are_actionable(monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(programs.db, "write", broken)
    with pytest.raises(HTTPException) as exc:
        await programs.create_program(programs.ProgramCreate(name="Valid program"), "local")
    assert exc.value.status_code == 503
    assert "No record was created" in exc.value.detail