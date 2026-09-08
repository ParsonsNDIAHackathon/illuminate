"""Claim staging and the trust rule (D5).

Every fact becomes a Claim node carrying its evidence Artifact, method, source,
confidence and timestamp. Facts from authoritative connectors auto-commit; facts
from open sources need human approval or corroboration by two independent
sources. Committing writes the direct relationship/property for query speed with
claim_id carried as a property, so traversal stays fast and provenance stays
reachable."""
from __future__ import annotations

import json as _json

from .. import db
from ..connectors.base import Fact, NodeRef, now_iso
from ..ids import artifact_id, claim_id, edge_id
from ..schema import RELS

REL_PREDICATES = set(RELS) - {"EVIDENCES", "ASSERTS", "TARGETS", "ABOUT"}
ATTR_ALLOWLIST = {"uei", "cage", "lei", "registration_status", "public", "ticker", "cik", "legal_name", "employees", "website",
                  "board_size", "flagged", "littlesis_id", "opencorporates_id", "duns", "business_types", "naics_codes", "sam_registered",
                  "incorporation_date", "entity_status", "market_cap", "last_price", "price_change_12m", "registration_expires", "organization_structure"}
SCREEN_PREDICATES = {"sanctions_screen", "exclusion_screen", "financial_screen", "adverse_media_screen", "registry_screen"}
# 'mention' asserts only that an artifact is about the subject — the connector's own observation, committed on arrival.
OBSERVATION_PREDICATES = SCREEN_PREDICATES | {"mention"}
CORROBORATION_SOURCES = 2


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
    fact.subject = await _resolve_ref(fact.subject)
    if fact.object:
        fact.object = await _resolve_ref(fact.object)
    if fact.object and fact.object.id == fact.subject.id and fact.predicate in REL_PREDICATES:
        # e.g. GLEIF says the entity is its own parent after resolution — nothing to assert
        return await _noop_claim(fact, source=source, trust=trust)
    cid = claim_id()
    params: dict = {
        "cid": cid, "pred": fact.predicate, "source": source, "trust": trust, "method": fact.method, "model": model,
        "conf": float(fact.confidence), "now": now_iso(), "value": fact.value, "detail": fact.detail,
        "rel_props_json": _json.dumps({k: v for k, v in fact.props.items() if v is not None}), "sid": fact.subject.id, "oid": fact.object.id if fact.object else None,
        "rid1": edge_id(), "rid2": edge_id(), "rid3": edge_id(), "rid4": edge_id(),
    }
    parts = [
        _merge_node("s", fact.subject, "s", params),
        "MERGE (c:Claim {id:$cid}) ON CREATE SET c.predicate=$pred, c.subject_id=$sid, c.object_id=$oid, c.object_value=$value, c.source=$source,",
        "  c.trust=$trust, c.method=$method, c.model=$model, c.confidence=$conf, c.retrieved_at=$now, c.status='staged', c.detail=$detail, c.rel_props=$rel_props_json",
        "MERGE (c)-[ra:ASSERTS]->(s) ON CREATE SET ra.id=$rid1",
    ]
    if fact.object:
        parts.append(_merge_node("o", fact.object, "o", params))
        parts.append("MERGE (c)-[rt:TARGETS]->(o) ON CREATE SET rt.id=$rid2")
    if fact.artifact:
        a = fact.artifact
        params.update({"aid": artifact_id(a.url), "aurl": a.url, "atitle": a.title[:300], "akind": a.kind, "asource": a.source or source, "apub": a.published_at,
                       "aprops": {k: v for k, v in a.props.items() if v is not None}})
        parts += [
            "MERGE (a:Artifact {id:$aid}) ON CREATE SET a.url=$aurl, a.title=$atitle, a.kind=$akind, a.source=$asource, a.published_at=$apub, a.retrieved_at=$now",
            "SET a += $aprops",
            "MERGE (a)-[re:EVIDENCES]->(c) ON CREATE SET re.id=$rid3",
            "MERGE (a)-[rb:ABOUT]->(s) ON CREATE SET rb.id=$rid4",
        ]
    parts.append("RETURN c.id AS id")
    await db.write("\n".join(parts), params)
    return cid


async def _noop_claim(fact: Fact, *, source: str, trust: str) -> str:
    cid = claim_id()
    await db.write(
        "MERGE (c:Claim {id:$cid}) ON CREATE SET c.predicate=$pred, c.subject_id=$sid, c.object_id=$sid, c.source=$source, c.trust=$trust, c.method=$method, "
        "c.confidence=$conf, c.retrieved_at=$now, c.status='rejected', c.decision_note='self-referential after entity resolution' "
        "WITH c MATCH (s {id:$sid}) MERGE (c)-[r:ASSERTS]->(s) ON CREATE SET r.id=$rid",
        {"cid": cid, "pred": fact.predicate, "sid": fact.subject.id, "source": source, "trust": trust, "method": fact.method, "conf": float(fact.confidence), "now": now_iso(), "rid": edge_id()},
    )
    return cid


async def decide(cid: str, *, trust: str) -> str:
    """Apply the trust rule to a staged claim. Returns the resulting status."""
    row = (await db.read("MATCH (c:Claim {id:$id}) RETURN c{.*} AS c", {"id": cid}))[0]["c"]
    if row.get("status") == "rejected":
        return "rejected"
    if row["predicate"] in OBSERVATION_PREDICATES:
        # A screen/mention records what a source said on a date; it is an observation of the connector itself.
        return await commit(cid)
    if trust == "authoritative" and float(row.get("confidence") or 0) >= 0.8:
        return await commit(cid)
    # Open source: corroboration by independent sources commits; otherwise wait for a human.
    others = await db.read(
        "MATCH (c:Claim) WHERE c.subject_id=$s AND c.predicate=$p AND coalesce(c.object_id,'')=coalesce($o,'') AND coalesce(c.object_value,'')=coalesce($v,'') "
        "AND c.status IN ['staged','committed'] RETURN count(DISTINCT c.source) AS n",
        {"s": row["subject_id"], "p": row["predicate"], "o": row.get("object_id"), "v": row.get("object_value")},
    )
    if others and others[0]["n"] >= CORROBORATION_SOURCES:
        return await commit(cid, note="corroborated by independent sources")
    return "staged"


async def commit(cid: str, note: str | None = None) -> str:
    rows = await db.read(
        "MATCH (c:Claim {id:$id})-[:ASSERTS]->(s) OPTIONAL MATCH (c)-[:TARGETS]->(o) "
        "RETURN c{.*} AS c, s.id AS sid, head(labels(s)) AS slabel, o.id AS oid, head(labels(o)) AS olabel", {"id": cid})
    if not rows:
        raise KeyError(cid)
    r = rows[0]
    c = r["c"]
    pred = c["predicate"]
    rel_props = _json.loads(c.get("rel_props") or "{}") if c.get("rel_props") else {}
    prov = {"source": c["source"], "source_url": None, "retrieved_at": c["retrieved_at"], "method": c["method"], "confidence": c["confidence"], "claim_id": cid}
    art = await db.read("MATCH (a:Artifact)-[:EVIDENCES]->(c:Claim {id:$id}) RETURN a.url AS url LIMIT 1", {"id": cid})
    if art:
        prov["source_url"] = art[0]["url"]

    if pred in REL_PREDICATES and r["oid"]:
        keys = [k for k in ("from", "title", "contract_ref") if k in rel_props] if pred in ("HELD_ROLE", "SUPPLIES") else []
        key_clause = " {" + ", ".join(f"{k}: $rp.{k}" for k in keys) + "}" if keys else ""
        await db.write(
            f"MATCH (s {{id:$sid}}), (o {{id:$oid}}) MERGE (s)-[r:{pred}{key_clause}]->(o) "
            "ON CREATE SET r.id=$rid SET r += $rp, r += $prov",
            {"sid": r["sid"], "oid": r["oid"], "rp": rel_props, "prov": prov, "rid": edge_id()},
        )
    elif pred.startswith("attr:"):
        name = pred[5:]
        if name in ATTR_ALLOWLIST:
            val = c.get("object_value")
            if val in ("true", "false"):
                val = val == "true"
            await db.write(f"MATCH (s {{id:$sid}}) SET s.{name} = $v, s.{name}_claim_id = $cid", {"sid": r["sid"], "v": val, "cid": cid})
    elif pred == "sanctions_screen" or pred == "exclusion_screen":
        if c.get("object_value") == "hit":
            await db.write("MATCH (s {id:$sid}) SET s.flagged = true, s.flag_reason = $why", {"sid": r["sid"], "why": f"{pred}: {c.get('detail') or 'hit'}"})
    await db.write("MATCH (c:Claim {id:$id}) SET c.status='committed', c.decided_at=$now, c.decision_note=$note", {"id": cid, "now": now_iso(), "note": note})
    return "committed"


async def reject(cid: str, note: str | None = None) -> str:
    await db.write("MATCH (c:Claim {id:$id}) SET c.status='rejected', c.decided_at=$now, c.decision_note=$note", {"id": cid, "now": now_iso(), "note": note})
    return "rejected"


async def list_claims(status: str | None = None, entity_id: str | None = None, limit: int = 200) -> list[dict]:
    where = ["1=1"]
    params: dict = {"limit": limit}
    if status:
        where.append("c.status = $status")
        params["status"] = status
    if entity_id:
        where.append("(c.subject_id = $eid OR c.object_id = $eid)")
        params["eid"] = entity_id
    return await db.read(
        f"""
        MATCH (c:Claim) WHERE {' AND '.join(where)}
        OPTIONAL MATCH (c)-[:ASSERTS]->(s) OPTIONAL MATCH (c)-[:TARGETS]->(o) OPTIONAL MATCH (a:Artifact)-[:EVIDENCES]->(c)
        RETURN c{{.*}} AS claim, s.name AS subject, head(labels(s)) AS subject_label, o.name AS object, head(labels(o)) AS object_label,
               collect(DISTINCT a{{.id,.title,.url,.kind}}) AS artifacts
        ORDER BY claim.retrieved_at DESC LIMIT $limit
        """,
        params,
    )
