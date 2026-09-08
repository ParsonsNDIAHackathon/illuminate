"""Claim decision contention against live Neo4j (skipped when unavailable)."""
import asyncio

import pytest

from illuminate import db
from illuminate.enrichment import claims


async def _reachable():
    await db.close_driver()
    try:
        await db.read("RETURN 1 AS x")
        return True
    except Exception:
        return False


async def test_concurrent_commit_and_reject_keep_status_and_graph_fact_consistent():
    if not await _reachable():
        pytest.skip("neo4j not reachable")
    claim_id = "test_claim_decision_race"
    entity_id = "test_claim_decision_entity"
    await db.write(
        "MERGE (e:Entity {id:$entity_id}) "
        "SET e.name='Decision Race Test' "
        "MERGE (c:Claim {id:$claim_id}) "
        "SET c.status='staged', c.source_status='staged', "
        "c.predicate='attr:flagged', c.object_value='true', "
        "c.source='test', c.rel_props='{}' "
        "MERGE (c)-[:ASSERTS]->(e)",
        {"claim_id": claim_id, "entity_id": entity_id},
    )
    try:
        committed, rejected = await asyncio.gather(
            claims.commit(claim_id),
            claims.reject(claim_id),
            return_exceptions=True,
        )
        rows = await db.read(
            "MATCH (c:Claim {id:$claim_id})-[:ASSERTS]->(e:Entity {id:$entity_id}) "
            "RETURN c.status AS status, coalesce(e.flagged,false) AS flagged",
            {"claim_id": claim_id, "entity_id": entity_id},
        )
        assert len(rows) == 1
        if rows[0]["status"] == "committed":
            assert committed == "committed"
            assert isinstance(rejected, ValueError)
            assert rows[0]["flagged"] is True
        else:
            assert rows[0]["status"] == "rejected"
            assert committed == rejected == "rejected"
            assert rows[0]["flagged"] is False
    finally:
        await db.write(
            "MATCH (n) WHERE n.id IN [$claim_id, $entity_id] DETACH DELETE n",
            {"claim_id": claim_id, "entity_id": entity_id},
        )
        await db.close_driver()