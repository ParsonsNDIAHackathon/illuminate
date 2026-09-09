"""The graph changes without a reload: every committed write announces what it
touched, and the canvas loads the whole graph rather than one consumer's chain."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from illuminate import db, events
from illuminate.cypher.validator import validate
from illuminate.tools.permissions import PermissionGate

TEST_ID = "ent_testlive1"
OTHER_ID = "ent_testlive2"


def test_node_ids_finds_ids_at_any_depth():
    found = events.node_ids({"id": "ent_abc123", "nested": [{"to_id": "per_9f0"}, "rel_notanode", "plain"], "n": 3})
    assert found == ["ent_abc123", "per_9f0"]
    assert events.node_ids({"x": None}, [], "") == []


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
    await db.write("MATCH (e:Entity) WHERE e.id STARTS WITH 'ent_testlive' DETACH DELETE e")
    await db.close_driver()


async def test_approved_write_announces_what_it_touched(gate):
    """A new entity with nothing attached to it yet still has to reach the canvas —
    that is the case the old root-neighbourhood view silently dropped."""
    seen = []

    async def listener(ev, payload):
        seen.append((ev, payload))

    events.add_listener(listener)
    try:
        v = validate("MERGE (e:Entity {id:$id}) ON CREATE SET e.name=$n RETURN e.id AS id")
        d = await gate.request(v, {"id": TEST_ID, "n": "Live Test Program"}, source="test", tool="propose_entity", mode="auto_create")
        assert d.status == "executed"
        await asyncio.sleep(0)
        deltas = [p for e, p in seen if e == "graph_delta"]
        assert deltas, "an approved write announces a graph delta"
        delta = deltas[-1]
        assert TEST_ID in delta["focus"]
        assert TEST_ID in [n["id"] for n in delta["subgraph"]["nodes"]]
        assert delta["reason"] == "propose_entity"
    finally:
        events.remove_listener(listener)


async def test_delta_carries_one_hop_of_context(gate):
    """The delta has to arrive attached: a relationship whose other end is missing
    would be dropped by the canvas."""
    await db.write(
        "MERGE (a:Entity {id:$a}) ON CREATE SET a.name='Live A' MERGE (b:Entity {id:$b}) ON CREATE SET b.name='Live B' "
        "MERGE (a)-[r:SUPPLIES]->(b) ON CREATE SET r.id='rel_testlive'",
        {"a": TEST_ID, "b": OTHER_ID},
    )
    sub = await events.delta_for([TEST_ID])
    assert {TEST_ID, OTHER_ID} <= {n["id"] for n in sub["nodes"]}
    assert "rel_testlive" in {e["id"] for e in sub["edges"]}
    assert await events.delta_for([]) == {"nodes": [], "edges": []}


@pytest.fixture
def client():
    from illuminate.main import app
    with TestClient(app) as c:
        if not c.get("/api/health").json().get("neo4j"):
            pytest.skip("neo4j not reachable")
        yield c


def test_graph_all_returns_every_program_not_just_the_root(client):
    programs = client.get("/api/entities?kind=program&limit=100").json()["items"]
    if len(programs) < 2:
        pytest.skip("needs more than one program to prove the graph is not rooted")
    sub = client.get("/api/graph/all").json()["subgraph"]
    ids = {n["id"] for n in sub["nodes"]}
    assert {p["id"] for p in programs} <= ids, "every consumer is on the canvas by default"
    assert all(e["source"] in ids and e["target"] in ids for e in sub["edges"])


def test_graph_all_honours_layers(client):
    """An off layer takes the ordinary people. A person scored over the pin floor is not
    ordinary: the canvas can only pin what it was sent, so those come either way and the
    canvas decides (RISK_PIN_FLOOR, web/src/stores/graphLayers.ts)."""
    from illuminate.config import RISK_PIN_FLOOR
    lean = client.get("/api/graph/all?people=false").json()["subgraph"]
    people = [n for n in lean["nodes"] if n["label"] == "Person"]
    assert all((n["props"].get("risk_score") or 0) > RISK_PIN_FLOOR for n in people), \
        "an off people layer sends only the risky ones"
    full = client.get("/api/graph/all?people=true&artifacts=true").json()["subgraph"]
    assert len(full["nodes"]) >= len(lean["nodes"])
    assert {n["id"] for n in people} <= {n["id"] for n in full["nodes"]}, "the layer only ever adds people"


def test_graph_all_splits_artifacts_sources_and_claims(client):
    from illuminate.schema import SOURCE_KINDS
    every = client.get("/api/graph/all?artifacts=true&sources=true&claims=true").json()["subgraph"]["nodes"]
    for n in every:
        if n["label"] == "Artifact":
            expected = "sources" if (n["props"].get("kind") or "record") in SOURCE_KINDS else "artifacts"
            assert n["layer"] == expected, n["name"]
        elif n["label"] == "Claim":
            assert n["layer"] == "claims"
    only_sources = client.get("/api/graph/all?sources=true").json()["subgraph"]["nodes"]
    assert all(n["layer"] == "sources" for n in only_sources if n["label"] == "Artifact")
    assert not [n for n in only_sources if n["label"] == "Claim"]
    only_claims = client.get("/api/graph/all?claims=true").json()["subgraph"]["nodes"]
    assert not [n for n in only_claims if n["label"] == "Artifact"]
    only_docs = client.get("/api/graph/all?artifacts=true").json()["subgraph"]["nodes"]
    assert all(n["layer"] == "artifacts" for n in only_docs if n["label"] == "Artifact")
    assert not [n for n in only_docs if n["label"] == "Claim"]
