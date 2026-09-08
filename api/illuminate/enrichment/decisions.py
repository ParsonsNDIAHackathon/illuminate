"""Append-only analyst dispositions and a unified accountability timeline."""
from __future__ import annotations

import uuid

from .. import db
from ..connectors.base import now_iso
from ..schema import SUPPLY_SCOPE_MAX_DEPTH

DISPOSITIONS = {
    "investigate",
    "monitor",
    "seek_alternate_source",
    "accept_with_rationale",
    "close_no_action",
}


async def record(
    entity_id: str,
    *,
    disposition: str,
    rationale: str,
    owner: str,
    due_date: str | None,
    actor: str,
    program_id: str | None = None,
    finding_ids: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    expected_version: int = 0,
) -> dict:
    if disposition not in DISPOSITIONS:
        raise ValueError("unsupported analyst disposition")
    event_id = "ade_" + uuid.uuid4().hex
    timestamp = now_iso()
    finding_ids = sorted(set(finding_ids or []))
    evidence_refs = sorted(set(evidence_refs or []))

    async def work(tx):
        entity_rows = await _rows(
            tx,
            "MATCH (e:Entity {id:$entity_id}) "
            "SET e.decision_guard=coalesce(e.decision_guard,0)+1 "
            "WITH e "
            "OPTIONAL MATCH (e)<-[:DECISION_FOR]-(event:AnalystDecision) "
            "WITH e, coalesce(max(coalesce(event.sequence,event.version)),0) AS current_sequence, "
            "coalesce(max(CASE WHEN event.program_id=$program_id "
            "OR (event.program_id IS NULL AND $program_id IS NULL) THEN event.version ELSE 0 END),0) AS current_version "
            "RETURN e.id AS id, coalesce(e.simulated,false) AS simulated, current_sequence, current_version",
            {"entity_id": entity_id, "program_id": program_id},
        )
        if not entity_rows:
            raise KeyError(entity_id)
        current_version = int(entity_rows[0]["current_version"])
        if current_version != expected_version:
            raise ValueError("analyst decision changed; refresh and try again")

        simulated = bool(entity_rows[0]["simulated"])
        if program_id:
            program_rows = await _rows(
                tx,
                "MATCH (e:Entity {id:$entity_id}), (program:Entity {id:$program_id}) "
                "WHERE program.kind='program' "
                f"OPTIONAL MATCH path=(e)-[:SUPPLIES*0..{SUPPLY_SCOPE_MAX_DEPTH}]->(program) "
                "RETURN program.id AS id, coalesce(program.simulated,false) AS simulated, path IS NOT NULL AS related",
                {"entity_id": entity_id, "program_id": program_id},
            )
            if not program_rows or not program_rows[0]["related"]:
                raise ValueError("program is not a supply-chain context for this vendor")
            simulated = simulated or bool(program_rows[0]["simulated"])

        linked_evidence: list[dict] = []
        if evidence_refs:
            linked_evidence = await _rows(
                tx,
                "UNWIND $evidence_refs AS ref "
                "MATCH (evidence {id:ref}) "
                "WHERE (evidence:Claim AND (evidence.subject_id=$entity_id OR evidence.object_id=$entity_id)) "
                "OR (evidence:Artifact AND EXISTS { "
                "  MATCH (evidence)-[:EVIDENCES]->(claim:Claim) "
                "  WHERE claim.subject_id=$entity_id OR claim.object_id=$entity_id "
                "}) "
                "RETURN evidence.id AS id, coalesce(evidence.simulated,false) OR "
                "EXISTS { MATCH (evidence)-[:EVIDENCES]->(claim:Claim) WHERE coalesce(claim.simulated,false) } AS simulated",
                {"entity_id": entity_id, "evidence_refs": evidence_refs},
            )
            if {row["id"] for row in linked_evidence} != set(evidence_refs):
                raise ValueError("evidence references must belong to this vendor")
            simulated = simulated or any(bool(row["simulated"]) for row in linked_evidence)

        rows = await _rows(
            tx,
            "MATCH (e:Entity {id:$entity_id}) "
            "CREATE (decision:AnalystDecision {id:$event_id, entity_id:$entity_id, disposition:$disposition, "
            "rationale:$rationale, owner:$owner, due_date:$due_date, actor:$actor, decided_at:$decided_at, "
            "program_id:$program_id, finding_ids:$finding_ids, evidence_refs:$evidence_refs, "
            "version:$version, sequence:$sequence, simulated:$simulated}) "
            "CREATE (decision)-[:DECISION_FOR]->(e) "
            "RETURN decision{.*} AS decision",
            {
                "entity_id": entity_id,
                "event_id": event_id,
                "disposition": disposition,
                "rationale": rationale,
                "owner": owner,
                "due_date": due_date,
                "actor": actor,
                "decided_at": timestamp,
                "program_id": program_id,
                "finding_ids": finding_ids,
                "evidence_refs": evidence_refs,
                "version": current_version + 1,
                "sequence": int(entity_rows[0]["current_sequence"]) + 1,
                "simulated": simulated,
            },
        )
        if program_id:
            await _rows(
                tx,
                "MATCH (decision:AnalystDecision {id:$event_id}), (program:Entity {id:$program_id}) "
                "CREATE (decision)-[:DECISION_PROGRAM]->(program)",
                {"event_id": event_id, "program_id": program_id},
            )
        if evidence_refs:
            await _rows(
                tx,
                "MATCH (decision:AnalystDecision {id:$event_id}) "
                "MATCH (evidence) WHERE evidence.id IN $evidence_refs "
                "CREATE (decision)-[:DECISION_EVIDENCE]->(evidence)",
                {"event_id": event_id, "evidence_refs": evidence_refs},
            )
        return rows[0]["decision"]

    return await db.transactional_write(work)


async def history(entity_id: str, limit: int = 200, program_id: str | None = None) -> dict:
    rows = await db.read(
        """
        MATCH (e:Entity {id:$entity_id})
        RETURN [(decision:AnalystDecision)-[:DECISION_FOR]->(e) | decision{.*}] AS decisions,
               [(review:ClaimReview)-[:REVIEW_OF]->(claim:Claim)
                 WHERE claim.subject_id=$entity_id OR claim.object_id=$entity_id |
                 review{
                   .id,.claim_id,.from_status,.to_status,.rationale,.actor,.decided_at,.version,
                   simulated:coalesce(review.simulated,false), kind:'claim_review'
                 }
               ] AS reviews
        """,
        {"entity_id": entity_id},
    )
    if not rows:
        raise KeyError(entity_id)
    decisions = list({
        item["id"]: {**item, "kind": "analyst_decision"}
        for item in rows[0].get("decisions") or [] if item.get("id")
    }.values())
    reviews = list({
        item["id"]: {**item, "kind": "claim_review"}
        for item in rows[0].get("reviews") or [] if item.get("id")
    }.values())
    events = sorted(decisions + reviews, key=lambda item: (str(item.get("decided_at") or ""), str(item.get("id") or "")), reverse=True)
    events = events[:max(1, min(limit, 500))]
    scoped = [item for item in decisions if item.get("program_id") == program_id]
    current = max(scoped, key=lambda item: int(item.get("version") or 0), default=None)
    return {"current": current, "events": events}


async def _rows(tx, query: str, params: dict) -> list[dict]:
    result = await tx.run(query, params)
    rows = [record.data() for record in await result.fetch(500)]
    await result.consume()
    return rows