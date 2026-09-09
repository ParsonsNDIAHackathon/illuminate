"""Focusing the canvas on one program shows that program's supply chain and nothing else.

Programs share suppliers, so an unconfined walk crosses from one program into another
through a shared supplier and the single-program view quietly becomes the whole graph.
"""
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

    # The risk sweep rides with the confinement: a focused program keeps its scored nodes whatever
    # the depth, while expanding a bare entity stays where the user pointed.
    assert "shortestPath" not in open_cy

    confined_cy, confined_params = t.build({"entity_id": "ent_x", "depth": 2, "program_id": "ent_x"})
    assert "blacklistNodes:blocked" in confined_cy
    assert confined_params["program"] == "ent_x"
    assert "shortestPath" in confined_cy and confined_params["risk_floor"] > 0
    # Ownership is walked upwards in a program view — the owner of a supplier, not that owner's
    # other subsidiaries — while SUPPLIES stays two-way and the sweep's own path is undirected.
    assert "<OWNS" in confined_cy and "<ULTIMATE_PARENT_OF" in confined_cy
    assert "<SUPPLIES" not in confined_cy and "<OWNS" not in open_cy
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


def test_a_focused_program_carries_its_risky_nodes_past_the_depth(client):
    """Depth says how much context to draw, not which findings are out of sight. Around the
    V-22 program at depth 2 the director scored 100 is three hops out and the metals group
    five; both belong to that chain and both have to arrive, people layer or no people layer."""
    from illuminate.config import RISK_PIN_FLOOR
    me, scored = None, set()
    for p in _programs(client):
        reach = client.get(f"/api/graph/subgraph?entity_id={p['id']}&depth=6&program_id={p['id']}").json()["subgraph"]
        found = {n["id"] for n in reach["nodes"] if (n["props"].get("risk_score") or 0) > RISK_PIN_FLOOR}
        if found:
            me, scored = p["id"], found
            break
    if not me:
        pytest.skip("no program's chain has anything scored over the pin floor")

    for people in ("true", "false"):
        sub = client.get(f"/api/graph/subgraph?entity_id={me}&depth=1&program_id={me}&people={people}").json()["subgraph"]
        ids = {n["id"] for n in sub["nodes"]}
        assert scored <= ids, f"a scored node was left outside the depth with people={people}"
        # Each one arrives on a path, not as a lone dot the canvas cannot place.
        joined = {e["source"] for e in sub["edges"]} | {e["target"] for e in sub["edges"]}
        assert scored <= joined


async def test_a_focused_program_leaves_the_sister_companies_out():
    """An OWNS edge earns its place by pointing at the chain. The owner of a supplier controls a
    company on the contract; that owner's other subsidiaries say nothing about the program, and
    RAYTHEON COMPANY alone brings a dozen of them. Risky ones are the exception — the sweep fetches
    those and the canvas pins them."""
    from illuminate.config import RISK_PIN_FLOOR
    from illuminate.graphio import subgraph_from_graph
    await db.close_driver()
    try:
        await db.read("RETURN 1 AS x")
    except Exception:
        pytest.skip("neo4j not reachable")
    try:
        programs = await db.read("MATCH (p:Entity {kind:'program'}) RETURN p.id AS id ORDER BY p.name")
        t = TEMPLATES["neighbourhood"]
        for prog in programs:
            cy, bound = t.build({"entity_id": prog["id"], "depth": 2, "program_id": prog["id"]})
            _, graph, _ = await db.read_graph(validate(cy, params=bound).statement, bound)
            ids = list(subgraph_from_graph(graph)["nodes"])
            siblings = await db.read(
                "MATCH (owner:Entity)-[:OWNS|ULTIMATE_PARENT_OF]->(child:Entity) "
                "WHERE owner.id IN $ids AND NOT (child)-[:SUPPLIES]->() "
                "AND coalesce(child.risk_score, 0) <= $floor "
                "RETURN DISTINCT child.id AS id, child.name AS name",
                {"ids": ids, "floor": RISK_PIN_FLOOR},
            )
            drawn = [s["name"] for s in siblings if s["id"] in ids]
            assert not drawn, f"sister companies on the {prog['id']} canvas: {drawn}"
    finally:
        await db.close_driver()


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
