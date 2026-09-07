"""Integration test against a live Neo4j (skipped when unreachable)."""
import asyncio

import pytest

from illuminate import db
from illuminate.cypher.validator import validate
from illuminate.tools.permissions import PermissionGate


async def _reachable():
    await db.close_driver()  # driver is bound to the previous test's event loop
    try:
        await db.read("RETURN 1 AS x")
        return True
    except Exception:
        return False


@pytest.fixture
async def gate():
    if not await _reachable():
        pytest.skip("neo4j not reachable")
    g = PermissionGate()
    yield g
    await db.write("MATCH (e:Entity) WHERE e.id STARTS WITH 'test_' DETACH DELETE e")
    await db.close_driver()


async def test_write_waits_then_executes_on_approve(gate):
    v = validate("MERGE (e:Entity {id:$id}) ON CREATE SET e.name=$n RETURN e.id")
    events = []

    async def listener(ev, payload):
        events.append((ev, payload))

    gate.add_listener(listener)
    task = asyncio.create_task(gate.request(v, {"id": "test_1", "n": "Test One"}, source="test", mode="ask_always"))
    await asyncio.sleep(0.3)
    assert events and events[0][0] == "permission_request"
    req = events[0][1]
    assert req["preview"]["counters"]["nodes_created"] == 1
    # nothing committed yet
    assert (await db.read("MATCH (e:Entity {id:'test_1'}) RETURN count(e) AS n"))[0]["n"] == 0
    d = await gate.approve(req["id"])
    assert d.status == "executed"
    assert (await task).status == "executed"
    assert (await db.read("MATCH (e:Entity {id:'test_1'}) RETURN count(e) AS n"))[0]["n"] == 1


async def test_refuse_returns_to_caller(gate):
    v = validate("CREATE (e:Entity {id:'test_2', name:'x'})")
    task = asyncio.create_task(gate.request(v, {}, source="test", mode="ask_always"))
    await asyncio.sleep(0.3)
    pid = gate.pending()[0].id
    await gate.refuse(pid, "no thanks")
    d = await task
    assert d.status == "refused" and "no thanks" in d.reason
    assert (await db.read("MATCH (e:Entity {id:'test_2'}) RETURN count(e) AS n"))[0]["n"] == 0


async def test_auto_create_mode(gate):
    v = validate("MERGE (e:Entity {id:$id}) ON CREATE SET e.name=$n")
    d = await gate.request(v, {"id": "test_3", "n": "Auto"}, source="test", mode="auto_create")
    assert d.status == "executed"
    v2 = validate("MATCH (e:Entity {id:$id}) SET e.name='changed'")
    task = asyncio.create_task(gate.request(v2, {"id": "test_3"}, source="test", mode="auto_create"))
    await asyncio.sleep(0.3)
    assert gate.pending(), "modify must still ask in auto_create mode"
    await gate.refuse(gate.pending()[0].id)
    await task


async def test_destructive_requires_acknowledged_count(gate):
    await db.write("CREATE (e:Entity {id:'test_4', name:'x'})")
    v = validate("MATCH (e:Entity {id:'test_4'}) DETACH DELETE e")
    assert v.classification == "DESTRUCTIVE"
    task = asyncio.create_task(gate.request(v, {}, source="test", mode="auto_create"))
    await asyncio.sleep(0.3)
    pid = gate.pending()[0].id
    d = await gate.approve(pid)  # no acknowledgement
    assert d.status == "pending" and "acknowledge" in d.reason
    d = await gate.approve(pid, acknowledge_count=1)
    assert d.status == "executed"
    assert (await task).status == "executed"


async def test_session_allowlist(gate):
    v = validate("MERGE (e:Entity {id:$id}) SET e.name=$n")
    task = asyncio.create_task(gate.request(v, {"id": "test_5", "n": "a"}, source="test", mode="session_allowlist"))
    await asyncio.sleep(0.3)
    await gate.approve(gate.pending()[0].id, remember_shape=True)
    await task
    d = await gate.request(v, {"id": "test_6", "n": "b"}, source="test", mode="session_allowlist")
    assert d.status == "executed" and "auto-approved" in gate.requests[d.request_id].decision_note
