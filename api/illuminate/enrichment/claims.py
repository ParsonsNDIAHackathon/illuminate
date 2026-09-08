"""Claim staging and the trust rule (D5).

Every fact becomes a Claim node carrying its evidence Artifact, method, source,
confidence and timestamp. Facts from authoritative connectors auto-commit; facts
from open sources need human approval or corroboration by two independent
sources. Committing writes the direct relationship/property for query speed with
claim_id carried as a property, so traversal stays fast and provenance stays
reachable."""
from __future__ import annotations

import json as _json
import hashlib
import uuid

from .. import db
from ..connectors.base import Fact, NodeRef, now_iso
from ..connectors.http import HttpError
from ..connectors.http import scrub
from ..ids import artifact_id, claim_id, edge_id
from ..schema import RELS
from ..connectors.registry import source_metadata

REL_PREDICATES = set(RELS) - {"EVIDENCES", "ASSERTS", "TARGETS", "ABOUT"}
ATTR_ALLOWLIST = {"uei", "cage", "lei", "registration_status", "public", "ticker", "cik", "legal_name", "employees", "website",
                  "board_size", "flagged", "littlesis_id", "opencorporates_id", "duns", "business_types", "naics_codes", "sam_registered",
                  "incorporation_date", "entity_status", "market_cap", "last_price", "price_change_12m", "registration_expires", "organization_structure"}
SCREEN_PREDICATES = {
    "sanctions_screen", "exclusion_screen", "financial_screen", "adverse_media_screen", "registry_screen",
    # Contextual adapters record dated source observations rather than overwrite a
    # scalar entity property (one entity can have many CVEs, clauses, and places).
    "vulnerability_screen", "far_clause_screen", "location_context_screen",
}
# 'mention' asserts only that an artifact is about the subject — the connector's own observation, committed on arrival.
OBSERVATION_PREDICATES = SCREEN_PREDICATES | {"mention"}
CORROBORATION_SOURCES = 2
# Which relationship props identify a *distinct* edge, for claims written before
# Fact.merge_keys was carried through staging. A connector now says so per fact:
# one HELD_ROLE per tenure, but one aggregate SUPPLIES edge per pair of entities.
LEGACY_MERGE_KEYS = {"HELD_ROLE": ("from", "title"), "SUPPLIES": ("from", "title", "contract_ref")}


def _merge_node(alias: str, ref: NodeRef, pfx: str, params: dict) -> str:
    params[f"{pfx}_id"] = ref.id
    params[f"{pfx}_props"] = {k: v for k, v in ref.props.items() if v is not None}
    return f"MERGE ({alias}:{ref.label} {{id:${pfx}_id}}) ON CREATE SET {alias} += ${pfx}_props"


async def _resolve_ref(ref: NodeRef) -> NodeRef:
    """A connector proposing an Entity by LEI/name must not create a duplicate of
    an entity we already know under a UEI. Resolve before merging; keep the
    resolution method on the node so a fuzzy merge is visible."""
    if ref.label != "Entity":
        return ref
    exists = await db.read("MATCH (e:Entity {id:$id}) RETURN e.id AS id LIMIT 1", {"id": ref.id})
    if exists:
        return ref
    from ..resolve import find_entity
    p = ref.props or {}
    m = await find_entity(uei=p.get("uei"), lei=p.get("lei"), cage=p.get("cage"), name=p.get("name"))
    if m and m.confidence >= 0.85:
        props = {k: v for k, v in p.items() if k in ("lei", "cage", "uei", "legal_name", "country") and v}
        props["resolved_method"] = m.method
        props["resolved_confidence"] = m.confidence
        return NodeRef("Entity", m.id, props)
    return ref


async def stage(fact: Fact, *, source: str, trust: str, model: str | None = None) -> str:
    """Write the Claim (+ Artifact) for a fact. Returns the claim id. Nothing about
    the world is asserted in the graph yet — only that a source said it."""
    # Capture this before entity resolution, which intentionally keeps only
    # identity properties when it redirects a reference to an existing entity.
    simulated = bool(fact.props.get("simulated") or fact.subject.props.get("simulated") or
                     (fact.object and fact.object.props.get("simulated")) or
                     (fact.artifact and fact.artifact.props.get("simulated")))
    fact.subject = await _resolve_ref(fact.subject)
    if fact.object:
        fact.object = await _resolve_ref(fact.object)
    if fact.object and fact.object.id == fact.subject.id and fact.predicate in REL_PREDICATES:
        # e.g. GLEIF says the entity is its own parent after resolution — nothing to assert
        return await _noop_claim(fact, source=source, trust=trust, simulated=simulated)
    cid = observation_key(fact, source)
    meta = source_metadata(source)
    ingested_at = now_iso()
    retrieved_at = fact.props.get("retrieved_at") or ingested_at
    as_of = (
        fact.props.get("as_of")
        or (fact.artifact.published_at if fact.artifact else None)
        or retrieved_at
    )
    params: dict = {
        "cid": cid, "pred": fact.predicate, "source": source, "trust": trust, "method": fact.method, "model": model,
        "conf": float(fact.confidence), "now": ingested_at,
        "retrieved_at": retrieved_at, "as_of": as_of,
        "retrieval_status": fact.props.get("retrieval_status") or "unknown",
        "retrieval_mode": fact.props.get("retrieval_mode") or "operational_live",
        "cache": bool(fact.props.get("cache")), "fallback": bool(fact.props.get("fallback")),
        "cache_age_s": fact.props.get("cache_age_s"), "value": fact.value, "detail": fact.detail,
        "rel_props_json": _json.dumps({k: v for k, v in fact.props.items() if v is not None}),
        "merge_keys_json": _json.dumps(list(fact.merge_keys)), "sid": fact.subject.id, "oid": fact.object.id if fact.object else None,
        "rid1": edge_id(), "rid2": edge_id(), "rid3": edge_id(), "rid4": edge_id(),
        "source_meta": meta, "simulated": simulated,
    }
    parts = [
        _merge_node("s", fact.subject, "s", params),
        "MERGE (c:Claim {id:$cid}) ON CREATE SET c.predicate=$pred, c.subject_id=$sid, c.object_id=$oid, c.object_value=$value, c.source=$source,",
        "  c.trust=$trust, c.method=$method, c.model=$model, c.confidence=$conf, c.retrieved_at=$retrieved_at, c.as_of=$as_of, c.status='staged', c.source_status='staged', c.detail=$detail,",
        "  c.rel_props=$rel_props_json, c.merge_keys=$merge_keys_json, c.simulated=$simulated",
        "SET c += $source_meta, c.method=$method, c.model=$model, c.confidence=$conf, c.detail=$detail, "
        "c.rel_props=$rel_props_json, c.merge_keys=$merge_keys_json, c.retrieval_status=$retrieval_status, "
        "c.retrieval_mode=$retrieval_mode, c.cache=$cache, c.fallback=$fallback, c.cache_age_s=$cache_age_s, "
        "c.latest_retrieved_at=$retrieved_at, c.latest_as_of=$as_of, c.ingested_at=$now, "
        "c.ingestion_count=coalesce(c.ingestion_count,0)+1",
        "MERGE (c)-[ra:ASSERTS]->(s) ON CREATE SET ra.id=$rid1",
    ]
    if fact.object:
        parts.append(_merge_node("o", fact.object, "o", params))
        parts.append("MERGE (c)-[rt:TARGETS]->(o) ON CREATE SET rt.id=$rid2")
    if fact.artifact:
        a = fact.artifact
        artifact_observation_id = a.props.get("source_identifier")
        safe_url = scrub(a.url)
        artifact_identity = f"{safe_url}#{artifact_observation_id}" if artifact_observation_id else safe_url
        params.update({"aid": artifact_id(artifact_identity), "aurl": safe_url, "atitle": a.title[:300], "akind": a.kind, "asource": a.source or source, "apub": a.published_at,
                        "aprops": {k: v for k, v in a.props.items() if v is not None and k not in {"source_status", "retrieval_status", "retrieval_mode", "retrieved_at", "latest_retrieved_at", "as_of", "latest_as_of", "cache", "fallback", "cache_age_s"}},
                        "artifact_retrieval_status": a.props.get("retrieval_status") or params["retrieval_status"],
                        "artifact_retrieval_mode": a.props.get("retrieval_mode") or params["retrieval_mode"],
                        "artifact_cache": bool(a.props.get("cache", params["cache"])),
                        "artifact_fallback": bool(a.props.get("fallback", params["fallback"])),
                        "artifact_cache_age_s": a.props.get("cache_age_s", params["cache_age_s"])})
        parts += [
            "MERGE (a:Artifact {id:$aid}) ON CREATE SET a.url=$aurl, a.title=$atitle, a.kind=$akind, a.source=$asource, "
            "a.published_at=$apub, a.retrieved_at=$retrieved_at, a.as_of=$as_of, a.ingested_at=$now, "
            "a.latest_retrieved_at=$retrieved_at, a.latest_as_of=$as_of, a.ingestion_count=1, "
            "a += $aprops, a += $source_meta, "
            "a.retrieval_status=$artifact_retrieval_status, a.retrieval_mode=$artifact_retrieval_mode, "
            "a.cache=$artifact_cache, a.fallback=$artifact_fallback, a.cache_age_s=$artifact_cache_age_s, a.simulated=$simulated",
            "MERGE (a)-[re:EVIDENCES]->(c) ON CREATE SET re.id=$rid3, re.retrieved_at=$retrieved_at, re.as_of=$as_of "
            "SET re.source=$source, re.artifact_title=$atitle, re.artifact_kind=$akind, re.artifact_published_at=$apub, "
            "re.ingested_at=$now, re.latest_retrieved_at=$retrieved_at, re.latest_as_of=$as_of, re.retrieval_status=$artifact_retrieval_status, "
            "re.retrieval_mode=$artifact_retrieval_mode, re.cache=$artifact_cache, re.fallback=$artifact_fallback, "
            "re.cache_age_s=$artifact_cache_age_s, re.simulated=$simulated, re += $aprops, re += $source_meta",
            "MERGE (a)-[rb:ABOUT]->(s) ON CREATE SET rb.id=$rid4",
        ]
    parts.append("RETURN c.id AS id")
    await db.write("\n".join(parts), params)
    return cid


async def _noop_claim(fact: Fact, *, source: str, trust: str, simulated: bool | None = None) -> str:
    cid = observation_key(fact, source)
    meta = source_metadata(source)
    simulated = bool(fact.props.get("simulated") or fact.subject.props.get("simulated")) if simulated is None else simulated
    now = now_iso()
    retrieved_at = fact.props.get("retrieved_at") or now
    as_of = fact.props.get("as_of") or retrieved_at
    await db.write(
        "MERGE (c:Claim {id:$cid}) ON CREATE SET c.predicate=$pred, c.subject_id=$sid, c.object_id=$sid, c.source=$source, c.trust=$trust, c.method=$method, "
        "c.confidence=$conf, c.retrieved_at=$retrieved_at, c.as_of=$as_of, c.status='rejected', c.source_status='rejected', c.simulated=$simulated, "
        "c.decision_note='self-referential after entity resolution' SET c += $meta, c.ingested_at=$now, "
        "c.latest_retrieved_at=$retrieved_at, c.latest_as_of=$as_of, c.retrieval_status=$retrieval_status, c.retrieval_mode=$retrieval_mode, "
        "c.cache=$cache, c.fallback=$fallback, c.cache_age_s=$cache_age_s, c.ingestion_count=coalesce(c.ingestion_count,0)+1 "
        "WITH c MATCH (s {id:$sid}) MERGE (c)-[r:ASSERTS]->(s) ON CREATE SET r.id=$rid",
        {"cid": cid, "pred": fact.predicate, "sid": fact.subject.id, "source": source, "trust": trust, "method": fact.method,
         "conf": float(fact.confidence), "now": now, "retrieved_at": retrieved_at,
         "as_of": as_of, "rid": edge_id(), "meta": meta, "simulated": simulated,
         "retrieval_status": fact.props.get("retrieval_status") or "unknown",
         "retrieval_mode": fact.props.get("retrieval_mode") or "operational_live",
         "cache": bool(fact.props.get("cache")), "fallback": bool(fact.props.get("fallback")),
         "cache_age_s": fact.props.get("cache_age_s")},
    )
    return cid


async def decide(cid: str, *, trust: str) -> str:
    """Apply the trust rule to a staged claim. Returns the resulting status."""
    row = (await db.read("MATCH (c:Claim {id:$id}) RETURN c{.*} AS c", {"id": cid}))[0]["c"]
    if row.get("status") == "rejected":
        return "rejected"
    if row["predicate"] in OBSERVATION_PREDICATES:
        # A screen/mention records what a source said on a date; it is an observation of the connector itself.
        return await commit(cid, refresh_materialization=True)
    if trust == "authoritative" and float(row.get("confidence") or 0) >= 0.8:
        return await commit(cid, refresh_materialization=True)
    # Open source: corroboration by independent sources commits; otherwise wait for a human.
    others = await db.read(
        "MATCH (c:Claim) WHERE c.subject_id=$s AND c.predicate=$p AND coalesce(c.object_id,'')=coalesce($o,'') AND coalesce(c.object_value,'')=coalesce($v,'') "
        "AND c.status IN ['staged','committed'] RETURN count(DISTINCT c.source) AS n",
        {"s": row["subject_id"], "p": row["predicate"], "o": row.get("object_id"), "v": row.get("object_value")},
    )
    if others and others[0]["n"] >= CORROBORATION_SOURCES:
        return await commit(cid, note="corroborated by independent sources", refresh_materialization=True)
    return "staged"


async def commit(
    cid: str,
    note: str | None = None,
    actor: str = "system",
    *,
    refresh_materialization: bool = False,
) -> str:
    review_id = "cre_" + uuid.uuid4().hex
    async def work(tx) -> str:
        rows = await _tx_rows(
            tx,
            "MATCH (c:Claim {id:$id})-[:ASSERTS]->(s) "
            "OPTIONAL MATCH (c)-[:TARGETS]->(o) "
            "SET c.decision_lock=coalesce(c.decision_lock,0)+1 "
            "RETURN c{.*} AS c, s.id AS sid, head(labels(s)) AS slabel, "
            "o.id AS oid, head(labels(o)) AS olabel",
            {"id": cid},
        )
        if not rows:
            raise KeyError(cid)
        r = rows[0]
        c = r["c"]
        status = c.get("status")
        if status == "rejected":
            return "rejected"
        if status not in {"staged", "committed"}:
            raise ValueError(f"claim {cid} cannot be committed from status {status!r}")
        first_commit = status == "staged"
        if not first_commit and not refresh_materialization:
            return "committed"
        pred = c["predicate"]
        rel_props = _json.loads(c.get("rel_props") or "{}") if c.get("rel_props") else {}
        simulated = bool(rel_props.get("simulated") or c.get("simulated"))
        rel_props["simulated"] = simulated
        prov = {
            k: c.get(k)
            for k in (
                "source", "source_id", "catalog_ids", "retrieved_at", "usage_note",
                "quality_note", "supports", "unknowns", "method", "confidence",
                "retrieval_status", "retrieval_mode", "latest_retrieved_at",
                "latest_as_of", "as_of", "cache", "fallback", "cache_age_s",
            )
        }
        prov["simulated"] = simulated
        prov.update({
            "source_url": None,
            "source_status": "committed",
            "connector_error": c.get("connector_error"),
            "claim_id": cid,
        })
        art = await _tx_rows(
            tx,
            "MATCH (a:Artifact)-[:EVIDENCES]->(c:Claim {id:$id}) "
            "RETURN a.url AS url LIMIT 1",
            {"id": cid},
        )
        if art:
            prov["source_url"] = art[0]["url"]

        if pred in REL_PREDICATES and r["oid"]:
            declared = (
                _json.loads(c["merge_keys"])
                if c.get("merge_keys") is not None
                else list(LEGACY_MERGE_KEYS.get(pred, ()))
            )
            keys = [key for key in declared if key in rel_props]
            key_clause = (
                " {" + ", ".join(f"{key}: $rp.{key}" for key in keys) + "}"
                if keys else ""
            )
            ownership_guard = (
                "WITH r WHERE r.claim_id IS NULL OR r.claim_id=$cid "
                if not first_commit else ""
            )
            await _tx_rows(
                tx,
                f"MATCH (s {{id:$sid}}), (o {{id:$oid}}) "
                f"MERGE (s)-[r:{pred}{key_clause}]->(o) "
                f"ON CREATE SET r.id=$rid {ownership_guard}"
                "SET r += $rp, r += $prov",
                {
                    "sid": r["sid"], "oid": r["oid"], "rp": rel_props,
                    "prov": prov, "rid": edge_id(), "cid": cid,
                },
            )
        elif pred.startswith("attr:"):
            name = pred[5:]
            if name in ATTR_ALLOWLIST:
                val = c.get("object_value")
                if val in ("true", "false"):
                    val = val == "true"
                ownership_guard = (
                    f"WHERE s.{name}_claim_id IS NULL OR s.{name}_claim_id=$cid "
                    if not first_commit else ""
                )
                await _tx_rows(
                    tx,
                    f"MATCH (s {{id:$sid}}) "
                    f"{ownership_guard}"
                    f"SET s.{name} = $v, s.{name}_claim_id = $cid",
                    {"sid": r["sid"], "v": val, "cid": cid},
                )
        elif pred in {"sanctions_screen", "exclusion_screen"}:
            if c.get("object_value") == "hit":
                await _tx_rows(
                    tx,
                    "MATCH (s {id:$sid}) "
                    "SET s.flagged = true, s.flag_reason = $why",
                    {"sid": r["sid"], "why": f"{pred}: {c.get('detail') or 'hit'}"},
                )
        if first_commit:
            await _tx_rows(
                tx,
                "MATCH (c:Claim {id:$id}) "
                "SET c.status='committed', c.source_status='committed', "
                "c.decided_at=$now, c.decision_note=$note, c.decision_actor=$actor, "
                "c.decision_version=coalesce(c.decision_version,0)+1 "
                "CREATE (review:ClaimReview {id:$review_id, claim_id:$id, from_status:'staged', "
                "to_status:'committed', rationale:$note, actor:$actor, decided_at:$now, "
                "version:c.decision_version, simulated:coalesce(c.simulated,false)}) "
                "CREATE (review)-[:REVIEW_OF]->(c)",
                {
                    "id": cid,
                    "now": now_iso(),
                    "note": note,
                    "actor": actor,
                    "review_id": review_id,
                },
            )
        else:
            # A repeated live observation refreshes the materialized fact above
            # but must not masquerade as a new analyst decision.
            await _tx_rows(
                tx,
                "MATCH (c:Claim {id:$id}) SET c.source_status='committed'",
                {"id": cid},
            )
        return "committed"

    return await db.transactional_write(work)


async def endpoints(cid: str) -> list[str]:
    """The nodes a claim speaks about — what committing it changes in the graph."""
    rows = await db.read(
        "MATCH (c:Claim {id:$id})-[:ASSERTS]->(s) OPTIONAL MATCH (c)-[:TARGETS]->(o) RETURN s.id AS sid, o.id AS oid",
        {"id": cid},
    )
    if not rows:
        return [cid]
    return [i for i in (rows[0]["sid"], rows[0]["oid"], cid) if i]


async def reject(cid: str, note: str | None = None, actor: str = "system") -> str:
    review_id = "cre_" + uuid.uuid4().hex
    async def work(tx) -> str:
        rows = await _tx_rows(
            tx,
            "MATCH (c:Claim {id:$id}) "
            "SET c.decision_lock=coalesce(c.decision_lock,0)+1 "
            "RETURN c.status AS status",
            {"id": cid},
        )
        if not rows:
            raise KeyError(cid)
        status = rows[0].get("status")
        if status == "rejected":
            return "rejected"
        if status != "staged":
            raise ValueError(f"claim {cid} cannot be rejected from status {status!r}")
        await _tx_rows(
            tx,
            "MATCH (c:Claim {id:$id}) "
            "SET c.status='rejected', c.source_status='rejected', "
            "c.decided_at=$now, c.decision_note=$note, c.decision_actor=$actor, "
            "c.decision_version=coalesce(c.decision_version,0)+1 "
            "CREATE (review:ClaimReview {id:$review_id, claim_id:$id, from_status:'staged', "
            "to_status:'rejected', rationale:$note, actor:$actor, decided_at:$now, "
            "version:c.decision_version, simulated:coalesce(c.simulated,false)}) "
            "CREATE (review)-[:REVIEW_OF]->(c)",
            {
                "id": cid,
                "now": now_iso(),
                "note": note,
                "actor": actor,
                "review_id": review_id,
            },
        )
        return "rejected"

    return await db.transactional_write(work)

async def _tx_rows(tx, query: str, params: dict) -> list[dict]:
    result = await tx.run(query, params)
    rows = [record.data() for record in await result.fetch(50)]
    await result.consume()
    return rows
async def record_connector_error(source: str, entity_id: str, error: Exception) -> str:
    """Persist a credential-free failed attempt so absence of claims is explainable downstream."""
    meta = source_metadata(source)
    retrieved_at = now_iso()
    rid = "src_" + hashlib.sha256(f"{source}:{entity_id}:{retrieved_at}".encode()).hexdigest()[:24]
    error_meta = connector_error_metadata(error)
    await db.write(
        "MERGE (r:SourceRecord {id:$id}) SET r += $meta, r.source=$source, r.entity_id=$entity_id, "
        "r.retrieved_at=$now, r.source_status='error', r.connector_error=$error, "
        "r.connector_error_type=$error_type, r.connector_error_status=$error_status",
        {"id": rid, "meta": meta, "source": source, "entity_id": entity_id, "now": retrieved_at,
         "error": error_meta["connector_error"], "error_type": error_meta["connector_error_type"],
         "error_status": error_meta["connector_error_status"]},
    )
    return rid


def connector_error_metadata(error: Exception) -> dict:
    """Return only allowlisted diagnostics; exception messages can contain credential-bearing URLs or bodies."""
    error_type = type(error).__name__
    status = error.status if isinstance(error, HttpError) else None
    summary = error_type + (f" (HTTP {status})" if status is not None else "")
    return {"connector_error": summary, "connector_error_type": error_type, "connector_error_status": status}


async def list_claims(
    status: str | None = None,
    entity_id: str | None = None,
    limit: int = 200,
    claim_id: str | None = None,
) -> list[dict]:
    limit = max(1, min(int(limit), 500))
    where = ["1=1"]
    params: dict = {"limit": limit}
    if status:
        where.append("c.status = $status")
        params["status"] = status
    if entity_id:
        where.append("(c.subject_id = $eid OR c.object_id = $eid)")
        params["eid"] = entity_id
    if claim_id:
        where.append("c.id = $claim_id")
        params["claim_id"] = claim_id
        params["limit"] = 1
    return await db.read(
        f"""
        MATCH (c:Claim) WHERE {' AND '.join(where)}
        OPTIONAL MATCH (c)-[:ASSERTS]->(s) OPTIONAL MATCH (c)-[:TARGETS]->(o) OPTIONAL MATCH (a:Artifact)-[:EVIDENCES]->(c)
        RETURN c{{.*}} AS claim, s.name AS subject, head(labels(s)) AS subject_label, o.name AS object, head(labels(o)) AS object_label,
               collect(DISTINCT a{{.id,.title,.url,.kind,.source_id,.source_identifier,.catalog_ids,.retrieved_at,.usage_note,.quality_note,.source_status,.connector_error,.simulated}}) AS artifacts
        ORDER BY claim.retrieved_at DESC LIMIT $limit
        """,
        params,
    )


async def list_source_records(entity_id: str | None = None, limit: int = 200) -> list[dict]:
    """Expose successful cached retrievals and failures without promoting either to findings."""
    limit = max(1, min(int(limit), 500))
    where = "WHERE r.entity_id = $entity_id" if entity_id else ""
    return await db.read(
        f"MATCH (r:SourceRecord) {where} RETURN r{{.*}} AS source_record "
        "ORDER BY r.retrieved_at DESC LIMIT $limit",
        {"entity_id": entity_id, "limit": limit},
    )

def observation_key(fact: Fact, source: str) -> str:
    """Stable identity for the same upstream observation across worker restarts."""
    props = fact.props or {}
    upstream = next((props.get(k) for k in ("upstream_id", "source_id", "record_id", "award_id", "filing_id")
                     if props.get(k) is not None), None)
    if upstream is None and fact.artifact:
        upstream = fact.artifact.props.get("source_identifier")
    upstream = upstream or (fact.artifact.url if fact.artifact else None)
    material = [source, str(upstream or ""), fact.subject.id, fact.predicate,
                fact.object.id if fact.object else "", fact.value or ""]
    # Connector-declared merge keys distinguish genuinely separate observations
    # such as two board tenures. Aggregate facts such as SUPPLIES intentionally
    # declare no keys, so a refresh updates the existing observation and edge.
    material.extend([f"{key}={props.get(key)}" for key in fact.merge_keys])
    return "clm_obs_" + hashlib.sha256(_json.dumps(material, separators=(",", ":"), default=str).encode()).hexdigest()[:32]
