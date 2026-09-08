"""End-to-end supply risk lineage projection against Neo4j when available."""
from datetime import date

import pytest

from illuminate import db
from illuminate.report import evaluate_risk_contract, supply_position


async def _reachable() -> bool:
    await db.close_driver()
    try:
        await db.read("RETURN 1 AS x")
        return True
    except Exception:
        return False


async def test_subaru_style_sole_source_factor_projects_exact_award_lineage():
    if not await _reachable():
        pytest.skip("neo4j not reachable")

    supplier_id = "test_subaru_lineage_supplier"
    program_id = "test_subaru_lineage_v22"
    claim_id = "clm_test_subaru_lineage"
    artifact_id = "art_test_subaru_lineage"
    relationship_id = "rel_test_subaru_lineage"
    award_id = "SJP10A21F0142"
    award_url = (
        "https://www.usaspending.gov/award/"
        "CONT_AWD_SJP10A21F0142_9700_N6264921D0037_9700"
    )
    retrieved_at = "2026-09-01T00:00:00Z"

    await db.write(
        """
        CREATE (supplier:Entity {
          id:$supplier_id, name:'SUBARU CORPORATION', simulated:false
        })
        CREATE (program:Entity {
          id:$program_id, name:'V-22 Osprey Program (PMA-275)',
          kind:'program', simulated:false
        })
        CREATE (claim:Claim {
          id:$claim_id, predicate:'supply_sole_source',
          subject_id:$supplier_id, object_id:$program_id, object_value:true,
          source:'USAspending', source_url:$award_url, method:'connector',
          confidence:0.95, status:'committed', retrieved_at:$retrieved_at,
          simulated:false
        })
        CREATE (artifact:Artifact {
          id:$artifact_id, kind:'award', award_id:$award_id,
          title:'Subaru V-22 customer service award', url:$award_url,
          source:'USAspending', retrieved_at:$retrieved_at, simulated:false
        })
        CREATE (supplier)-[s:SUPPLIES {
          id:$relationship_id, sole_source:true, contract_ref:$award_id,
          source:'USAspending', source_url:$award_url, method:'connector',
          confidence:0.95, status:'committed', retrieved_at:$retrieved_at,
          claim_id:$claim_id, simulated:false
        }]->(program)
        CREATE (claim)-[:ASSERTS]->(supplier)
        CREATE (claim)-[:TARGETS]->(program)
        CREATE (artifact)-[:EVIDENCES {
          source:'USAspending', method:'connector', confidence:0.95,
          retrieved_at:$retrieved_at, simulated:false
        }]->(claim)
        """,
        {
            "supplier_id": supplier_id,
            "program_id": program_id,
            "claim_id": claim_id,
            "artifact_id": artifact_id,
            "relationship_id": relationship_id,
            "award_id": award_id,
            "award_url": award_url,
            "retrieved_at": retrieved_at,
        },
    )
    try:
        supply = await supply_position(supplier_id, program_id)
        risk = evaluate_risk_contract(
            {"e": {"id": supplier_id, "simulated": False}, "parent_seat_evidence": []},
            supply,
            [],
            as_of=date(2026, 9, 8),
        )
        category = next(
            item for item in risk["categories"] if item["id"] == "supply_criticality"
        )
        factor = category["factors"][0]

        assert category["contribution"] == 10
        assert factor["evidence_refs"] == [claim_id, artifact_id, relationship_id]
        assert factor["claim_status"] == "committed"
        assert factor["artifacts"][0]["award_id"] == award_id
        assert factor["artifacts"][0]["url"] == award_url
        assert factor["graph_path"] == {
            "relationship_id": relationship_id,
            "supplier_id": supplier_id,
            "consumer_id": program_id,
        }

        await db.write(
            "MATCH (c:Claim {id:$claim_id})<-[e:EVIDENCES]-(a:Artifact {id:$artifact_id}) "
            "SET c.retrieved_at='2020-01-01T00:00:00Z', "
            "a.retrieved_at='2020-01-01T00:00:00Z', "
            "e.retrieved_at='2020-01-01T00:00:00Z'",
            {"claim_id": claim_id, "artifact_id": artifact_id},
        )
        stale_supply = await supply_position(supplier_id, program_id)
        stale_risk = evaluate_risk_contract(
            {"e": {"id": supplier_id, "simulated": False}, "parent_seat_evidence": []},
            stale_supply,
            [],
            as_of=date(2026, 9, 8),
        )
        stale_category = next(
            item for item in stale_risk["categories"] if item["id"] == "supply_criticality"
        )
        assert stale_category["factors"] == []
        assert stale_category["contribution"] == 0
    finally:
        await db.write(
            "MATCH (n) WHERE n.id IN [$supplier_id,$program_id,$claim_id,$artifact_id] "
            "DETACH DELETE n",
            {
                "supplier_id": supplier_id,
                "program_id": program_id,
                "claim_id": claim_id,
                "artifact_id": artifact_id,
            },
        )
        await db.close_driver()