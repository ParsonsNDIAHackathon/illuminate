"""Ultimate ownership is walked, not stated. No test in this module connects to Neo4j."""
from __future__ import annotations

import pytest

from illuminate import db
from illuminate.report import ULTIMATE_PARENT_DEPTH, risk_indicators, ultimate_parents


def row(**over):
    base = {
        "id": "ent_zhejiang",
        "name": "Zhejiang Provincial Metals Group",
        "simulated": False,
        "hops": 2,
        "relationship_ids": ["rel_zj_owns_hk", "rel_hk_owns_ning"],
        "chain": ["Zhejiang Provincial Metals Group", "Pacific Alloy Holdings", "Ningbo Precision Castings"],
        "relationship_id": "rel_zj_owns_hk",
        "relationship_simulated": False,
        "claim_id": None,
        "source": "scenario",
        "source_url": None,
    }
    return {**base, **over}


def reader(rows, sink=None):
    async def read(cypher, params):
        if sink is not None:
            sink.append((cypher, params))
        return rows
    return read


@pytest.mark.asyncio
async def test_the_walk_climbs_owns_and_stops_at_an_owner_nobody_owns(monkeypatch):
    calls: list = []
    monkeypatch.setattr(db, "read", reader([row()], calls))
    await ultimate_parents("ent_ningbo")
    cypher, params = calls[0]
    assert params == {"id": "ent_ningbo", "include_simulated": False}
    # It is the traversal that finds the parent, not an edge that names one.
    assert f"[:OWNS|ULTIMATE_PARENT_OF*1..{ULTIMATE_PARENT_DEPTH}]" in cypher
    assert "MATCH (owner:Entity)-[incoming:OWNS|ULTIMATE_PARENT_OF]->(up)" in cypher
    path_policy = cypher.split("WITH up, path", 1)[0]
    assert "all(n IN nodes(path)" in path_policy
    assert "all(h IN relationships(path)" in path_policy
    assert "MATCH (hc:Claim {id:h.claim_id})" in path_policy
    assert "MATCH (ha:Artifact)-[:EVIDENCES]->(hc)" in path_policy
    assert "MATCH (:Artifact)-[he:EVIDENCES]->(hc)" in path_policy
    assert path_policy.index("$include_simulated") < cypher.index("ORDER BY length(path)")


@pytest.mark.asyncio
async def test_a_multi_hop_parent_is_reported_as_derived_and_names_the_intermediaries(monkeypatch):
    monkeypatch.setattr(db, "read", reader([row()]))
    found = await ultimate_parents("ent_ningbo")
    assert [p["name"] for p in found] == ["Zhejiang Provincial Metals Group"]
    assert found[0]["source"] == "derived: ownership chain via Pacific Alloy Holdings"


@pytest.mark.asyncio
async def test_a_single_stated_hop_keeps_the_source_that_stated_it(monkeypatch):
    monkeypatch.setattr(db, "read", reader([row(
        hops=1, chain=["RTX Corp", "Hamilton Sundstrand"], relationship_ids=["rel_owns"], source="GLEIF",
    )]))
    found = await ultimate_parents("ent_hamilton")
    assert found[0]["source"] == "GLEIF"


@pytest.mark.asyncio
async def test_simulation_propagates_down_a_derived_chain(monkeypatch):
    monkeypatch.setattr(db, "read", reader([row(simulated=False, relationship_simulated=True)]))
    found = await ultimate_parents("ent_ningbo")
    assert found[0]["simulated"] is True
    assert found[0]["relationship_simulated"] is True


@pytest.mark.asyncio
async def test_rows_without_a_parent_are_dropped(monkeypatch):
    monkeypatch.setattr(db, "read", reader([{"id": None, "name": None, "hops": 0, "chain": [], "relationship_ids": []}]))
    assert await ultimate_parents("ent_orphan") == []


@pytest.mark.asyncio
async def test_the_ownership_finding_highlights_every_hop_of_the_chain():
    core = {
        "e": {"id": "ent_ningbo", "name": "Ningbo Precision Castings"},
        "parent_seat": {"code": "CN", "id": "loc_cn", "relationship_id": "rel_seat"},
        "parent_seat_evidence": [],
        "ultimate_parents": [row()],
    }
    result = await risk_indicators(
        "ent_ningbo", core,
        {"supplies": [], "sole_source": []},
        {"current": [], "former": []},
        [],
    )
    ownership = next(i for i in result["indicators"] if i["family"] == "ownership")
    assert ownership["severity"] == "high"
    # Both OWNS hops travel with the finding, so the whole path can light up on the canvas.
    assert "rel_zj_owns_hk" in ownership["element_ids"]
    assert "rel_hk_owns_ning" in ownership["element_ids"]
