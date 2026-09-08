"""The discover_suppliers tool end to end, minus the network (live Neo4j; skipped
when unreachable). The award search itself is covered by test_program_suppliers;
what matters here is that the tool refuses what it cannot do, writes the search
terms onto the program through the permission gate, and queues the right job."""
import asyncio

import pytest

from illuminate import db
from illuminate.enrichment import worker as worker_mod
from illuminate.tools import handlers
from illuminate.tools.handlers import ToolContext, discover_suppliers

MARK = "discovertest"
PROG = f"ent_{MARK}_program"
ORG = f"ent_{MARK}_company"


async def _reachable() -> bool:
    await db.close_driver()   # the driver is bound to the previous test's event loop
    try:
        await db.read("RETURN 1 AS x")
        return True
    except Exception:
        return False


@pytest.fixture
async def graph(monkeypatch):
    if not await _reachable():
        pytest.skip("neo4j not reachable")
    await db.write("MERGE (e:Entity {id:$id}) SET e.name='Test Program', e.kind='program'", {"id": PROG})
    await db.write("MERGE (e:Entity {id:$id}) SET e.name='Test Company', e.kind='organization'", {"id": ORG})
    queued: list[dict] = []

    async def enqueue(entity_id, connectors=None, user="local", requested_by="ui"):
        queued.append({"entity_id": entity_id, "connectors": connectors})
        return worker_mod.Job(id="job_test", entity_id=entity_id, entity_name="Test Program", connectors=connectors or [])

    monkeypatch.setattr(worker_mod.worker, "enqueue", enqueue)
    yield queued
    await db.write(f"MATCH (n) WHERE n.id CONTAINS '{MARK}' DETACH DELETE n")
    await db.close_driver()


async def call(**kw):
    """Run the tool and approve the permission request it raises."""
    task = asyncio.create_task(discover_suppliers(ToolContext(source="chat"), **kw))
    for _ in range(200):
        await asyncio.sleep(0.01)
        pending = [r for r in handlers.gate.requests.values() if r.status == "pending" and r.tool == "discover_suppliers"]
        if pending:
            await handlers.gate.approve(pending[0].id)
            break
        if task.done():
            break
    return await task


async def test_it_refuses_an_organization(graph):
    res = await discover_suppliers(ToolContext(), entity_id=ORG, keywords=["X"])
    assert not res.ok and "not a program" in res.data["error"]
    assert "enrich_entity" in res.data["hint"], "the model is told where to go instead"
    assert not graph, "and nothing is queued"


async def test_it_refuses_an_unknown_entity(graph):
    assert not (await discover_suppliers(ToolContext(), entity_id="ent_nope", keywords=["X"])).ok


async def test_it_refuses_empty_keywords(graph):
    res = await discover_suppliers(ToolContext(), entity_id=PROG, keywords=["  "])
    assert not res.ok and "keywords are required" in res.data["error"]


async def test_it_saves_the_search_and_queues_the_award_pass(graph):
    res = await call(entity_id=PROG, keywords=["E-2D", " E-2C "], since="2021-01-01", max_subs=0)
    assert res.ok, res.data
    assert res.permission["status"] == "executed"
    assert res.data["search"] == {"keywords": ["E-2D", "E-2C"], "since": "2021-01-01", "until": "2026-09-30",
                                  "agency": "Department of Defense", "max_primes": 20, "max_subs": 0}
    assert graph == [{"entity_id": PROG, "connectors": ["usaspending"]}], "only the award source, not the company screens"
    saved = (await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": PROG}))[0]["e"]
    assert saved["keywords"] == ["E-2D", "E-2C"] and saved["award_since"] == "2021-01-01" and saved["max_subs"] == 0
    assert "award_until" not in saved, "an unset parameter is left to the connector's default"


async def test_an_empty_agency_is_saved_as_search_every_agency(graph):
    res = await call(entity_id=PROG, keywords=["E-2D"], agency="")
    assert res.ok and res.data["search"]["agency"] is None


async def test_the_http_route_reaches_the_same_handler(graph):
    """The UI posts here; a refusal must come back as a 400, not a hang."""
    from fastapi.testclient import TestClient

    from illuminate.main import app

    with TestClient(app) as client:
        r = client.post(f"/api/programs/{ORG}/suppliers", json={"keywords": ["E-2D"]}, headers={"X-User": "local"})
    assert r.status_code == 400 and "not a program" in r.json()["detail"]
