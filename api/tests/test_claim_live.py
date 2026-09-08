"""Claim decision contention against live Neo4j (skipped when unavailable)."""
import asyncio

import pytest

from illuminate import db
from illuminate.enrichment import claims, decisions
from illuminate.routers import exports
from illuminate.connectors.base import ArtifactRef, Fact, NodeRef


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

async def test_repeat_live_observation_preserves_first_retrieval_and_refreshes_latest_fact():
    if not await _reachable():
        pytest.skip("neo4j not reachable")
    supplier_id = "test_retrieval_supplier"
    program_id = "test_retrieval_program"
    artifact_url = "https://example.test/award/retrieval-regression"

    def fact(amount: int, retrieved_at: str, status: str, cache: bool) -> Fact:
        return Fact(
            NodeRef("Entity", supplier_id, {"name": "Retrieval Supplier", "kind": "organization"}),
            "SUPPLIES",
            object=NodeRef("Entity", program_id, {"name": "Retrieval Program", "kind": "program"}),
            props={
                "amount": amount,
                "retrieved_at": retrieved_at,
                "retrieval_status": status,
                "retrieval_mode": "operational_live",
                "cache": cache,
            },
            artifact=ArtifactRef(
                artifact_url,
                "Award retrieval regression",
                kind="award",
                props={"source_identifier": "award-retrieval-regression"},
            ),
        )

    first = "2026-08-19T12:00:00Z"
    latest = "2026-09-08T12:00:00Z"
    try:
        first_id = await claims.stage(
            fact(100, first, "cached", True),
            source="usaspending",
            trust="authoritative",
        )
        assert await claims.decide(first_id, trust="authoritative") == "committed"
        second_id = await claims.stage(
            fact(250, latest, "live", False),
            source="usaspending",
            trust="authoritative",
        )
        assert second_id == first_id
        assert await claims.decide(second_id, trust="authoritative") == "committed"

        rows = await db.read(
            "MATCH (s:Entity {id:$supplier})-[r:SUPPLIES]->(p:Entity {id:$program}) "
            "MATCH (c:Claim {id:$claim}) "
            "MATCH (a:Artifact)-[e:EVIDENCES]->(c) "
            "RETURN c.retrieved_at AS claim_first, c.latest_retrieved_at AS claim_latest, "
            "r.retrieved_at AS edge_first, r.latest_retrieved_at AS edge_latest, r.amount AS amount, "
            "a.retrieved_at AS artifact_first, a.latest_retrieved_at AS artifact_latest, "
            "e.retrieved_at AS evidence_first, e.latest_retrieved_at AS evidence_latest",
            {"supplier": supplier_id, "program": program_id, "claim": first_id},
        )
        assert rows == [{
            "claim_first": first,
            "claim_latest": latest,
            "edge_first": first,
            "edge_latest": latest,
            "amount": 250,
            "artifact_first": first,
            "artifact_latest": first,
            "evidence_first": first,
            "evidence_latest": latest,
        }]
    finally:
        await db.write(
            "MATCH (n) WHERE n.id IN [$supplier,$program] DETACH DELETE n "
            "WITH count(n) AS ignored MATCH (c:Claim) "
            "WHERE c.subject_id=$supplier AND c.object_id=$program DETACH DELETE c",
            {"supplier": supplier_id, "program": program_id},
        )
        await db.write(
            "MATCH (a:Artifact {url:$url}) DETACH DELETE a",
            {"url": artifact_url},
        )
        await db.close_driver()


async def test_shared_url_preserves_artifact_lineage_and_scopes_each_evidence_observation():
    if not await _reachable():
        pytest.skip("neo4j not reachable")
    entity_id = "test_shared_artifact_entity"
    artifact_url = "https://example.test/news/shared-artifact-regression"

    def fact(*, source: str, retrieved_at: str, simulated: bool) -> Fact:
        return Fact(
            NodeRef("Entity", entity_id, {"name": "Shared Artifact Entity", "kind": "organization"}),
            "mention",
            props={
                "retrieved_at": retrieved_at,
                "retrieval_status": "live",
                "retrieval_mode": "operational_live",
                "simulated": simulated,
            },
            artifact=ArtifactRef(
                artifact_url,
                f"{source} discovery title",
                kind="news",
                source=f"{source} publisher",
                props={"connector_variant": source, "simulated": simulated},
            ),
        )

    first = "2026-09-08T10:00:00Z"
    second = "2026-09-08T11:00:00Z"
    try:
        first_id = await claims.stage(
            fact(source="gdelt", retrieved_at=first, simulated=False),
            source="gdelt",
            trust="open",
        )
        second_id = await claims.stage(
            fact(source="littlesis", retrieved_at=second, simulated=True),
            source="littlesis",
            trust="open",
        )
        assert first_id != second_id

        rows = await db.read(
            "MATCH (a:Artifact {url:$url})-[e:EVIDENCES]->(c:Claim) "
            "RETURN a.source AS artifact_source, a.source_id AS artifact_source_id, "
            "a.catalog_ids AS artifact_catalog_ids, a.connector_variant AS artifact_variant, "
            "a.simulated AS artifact_simulated, a.retrieved_at AS artifact_retrieved_at, "
            "c.source AS claim_source, e.source_id AS evidence_source_id, "
            "e.catalog_ids AS evidence_catalog_ids, e.connector_variant AS evidence_variant, "
            "e.simulated AS evidence_simulated, e.latest_retrieved_at AS evidence_retrieved_at "
            "ORDER BY claim_source",
            {"url": artifact_url},
        )
        assert len(rows) == 2
        assert all(row["artifact_source"] == "gdelt publisher" for row in rows)
        assert all(row["artifact_source_id"] == "gdelt-2.x" for row in rows)
        assert all(row["artifact_catalog_ids"] == ["ndia:62"] for row in rows)
        assert all(row["artifact_variant"] == "gdelt" for row in rows)
        assert all(row["artifact_simulated"] is False for row in rows)
        assert all(row["artifact_retrieved_at"] == first for row in rows)
        assert rows[0]["claim_source"] == "gdelt"
        assert rows[0]["evidence_source_id"] == "gdelt-2.x"
        assert rows[0]["evidence_catalog_ids"] == ["ndia:62"]
        assert rows[0]["evidence_variant"] == "gdelt"
        assert rows[0]["evidence_simulated"] is False
        assert rows[0]["evidence_retrieved_at"] == first
        assert rows[1]["claim_source"] == "littlesis"
        assert rows[1]["evidence_source_id"] == "littlesis"
        assert rows[1]["evidence_catalog_ids"] == []
        assert rows[1]["evidence_variant"] == "littlesis"
        assert rows[1]["evidence_simulated"] is True
        assert rows[1]["evidence_retrieved_at"] == second
    finally:
        await db.write(
            "MATCH (c:Claim {subject_id:$entity_id}) DETACH DELETE c",
            {"entity_id": entity_id},
        )
        await db.write(
            "MATCH (n) WHERE n.id=$entity_id OR (n:Artifact AND n.url=$url) DETACH DELETE n",
            {"entity_id": entity_id, "url": artifact_url},
        )
        await db.close_driver()


async def test_concurrent_vendor_decisions_keep_one_version_and_link_valid_scope():
    if not await _reachable():
        pytest.skip("neo4j not reachable")
    vendor_id = "test_decision_vendor"
    program_id = "test_decision_program"
    second_program_id = "test_decision_program_b"
    claim_id = "clm_test_decision_evidence"
    artifact_id = "art_test_decision_evidence"
    await db.write(
        "CREATE (vendor:Entity {id:$vendor_id, name:'Decision Vendor'}) "
        "CREATE (program:Entity {id:$program_id, name:'Decision Program', kind:'program'}) "
        "CREATE (program_b:Entity {id:$second_program_id, name:'Second Decision Program', kind:'program'}) "
        "CREATE (claim:Claim {id:$claim_id, subject_id:$vendor_id, status:'committed', "
        "classification:'UNCLASSIFIED', simulated:true}) "
        "CREATE (artifact:Artifact {id:$artifact_id, simulated:false}) "
        "CREATE (vendor)-[:SUPPLIES]->(program) "
        "CREATE (vendor)-[:SUPPLIES]->(program_b) "
        "CREATE (claim)-[:ASSERTS]->(vendor) "
        "CREATE (artifact)-[:EVIDENCES]->(claim)",
        {
            "vendor_id": vendor_id, "program_id": program_id, "second_program_id": second_program_id,
            "claim_id": claim_id, "artifact_id": artifact_id,
        },
    )
    try:
        first = await decisions.record(
            vendor_id, disposition="investigate", rationale="Validate simulated evidence.",
            owner="Test Team", due_date=None, actor="test-analyst", program_id=program_id,
            finding_ids=["finding:risk:test"], evidence_refs=[claim_id, artifact_id],
            expected_version=0,
        )
        second_scope = await decisions.record(
            vendor_id, disposition="monitor", rationale="Monitor artifact-backed evidence.",
            owner="Test Team", due_date=None, actor="test-analyst", program_id=second_program_id,
            finding_ids=["finding:risk:test"], evidence_refs=[artifact_id], expected_version=0,
        )
        scoped_export_query = exports._SELECT.replace(
            "WHERE c.id IS NOT NULL AND s.id IS NOT NULL",
            "WHERE c.id=$claim_id AND c.id IS NOT NULL AND s.id IS NOT NULL",
        )
        exported = await db.read(scoped_export_query, {
            "include_rejected": False, "since_time": "1970-01-01T00:00:00Z", "since_id": "",
            "upper_time": "9999-12-31T23:59:59Z", "upper_id": "~", "fetch": 10, "claim_id": claim_id,
        })
        exported_row = next(row for row in exported if row["claim_id"] == claim_id)
        assert exported_row["analyst_disposition"]["action"] == "monitor"
        assert exported_row["analyst_disposition"]["evidence_refs"] == [artifact_id]

        a_update = await decisions.record(
            vendor_id, disposition="investigate", rationale="Continue program A review.",
            owner="Test Team", due_date=None, actor="test-analyst", program_id=program_id,
            finding_ids=["finding:risk:test"], evidence_refs=[claim_id], expected_version=1,
        )
        attempts = await asyncio.gather(
            decisions.record(
                vendor_id, disposition="monitor", rationale="First competing update.",
                owner="Test Team", due_date=None, actor="test-analyst", program_id=program_id,
                finding_ids=["finding:risk:test"], evidence_refs=[claim_id], expected_version=2,
            ),
            decisions.record(
                vendor_id, disposition="close_no_action", rationale="Second competing update.",
                owner="Test Team", due_date=None, actor="test-analyst", program_id=program_id,
                finding_ids=["finding:risk:test"], evidence_refs=[claim_id], expected_version=2,
            ),
            return_exceptions=True,
        )
        rows = await db.read(
            "MATCH (decision:AnalystDecision)-[:DECISION_FOR]->(:Entity {id:$vendor_id}) "
            "OPTIONAL MATCH (decision)-[program_link:DECISION_PROGRAM]->(decision_program:Entity) "
            "OPTIONAL MATCH (decision)-[evidence_link:DECISION_EVIDENCE]->() "
            "RETURN decision.version AS version, decision.sequence AS sequence, decision.simulated AS simulated, "
            "count(DISTINCT program_link) AS program_links, decision_program.id AS program_id, "
            "count(DISTINCT evidence_link) AS evidence_links "
            "ORDER BY sequence",
            {"vendor_id": vendor_id, "program_id": program_id},
        )
        assert first["version"] == 1 and first["simulated"] is True
        assert second_scope["version"] == 1 and second_scope["sequence"] == 2
        assert a_update["version"] == 2 and a_update["sequence"] == 3
        assert sum(isinstance(item, ValueError) for item in attempts) == 1
        assert [row["version"] for row in rows] == [1, 1, 2, 3]
        assert [row["sequence"] for row in rows] == [1, 2, 3, 4]
        assert all(row["program_links"] == 1 for row in rows)
        assert rows[0]["evidence_links"] == 2
    finally:
        await db.write(
            "MATCH (n) WHERE n.id IN [$vendor_id,$program_id,$second_program_id,$claim_id,$artifact_id] "
            "OR (n:AnalystDecision AND n.entity_id=$vendor_id) DETACH DELETE n",
            {
                "vendor_id": vendor_id, "program_id": program_id, "second_program_id": second_program_id,
                "claim_id": claim_id, "artifact_id": artifact_id,
            },
        )
        await db.close_driver()
