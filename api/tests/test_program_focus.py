"""Focusing the canvas on one program shows that program's supply chain and nothing else.

Programs share suppliers, so an unconfined walk crosses from one program into another
through a shared supplier and the single-program view quietly becomes the whole graph.
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from illuminate import db, events
from illuminate.cypher.templates import MAX_DEPTH, TEMPLATES
from illuminate.cypher.validator import validate
from illuminate.graphio import subgraph_from_graph
from illuminate.tools.permissions import PermissionGate


def test_neighbourhood_confines_the_walk_only_when_a_program_is_given():
    t = TEMPLATES["neighbourhood"]
    open_cy, open_params = t.build({"entity_id": "ent_x", "depth": 2})
    assert "blacklistNodes" not in open_cy
    assert "program" not in open_params

    confined_cy, confined_params = t.build({"entity_id": "ent_x", "depth": 2, "program_id": "ent_x"})
    assert "relationshipFilter:'<SUPPLIES'" in confined_cy
    assert "whitelistNodes:allowed" in confined_cy
    assert confined_params["program"] == "ent_x"
    assert validate(confined_cy, params=confined_params).classification == "READ"


def test_focused_membership_depth_is_independent_of_local_expansion_depth():
    cypher, params = TEMPLATES["neighbourhood"].build({
        "entity_id": "ent_prime",
        "program_id": "ent_program",
        "depth": 1,
    })

    assert (
        f"maxLevel:{MAX_DEPTH}, relationshipFilter:'<SUPPLIES', limit:$membership_limit"
        in cypher
    )
    assert "maxLevel:1, relationshipFilter:'SUPPLIES|OWNS|ULTIMATE_PARENT_OF|" in cypher
    assert params["membership_limit"] > params["limit"]


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

    metadata = next(
        params for query, params in writes
        if "SeedMetadata" in query and "m.root_id=$root_id" in query
    )
    assert metadata["root_id"] == "program-a"
    assert metadata["status"] == "complete"


async def test_focused_neighbourhood_does_not_cross_a_shared_country():
    await db.close_driver()
    try:
        await db.read("RETURN 1 AS x")
    except Exception:
        pytest.skip("neo4j not reachable")

    ids = ["ent_focus_a", "ent_focus_b", "ent_supplier_a", "ent_supplier_b", "loc_focus_shared"]
    try:
        await db.write(
            """
            MERGE (a:Entity {id:'ent_focus_a'}) SET a.name='Focus A', a.kind='program'
            MERGE (b:Entity {id:'ent_focus_b'}) SET b.name='Focus B', b.kind='program'
            MERGE (sa:Entity {id:'ent_supplier_a'}) SET sa.name='Supplier A', sa.kind='organization'
            MERGE (sb:Entity {id:'ent_supplier_b'}) SET sb.name='Supplier B', sb.kind='organization'
            MERGE (country:Location {id:'loc_focus_shared'}) SET country.name='Shared Country'
            MERGE (sa)-[ra:SUPPLIES]->(a) SET ra.id='rel_focus_supply_a'
            MERGE (sb)-[rb:SUPPLIES]->(b) SET rb.id='rel_focus_supply_b'
            MERGE (sa)-[rca:INCORPORATED_IN]->(country) SET rca.id='rel_focus_country_a'
            MERGE (sb)-[rcb:INCORPORATED_IN]->(country) SET rcb.id='rel_focus_country_b'
            """
        )
        cypher, params = TEMPLATES["neighbourhood"].build({
            "entity_id": "ent_focus_a",
            "program_id": "ent_focus_a",
            "depth": 3,
            "layers": {"people": False, "countries": True},
        })
        _, graph, _ = await db.read_graph(cypher, params)
        subgraph = subgraph_from_graph(graph)
        visible = {node["id"] for node in subgraph["nodes"]}
        assert {"ent_focus_a", "ent_supplier_a", "loc_focus_shared"} <= visible
        assert "ent_focus_b" not in visible
        assert "ent_supplier_b" not in visible
    finally:
        await db.write("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", {"ids": ids})
        await db.close_driver()


async def test_focused_local_expansion_can_reach_deeper_program_suppliers():
    await db.close_driver()
    try:
        await db.read("RETURN 1 AS x")
    except Exception:
        pytest.skip("neo4j not reachable")

    ids = [
        "ent_expand_program",
        "ent_expand_prime",
        "ent_expand_tier2",
        "ent_expand_tier3",
    ]
    try:
        await db.write(
            """
            MERGE (program:Entity {id:'ent_expand_program'})
              SET program.name='Expansion Program', program.kind='program'
            MERGE (prime:Entity {id:'ent_expand_prime'})
              SET prime.name='Expansion Prime', prime.kind='organization'
            MERGE (tier2:Entity {id:'ent_expand_tier2'})
              SET tier2.name='Expansion Tier 2', tier2.kind='organization'
            MERGE (tier3:Entity {id:'ent_expand_tier3'})
              SET tier3.name='Expansion Tier 3', tier3.kind='organization'
            MERGE (prime)-[r1:SUPPLIES]->(program) SET r1.id='rel_expand_prime'
            MERGE (tier2)-[r2:SUPPLIES]->(prime) SET r2.id='rel_expand_tier2'
            MERGE (tier3)-[r3:SUPPLIES]->(tier2) SET r3.id='rel_expand_tier3'
            """
        )

        async def visible_from(entity_id):
            cypher, params = TEMPLATES["neighbourhood"].build({
                "entity_id": entity_id,
                "program_id": "ent_expand_program",
                "depth": 1,
                "layers": {"people": False},
            })
            _, graph, _ = await db.read_graph(cypher, params)
            return {node["id"] for node in subgraph_from_graph(graph)["nodes"]}

        assert {
            "ent_expand_program",
            "ent_expand_prime",
            "ent_expand_tier2",
        } <= await visible_from("ent_expand_prime")
        assert {
            "ent_expand_prime",
            "ent_expand_tier2",
            "ent_expand_tier3",
        } <= await visible_from("ent_expand_tier2")
    finally:
        await db.write("MATCH (n) WHERE n.id IN $ids DETACH DELETE n", {"ids": ids})
        await db.close_driver()
