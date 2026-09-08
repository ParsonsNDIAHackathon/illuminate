"""Focusing the canvas on one program shows that program's supply chain and nothing else.

Programs share suppliers, so an unconfined walk crosses from one program into another
through a shared supplier and the single-program view quietly becomes the whole graph.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from illuminate import db, events
from illuminate.cypher.templates import TEMPLATES
from illuminate.cypher.validator import validate
from illuminate.tools.permissions import PermissionGate


def test_neighbourhood_confines_the_walk_only_when_a_program_is_given():
    t = TEMPLATES["neighbourhood"]
    open_cy, open_params = t.build({"entity_id": "ent_x", "depth": 2})
    assert "blacklistNodes" not in open_cy
    assert "program" not in open_params

    confined_cy, confined_params = t.build({"entity_id": "ent_x", "depth": 2, "program_id": "ent_x"})
    assert "blacklistNodes:blocked" in confined_cy
    assert confined_params["program"] == "ent_x"
    assert validate(confined_cy, params=confined_params).classification == "READ"


@pytest.fixture
def client():
    from illuminate.main import app
    with TestClient(app) as c:
        if not c.get("/api/health").json().get("neo4j"):
            pytest.skip("neo4j not reachable")
        yield c


def _programs(client) -> list[dict]:
    return client.get("/api/graph/programs").json()["items"]


def test_programs_endpoint_lists_what_the_picker_offers(client):
    items = _programs(client)
    assert all(set(p) == {"id", "name"} for p in items)
    assert items == sorted(items, key=lambda p: p["name"])
    kinds = {client.get(f"/api/graph/node/{p['id']}").json()["props"].get("kind") for p in items}
    assert kinds <= {"program"}


def test_focused_subgraph_leaves_the_other_programs_out(client):
    programs = _programs(client)
    if len(programs) < 2:
        pytest.skip("needs more than one program to prove the walk does not cross over")
    me, other = programs[0]["id"], programs[1]["id"]

    confined = client.get(f"/api/graph/subgraph?entity_id={me}&depth=3&program_id={me}").json()["subgraph"]
    ids = {n["id"] for n in confined["nodes"]}
    assert me in ids
    assert other not in ids, "another program must not be reachable through a shared supplier"
    assert all(e["source"] in ids and e["target"] in ids for e in confined["edges"])

    # …and without the confinement it is: otherwise this test proves nothing.
    open_sub = client.get(f"/api/graph/subgraph?entity_id={me}&depth=3").json()["subgraph"]
    open_ids = {n["id"] for n in open_sub["nodes"]}
    if other not in open_ids:
        pytest.skip("these two programs share no supplier within the depth, nothing to confine")
    assert ids < open_ids


PROG_ID = "ent_testfocusprog"


async def test_a_new_program_is_announced_with_the_kind_the_picker_reads():
    """The focus picker is kept current from graph deltas rather than a reload, so a
    program created anywhere has to arrive in the delta recognisable as a program."""
    await db.close_driver()  # the driver is bound to the previous test's event loop
    try:
        await db.read("RETURN 1 AS x")
    except Exception:
        pytest.skip("neo4j not reachable")

    seen: list[dict] = []

    async def listener(ev, payload):
        if ev == "graph_delta":
            seen.append(payload)

    events.add_listener(listener)
    try:
        v = validate("MERGE (e:Entity {id:$id}) ON CREATE SET e.name=$n, e.kind='program' RETURN e.id AS id")
        d = await PermissionGate().request(v, {"id": PROG_ID, "n": "Test Focus Program"}, source="test", tool="propose_entity", mode="auto_create")
        assert d.status == "executed"
        nodes = [n for p in seen for n in p["subgraph"]["nodes"] if n["id"] == PROG_ID]
        assert nodes, "the new program was never announced"
        assert nodes[0]["label"] == "Entity" and nodes[0]["props"]["kind"] == "program"
        assert nodes[0]["name"] == "Test Focus Program"
        assert PROG_ID in {p["id"] for p in await db.read("MATCH (e:Entity) WHERE e.kind='program' RETURN e.id AS id")}
    finally:
        events.remove_listener(listener)
        await db.write("MATCH (e:Entity {id:$id}) DETACH DELETE e", {"id": PROG_ID})
        await db.close_driver()


def test_workspace_holds_no_consumer(client):
    ws = client.get("/api/workspace").json()
    assert "root_id" not in ws and "root_label" not in ws
    # a stale root in a saved workspace file is ignored rather than resurrected
    saved = client.put("/api/workspace", json={**{k: v for k, v in ws.items() if k != "defaults"}, "root_id": "ent_x"}).json()
    assert "root_id" not in saved


async def test_seed_entry_completes_without_mutating_workspace_consumer(monkeypatch):
    from illuminate.seed import seed

    async def noop(*_args, **_kwargs):
        return None

    async def seed_program(*_args, **_kwargs):
        return {
            "root_id": "program-a",
            "root_name": "Program A",
            "primes": 1,
            "subs": 1,
        }

    writes = []

    async def write(query, params=None):
        writes.append((query, params))

    async def read(*_args, **_kwargs):
        return []

    monkeypatch.setattr(seed, "set_cache_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(seed, "ensure_schema", noop)
    monkeypatch.setattr(seed, "seed_catalog_lineage", noop)
    monkeypatch.setattr(seed, "seed_program", seed_program)
    monkeypatch.setattr(seed, "seed_cached_gdelt", noop)
    monkeypatch.setattr(seed, "stats", lambda: noop())
    monkeypatch.setattr(seed.db, "read", read)
    monkeypatch.setattr(seed.db, "write", write)
    monkeypatch.setattr(seed.db, "close_driver", noop)

    args = SimpleNamespace(
        offline=True,
        reset=False,
        keyword=["V-22"],
        root_name="Program A",
        since="2025-01-01",
        until="2026-01-01",
        primes=1,
        subs=1,
        agency="Department of Defense",
        people=1,
        skip_enrich=True,
        scenario=False,
    )

    await seed.main_async(args)

    metadata = next(params for query, params in writes if "SeedMetadata" in query)
    assert metadata["root_id"] == "program-a"
    assert metadata["status"] == "complete"
