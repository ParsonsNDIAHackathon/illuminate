from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import db, events
from ..content import document, summarize
from ..connectors.http import HttpError, fetch_document
from ..graphio import subgraph_from_graph
from ..raw import find_raw
from ..report import build_report
from ..schema import SOURCE_KINDS
from ..tools.handlers import ToolContext, expand_subgraph, search_entities
from .deps import user_id

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph/stats")
async def stats():
    rows = await db.read(
        "MATCH (n) WITH labels(n)[0] AS l, count(*) AS c RETURN collect({label:l, count:c}) AS nodes"
    )
    rels = await db.read("MATCH ()-[r]->() WITH type(r) AS t, count(*) AS c RETURN collect({type:t, count:c}) AS rels")
    # Scenario records are drawn and scored exactly like observed ones, so the app-bar badge
    # is the workspace's only disclosure. It has to answer "does this workspace hold scenario
    # material" — a property of the data, not of whatever the canvas happens to have loaded.
    simulated = await db.read(
        "RETURN EXISTS { MATCH (n) WHERE coalesce(n.simulated,false) } "
        "OR EXISTS { MATCH ()-[r]->() WHERE coalesce(r.simulated,false) } AS simulated")
    return {"nodes": rows[0]["nodes"] if rows else [], "rels": rels[0]["rels"] if rels else [],
            "simulated": bool(simulated[0]["simulated"]) if simulated else False}


@router.get("/graph/search")
async def search(q: str, kind: str = "any", limit: int = 10, user: str = Depends(user_id)):
    r = await search_entities(ToolContext.from_workspace(source="ui", user=user), q, kind, limit)
    return r.data


@router.get("/graph/subgraph")
async def subgraph(entity_id: str, depth: int = 2, people: bool = True, countries: bool = False, artifacts: bool = False,
                   sources: bool = False, claims: bool = False, categories: bool = False,
                   program_id: str | None = None, user: str = Depends(user_id)):
    """A neighbourhood around one entity. program_id — the program the canvas is focused
    on — keeps the walk inside that program's supply chain instead of crossing into
    another program through a supplier they share."""
    ctx = ToolContext.from_workspace(source="ui", user=user)
    layers = {"people": people, "countries": countries, "artifacts": artifacts, "sources": sources, "claims": claims, "categories": categories}
    r = await expand_subgraph(ctx, entity_id, depth, layers, program_id)
    return {"subgraph": r.subgraph, "cypher": r.cypher, "params": r.params}


@router.get("/graph/programs")
async def programs():
    """The programs the canvas can be narrowed to. The list the focus picker is built from."""
    rows = await db.read(
        "MATCH (e:Entity) WHERE e.kind = 'program' RETURN e.id AS id, e.name AS name ORDER BY e.name"
    )
    return {"items": rows}


# Layer name -> the node labels it governs. Entities are always drawn. Artifacts are one label
# split over two layers by kind (see schema.SOURCE_KINDS), handled separately in the query.
_LAYER_LABELS = {"people": ["Person"], "countries": ["Location"], "categories": ["Category"], "claims": ["Claim"]}


@router.get("/graph/all")
async def graph_all(people: bool = True, countries: bool = False, artifacts: bool = False, sources: bool = False, claims: bool = False,
                    categories: bool = False, limit: int = Query(1500, le=5000)):
    """The whole graph, not one consumer's neighbourhood. A workspace holds several
    programs and the entities that supply them; the canvas shows all of it by default
    and narrows to a single consumer only when the user asks for that."""
    on = {"people": people, "countries": countries, "categories": categories, "claims": claims}
    labels = ["Entity"] + [l for k, v in on.items() if v for l in _LAYER_LABELS[k]]
    # Collected into two lists rather than a row per edge: the read cap counts records, and
    # the graph is hydrated from whatever the row references however deeply it is nested.
    _, graph, _ = await db.read_graph(
        """
        MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels)
           OR (n:Artifact AND CASE WHEN coalesce(n.kind, 'record') IN $source_kinds THEN $sources ELSE $artifacts END)
        WITH n, CASE WHEN n:Entity THEN 0 WHEN n:Person THEN 1 WHEN n:Location THEN 2
                     WHEN n:Category THEN 3 WHEN n:Artifact THEN 4 ELSE 5 END AS rank
        ORDER BY rank, coalesce(n.name, n.id)
        WITH collect(n)[..$limit] AS nodes
        UNWIND nodes AS n
        OPTIONAL MATCH (n)-[r]->(m) WHERE m IN nodes
        RETURN nodes, collect(DISTINCT r) AS rels
        """,
        {"labels": labels, "limit": limit, "artifacts": artifacts, "sources": sources, "source_kinds": list(SOURCE_KINDS)},
    )
    sub = subgraph_from_graph(graph)
    return {"subgraph": sub, "truncated": len(sub["nodes"]) >= limit}


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
async def entities(q: str | None = None, kind: str | None = None, flagged: bool | None = None, band: str | None = None,
                   sort: str = "tier", limit: int = Query(100, le=1000), offset: int = 0):
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
    if band:
        where.append("e.risk_band = $band")
        params["band"] = band
    # Unscored rows sort last under either order: a null score is missing data, not a low one.
    order = "e.risk_score IS NULL, e.risk_score DESC, name" if sort == "risk" else "tier, name"
    rows = await db.read(
        f"""
        MATCH (e:Entity) WHERE {' AND '.join(where)}
        OPTIONAL MATCH (e)-[s:SUPPLIES]->(c:Entity)
        OPTIONAL MATCH (e)-[:INCORPORATED_IN]->(inc:Location)
        OPTIONAL MATCH (e)-[:PARENT_SEATED_IN]->(seat:Location)
        WITH e, min(s.tier) AS tier, count(DISTINCT c) AS consumers, head(collect(DISTINCT inc.code)) AS inc, head(collect(DISTINCT seat.code)) AS seat,
             any(x IN collect(s.sole_source) WHERE x = true) AS sole_source
        // The ultimate parent is the root of the control chain, walked rather than looked up.
        CALL {{
          WITH e
          OPTIONAL MATCH path=(up:Entity)-[:OWNS|ULTIMATE_PARENT_OF*1..6]->(e)
          WHERE up.id <> e.id AND NOT EXISTS {{ (:Entity)-[:OWNS|ULTIMATE_PARENT_OF]->(up) }}
          RETURN up.name AS parent ORDER BY length(path), up.name LIMIT 1
        }}
        RETURN e.id AS id, e.name AS name, e.kind AS kind, e.uei AS uei, e.cage AS cage, e.lei AS lei, tier, consumers, inc AS incorporated, seat AS parent_seat, parent,
               sole_source, coalesce(e.flagged,false) AS flagged, coalesce(e.simulated,false) AS simulated, e.source AS source,
               e.risk_score AS risk_score, e.risk_band AS risk_band, e.risk_top_factor AS risk_top_factor, e.risk_confidence AS risk_confidence,
               e.risk_dimensions_scored AS risk_dimensions_scored, e.risk_dimensions_requested AS risk_dimensions_requested
        ORDER BY {order} SKIP $offset LIMIT $limit
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
               coalesce(p.flagged,false) AS flagged, p.risk_score AS risk_score, p.risk_band AS risk_band, p.risk_top_factor AS risk_top_factor, p.risk_confidence AS risk_confidence,
               p.risk_dimensions_scored AS risk_dimensions_scored, p.risk_dimensions_requested AS risk_dimensions_requested,
               size([x IN roles WHERE x.current]) AS current_roles, size(apoc.coll.toSet([x IN roles | coalesce(x.lei, x.entity_id)])) AS entities
        ORDER BY p.risk_score IS NULL, p.risk_score DESC, entities DESC, name LIMIT $limit
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
    raw = find_raw(artifact_id, row["artifact"] or {})
    return {**row, "raw": raw, "summary": summarize(row["artifact"] or {}, raw)}


async def _artifact_props(artifact_id: str) -> dict:
    rows = await db.read("MATCH (a:Artifact {id:$id}) RETURN a{.*} AS artifact", {"id": artifact_id})
    if not rows or not rows[0].get("artifact"):
        raise HTTPException(404, "no such artifact")
    return rows[0]["artifact"]


@router.get("/artifacts/{artifact_id}/content")
async def artifact_content(artifact_id: str):
    """The source document behind the artifact, fetched and typed for display."""
    return await document(await _artifact_props(artifact_id))


@router.get("/artifacts/{artifact_id}/file")
async def artifact_file(artifact_id: str):
    """Proxy the source bytes so a PDF or image renders in the page — the browser cannot
    fetch them cross-origin. Only non-markup types are served: returning remote HTML from
    our own origin would hand it our cookies, and /content already renders HTML safely."""
    props = await _artifact_props(artifact_id)
    url = (props.get("url") or "").strip()
    if not url:
        raise HTTPException(404, "artifact has no source URL")
    try:
        doc = await fetch_document(url)
    except HttpError as e:
        raise HTTPException(502, str(e))
    mime = doc["content_type"].split(";")[0].strip()
    if mime.startswith("text/") or mime in ("application/xhtml+xml", "image/svg+xml") or mime.endswith(("+xml", "/xml")):
        raise HTTPException(415, f"{mime} is served through /content, not as bytes")
    if not (mime == "application/pdf" or mime.startswith(("image/", "audio/", "video/"))):
        mime = "application/octet-stream"
    return Response(content=doc["body"], media_type=mime, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'",
        "Cache-Control": "private, max-age=3600",
    })


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
async def report(entity_id: str, root_id: str | None = None, user: str = Depends(user_id)):
    """root_id — the focused program, when there is one — is what tier_from_root counts to."""
    rep = await build_report(entity_id, root_id)
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
    await events.announce([entity_id], reason="summary", source="ui")
    return {"summary": out["summary"], "model": out["model"]}
