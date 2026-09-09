"""A person has a page of their own, and can be stood on as the root of a neighbourhood.
No test here connects to Neo4j."""
from __future__ import annotations

import pytest

from illuminate import report
from illuminate.cypher.templates import TEMPLATES


def test_a_neighbourhood_can_be_walked_from_a_person_as_well_as_an_entity():
    cy, _ = TEMPLATES["neighbourhood"].build({"entity_id": "per_x", "layers": {}})
    assert "root:Entity OR root:Person" in cy
    focused, _ = TEMPLATES["neighbourhood"].build({"entity_id": "per_x", "layers": {}, "program_id": "ent_prog"})
    assert "root:Entity OR root:Person" in focused
    assert "(root:Entity {id:$id})" not in cy and "(root:Entity {id:$id})" not in focused


def test_screens_and_artifacts_refuse_a_label_that_is_not_a_party():
    with pytest.raises(ValueError):
        report._party("Claim")
    assert report._party("Person") == "Person"


@pytest.fixture
def fake_db(monkeypatch):
    calls: list[tuple[str, dict]] = []

    async def read(cypher, params=None):
        calls.append((cypher, params or {}))
        if "MATCH (p:Person {id:$id})" in cypher:
            if params["id"] != "per_x":
                return []
            return [{
                "person": {"id": "per_x", "name": "R. Ostrowski", "source": "scenario", "simulated": True,
                           "risk_components": "[{}]", "risk_score": 40, "risk_band": "elevated"},
                "roles": [
                    {"edge_id": "rel_1", "rel": "HELD_ROLE", "entity_id": "ent_group", "entity": "Obsidian Lantern", "title": "Named affiliate",
                     "current": True, "from": "2021-08-01", "to": None, "flagged": True, "simulated": True, "risk_score": 69, "risk_band": "high",
                     "supplier": False, "source": "scenario", "source_url": None, "detail": None, "kind": "organization", "role_type": "position", "pct": None, "flag_reason": "designated"},
                    {"edge_id": "rel_2", "rel": "HELD_ROLE", "entity_id": "ent_vendor", "entity": "B3GLOBALCON LLC", "title": "Network Operations Engineer",
                     "current": False, "from": "2019-01-01", "to": "2020-01-01", "flagged": False, "simulated": False, "risk_score": 22, "risk_band": "low",
                     "supplier": True, "source": "littlesis", "source_url": "https://example.test/x", "detail": None, "kind": "organization", "role_type": "position", "pct": None, "flag_reason": None},
                ],
            }]
        if "ENDS WITH '_screen'" in cypher:
            assert "(e:Person {id:$id})" in cypher, "a person's screens are looked up on the Person label"
            return [{"predicate": "sanctions_screen", "result": "clear", "source": "OFAC", "confidence": 0.9,
                     "retrieved_at": "2026-09-09T00:00:00Z", "artifact": None, "detail": "no individual designation matched"}]
        if "[:ABOUT]" in cypher:
            assert "(e:Person {id:$id})" in cypher, "a person's artifacts are looked up on the Person label"
            return []
        return []

    async def explain(node_id):
        return {"id": node_id, "score": 40, "band": "elevated", "confidence": 69, "components": [{"dimension": "proximity"}],
                "note": None, "top_factor": "1 degree of separation from Obsidian Lantern"}

    monkeypatch.setattr(report.db, "read", read)
    monkeypatch.setattr(report.risk, "explain", explain)
    return calls


@pytest.mark.asyncio
async def test_the_person_page_splits_roles_by_tenure_and_carries_the_employers_standing(fake_db):
    rep = await report.build_person_report("per_x")
    assert rep["identity"]["name"] == "R. Ostrowski" and rep["identity"]["simulated"] is True
    assert [r["entity"] for r in rep["current"]] == ["Obsidian Lantern"]
    assert [r["entity"] for r in rep["former"]] == ["B3GLOBALCON LLC"]
    assert rep["current"][0]["flagged"] is True and rep["current"][0]["risk_band"] == "high"
    assert rep["former"][0]["supplier"] is True
    # The stored breakdown arrives once, parsed, under risk — not as the raw JSON string too.
    assert "risk_components" not in rep["person"]
    assert rep["risk"]["components"] == [{"dimension": "proximity"}]
    assert rep["screens"][0]["result"] == "clear"
    assert rep["sources"] == ["littlesis", "scenario"]


@pytest.mark.asyncio
async def test_an_unknown_person_is_none_so_the_route_can_404(fake_db):
    assert await report.build_person_report("per_nobody") is None
