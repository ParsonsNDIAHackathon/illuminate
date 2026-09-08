"""Versioned, portable export of committed Illuminate findings.

This is deliberately independent of graphio: graphio is a UI projection while
this module is a public data contract with bounded, repeatable pagination.
"""
from __future__ import annotations

import base64
import asyncio
import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from .. import db

router = APIRouter(prefix="/api/exports/v1", tags=["exports"])
VERSION = "1.0"
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


class Provenance(BaseModel):
    source: str | None = None
    source_url: str | None = None
    retrieved_at: str | None = None
    method: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    claim_id: str | None = None
    license: str | None = None


class Risk(BaseModel):
    score: float | None = None
    level: str | None = None
    category: str | None = None
    rationale: str | None = None


class Quality(BaseModel):
    score: float | None = Field(default=None, ge=0, le=1)
    completeness: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class PathNode(BaseModel):
    id: str
    type: str
    name: str | None = None


class PathEdge(BaseModel):
    type: Literal["ASSERTS", "TARGETS", "EVIDENCES"]
    source: str
    target: str


class TypedPath(BaseModel):
    nodes: list[PathNode]
    edges: list[PathEdge]


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    subject_id: str
    subject_type: str
    subject_name: str | None = None
    predicate: str
    object_id: str | None = None
    object_type: str | None = None
    object_name: str | None = None
    object_value: str | int | float | bool | None = None
    detail: str | None = None
    risk: Risk
    recommendation: str | None = None
    paths: list[TypedPath]
    provenance: list[Provenance]
    classification: str
    license: str | None = None
    quality: Quality
    truth_status: Literal["staged", "committed", "rejected", "unknown"]
    simulated: bool
    deleted: bool = False
    observed_at: datetime


class PageMeta(BaseModel):
    schema_version: Literal["1.0"] = VERSION
    generated_at: datetime
    count: int
    limit: int
    next_cursor: str | None
    watermark: str


class FindingPage(BaseModel):
    meta: PageMeta
    findings: list[Finding]


FIELD_DICTIONARY = {
    "finding_id": "Stable deterministic identifier derived only from the persisted Claim and subject ids.",
    "subject_*": "The node asserted about; its id, graph label, and display name.",
    "predicate": "Machine-readable assertion type.",
    "object_*": "Optional target node or scalar assertion value.",
    "risk": "Normalized score, level, category, and human-readable rationale when available.",
    "recommendation": "Recommended review or mitigation action; never an automated accusation.",
    "paths": "Typed Claim-to-subject, Claim-to-target, and evidence-to-Claim lineage paths.",
    "provenance": "Safe source metadata only; restricted raw source payloads are never exported.",
    "classification": "Information handling classification supplied by the finding, default UNCLASSIFIED.",
    "license": "Source or record license/SPDX expression when known.",
    "quality": "Normalized quality/completeness scores and notes.",
    "truth_status": "Claim review state: staged, committed, rejected, or unknown.",
    "simulated": "True when the finding or any exported path participant is simulated.",
    "deleted": "True on an incremental tombstone; full exports omit tombstoned findings.",
    "observed_at": "Latest source retrieval/update/decision time; incremental ordering uses the export revision.",
}

_SELECT = """
MATCH (c:Claim)-[:ASSERTS]->(s)
WHERE c.id IS NOT NULL AND s.id IS NOT NULL
OPTIONAL MATCH (c)-[:TARGETS]->(o)
WITH c, s, o ORDER BY coalesce(o.id,'')
WITH c, s, collect(DISTINCT o) AS target_nodes
OPTIONAL MATCH (a:Artifact)-[:EVIDENCES]->(c)
WITH c, s, target_nodes, a ORDER BY coalesce(a.id,'')
WITH c, s, target_nodes, collect(DISTINCT a{
  .id, .title, .source, source_url:coalesce(a.source_url,a.url),
  .retrieved_at, .method, .confidence, .license, .simulated
}) AS artifacts,
reduce(changed=datetime('1970-01-01T00:00:00Z'), value IN [c.updated_at,c.decided_at,c.retrieved_at] |
  CASE WHEN value IS NOT NULL AND datetime(toString(value)) > changed
       THEN datetime(toString(value)) ELSE changed END) AS changed,
c.id + '|' + s.id AS identity_key
WHERE ($include_rejected OR coalesce(c.status,'unknown') <> 'rejected')
  AND (changed > datetime($since_time) OR (changed = datetime($since_time) AND identity_key > $since_id))
  AND (changed < datetime($upper_time) OR (changed = datetime($upper_time) AND identity_key <= $upper_id))
RETURN c.id AS claim_id, c.predicate AS predicate, c.object_value AS object_value,
       c.detail AS detail, c.risk_score AS risk_score, c.risk_level AS risk_level,
       c.risk_category AS risk_category, c.risk_rationale AS risk_rationale,
       c.recommendation AS recommendation, c.source AS source, c.source_url AS source_url,
       c.retrieved_at AS retrieved_at, c.method AS method, c.confidence AS confidence,
       c.classification AS classification, c.license AS license, c.quality_score AS quality_score,
       c.completeness AS completeness, c.quality_notes AS quality_notes, c.status AS status,
       coalesce(c.simulated,false) AS claim_simulated,
       s.id AS subject_id, labels(s)[0] AS subject_type, coalesce(s.name,s.title) AS subject_name,
       coalesce(s.simulated,false) AS subject_simulated,
       [o IN target_nodes WHERE o.id IS NOT NULL | o{
         .id, type:labels(o)[0], name:coalesce(o.name,o.title), simulated:coalesce(o.simulated,false)
       }] AS targets, artifacts, toString(changed) AS observed,
       identity_key
ORDER BY changed, identity_key
LIMIT $fetch
"""

_UPPER = """
MATCH (c:Claim)-[:ASSERTS]->(s)
WHERE c.id IS NOT NULL AND s.id IS NOT NULL
WITH c, s,
reduce(changed=datetime('1970-01-01T00:00:00Z'), value IN [c.updated_at,c.decided_at,c.retrieved_at] |
  CASE WHEN value IS NOT NULL AND datetime(toString(value)) > changed
       THEN datetime(toString(value)) ELSE changed END) AS changed,
c.id + '|' + s.id AS identity_key
RETURN toString(changed) AS observed, identity_key AS id
ORDER BY changed DESC, identity_key DESC LIMIT 1
"""

_UPSERT_EVENTS = """
MERGE (counter:InsightExportCounter {version:$version})
ON CREATE SET counter.value = 0
SET counter.value = counter.value
WITH counter
UNWIND $records AS row
MERGE (state:InsightExportState {version:$version, finding_id:row.finding_id})
SET state.sync_id = $sync_id,
    state.claim_id = row.claim_id,
    state.subject_id = row.subject_id
WITH counter, row, state
WHERE state.fingerprint IS NULL OR state.fingerprint <> row.fingerprint
WITH counter, collect({row:row, state:state}) AS changes
SET counter.value = counter.value + size(changes)
WITH changes, counter.value - size(changes) AS start_revision
UNWIND CASE WHEN size(changes) = 0 THEN [] ELSE range(0, size(changes) - 1) END AS offset
WITH changes[offset] AS change, start_revision + offset + 1 AS revision
SET change.state.fingerprint = change.row.fingerprint,
    change.state.revision = revision,
    change.state.payload = change.row.payload,
    change.state.deleted = change.row.deleted
CREATE (:InsightExportEvent {
  version:$version, revision:revision, finding_id:change.row.finding_id,
  truth_status:change.row.truth_status, deleted:change.row.deleted,
  payload:change.row.payload
})
"""

_COUNTER = """
MATCH (counter:InsightExportCounter {version:$version})
RETURN counter.value AS value
"""

_LATEST_EVENTS = """
MATCH (event:InsightExportEvent {version:$version})
WHERE event.revision <= $upper
WITH event.finding_id AS finding_id, max(event.revision) AS revision
WHERE finding_id > $after_id
MATCH (event:InsightExportEvent {version:$version, revision:revision})
WHERE coalesce(event.deleted,false) = false
  AND ($include_rejected OR event.truth_status <> 'rejected')
RETURN event.finding_id AS finding_id, event.revision AS revision, event.payload AS payload
ORDER BY finding_id
LIMIT $fetch
"""

_ACQUIRE_LOCK = """
MERGE (lock:InsightExportLock {version:$version})
ON CREATE SET lock.owner = null, lock.expires_at = datetime('1970-01-01T00:00:00Z'),
              lock.completed_at = datetime('1970-01-01T00:00:00Z'), lock.guard = 0
SET lock.guard = coalesce(lock.guard,0) + 1
WITH lock
WHERE lock.owner IS NULL OR lock.owner = $owner OR lock.expires_at < datetime()
SET lock.owner = $owner,
    lock.expires_at = datetime() + duration({seconds:$lease_seconds})
RETURN lock.owner AS owner, toString(lock.completed_at) AS completed_at
"""

_RENEW_LOCK = """
MATCH (lock:InsightExportLock {version:$version, owner:$owner})
SET lock.expires_at = datetime() + duration({seconds:$lease_seconds})
RETURN lock.owner AS owner
"""

_RELEASE_LOCK = """
MATCH (lock:InsightExportLock {version:$version, owner:$owner})
SET lock.owner = null,
    lock.expires_at = datetime('1970-01-01T00:00:00Z'),
    lock.completed_at = CASE WHEN $completed THEN datetime() ELSE lock.completed_at END
RETURN true AS released
"""

_MISSING_STATES = """
MATCH (state:InsightExportState {version:$version})
WHERE coalesce(state.sync_id,'') <> $sync_id
  AND coalesce(state.deleted,false) = false
  AND state.finding_id > $after_id
  AND NOT EXISTS {
    MATCH (claim:Claim {id:state.claim_id})-[:ASSERTS]->(subject {id:state.subject_id})
  }
RETURN state.finding_id AS finding_id, state.claim_id AS claim_id,
       state.subject_id AS subject_id, state.payload AS payload
ORDER BY state.finding_id
LIMIT $fetch
"""

_INCREMENTAL_EVENTS = """
MATCH (event:InsightExportEvent {version:$version})
WHERE event.revision > $since_revision AND event.revision <= $upper
  AND (event.revision > $after_revision
       OR (event.revision = $after_revision AND event.finding_id > $after_id))
  AND ($include_rejected OR event.truth_status <> 'rejected')
RETURN event.finding_id AS finding_id, event.revision AS revision, event.payload AS payload
ORDER BY revision, finding_id
LIMIT $fetch
"""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token(data: dict[str, Any]) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _untoken(value: str | None, kind: str) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        data = json.loads(raw)
        position_key = "after" if kind == "cursor" else "position"
        if (not isinstance(data, dict) or data.get("v") != VERSION or data.get("kind") != kind
                or not isinstance(data.get(position_key), list) or len(data[position_key]) != 2
                or not all(isinstance(item, str) for item in data[position_key])):
            raise ValueError
        if kind == "cursor" and (
            not isinstance(data.get("upper"), list) or len(data["upper"]) != 2
            or not all(isinstance(item, str) for item in data["upper"])
            or not isinstance(data.get("include_rejected"), bool)
            or data.get("mode") not in {"full", "incremental"}
            or not isinstance(data.get("since_revision"), str)
        ):
            raise ValueError
        int(data[position_key][0])
        if kind == "cursor":
            int(data["upper"][0])
            int(data["since_revision"])
        return data
    except Exception as exc:
        raise HTTPException(400, f"invalid {kind} token") from exc


def _stable_finding_id(row: dict[str, Any]) -> str:
    identity = "|".join(str(row.get(k) or "") for k in ("claim_id", "subject_id"))
    if identity == "|":
        identity = "|".join(str(row.get(k) or "") for k in ("predicate", "object_value", "source_url"))
    return "fnd_" + hashlib.sha256(identity.encode()).hexdigest()[:20]


def _finding(row: dict[str, Any]) -> Finding:
    fid = _stable_finding_id(row)
    subject_id = str(row.get("subject_id") or "unknown")
    claim_node = PathNode(id=fid, type="Claim", name=row.get("predicate"))
    subject = PathNode(id=subject_id, type=row.get("subject_type") or "Node", name=row.get("subject_name"))
    paths = [TypedPath(nodes=[claim_node, subject], edges=[PathEdge(type="ASSERTS", source=fid, target=subject_id)])]
    targets = row.get("targets") or []
    for item in targets:
        target = PathNode(id=str(item["id"]), type=item.get("type") or "Node", name=item.get("name"))
        paths.append(TypedPath(nodes=[claim_node, target], edges=[PathEdge(type="TARGETS", source=fid, target=target.id)]))
    provenance = [Provenance(source=row.get("source"), source_url=row.get("source_url"),
                             retrieved_at=_string(row.get("retrieved_at")), method=row.get("method"),
                             confidence=row.get("confidence"), claim_id=row.get("claim_id"),
                             license=row.get("license"))]
    simulated = bool(row.get("claim_simulated") or row.get("subject_simulated")
                     or any(item.get("simulated") for item in targets))
    for artifact in row.get("artifacts") or []:
        if not artifact.get("id"):
            continue
        aid = str(artifact["id"])
        artifact_node = PathNode(id=aid, type="Artifact", name=artifact.get("title"))
        paths.append(TypedPath(nodes=[artifact_node, claim_node], edges=[PathEdge(type="EVIDENCES", source=aid, target=fid)]))
        provenance.append(Provenance(source=artifact.get("source"), source_url=artifact.get("source_url"),
                                     retrieved_at=_string(artifact.get("retrieved_at")), method=artifact.get("method"),
                                     confidence=artifact.get("confidence"), claim_id=row.get("claim_id"),
                                     license=artifact.get("license")))
        simulated = simulated or bool(artifact.get("simulated"))
    status = row.get("status") if row.get("status") in {"staged", "committed", "rejected"} else "unknown"
    primary = targets[0] if targets else {}
    return Finding(
        finding_id=fid, subject_id=subject_id, subject_type=row.get("subject_type") or "Node",
        subject_name=row.get("subject_name"), predicate=row.get("predicate") or "unknown",
        object_id=_string(primary.get("id")), object_type=primary.get("type"), object_name=primary.get("name"),
        object_value=_scalar(row.get("object_value")), detail=row.get("detail"),
        risk=Risk(score=row.get("risk_score"), level=row.get("risk_level"), category=row.get("risk_category"),
                  rationale=row.get("risk_rationale")),
        recommendation=row.get("recommendation"), paths=paths, provenance=provenance,
        classification=row.get("classification") or "UNCLASSIFIED", license=row.get("license"),
        quality=Quality(score=row.get("quality_score"), completeness=row.get("completeness"), notes=row.get("quality_notes")),
        truth_status=status, simulated=simulated, observed_at=_string(row.get("observed")) or "1970-01-01T00:00:00Z",
    )


def _string(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return _string(value)


async def _acquire_sync_lock(owner: str, wait_seconds: float = 60.0) -> str:
    deadline = asyncio.get_running_loop().time() + wait_seconds
    while True:
        result = await db.write(_ACQUIRE_LOCK, {
            "version": VERSION, "owner": owner, "lease_seconds": 300,
        })
        if result["rows"]:
            return result["rows"][0].get("completed_at") or "1970-01-01T00:00:00Z"
        if asyncio.get_running_loop().time() >= deadline:
            raise HTTPException(503, "export synchronization is busy; retry shortly")
        await asyncio.sleep(0.1)


async def _renew_sync_lock(owner: str) -> None:
    result = await db.write(_RENEW_LOCK, {
        "version": VERSION, "owner": owner, "lease_seconds": 300,
    })
    if not result["rows"]:
        raise HTTPException(503, "export synchronization lease was lost; retry")


async def _write_events(owner: str, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    await _renew_sync_lock(owner)
    await db.write(_UPSERT_EVENTS, {"version": VERSION, "sync_id": owner, "records": records})


async def _sync_export_ledger() -> int:
    """Materialize immutable events when any safe exported field changes."""
    owner = uuid.uuid4().hex
    started_at = _utc_now()
    last_completed = await _acquire_sync_lock(owner)
    completed = False
    try:
        completed_at = datetime.fromisoformat(last_completed.replace("Z", "+00:00"))
        if completed_at >= started_at:
            counter = await db.read(_COUNTER, {"version": VERSION})
            return int(counter[0]["value"]) if counter else 0
        upper = await db.read(_UPPER, {})
        if upper:
            upper_time, upper_id = upper[0]["observed"], upper[0]["id"]
            after_time, after_id = "1970-01-01T00:00:00Z", ""
            while True:
                rows = await db.read(_SELECT, {
                    "include_rejected": True, "since_time": after_time, "since_id": after_id,
                    "upper_time": upper_time, "upper_id": upper_id, "fetch": MAX_LIMIT,
                })
                records = []
                for row in rows:
                    finding = _finding(row)
                    payload = finding.model_dump_json()
                    records.append({
                        "finding_id": finding.finding_id, "claim_id": row["claim_id"],
                        "subject_id": row["subject_id"], "truth_status": finding.truth_status,
                        "deleted": False, "payload": payload,
                        "fingerprint": hashlib.sha256(payload.encode()).hexdigest(),
                    })
                await _write_events(owner, records)
                if len(rows) < MAX_LIMIT:
                    break
                after_time, after_id = rows[-1]["observed"], rows[-1]["identity_key"]

        after_id = ""
        while True:
            missing = await db.read(_MISSING_STATES, {
                "version": VERSION, "sync_id": owner, "after_id": after_id, "fetch": MAX_LIMIT,
            })
            tombstones = []
            for row in missing:
                finding = Finding.model_validate_json(row["payload"]).model_copy(update={"deleted": True})
                payload = finding.model_dump_json()
                tombstones.append({
                    "finding_id": finding.finding_id, "claim_id": row.get("claim_id"),
                    "subject_id": row.get("subject_id"), "truth_status": finding.truth_status,
                    "deleted": True, "payload": payload,
                    "fingerprint": hashlib.sha256(payload.encode()).hexdigest(),
                })
            await _write_events(owner, tombstones)
            if len(missing) < MAX_LIMIT:
                break
            after_id = missing[-1]["finding_id"]

        counter = await db.read(_COUNTER, {"version": VERSION})
        completed = True
        return int(counter[0]["value"]) if counter else 0
    finally:
        await db.write(_RELEASE_LOCK, {
            "version": VERSION, "owner": owner, "completed": completed,
        })


async def _page(limit: int, cursor: str | None, since: str | None, include_rejected: bool,
                incremental: bool = False) -> FindingPage:
    cur = _untoken(cursor, "cursor")
    mark = _untoken(since, "watermark")
    if cur and since:
        raise HTTPException(400, "cursor and since cannot be combined")
    if cur:
        after_revision, after_id = int(cur["after"][0]), cur["after"][1]
        upper_revision = int(cur["upper"][0])
        mode = cur["mode"]
        since_revision = int(cur["since_revision"])
        include_rejected = bool(cur["include_rejected"])
    else:
        current_upper = await _sync_export_ledger()
        mode = "incremental" if incremental else "full"
        since_revision = int(mark["position"][0]) if mark else 0
        after_revision, after_id = since_revision, ""
        upper_revision = max(current_upper, since_revision)
    params = {
        "version": VERSION, "upper": upper_revision, "fetch": limit + 1,
        "include_rejected": include_rejected, "after_id": after_id,
    }
    if mode == "incremental":
        params.update({"since_revision": since_revision, "after_revision": after_revision})
        rows = await db.read(_INCREMENTAL_EVENTS, params)
    else:
        rows = await db.read(_LATEST_EVENTS, params)
    has_more = len(rows) > limit
    rows = rows[:limit]
    findings = [Finding.model_validate_json(row["payload"]) for row in rows]
    next_cursor = None
    if has_more:
        last = rows[-1]
        next_cursor = _token({
            "v": VERSION, "kind": "cursor", "mode": mode,
            "after": [str(last["revision"]), last["finding_id"]],
            "upper": [str(upper_revision), ""], "since_revision": str(since_revision),
            "include_rejected": include_rejected,
        })
    watermark = _token({"v": VERSION, "kind": "watermark", "position": [str(upper_revision), ""]})
    page = FindingPage(meta=PageMeta(generated_at=_utc_now(), count=len(findings), limit=limit,
                                     next_cursor=next_cursor, watermark=watermark), findings=findings)
    return FindingPage.model_validate(page.model_dump())


def _render(page: FindingPage, fmt: str) -> Response | FindingPage:
    if fmt == "json":
        return page
    rows = [f.model_dump(mode="json") for f in page.findings]
    headers = {
        "X-Illuminate-Schema-Version": VERSION,
        "X-Illuminate-Watermark": page.meta.watermark,
        "X-Illuminate-Next-Cursor": page.meta.next_cursor or "",
    }
    if fmt == "ndjson":
        body = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
        return Response(body + ("\n" if body else ""), media_type="application/x-ndjson", headers=headers)
    output = io.StringIO()
    fields = list(Finding.model_fields)
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, separators=(",", ":")) for k, v in row.items()})
    return Response(output.getvalue(), media_type="text/csv", headers=headers)


@router.get("/schema")
async def export_schema():
    return {"schema_version": VERSION, "schema": FindingPage.model_json_schema()}


@router.get("/fields")
async def field_dictionary():
    return {"schema_version": VERSION, "fields": FIELD_DICTIONARY}


@router.get("/sample")
async def sample():
    example = Finding(
        finding_id=_stable_finding_id({"claim_id": "clm_example", "subject_id": "ent_example"}),
        subject_id="ent_example", subject_type="Entity", subject_name="Example Supplier",
        predicate="sole_source_dependency", object_value="true", detail="Illustrative finding only.",
        risk=Risk(score=72, level="high", category="concentration", rationale="Single qualified source."),
        recommendation="Validate alternate sources.", paths=[], provenance=[Provenance(source="example", claim_id="clm_example")],
        classification="UNCLASSIFIED", license="CC0-1.0", quality=Quality(score=1, completeness=1),
        truth_status="committed", simulated=True, observed_at="2026-09-08T00:00:00Z",
    )
    return {"schema_version": VERSION, "finding": example.model_dump(mode="json")}


@router.get("/findings", response_model=None)
async def findings(limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT), cursor: str | None = None,
                   format: Literal["json", "ndjson", "csv"] = "json", include_rejected: bool = True):
    return _render(await _page(limit, cursor, None, include_rejected), format)


@router.get("/findings/incremental", response_model=None)
async def incremental(since: str | None = None, limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
                      cursor: str | None = None, format: Literal["json", "ndjson", "csv"] = "json",
                      include_rejected: bool = True):
    return _render(await _page(limit, cursor, since, include_rejected, incremental=True), format)