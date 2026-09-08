"""How many edges a repeated fact makes (live Neo4j; skipped when unreachable).

A connector declares which relationship props identify a *distinct* edge. One
HELD_ROLE per tenure, but one SUPPLIES edge per pair of entities however many
contracts back it — otherwise a program's prime supplier arrives as a bundle of
parallel edges, one per award, and the canvas becomes unreadable.
"""
import pytest

from illuminate import db
from illuminate.connectors.base import Fact, NodeRef
from illuminate.enrichment import claims

MARK = "mergekeystest"
SUP = f"ent_{MARK}_supplier"
PROG = f"ent_{MARK}_program"
PER = f"per_{MARK}_director"


def supplier() -> NodeRef:
    return NodeRef("Entity", SUP, {"name": "Test Supplier", "kind": "organization"})


def program() -> NodeRef:
    return NodeRef("Entity", PROG, {"name": "Test Program", "kind": "program"})


async def _reachable() -> bool:
    await db.close_driver()   # the driver is bound to the previous test's event loop
    try:
        await db.read("RETURN 1 AS x")
        return True
    except Exception:
        return False


@pytest.fixture
async def graph():
    if not await _reachable():
        pytest.skip("neo4j not reachable")
    yield
    await db.write(f"MATCH (n) WHERE n.id CONTAINS '{MARK}' DETACH DELETE n")
    await db.write(f"MATCH (c:Claim) WHERE c.subject_id CONTAINS '{MARK}' OR c.object_id CONTAINS '{MARK}' DETACH DELETE c")
    await db.close_driver()


async def commit(fact: Fact) -> None:
    cid = await claims.stage(fact, source="usaspending", trust="authoritative")
    assert await claims.decide(cid, trust="authoritative") == "committed"


async def edges(rel: str) -> list[dict]:
    return await db.read(f"MATCH (a)-[r:{rel}]->(b) WHERE a.id CONTAINS '{MARK}' RETURN properties(r) AS p")


async def test_two_contracts_make_one_supplies_edge(graph):
    await commit(Fact(supplier(), "SUPPLIES", object=program(), confidence=0.95,
                      props={"tier": 1, "amount": 100.0, "contract_ref": "N001"}))
    await commit(Fact(supplier(), "SUPPLIES", object=program(), confidence=0.95,
                      props={"tier": 1, "amount": 250.0, "contract_ref": "N002"}))
    rows = await edges("SUPPLIES")
    assert len(rows) == 1, "a re-run must update the supply edge, not add a parallel one"
    assert rows[0]["p"]["amount"] == 250.0 and rows[0]["p"]["contract_ref"] == "N002"
    assert rows[0]["p"]["claim_id"].startswith("clm_"), "provenance follows the latest claim"


async def test_declared_merge_keys_still_separate_tenures(graph):
    person = NodeRef("Person", PER, {"name": "Test Director", "name_norm": "test director"})
    for frm, title in (("2018-01-01", "Director"), ("2023-01-01", "Chair")):
        await commit(Fact(person, "HELD_ROLE", object=supplier(), confidence=0.9, merge_keys=["from", "title"],
                          props={"title": title, "role_type": "board", "from": frm, "current": frm > "2020"}))
    rows = await edges("HELD_ROLE")
    assert len(rows) == 2, "one edge per tenure, as the connector declared"
    assert {r["p"]["title"] for r in rows} == {"Director", "Chair"}


async def test_a_claim_predating_merge_keys_keeps_the_legacy_keying(graph):
    """Claims staged before the field existed have no merge_keys; SUPPLIES then keyed
    on contract_ref. Those rows must not suddenly collapse into one edge."""
    await commit(Fact(supplier(), "SUPPLIES", object=program(), confidence=0.95, props={"tier": 1, "contract_ref": "N001"}))
    await db.write("MATCH (c:Claim) WHERE c.subject_id = $s REMOVE c.merge_keys", {"s": SUP})
    rows = await db.read("MATCH (c:Claim) WHERE c.subject_id = $s RETURN c.id AS id", {"s": SUP})
    await db.write("MATCH (c:Claim {id:$id}) SET c.status='staged'", {"id": rows[0]["id"]})
    await claims.commit(rows[0]["id"])
    assert len(await edges("SUPPLIES")) == 1
