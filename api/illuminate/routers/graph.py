from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .. import db, events
from ..config import load_workspace, settings
from ..content import document, summarize
from ..connectors.http import HttpError, fetch_document
from ..graphio import subgraph_from_graph
from ..raw import find_raw
from ..report import build_report, deterministic_summary, persist_summary
from ..enrichment import decisions
from ..enrichment.worker import worker
from ..supply_chain import SupplyChainAnalysis, get_supply_chain_analysis
from ..schema import SOURCE_KINDS, SUPPLY_SCOPE_MAX_DEPTH
from ..tools.handlers import ToolContext, expand_subgraph, filter_simulated_subgraph, search_entities
from .deps import user_id

router = APIRouter(prefix="/api", tags=["graph"])

_PUBLIC_ARTIFACT_PROJECTION = (
    "a{.id,.title,.url,.kind,.source,.source_id,.source_identifier,.catalog_ids,"
    ".published_at,.retrieved_at,.usage_note,.quality_note,.supports,.unknowns,"
    ".source_status,.connector_error,.simulated,.amount,.sentiment}"
)


@router.get("/graph/stats")
async def stats():
    include_simulated = load_workspace().include_simulated
    rows = await db.read(
        "MATCH (n) WHERE $include_simulated OR coalesce(n.simulated,false)=false "
        "WITH labels(n)[0] AS l, count(*) AS c RETURN collect({label:l, count:c}) AS nodes",
        {"include_simulated": include_simulated},
    )
    rels = await db.read(
        "MATCH (a)-[r]->(b) WHERE $include_simulated OR "
        "(coalesce(a.simulated,false)=false AND coalesce(r.simulated,false)=false "
        "AND coalesce(b.simulated,false)=false) "
        "WITH type(r) AS t, count(*) AS c RETURN collect({type:t, count:c}) AS rels",
        {"include_simulated": include_simulated},
    )
    return {"nodes": rows[0]["nodes"] if rows else [], "rels": rels[0]["rels"] if rels else []}


@router.get("/graph/search")
async def search(q: str, kind: str = "any", limit: int = Query(10, ge=1, le=50), user: str = Depends(user_id)):
    r = await search_entities(ToolContext.from_workspace(source="ui", user=user), q, kind, limit)
    return r.data


@router.get("/graph/subgraph")
async def subgraph(entity_id: str, depth: int = Query(2, ge=1, le=6), people: bool = True, countries: bool = False, artifacts: bool = False,
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
        "MATCH (e:Entity) WHERE e.kind = 'program' "
        "AND ($include_simulated OR coalesce(e.simulated,false)=false) "
        "RETURN e.id AS id, e.name AS name ORDER BY e.name",
        {"include_simulated": load_workspace().include_simulated},
    )
    return {"items": rows}


# Layer name -> the node labels it governs. Entities are always drawn. Artifacts are one label
# split over two layers by kind (see schema.SOURCE_KINDS), handled separately in the query.
_LAYER_LABELS = {"people": ["Person"], "countries": ["Location"], "categories": ["Category"], "claims": ["Claim"]}


@router.get("/graph/all")
async def graph_all(people: bool = True, countries: bool = False, artifacts: bool = False, sources: bool = False, claims: bool = False,
                    categories: bool = False, limit: int = Query(1500, ge=1, le=5000)):
    """The whole graph, not one consumer's neighbourhood. A workspace holds several
    programs and the entities that supply them; the canvas shows all of it by default
    and narrows to a single consumer only when the user asks for that."""
    on = {"people": people, "countries": countries, "categories": categories, "claims": claims}
    labels = ["Entity"] + [l for k, v in on.items() if v for l in _LAYER_LABELS[k]]
    # Collected into two lists rather than a row per edge: the read cap counts records, and
    # the graph is hydrated from whatever the row references however deeply it is nested.
    include_simulated = load_workspace().include_simulated
    _, graph, _ = await db.read_graph(
        """
        MATCH (n) WHERE ($include_simulated OR coalesce(n.simulated,false)=false)
          AND (any(l IN labels(n) WHERE l IN $labels)
           OR (n:Artifact AND CASE WHEN coalesce(n.kind, 'record') IN $source_kinds THEN $sources ELSE $artifacts END))
        WITH n, CASE WHEN n:Entity THEN 0 WHEN n:Person THEN 1 WHEN n:Location THEN 2
                     WHEN n:Category THEN 3 WHEN n:Artifact THEN 4 ELSE 5 END AS rank
        ORDER BY rank, coalesce(n.name, n.id)
        WITH collect(n)[..$limit] AS nodes
        UNWIND nodes AS n
        OPTIONAL MATCH (n)-[r]->(m) WHERE m IN nodes
          AND ($include_simulated OR coalesce(r.simulated,false)=false)
        RETURN nodes, collect(DISTINCT r) AS rels
        """,
        {"labels": labels, "limit": limit, "artifacts": artifacts, "sources": sources,
         "source_kinds": list(SOURCE_KINDS), "include_simulated": include_simulated},
    )
    sub = filter_simulated_subgraph(subgraph_from_graph(graph), include_simulated)
    return {"subgraph": sub, "truncated": len(sub["nodes"]) >= limit}


@router.get("/graph/node/{node_id}")
async def node(node_id: str):
    include_simulated = load_workspace().include_simulated
    rows = await db.read(
        "MATCH (n {id:$id}) WHERE $include_simulated OR coalesce(n.simulated,false)=false "
        "OPTIONAL MATCH (n)-[r]-(m) WHERE $include_simulated OR "
        "(coalesce(r.simulated,false)=false AND coalesce(m.simulated,false)=false) "
        "WITH n, type(r) AS t, count(m) AS c "
        "RETURN n{.id,.name,.title,.kind,.uei,.cage,.lei,.code,.source,.source_url,"
        ".retrieved_at,.published_at,.simulated,.flagged,.registration_status,"
        ".source_status,.confidence} AS props, labels(n) AS labels, "
        "collect({type:t, count:c}) AS degree",
        {"id": node_id, "include_simulated": include_simulated},
    )
    if not rows:
        raise HTTPException(404, "no such node")
    return rows[0]


@router.get("/entities")
async def entities(q: str | None = None, kind: str | None = None, flagged: bool | None = None,
                   root_id: str | None = None, include_simulated: bool | None = None,
                   limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0, le=100000)):
    include_simulated = load_workspace().include_simulated and include_simulated is not False
    where = ["($include_simulated OR coalesce(e.simulated,false)=false)"]
    params: dict = {"limit": limit, "offset": offset, "include_simulated": include_simulated}
    if q:
        where.append("toLower(e.name) CONTAINS toLower($q)")
        params["q"] = q
    if kind:
        where.append("e.kind = $kind")
        params["kind"] = kind
    if flagged is not None:
        where.append("coalesce(e.flagged,false) = $flagged")
        params["flagged"] = flagged
    if root_id:
        params["root_id"] = root_id
        scoped_match = (
            f"MATCH path=(e:Entity)-[:SUPPLIES*1..{SUPPLY_SCOPE_MAX_DEPTH}]->"
            "(program:Entity {id:$root_id}) "
            f"WHERE program.kind='program' AND {' AND '.join(where)} "
            "AND ($include_simulated OR (all(n IN nodes(path) WHERE coalesce(n.simulated,false)=false) "
            "AND all(r IN relationships(path) WHERE coalesce(r.simulated,false)=false))) "
            "WITH e, min(length(path)) AS tier"
        )
        total_query = (
            f"MATCH path=(e:Entity)-[:SUPPLIES*1..{SUPPLY_SCOPE_MAX_DEPTH}]->"
            "(program:Entity {id:$root_id}) "
            f"WHERE program.kind='program' AND {' AND '.join(where)} "
            "AND ($include_simulated OR (all(n IN nodes(path) WHERE coalesce(n.simulated,false)=false) "
            "AND all(r IN relationships(path) WHERE coalesce(r.simulated,false)=false))) "
            "WITH DISTINCT e RETURN count(e) AS n"
        )
    else:
        scoped_match = f"MATCH (e:Entity) WHERE {' AND '.join(where)} WITH e, null AS scoped_tier"
        total_query = f"MATCH (e:Entity) WHERE {' AND '.join(where)} RETURN count(e) AS n"
    rows = await db.read(
        f"""
        {scoped_match}
        OPTIONAL MATCH (e)-[s:SUPPLIES]->(c:Entity)
          WHERE $include_simulated OR (coalesce(s.simulated,false)=false AND coalesce(c.simulated,false)=false)
        OPTIONAL MATCH (e)-[ir:INCORPORATED_IN]->(inc:Location)
          WHERE $include_simulated OR (coalesce(ir.simulated,false)=false AND coalesce(inc.simulated,false)=false)
        OPTIONAL MATCH (e)-[ps:PARENT_SEATED_IN]->(seat:Location)
          WHERE $include_simulated OR (coalesce(ps.simulated,false)=false AND coalesce(seat.simulated,false)=false)
        WITH e, {"tier" if root_id else "min(s.tier)"} AS tier, count(DISTINCT c) AS consumers, head(collect(DISTINCT inc.code)) AS inc, head(collect(DISTINCT seat.code)) AS seat,
             any(x IN collect(s.sole_source) WHERE x = true) AS sole_source
        // The ultimate parent is the root of the control chain, walked rather than looked up.
        CALL {{
          WITH e
          OPTIONAL MATCH path=(up:Entity)-[:OWNS|ULTIMATE_PARENT_OF*1..6]->(e)
          WHERE up.id <> e.id
            AND ($include_simulated OR (
              all(n IN nodes(path) WHERE coalesce(n.simulated,false)=false)
              AND all(r IN relationships(path) WHERE
                coalesce(r.simulated,false)=false
                AND (
                  r.claim_id IS NULL OR NOT EXISTS {{
                    MATCH (rc:Claim {{id:r.claim_id}})
                    WHERE coalesce(rc.simulated,false)
                      OR EXISTS {{
                        MATCH (ra:Artifact)-[:EVIDENCES]->(rc)
                        WHERE coalesce(ra.simulated,false)
                      }}
                      OR EXISTS {{
                        MATCH (:Artifact)-[re:EVIDENCES]->(rc)
                        WHERE coalesce(re.simulated,false)
                      }}
                  }}
                )
              )
            ))
            AND NOT EXISTS {{
              MATCH (owner:Entity)-[incoming:OWNS|ULTIMATE_PARENT_OF]->(up)
              WHERE $include_simulated OR (
                coalesce(owner.simulated,false)=false
                AND coalesce(incoming.simulated,false)=false
                AND coalesce(up.simulated,false)=false
                AND (
                  incoming.claim_id IS NULL OR NOT EXISTS {{
                    MATCH (ic:Claim {{id:incoming.claim_id}})
                    WHERE coalesce(ic.simulated,false)
                      OR EXISTS {{
                        MATCH (ia:Artifact)-[:EVIDENCES]->(ic)
                        WHERE coalesce(ia.simulated,false)
                      }}
                      OR EXISTS {{
                        MATCH (:Artifact)-[ie:EVIDENCES]->(ic)
                        WHERE coalesce(ie.simulated,false)
                      }}
                  }}
                )
              )
            }}
          RETURN up.name AS parent ORDER BY length(path), up.name LIMIT 1
        }}
        RETURN e.id AS id, e.name AS name, e.kind AS kind, e.uei AS uei, e.cage AS cage, e.lei AS lei, tier, consumers, inc AS incorporated, seat AS parent_seat, parent,
               sole_source, coalesce(e.flagged,false) AS flagged, coalesce(e.simulated,false) AS simulated, e.source AS source
        ORDER BY tier, name SKIP $offset LIMIT $limit
        """,
        params,
    )
    total = await db.read(total_query, params)
    return {"items": rows, "total": total[0]["n"] if total else 0}


@router.get("/people")
async def people(q: str | None = None, limit: int = Query(200, ge=1, le=1000)):
    params: dict = {"limit": limit, "include_simulated": load_workspace().include_simulated}
    clauses = ["($include_simulated OR coalesce(p.simulated,false)=false)"]
    if q:
        clauses.append("toLower(p.name) CONTAINS toLower($q)")
        params["q"] = q
    where = "WHERE " + " AND ".join(clauses)
    return await db.read(
        f"""
        MATCH (p:Person) {where}
        OPTIONAL MATCH (p)-[r:HELD_ROLE]->(e:Entity)
          WHERE $include_simulated OR (coalesce(r.simulated,false)=false AND coalesce(e.simulated,false)=false)
        WITH p, collect({{entity_id:e.id, lei:e.lei, entity:e.name, title:r.title, role_type:r.role_type, from:r.from, to:r.to, current:coalesce(r.current, r.to IS NULL), edge_id:r.id}}) AS roles
        RETURN p.id AS id, p.name AS name, p.source AS source, p.source_url AS source_url, coalesce(p.simulated,false) AS simulated, roles,
               size([x IN roles WHERE x.current]) AS current_roles, size(apoc.coll.toSet([x IN roles | coalesce(x.lei, x.entity_id)])) AS entities
        ORDER BY entities DESC, name LIMIT $limit
        """,
        params,
    )


@router.get("/artifacts")
async def artifacts(kind: str | None = None, entity_id: str | None = None, limit: int = Query(200, ge=1, le=1000)):
    where = ["($include_simulated OR coalesce(a.simulated,false)=false)"]
    params: dict = {"limit": limit, "include_simulated": load_workspace().include_simulated}
    if kind:
        where.append("a.kind = $kind")
        params["kind"] = kind
    if entity_id:
        where.append(
            "EXISTS { MATCH (a)-[scope:ABOUT]->(subject:Entity {id:$eid}) "
            "WHERE $include_simulated OR (coalesce(scope.simulated,false)=false "
            "AND coalesce(subject.simulated,false)=false) }"
        )
        params["eid"] = entity_id
    return await db.read(
        f"""
        MATCH (a:Artifact) WHERE {' AND '.join(where)}
        OPTIONAL MATCH (a)-[ab:ABOUT]->(e:Entity)
          WHERE $include_simulated OR (
            coalesce(ab.simulated,false)=false AND coalesce(e.simulated,false)=false
          )
        OPTIONAL MATCH (a)-[ev:EVIDENCES]->(c:Claim)
          WHERE $include_simulated OR (
            coalesce(ev.simulated,false)=false AND coalesce(c.simulated,false)=false
          )
        RETURN a.id AS id, a.kind AS kind, a.title AS title, a.url AS url, a.source AS source, a.source_id AS source_id,
               a.source_identifier AS source_identifier,
               a.catalog_ids AS catalog_ids, a.published_at AS published_at, a.retrieved_at AS retrieved_at,
               a.usage_note AS usage_note, a.quality_note AS quality_note, a.supports AS supports, a.unknowns AS unknowns,
               a.source_status AS source_status,
               a.connector_error AS connector_error, coalesce(a.simulated,false) AS simulated,
               a.amount AS amount, a.sentiment AS sentiment, collect(DISTINCT e{{.id,.name}})[..5] AS about,
               count(DISTINCT c) AS claims, collect(DISTINCT c.status) AS claim_statuses
        ORDER BY coalesce(a.published_at, a.retrieved_at) DESC LIMIT $limit
        """,
        params,
    )


@router.get("/artifacts/{artifact_id}")
async def artifact_detail(artifact_id: str):
    """One artifact with safe metadata and a derived summary.

    Cached upstream payloads remain server-side because they can contain fields
    outside the artifact's public classification.
    """
    rows = await db.read(
        """
        MATCH (a:Artifact {id:$id})
        WHERE $include_simulated OR coalesce(a.simulated,false)=false
        OPTIONAL MATCH (a)-[ab:ABOUT]->(e:Entity)
          WHERE $include_simulated OR (
            coalesce(ab.simulated,false)=false AND coalesce(e.simulated,false)=false
          )
        OPTIONAL MATCH (a)-[ev:EVIDENCES]->(c:Claim)
          WHERE $include_simulated OR (
            coalesce(ev.simulated,false)=false AND coalesce(c.simulated,false)=false
          )
        RETURN """ + _PUBLIC_ARTIFACT_PROJECTION + """ AS artifact, collect(DISTINCT e{.id,.name}) AS about,
               collect(DISTINCT c{.id,.predicate,.status,.confidence}) AS claims
        """,
        {"id": artifact_id, "include_simulated": load_workspace().include_simulated},
    )
    if not rows:
        raise HTTPException(404, "no such artifact")
    row = rows[0]
    raw = find_raw(artifact_id, row["artifact"] or {})
    return {**row, "summary": summarize(row["artifact"] or {}, raw)}


async def _artifact_props(artifact_id: str) -> dict:
    rows = await db.read(
        f"MATCH (a:Artifact {{id:$id}}) "
        f"WHERE $include_simulated OR coalesce(a.simulated,false)=false "
        f"RETURN {_PUBLIC_ARTIFACT_PROJECTION} AS artifact",
        {"id": artifact_id, "include_simulated": load_workspace().include_simulated},
    )
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
    include_simulated = load_workspace().include_simulated
    return await db.read(
        """
        MATCH (l:Location)
        WHERE $include_simulated OR coalesce(l.simulated,false)=false
        OPTIONAL MATCH (e:Entity)-[r:INCORPORATED_IN|OPERATES_IN|MANUFACTURES_IN|PARENT_SEATED_IN]->(l)
          WHERE $include_simulated OR (
            coalesce(e.simulated,false)=false AND coalesce(r.simulated,false)=false
          )
        RETURN l.id AS id, l.code AS code, l.name AS name, l.kind AS kind,
               size([x IN collect(type(r)) WHERE x='INCORPORATED_IN']) AS incorporated,
               size([x IN collect(type(r)) WHERE x='MANUFACTURES_IN']) AS manufactures,
               size([x IN collect(type(r)) WHERE x='PARENT_SEATED_IN']) AS parent_seats
        ORDER BY incorporated + manufactures + parent_seats DESC
        """,
        {"include_simulated": include_simulated},
    )


@router.get("/entities/{entity_id}/report")
async def report(entity_id: str, root_id: str | None = None, include_simulated: bool | None = None,
                 refresh: bool = True, user: str = Depends(user_id)):
    """root_id — the focused program, when there is one — is what tier_from_root counts to."""
    include_simulated = load_workspace().include_simulated and include_simulated is not False
    rep = await build_report(entity_id, root_id, include_simulated=include_simulated)
    if not rep:
        raise HTTPException(404, "no such entity")
    rep["analyst_decisions"] = await decisions.history(entity_id, program_id=root_id)
    if refresh and rep.get("identity", {}).get("kind") == "organization":
        known_jobs = set(worker.jobs)
        try:
            job = await worker.enqueue(
                entity_id, user=user, requested_by="report"
            )
            rep["refresh"] = {
                "status": "deduplicated" if job.id in known_jobs else "queued",
                "job_id": job.id,
                "job_status": job.status,
                "requested_at": job.created_at,
                "window_s": max(0.0, settings.enrichment_refresh_dedupe_window_s),
                "results": getattr(job, "results", {}),
            }
        except Exception:
            rep["refresh"] = {
                "status": "unavailable",
                "reason": "refresh could not be queued",
                "action": "Retry enrichment from the entity inspector.",
            }
    else:
        rep["refresh"] = {
            "status": "not_requested" if rep.get("identity", {}).get("kind") == "organization"
            else "not_applicable"
        }
    rep["source_mode"] = "live"
    rep["refresh_status"] = rep["refresh"]
    return rep


@router.get("/entities/{entity_id}/supply-chain", response_model=SupplyChainAnalysis)
async def supply_chain(entity_id: str):
    """Explainable, bounded supply-chain findings for a program/root entity."""
    analysis = await get_supply_chain_analysis(entity_id)
    if analysis is None:
        raise HTTPException(404, "no such program or root entity")
    return analysis


@router.post("/entities/{entity_id}/summary")
async def regenerate_summary(entity_id: str, user: str = Depends(user_id)):
    from ..config import settings
    from ..llm.tasks import summarize_entity
    rep = await build_report(entity_id)
    if not rep:
        raise HTTPException(404, "no such entity")
    try:
        out = await asyncio.wait_for(
            summarize_entity(user, rep),
            timeout=settings.summary_timeout_s,
        )
    except (asyncio.TimeoutError, TimeoutError):
        out = deterministic_summary(rep, "model_timeout")
    except Exception:
        out = deterministic_summary(rep, "model_unavailable_or_invalid")
    await persist_summary(entity_id, out)
    await events.announce([entity_id], reason="summary", source="ui")
    return out
