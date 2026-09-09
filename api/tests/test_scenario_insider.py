"""The insider thread in the scenario overlay. No test in this module connects to Neo4j."""
from __future__ import annotations

import pytest

from illuminate.seed import seed


@pytest.fixture
def graph(monkeypatch):
    """Record what the scenario writes, and answer its one lookup with a tier-2 vendor."""
    written: dict = {"entities": {}, "rels": [], "writes": [], "people": {}, "claims": []}

    async def read(cypher, params=None):
        if "SUPPLIES {tier:2}" in cypher:
            return [{"id": "ent_vendor", "name": "B3Globalcon LLC"}]
        return []

    async def write(cypher, params=None):
        written["writes"].append((cypher, params or {}))
        if "MERGE (p:Person" in cypher:
            written["people"][params["id"]] = params["p"]
        if "MERGE (c:Claim" in cypher:
            written["claims"].append(params["p"])
        return {"rows": [], "counters": {}}

    async def merge_entity(eid, props):
        written["entities"][eid] = props

    async def merge_rel(src, rel, dst, props, key_props=None):
        written["rels"].append((src, rel, dst, props))

    async def merge_location(code):
        return f"loc_{code}"

    monkeypatch.setattr(seed.db, "read", read)
    monkeypatch.setattr(seed.db, "write", write)
    monkeypatch.setattr(seed, "merge_entity", merge_entity)
    monkeypatch.setattr(seed, "merge_rel", merge_rel)
    monkeypatch.setattr(seed, "merge_location", merge_location)
    monkeypatch.setattr(seed, "log", lambda *a, **k: None)
    return written


def roles(graph) -> list[tuple]:
    return [(s, d, p.get("title")) for s, rel, d, p in graph["rels"] if rel == "HELD_ROLE"]


@pytest.mark.asyncio
async def test_one_person_holds_a_role_at_the_vendor_and_at_the_flagged_group(graph):
    await seed.scenario_insider("ent_program", exclude="ent_other")
    held = roles(graph)
    assert len(held) == 2
    people = {s for s, _, _ in held}
    assert len(people) == 1, "the tie only exists if it is the same person on both edges"
    targets = {d for _, d, _ in held}
    assert "ent_vendor" in targets and len(targets) == 2


@pytest.mark.asyncio
async def test_the_group_is_flagged_and_carries_a_cyber_screen(graph):
    await seed.scenario_insider("ent_program", exclude="ent_other")
    assert any("e.flagged = true" in c for c, _ in graph["writes"])
    group_id = next(iter(graph["entities"]))
    on_group = [c for c in graph["claims"] if c["subject_id"] == group_id]
    predicates = {c["predicate"] for c in on_group}
    assert "cyber_screen" in predicates and "sanctions_screen" in predicates
    assert all(c["object_value"] == "hit" for c in on_group), "the group is the only party that screens as a hit"


@pytest.mark.asyncio
async def test_both_sanctions_lists_are_represented(graph):
    await seed.scenario_insider("ent_program", exclude="ent_other")
    sources = {c["source"] for c in graph["claims"] if c["predicate"] == "sanctions_screen"}
    assert {"OFAC", "UN Security Council"} <= sources


@pytest.mark.asyncio
async def test_the_person_is_screened_and_clear_on_every_list(graph):
    # The person is only a risk by association: their own record is as clean as the
    # vendor's, so the screens ran and every one of them came back clear.
    await seed.scenario_insider("ent_program", exclude="ent_other")
    person_id = next(iter(graph["people"]))
    screens = [c for c in graph["claims"] if c["subject_id"] == person_id and c["predicate"] == "sanctions_screen"]
    assert screens, "the person must be screened, or the report cannot say they came back clear"
    assert {c["object_value"] for c in screens} == {"clear"}
    assert {c["source"] for c in screens} == {"OFAC", "UN Security Council"}, "clear on the same lists that designate the group"


@pytest.mark.asyncio
async def test_the_person_is_never_flagged_directly(graph):
    await seed.scenario_insider("ent_program", exclude="ent_other")
    person_id = next(iter(graph["people"]))
    assert not graph["people"][person_id].get("flagged")
    assert all(person_id not in (params or {}).values() for cypher, params in graph["writes"] if "flagged = true" in cypher)


@pytest.mark.asyncio
async def test_everything_the_thread_writes_is_marked_simulated(graph):
    await seed.scenario_insider("ent_program", exclude="ent_other")
    assert all(p.get("simulated") for p in graph["entities"].values())
    assert all(p.get("simulated") for p in graph["people"].values())
    assert all(p.get("simulated") for _, _, _, p in graph["rels"])
    assert all(c["simulated"] for c in graph["claims"])


@pytest.mark.asyncio
async def test_the_vendor_itself_is_never_flagged_or_screened_as_a_hit(graph):
    # The whole point: the employer's own record stays clean, so the risk is only
    # reachable by going through the person.
    await seed.scenario_insider("ent_program", exclude="ent_other")
    assert "ent_vendor" not in graph["entities"]
    assert all(c["subject_id"] != "ent_vendor" for c in graph["claims"])


@pytest.mark.asyncio
async def test_the_host_of_the_ownership_thread_is_not_reused(graph, monkeypatch):
    captured: dict = {}

    async def read(cypher, params=None):
        captured.update(params or {})
        return []

    monkeypatch.setattr(seed.db, "read", read)
    await seed.scenario_insider("ent_program", exclude="ent_avian")
    assert captured.get("x") == "ent_avian"
    # With no second tier-2 vendor the thread declines to invent one.
    assert not graph["entities"]
