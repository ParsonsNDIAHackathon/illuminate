from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import db
from ..raw import find_raw
from ..report import build_report
from ..tools.handlers import ToolContext, expand_subgraph, search_entities
from .deps import user_id

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph/stats")
async def stats():
    rows = await db.read(
        "MATCH (n) WITH labels(n)[0] AS l, count(*) AS c RETURN collect({label:l, count:c}) AS nodes"
    )
    rels = await db.read("MATCH ()-[r]->() WITH type(r) AS t, count(*) AS c RETURN collect({type:t, count:c}) AS rels")
    return {"nodes": rows[0]["nodes"] if rows else [], "rels": rels[0]["rels"] if rels else []}


@router.get("/graph/search")
async def search(q: str, kind: str = "any", limit: int = 10, user: str = Depends(user_id)):
    r = await search_entities(ToolContext.from_workspace(source="ui", user=user), q, kind, limit)
    return r.data


@router.get("/graph/subgraph")
async def subgraph(entity_id: str, depth: int = 2, people: bool = True, countries: bool = False, artifacts: bool = False, categories: bool = False, user: str = Depends(user_id)):
    ctx = ToolContext.from_workspace(source="ui", user=user)
    r = await expand_subgraph(ctx, entity_id, depth, {"people": people, "countries": countries, "artifacts": artifacts, "categories": categories})
    return {"subgraph": r.subgraph, "cypher": r.cypher, "params": r.params}


@router.get("/graph/node/{node_id}")
async def node(node_id: str):
    rows = await db.read(
        "MATCH (n {id:$id}) OPTIONAL MATCH (n)-[r]-(m) WITH n, type(r) AS t, count(m) AS c "
        "RETURN n{.*} AS props, labels(n) AS labels, collect({type:t, count:c}) AS degree",
        {"id": node_id},
    )
    if not rows:
        raise HTTPException(404, "no such node")
    return rows[0]


@router.get("/entities")
async def entities(q: str | None = None, kind: str | None = None, flagged: bool | None = None, limit: int = Query(100, le=1000), offset: int = 0):
    where = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}
    if q:
        where.append("toLower(e.name) CONTAINS toLower($q)")
        params["q"] = q
    if kind:
        where.append("e.kind = $kind")
        params["kind"] = kind
    if flagged is not None:
        where.append("coalesce(e.flagged,false) = $flagged")
        params["flagged"] = flagged
    rows = await db.read(
        f"""
        MATCH (e:Entity) WHERE {' AND '.join(where)}
        OPTIONAL MATCH (e)-[s:SUPPLIES]->(c:Entity)
        OPTIONAL MATCH (e)-[:INCORPORATED_IN]->(inc:Location)
        OPTIONAL MATCH (e)-[:PARENT_SEATED_IN]->(seat:Location)
        OPTIONAL MATCH (up:Entity)-[:ULTIMATE_PARENT_OF]->(e)
        WITH e, min(s.tier) AS tier, count(DISTINCT c) AS consumers, head(collect(DISTINCT inc.code)) AS inc, head(collect(DISTINCT seat.code)) AS seat,
             head(collect(DISTINCT up.name)) AS parent, any(x IN collect(s.sole_source) WHERE x = true) AS sole_source
        RETURN e.id AS id, e.name AS name, e.kind AS kind, e.uei AS uei, e.cage AS cage, e.lei AS lei, tier, consumers, inc AS incorporated, seat AS parent_seat, parent,
               sole_source, coalesce(e.flagged,false) AS flagged, coalesce(e.simulated,false) AS simulated, e.source AS source
        ORDER BY tier, name SKIP $offset LIMIT $limit
        """,
        params,
    )
    total = await db.read(f"MATCH (e:Entity) WHERE {' AND '.join(where)} RETURN count(e) AS n", params)
    return {"items": rows, "total": total[0]["n"] if total else 0}


@router.get("/people")
async def people(q: str | None = None, limit: int = Query(200, le=1000)):
    params: dict = {"limit": limit}
    where = "WHERE toLower(p.name) CONTAINS toLower($q)" if q else ""
    if q:
        params["q"] = q
    return await db.read(
        f"""
        MATCH (p:Person) {where}
        OPTIONAL MATCH (p)-[r:HELD_ROLE]->(e:Entity)
        WITH p, collect({{entity_id:e.id, lei:e.lei, entity:e.name, title:r.title, role_type:r.role_type, from:r.from, to:r.to, current:coalesce(r.current, r.to IS NULL), edge_id:r.id}}) AS roles
        RETURN p.id AS id, p.name AS name, p.source AS source, p.source_url AS source_url, coalesce(p.simulated,false) AS simulated, roles,
               size([x IN roles WHERE x.current]) AS current_roles, size(apoc.coll.toSet([x IN roles | coalesce(x.lei, x.entity_id)])) AS entities
        ORDER BY entities DESC, name LIMIT $limit
        """,
        params,
    )


@router.get("/artifacts")
async def artifacts(kind: str | None = None, entity_id: str | None = None, limit: int = Query(200, le=1000)):
    where = ["1=1"]
    params: dict = {"limit": limit}
    if kind:
        where.append("a.kind = $kind")
        params["kind"] = kind
    if entity_id:
        where.append("EXISTS { MATCH (a)-[:ABOUT]->(:Entity {id:$eid}) }")
        params["eid"] = entity_id
    return await db.read(
        f"""
        MATCH (a:Artifact) WHERE {' AND '.join(where)}
        OPTIONAL MATCH (a)-[:ABOUT]->(e:Entity)
        OPTIONAL MATCH (a)-[:EVIDENCES]->(c:Claim)
        RETURN a.id AS id, a.kind AS kind, a.title AS title, a.url AS url, a.source AS source, a.published_at AS published_at, a.retrieved_at AS retrieved_at,
               a.amount AS amount, a.sentiment AS sentiment, collect(DISTINCT e{{.id,.name}})[..5] AS about, count(DISTINCT c) AS claims
        ORDER BY coalesce(a.published_at, a.retrieved_at) DESC LIMIT $limit
        """,
        params,
    )


@router.get("/artifacts/{artifact_id}")
async def artifact_detail(artifact_id: str):
    """One artifact with what it is attached to and, where the source response is cached, the raw payload."""
    rows = await db.read(
        """
        MATCH (a:Artifact {id:$id})
        OPTIONAL MATCH (a)-[:ABOUT]->(e:Entity)
        OPTIONAL MATCH (a)-[:EVIDENCES]->(c:Claim)
        RETURN a{.*} AS artifact, collect(DISTINCT e{.id,.name}) AS about,
               collect(DISTINCT c{.id,.predicate,.status,.confidence}) AS claims
        """,
        {"id": artifact_id},
    )
    if not rows:
        raise HTTPException(404, "no such artifact")
    row = rows[0]
    return {**row, "raw": find_raw(artifact_id, row["artifact"] or {})}


@router.get("/locations")
async def locations():
    return await db.read(
        """
        MATCH (l:Location)
        OPTIONAL MATCH (e:Entity)-[r:INCORPORATED_IN|OPERATES_IN|MANUFACTURES_IN|PARENT_SEATED_IN]->(l)
        RETURN l.id AS id, l.code AS code, l.name AS name, l.kind AS kind,
               size([x IN collect(type(r)) WHERE x='INCORPORATED_IN']) AS incorporated,
               size([x IN collect(type(r)) WHERE x='MANUFACTURES_IN']) AS manufactures,
               size([x IN collect(type(r)) WHERE x='PARENT_SEATED_IN']) AS parent_seats
        ORDER BY incorporated + manufactures + parent_seats DESC
        """
    )


@router.get("/entities/{entity_id}/report")
async def report(entity_id: str, user: str = Depends(user_id)):
    from ..config import load_workspace
    rep = await build_report(entity_id, load_workspace().root_id)
    if not rep:
        raise HTTPException(404, "no such entity")
    return rep


@router.post("/entities/{entity_id}/summary")
async def regenerate_summary(entity_id: str, user: str = Depends(user_id)):
    from ..llm.client import has_key
    from ..llm.tasks import summarize_entity
    import time
    if not has_key(user):
        raise HTTPException(400, "no OpenAI key configured")
    rep = await build_report(entity_id)
    if not rep:
        raise HTTPException(404, "no such entity")
    out = await summarize_entity(user, rep)
    if not out:
        raise HTTPException(502, "model did not return a summary")
    await db.write("MATCH (e:Entity {id:$id}) SET e.summary=$s, e.summary_model=$m, e.summary_at=$t",
                   {"id": entity_id, "s": out["summary"], "m": out["model"], "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return {"summary": out["summary"], "model": out["model"]}
