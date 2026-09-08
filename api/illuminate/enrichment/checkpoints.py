"""Durable enrichment job checkpoints.

The in-memory queue is intentionally disposable; Neo4j holds enough state for a
new worker process to resume only unfinished sources.
"""
from __future__ import annotations

import json
import time
from typing import Any

from .. import db


async def save(job: Any) -> None:
    await db.write(
        "MERGE (j:EnrichmentJob {id:$id}) SET j.entity_id=$entity_id, j.entity_name=$entity_name, "
        "j.connectors_json=$connectors, j.results_json=$results, j.status=$status, j.user=$user, "
        "j.requested_by=$requested_by, j.retrieval_mode=$mode, j.resumed_from=$resumed_from, "
        "j.parent_job_id=$parent_job_id, "
        "j.created_at=$created_at, j.started_at=$started_at, j.finished_at=$finished_at, "
        "j.summary_status=$summary_status, j.summary_updated=$summary_updated, j.checkpointed_at=$checkpointed_at",
        {
            "id": job.id, "entity_id": job.entity_id, "entity_name": job.entity_name,
            "connectors": json.dumps(job.connectors), "results": json.dumps(job.results),
            "status": job.status, "user": job.user, "requested_by": job.requested_by,
            "mode": job.retrieval_mode, "resumed_from": job.resumed_from,
            "parent_job_id": job.parent_job_id,
            "created_at": job.created_at, "started_at": job.started_at, "finished_at": job.finished_at,
            "summary_status": job.summary_status, "summary_updated": job.summary_updated,
            "checkpointed_at": time.time(),
        },
    )


async def load(job_id: str) -> dict | None:
    rows = await db.read(
        "MATCH (j:EnrichmentJob {id:$id}) RETURN j{.*} AS j LIMIT 1", {"id": job_id}
    )
    if not rows:
        return None
    row = rows[0]["j"]
    try:
        row["connectors"] = json.loads(row.get("connectors_json") or "[]")
        row["results"] = json.loads(row.get("results_json") or "{}")
    except (TypeError, ValueError):
        raise ValueError("stored enrichment checkpoint is corrupt")
    return row


async def interrupt_active() -> int:
    """Retire process-owned states left behind by a previous worker process."""
    result = await db.write(
        "MATCH (j:EnrichmentJob) WHERE j.status IN ['queued','running'] "
        "SET j.status='interrupted', j.finished_at=$now, "
        "j.interruption_reason='worker restarted; resume or allow a replacement refresh' "
        "RETURN count(j) AS count",
        {"now": time.time()},
    )
    rows = result.get("rows", []) if isinstance(result, dict) else result
    return int(rows[0].get("count", 0)) if rows else 0


async def mark_superseded(job_id: str, replacement_id: str) -> None:
    await db.write(
        "MATCH (j:EnrichmentJob {id:$id}) "
        "SET j.status='superseded', j.superseded_by=$replacement, j.finished_at=coalesce(j.finished_at,$now)",
        {"id": job_id, "replacement": replacement_id, "now": time.time()},
    )


def _decode(row: dict) -> dict:
    result = dict(row)
    try:
        result["connectors"] = json.loads(result.get("connectors_json") or "[]")
        result["results"] = json.loads(result.get("results_json") or "{}")
    except (TypeError, ValueError):
        result["connectors"] = []
        result["results"] = {"_checkpoint_error": "stored enrichment checkpoint is corrupt"}
        result["status"] = "failed"
    result["terminal"] = result.get("status") not in {"queued", "running"}
    return result


async def list_recent(limit: int = 50) -> list[dict]:
    rows = await db.read(
        "MATCH (j:EnrichmentJob) RETURN j{.*} AS j "
        "ORDER BY j.created_at DESC LIMIT $limit",
        {"limit": limit},
    )
    return [_decode(row["j"]) for row in rows]