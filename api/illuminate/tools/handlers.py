"""One handler module behind both transports (D1). Every handler takes a
ToolContext and returns a ToolResult whose `data` is what the model sees and
whose subgraph/style_ops/cypher are what the UI draws."""
from __future__ import annotations


import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .. import db, events, links as applinks
from ..config import load_workspace
from ..cypher.templates import TEMPLATES
from ..cypher.validator import CypherRejected, validate
from ..graphio import merge_subgraphs, rows_clean, subgraph_from_graph
from ..ids import edge_id, entity_id as make_entity_id, location_id, normalize_name, artifact_id, claim_id, lucene_query, search_tokens
from ..report import build_report
from ..resolve import find_entity, fuzzy_candidates
from ..styles import derive_legend, validate_ops
from .permissions import gate


@dataclass
class ToolContext:
    source: str = "chat"            # chat | mcp | ui
    conversation_id: str | None = None
    user: str = "local"
    layers: dict | None = None
    # The program the canvas is currently narrowed to, sent per request by whoever is
    # looking at it. Nothing is focused by default: a workspace holds every program.
    focus_id: str | None = None
    focus_label: str | None = None
    # What the caller currently has drawn, when it has a canvas at all. An encoding applied
    # to the graph the user is looking at should count what is in front of them; an agent
    # over MCP has no canvas and gets the whole graph.
    canvas_ids: list[str] | None = None

    @classmethod
    def from_workspace(cls, **kw) -> "ToolContext":
        ws = load_workspace()
        return cls(layers=kw.pop("layers", None) or ws.layers, **kw)


@dataclass
class ToolResult:
    ok: bool
    data: Any                                   # compact, model-facing
    cypher: str | None = None
    params: dict | None = None
    subgraph: dict | None = None                # {nodes, edges}
    style_ops: list[dict] = field(default_factory=list)
    legend: list[dict] = field(default_factory=list)
    permission: dict | None = None              # decision summary when a write was involved
    # Where the user can go with what this produced — a report to open, a page to visit.
    # Rendered as buttons under the answer, so a deliverable is one click away (links.py).
    links: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def for_model(self, max_chars: int = 12000) -> str:
        payload = {"ok": self.ok, "data": self.data}
        if self.notes:
            payload["notes"] = self.notes
        if self.permission:
            payload["permission"] = self.permission
        if self.subgraph:
            payload["subgraph_summary"] = {"nodes": len(self.subgraph["nodes"]), "edges": len(self.subgraph["edges"])}
        s = json.dumps(payload, default=str)
        if len(s) > max_chars:
            s = s[: max_chars - 40] + '… (truncated; refine the query)"}'
        return s


def _compact_rows(rows: list[dict], limit: int = 60) -> list[dict]:
    out = []
    for r in rows[:limit]:
        c = {}
        for k, v in r.items():
            if isinstance(v, dict) and "props" in v and "id" in v:
                c[k] = {"id": v["id"], "name": v.get("name"), "label": v.get("label") or v.get("type")}
            elif isinstance(v, dict) and "nodes" in v and "edges" in v:
                c[k] = {"path_nodes": [n["id"] for n in v["nodes"]], "path_edges": [e["id"] for e in v["edges"]]}
            elif isinstance(v, list) and v and isinstance(v[0], dict) and "props" in v[0]:
                c[k] = [{"id": x["id"], "name": x.get("name")} for x in v[:40]]
            else:
                c[k] = v
        out.append(c)
    return out


def _subgraph_from_rows(rows: list[dict]) -> dict:
    """Pick node/edge/path dicts out of already-cleaned rows into a subgraph."""
    nodes, edges = {}, {}
    def take(v):
        if isinstance(v, dict):
            if "props" in v and "label" in v:
                nodes[v["id"]] = v
            elif "props" in v and "type" in v:
                edges[v["id"]] = v
            elif "nodes" in v and "edges" in v:
                for n in v["nodes"]:
                    nodes[n["id"]] = n
                for e in v["edges"]:
                    edges[e["id"]] = e
        elif isinstance(v, list):
            for x in v:
                take(x)
    for r in rows:
        for v in r.values():
            take(v)
    edges = {k: e for k, e in edges.items() if e.get("source") in nodes and e.get("target") in nodes}
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


# ---------------------------------------------------------------------------------
async def search_entities(ctx: ToolContext, query: str, kind: str = "any", limit: int = 10) -> ToolResult:
    q = (query or "").strip()
    limit = max(1, min(int(limit or 10), 50))
    rows: list[dict] = []
    toks = search_tokens(q)
    if toks:
        # identifier hits first — UEI/CAGE/LEI are stored upper-case without separators
        ident = re.sub(r"[^A-Za-z0-9]", "", q).upper()
        rows = await db.read(
            "MATCH (e:Entity) WHERE e.uei = $u OR e.cage = $u OR e.lei = $u RETURN e.id AS id, e.name AS name, 'Entity' AS label, e.uei AS uei, e.cage AS cage, e.lei AS lei, 1.0 AS score LIMIT 5",
            {"u": ident},
        )
        if not rows:
            try:
                rows = await db.read(
                    "CALL db.index.fulltext.queryNodes('entity_search', $q) YIELD node, score "
                    "RETURN node.id AS id, node.name AS name, head(labels(node)) AS label, node.uei AS uei, node.cage AS cage, node.lei AS lei, score "
                    "ORDER BY score DESC LIMIT $limit",
                    {"q": lucene_query(q), "limit": limit},
                )
            except Exception:
                rows = []
            if not rows:
                # substring fallback (fulltext index missing or nothing fuzzy-close): every word somewhere in name or aliases
                rows = await db.read(
                    "MATCH (n) WHERE (n:Entity OR n:Person) "
                    "AND all(t IN $toks WHERE toLower(coalesce(n.name, '') + ' ' + coalesce(n.aliases_text, '')) CONTAINS t) "
                    "RETURN n.id AS id, n.name AS name, head(labels(n)) AS label, n.uei AS uei, n.cage AS cage, n.lei AS lei, 0.5 AS score LIMIT $limit",
                    {"toks": toks, "limit": limit},
                )
    if kind == "entity":
        rows = [r for r in rows if r["label"] == "Entity"]
    elif kind == "person":
        rows = [r for r in rows if r["label"] == "Person"]
    return ToolResult(ok=True, data={"query": q, "results": rows[:limit]})


async def expand_subgraph(ctx: ToolContext, entity_id: str, depth: int = 2, layers: dict | None = None, program_id: str | None = None) -> ToolResult:
    t = TEMPLATES["neighbourhood"]
    params = {"entity_id": entity_id, "depth": depth, "layers": {**(ctx.layers or {}), **(layers or {})},
              "program_id": program_id or ctx.focus_id}
    cy, bound = t.build(params)
    v = validate(cy, params=bound)
    records, graph, _ = await db.read_graph(v.statement, bound)
    rows = rows_clean(records)
    sub = subgraph_from_graph(graph)
    if rows and isinstance(rows[0].get("nodes"), list):
        sub = merge_subgraphs(sub, {"nodes": rows[0]["nodes"], "edges": rows[0].get("relationships", [])})
    return ToolResult(
        ok=True,
        data={"entity_id": entity_id, "nodes": [{"id": n["id"], "name": n["name"], "label": n["label"]} for n in sub["nodes"][:150]],
              "edges": [{"id": e["id"], "type": e["type"], "source": e["source"], "target": e["target"]} for e in sub["edges"][:200]]},
        cypher=v.statement, params=bound, subgraph=sub,
    )


async def run_template(ctx: ToolContext, name: str, params: dict | None = None, apply_styles: bool = True) -> ToolResult:
    t = TEMPLATES.get(name)
    if not t:
        return ToolResult(ok=False, data={"error": f"unknown template {name}", "templates": list(TEMPLATES)})
    p = dict(params or {})
    # A template's "root" is whatever the canvas is focused on; with nothing focused the
    # caller has to name the entity, and the missing-params error below says so.
    if "root_id" in t.required and not p.get("root_id"):
        p["root_id"] = ctx.focus_id
    if "entity_id" in t.required and not p.get("entity_id") and ctx.focus_id:
        p["entity_id"] = ctx.focus_id
    missing = [r for r in t.required if not p.get(r)]
    if missing:
        return ToolResult(ok=False, data={"error": f"missing params: {missing}", "schema": t.schema()})
    p.setdefault("layers", ctx.layers or {})
    try:
        cy, bound = t.build(p)
        v = validate(cy, params=bound)
    except (CypherRejected, KeyError) as e:
        return ToolResult(ok=False, data={"error": str(e)})
    records, graph, _ = await db.read_graph(v.statement, bound)
    rows = rows_clean(records)
    sub = merge_subgraphs(subgraph_from_graph(graph), _subgraph_from_rows(rows))
    ops: list[dict] = []
    if apply_styles and t.style:
        ops = [o.model_dump(exclude_none=True) for o in validate_ops(t.style(rows, p))]
    legend = [l.model_dump() for l in derive_legend(validate_ops(ops))] if ops else []
    return ToolResult(ok=True, data={"template": name, "row_count": len(rows), "rows": _compact_rows(rows)}, cypher=v.statement, params=bound,
                      subgraph=sub, style_ops=ops, legend=legend, notes=v.notes)


async def run_cypher(ctx: ToolContext, statement: str, params: dict | None = None, rationale: str | None = None) -> ToolResult:
    params = dict(params or {})
    try:
        v = validate(statement, params=params)
    except CypherRejected as e:
        return ToolResult(ok=False, data={"error": f"rejected by validator: {e.reason}"}, cypher=statement, params=params)
    if v.classification == "SCHEMA":
        return ToolResult(ok=False, data={"error": "schema changes are not available through tools"}, cypher=v.statement)
    if v.is_read:
        try:
            records, graph, _ = await db.read_graph(v.statement, params)
        except Exception as e:
            return ToolResult(ok=False, data={"error": f"query failed: {e}"}, cypher=v.statement, params=params)
        rows = rows_clean(records)
        sub = merge_subgraphs(subgraph_from_graph(graph), _subgraph_from_rows(rows))
        return ToolResult(ok=True, data={"classification": "READ", "row_count": len(rows), "rows": _compact_rows(rows)},
                          cypher=v.statement, params=params, subgraph=sub, notes=v.notes)
    decision = await gate.request(v, params, source=ctx.source, conversation_id=ctx.conversation_id, tool="run_cypher", rationale=rationale)
    perm = {"status": decision.status, "request_id": decision.request_id, "reason": decision.reason}
    if decision.status == "executed":
        return ToolResult(ok=True, data={"classification": v.classification, "counters": decision.result["counters"], "rows": decision.result["rows"][:20]},
                          cypher=v.statement, params=params, permission=perm)
    return ToolResult(ok=False, data={"classification": v.classification, "error": f"write {decision.status}: {decision.reason or ''}".strip()},
                      cypher=v.statement, params=params, permission=perm)


async def set_styles(ctx: ToolContext, ops: list[dict]) -> ToolResult:
    try:
        vops = validate_ops(ops)
    except Exception as e:
        return ToolResult(ok=False, data={"error": f"invalid style ops: {e}"})
    dumped = [o.model_dump(exclude_none=True) for o in vops]
    legend = [l.model_dump() for l in derive_legend(vops)]
    return ToolResult(ok=True, data={"applied": len(dumped), "legend": legend}, style_ops=dumped, legend=legend)


async def generate_report(ctx: ToolContext, subject_id: str | None = None, kind: str | None = None) -> ToolResult:
    """Write a report into the graph and hand the canvas the node it just made.

    The subject defaults to whatever program the canvas is focused on, because "write me a
    risk assessment" almost always means the thing on screen; with nothing focused the
    caller has to name one, and says so rather than guessing at a program.
    """
    from .. import reports as reports_mod

    kind = kind or reports_mod.DEFAULT_KIND
    subject_id = subject_id or ctx.focus_id
    if not subject_id:
        return ToolResult(ok=False, data={
            "error": "no subject: name the entity to report on, or focus the canvas on a program first",
            "kinds": reports_mod.kinds()})
    try:
        row = await reports_mod.generate(kind, subject_id, user=ctx.user)
    except reports_mod.ReportError as e:
        return ToolResult(ok=False, data={"error": str(e), "kinds": reports_mod.kinds()})
    # The report and its subject, one hop out: the node the user asked for is drawn beside
    # what it is about without a reload, the same way a committed write announces itself.
    sub = await events.delta_for([row["id"]])
    return ToolResult(
        ok=True,
        data={**row, "note": "Stored as a Report node in the graph and listed on the Reports tab. Its properties "
                             "carry the generation time and a regenerate control; regenerating rewrites this same "
                             "report from current data. A button to open it is already under your answer, so name "
                             "the report rather than repeating the link."},
        subgraph=sub,
        # The whole point of writing a document is reading it: the answer carries the door.
        links=applinks.dump([applinks.report(row["id"], row["title"], subject_name=row.get("subject_name"))]),
    )


async def get_entity_report(ctx: ToolContext, entity_id: str) -> ToolResult:
    rep = await build_report(entity_id, ctx.focus_id)
    if not rep:
        return ToolResult(ok=False, data={"error": f"no entity {entity_id}"})
    compact = {
        "identity": rep["identity"], "geography": rep["geography"], "control": rep["control"], "categories": rep["categories"],
        "supply": {k: rep["supply"][k] for k in ("tier_from_root", "suppliers_count", "sole_source_edges", "awards")},
        "supplies": rep["supply"]["supplies"][:10],
        "people": {"current": [{k: p[k] for k in ("name", "title", "role_type", "from", "interlock")} for p in rep["people"]["current"][:12]],
                   "former": [{k: p[k] for k in ("name", "title", "from", "to", "moved_to_flagged")} for p in rep["people"]["former"][:12]]},
        "risk": rep["risk"], "screens": rep["screens"], "news": rep["news"][:5], "sources": rep["sources"], "summary": rep["summary"]["text"],
    }
    name = rep["identity"].get("name") or entity_id
    return ToolResult(ok=True, data=compact,
                      links=applinks.dump([applinks.entity(entity_id, name), applinks.canvas(entity_id, name)]))


def _loc(code: str) -> tuple[str, str]:
    code = code.strip().upper()
    return location_id(code), code


async def propose_entity(ctx: ToolContext, name: str, kind: str = "organization", uei: str | None = None, cage: str | None = None, lei: str | None = None,
                         aliases: list[str] | None = None, keywords: list[str] | None = None, incorporated_in: str | None = None, manufactures_in: list[str] | None = None,
                         operates_in: list[str] | None = None, provides: list[str] | None = None, supplies_to: dict | None = None,
                         owned_by: dict | None = None, source_url: str | None = None, rationale: str | None = None) -> ToolResult:
    existing = await find_entity(uei=uei, cage=cage, lei=lei, name=name)
    if existing and existing.confidence >= 0.9 and not (supplies_to or owned_by or provides or manufactures_in or keywords):
        return ToolResult(ok=True, data={"resolved_existing": {"id": existing.id, "name": existing.name, "method": existing.method, "confidence": existing.confidence},
                                          "note": "entity already exists; nothing written"})
    eid = existing.id if (existing and existing.confidence >= 0.9) else make_entity_id(uei=uei, lei=lei, cage=cage, name=name)
    cands = [] if existing else await fuzzy_candidates(name)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    prov = {"source": "user" if ctx.source != "mcp" else "mcp", "source_url": source_url, "retrieved_at": now, "method": "proposed", "confidence": 0.7}
    params: dict[str, Any] = {"id": eid, "name": name, "name_norm": normalize_name(name), "kind": kind, "uei": (uei or None) and uei.upper(),
                              "cage": (cage or None) and cage.upper(), "lei": (lei or None) and lei.upper(),
                              "aliases": aliases or [], "aliases_norm": [normalize_name(a) for a in (aliases or [])], **prov}
    parts = [
        "MERGE (e:Entity {id:$id})",
        "ON CREATE SET e.name=$name, e.name_norm=$name_norm, e.kind=$kind, e.uei=$uei, e.cage=$cage, e.lei=$lei, e.aliases=$aliases, e.aliases_norm=$aliases_norm,",
        "  e.source=$source, e.source_url=$source_url, e.retrieved_at=$retrieved_at, e.method=$method, e.confidence=$confidence",
    ]
    kws = [k.strip() for k in (keywords or []) if isinstance(k, str) and k.strip()]
    if kws and kind == "program":
        # a program's award designations: what discover_suppliers searches on later
        params["keywords"] = kws
        parts.append("SET e.keywords = $keywords")
    if incorporated_in:
        lid, code = _loc(incorporated_in)
        params.update({"inc_id": lid, "inc_code": code, "inc_rid": edge_id()})
        parts += ["MERGE (inc:Location {id:$inc_id}) ON CREATE SET inc.code=$inc_code, inc.name=$inc_code, inc.kind=CASE WHEN size($inc_code)=2 THEN 'country' ELSE 'region' END",
                  "MERGE (e)-[ri:INCORPORATED_IN]->(inc) ON CREATE SET ri.id=$inc_rid, ri.source=$source, ri.source_url=$source_url, ri.retrieved_at=$retrieved_at, ri.method=$method, ri.confidence=$confidence"]
    for i, code in enumerate(manufactures_in or []):
        lid, c = _loc(code)
        params.update({f"mfg_id{i}": lid, f"mfg_code{i}": c, f"mfg_rid{i}": edge_id()})
        parts += [f"MERGE (m{i}:Location {{id:$mfg_id{i}}}) ON CREATE SET m{i}.code=$mfg_code{i}, m{i}.name=$mfg_code{i}, m{i}.kind=CASE WHEN size($mfg_code{i})=2 THEN 'country' ELSE 'region' END",
                  f"MERGE (e)-[rm{i}:MANUFACTURES_IN]->(m{i}) ON CREATE SET rm{i}.id=$mfg_rid{i}, rm{i}.source=$source, rm{i}.source_url=$source_url, rm{i}.retrieved_at=$retrieved_at, rm{i}.method=$method, rm{i}.confidence=$confidence"]
    for i, code in enumerate(operates_in or []):
        lid, c = _loc(code)
        params.update({f"op_id{i}": lid, f"op_code{i}": c, f"op_rid{i}": edge_id()})
        parts += [f"MERGE (o{i}:Location {{id:$op_id{i}}}) ON CREATE SET o{i}.code=$op_code{i}, o{i}.name=$op_code{i}, o{i}.kind=CASE WHEN size($op_code{i})=2 THEN 'country' ELSE 'region' END",
                  f"MERGE (e)-[ro{i}:OPERATES_IN]->(o{i}) ON CREATE SET ro{i}.id=$op_rid{i}, ro{i}.source=$source, ro{i}.retrieved_at=$retrieved_at, ro{i}.method=$method, ro{i}.confidence=$confidence"]
    for i, cid in enumerate(provides or []):
        params.update({f"cat{i}": cid, f"cat_rid{i}": edge_id()})
        parts += [f"WITH e MATCH (c{i}:Category {{id:$cat{i}}}) MERGE (e)-[rp{i}:PROVIDES]->(c{i}) ON CREATE SET rp{i}.id=$cat_rid{i}, rp{i}.source=$source, rp{i}.retrieved_at=$retrieved_at, rp{i}.method=$method, rp{i}.confidence=$confidence"]
    if supplies_to and supplies_to.get("entity_id"):
        params.update({"to_id": supplies_to["entity_id"], "tier": int(supplies_to.get("tier") or 1), "sole": bool(supplies_to.get("sole_source", False)),
                       "contract_ref": supplies_to.get("contract_ref"), "sup_rid": edge_id()})
        parts += ["WITH e MATCH (c:Entity {id:$to_id})",
                  "MERGE (e)-[s:SUPPLIES]->(c) ON CREATE SET s.id=$sup_rid, s.tier=$tier, s.sole_source=$sole, s.contract_ref=$contract_ref, s.source=$source, s.source_url=$source_url, s.retrieved_at=$retrieved_at, s.method=$method, s.confidence=$confidence"]
    if owned_by and owned_by.get("entity_id"):
        params.update({"own_id": owned_by["entity_id"], "pct": owned_by.get("pct"), "own_rid": edge_id(), "own_rid2": edge_id()})
        parts += ["WITH e MATCH (p:Entity {id:$own_id})",
                  "MERGE (p)-[o:OWNS]->(e) ON CREATE SET o.id=$own_rid, o.pct=$pct, o.source=$source, o.source_url=$source_url, o.retrieved_at=$retrieved_at, o.method=$method, o.confidence=$confidence"]
        if owned_by.get("ultimate"):
            parts += ["MERGE (p)-[u:ULTIMATE_PARENT_OF]->(e) ON CREATE SET u.id=$own_rid2, u.source=$source, u.retrieved_at=$retrieved_at, u.method=$method, u.confidence=$confidence"]
    parts.append("RETURN e.id AS id")
    statement = "\n".join(parts)
    try:
        v = validate(statement, params=params)
    except CypherRejected as e:
        return ToolResult(ok=False, data={"error": f"internal statement rejected: {e.reason}"}, cypher=statement)
    rat = rationale or f"Add {name}" + (f" as tier-{supplies_to.get('tier', 1)} supplier" if supplies_to else "")
    decision = await gate.request(v, params, source=ctx.source, conversation_id=ctx.conversation_id, tool="propose_entity", rationale=rat)
    perm = {"status": decision.status, "request_id": decision.request_id, "reason": decision.reason}
    if decision.status == "executed":
        data = {"entity_id": eid, "counters": decision.result["counters"], "resolved_existing": existing.__dict__ if existing else None}
        if cands:
            data["possible_duplicates"] = cands
        sub = None
        try:
            r = await expand_subgraph(ctx, eid, depth=1)
            sub = r.subgraph
        except Exception:
            pass
        return ToolResult(ok=True, data=data, cypher=v.statement, params=params, permission=perm, subgraph=sub)
    return ToolResult(ok=False, data={"error": f"write {decision.status}: {decision.reason or ''}".strip(), "possible_duplicates": cands}, cypher=v.statement, params=params, permission=perm)


async def attach_evidence(ctx: ToolContext, subject_id: str, predicate: str, source_url: str, object_id: str | None = None, object_value: str | None = None,
                          title: str | None = None, source: str = "user", confidence: float = 0.7, note: str | None = None) -> ToolResult:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    params = {"sid": subject_id, "pred": predicate, "oid": object_id, "oval": object_value, "url": source_url, "title": title or source_url,
              "source": source, "conf": float(confidence), "note": note, "now": now, "cid": claim_id(), "aid": artifact_id(source_url), "rid1": edge_id(), "rid2": edge_id(), "rid3": edge_id()}
    stmt = [
        "MATCH (s) WHERE s.id = $sid",
        "MERGE (c:Claim {id:$cid}) ON CREATE SET c.predicate=$pred, c.subject_id=$sid, c.object_id=$oid, c.object_value=$oval, c.source=$source, c.source_url=$url,",
        "  c.method='human', c.confidence=$conf, c.status='committed', c.retrieved_at=$now, c.detail=$note",
        "MERGE (c)-[ra:ASSERTS]->(s) ON CREATE SET ra.id=$rid1",
        "MERGE (a:Artifact {id:$aid}) ON CREATE SET a.url=$url, a.title=$title, a.kind='document', a.source=$source, a.retrieved_at=$now",
        "MERGE (a)-[re:EVIDENCES]->(c) ON CREATE SET re.id=$rid2",
        "MERGE (a)-[rb:ABOUT]->(s) ON CREATE SET rb.id=$rid3",
    ]
    if object_id:
        stmt += ["WITH c, s, a MATCH (o) WHERE o.id = $oid MERGE (c)-[rt:TARGETS]->(o) ON CREATE SET rt.id=$rid3"]
    stmt.append("RETURN c.id AS claim_id, a.id AS artifact_id")
    statement = "\n".join(stmt)
    v = validate(statement, params=params)
    decision = await gate.request(v, params, source=ctx.source, conversation_id=ctx.conversation_id, tool="attach_evidence", rationale=f"Attach evidence: {predicate} on {subject_id}")
    perm = {"status": decision.status, "request_id": decision.request_id, "reason": decision.reason}
    if decision.status == "executed":
        return ToolResult(ok=True, data={"claim_id": params["cid"], "artifact_id": params["aid"], "counters": decision.result["counters"]}, cypher=v.statement, params=params, permission=perm)
    return ToolResult(ok=False, data={"error": f"write {decision.status}: {decision.reason or ''}".strip()}, cypher=v.statement, params=params, permission=perm)


async def discover_suppliers(ctx: ToolContext, entity_id: str, keywords: list[str], agency: str | None = None, since: str | None = None,
                             until: str | None = None, max_primes: int | None = None, max_subs: int | None = None,
                             rationale: str | None = None) -> ToolResult:
    """Grow a program's supply network from award records. The search itself lives in
    the USAspending connector; this writes the parameters onto the program — so the
    discovery is repeatable and its terms are visible next to its results — and queues
    the job. The write goes through the gate like every other one."""
    from ..connectors.usaspending import program_search
    from ..enrichment.worker import worker

    rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": entity_id})
    if not rows:
        return ToolResult(ok=False, data={"error": f"no entity {entity_id}"})
    ent = rows[0]["e"]
    kind = ent.get("kind") or "organization"
    if kind != "program":
        return ToolResult(ok=False, data={"error": f"{ent.get('name')} is a {kind}, not a program",
                                          "hint": "discover_suppliers searches awards by program keyword; for a company use enrich_entity"})
    kws = [k.strip() for k in (keywords or []) if isinstance(k, str) and k.strip()]
    if not kws:
        return ToolResult(ok=False, data={"error": "keywords are required", "hint": "the designation the contracts carry, e.g. ['E-2D']"})

    # Only the parameters actually given are written; the rest are left to the connector's
    # defaults rather than frozen onto the node, so a default can still change under them.
    params: dict[str, Any] = {"id": entity_id, "keywords": kws}
    sets = ["e.keywords = $keywords"]
    optional = (("award_since", "since", since or None), ("award_until", "until", until or None), ("award_agency", "agency", agency),
                ("max_primes", "max_primes", int(max_primes) if max_primes else None),
                ("max_subs", "max_subs", int(max_subs) if max_subs is not None else None))
    for prop, key, value in optional:
        if value is not None:
            params[key] = value
            sets.append(f"e.{prop} = ${key}")
    statement = "MATCH (e:Entity {id:$id})\nWHERE e.kind = 'program'\nSET " + ", ".join(sets) + "\nRETURN e.id AS id"
    try:
        v = validate(statement, params=params)
    except CypherRejected as e:
        return ToolResult(ok=False, data={"error": f"internal statement rejected: {e.reason}"}, cypher=statement)
    rat = rationale or f"Search federal awards for {', '.join(kws)} and attach the recipients as suppliers of {ent.get('name')}"
    decision = await gate.request(v, params, source=ctx.source, conversation_id=ctx.conversation_id, tool="discover_suppliers", rationale=rat)
    perm = {"status": decision.status, "request_id": decision.request_id, "reason": decision.reason}
    if decision.status != "executed":
        return ToolResult(ok=False, data={"error": f"write {decision.status}: {decision.reason or ''}".strip()}, cypher=v.statement, params=params, permission=perm)

    fresh = (await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": entity_id}))[0]["e"]
    cfg = program_search(fresh)
    job = await worker.enqueue(entity_id, connectors=["usaspending"], user=ctx.user, requested_by=ctx.source)
    return ToolResult(ok=True, data={"job_id": job.id, "program": {"id": entity_id, "name": ent.get("name")}, "search": cfg, "status": job.status,
                                     "note": "Prime recipients arrive as tier-1 suppliers and reported sub-awardees as tier-2, each with its award record as evidence. "
                                             "Suppliers land with a name and UEI only — run enrich_entity on the ones that matter for identity, ownership, geography and screens."},
                      cypher=v.statement, params=params, permission=perm)


async def apply_color_scheme(ctx: ToolContext, scheme: str, ids: list[str] | None = None) -> ToolResult:
    """Paint the canvas with a preset encoding instead of deriving one.

    The buckets and the ramp live in schemes.py, so "colour by risk" is one call rather
    than a query, a mapping and a set_styles the model has to get right again every time.

    With no ids the scheme covers what the caller has on the canvas, so the legend counts
    what the user can actually see; a caller with no canvas gets the whole graph.
    """
    from .. import schemes

    try:
        out = await schemes.apply(scheme, ids if ids is not None else ctx.canvas_ids)
    except schemes.UnknownScheme:
        return ToolResult(ok=False, data={"error": f"unknown scheme {scheme!r}", "schemes": schemes.catalog()})
    return ToolResult(
        ok=True,
        data={"scheme": out["scheme"], "node_count": out["node_count"], "legend": out["legend"], "note": out["note"]},
        style_ops=out["style_ops"], legend=out["legend"],
    )


async def enrich_entity(ctx: ToolContext, entity_id: str, connectors: list[str] | None = None) -> ToolResult:
    from ..enrichment.worker import worker
    rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e.id AS id, e.name AS name", {"id": entity_id})
    if not rows:
        return ToolResult(ok=False, data={"error": f"no entity {entity_id}"})
    job = await worker.enqueue(entity_id, connectors=connectors, user=ctx.user, requested_by=ctx.source)
    return ToolResult(ok=True, data={"job_id": job.id, "entity": rows[0], "connectors": job.connectors, "status": job.status,
                                     "note": "Facts arrive as Claims. Authoritative connectors auto-commit; open-web facts wait for review."})


HANDLERS = {
    "search_entities": search_entities,
    "expand_subgraph": expand_subgraph,
    "run_template": run_template,
    "run_cypher": run_cypher,
    "propose_entity": propose_entity,
    "attach_evidence": attach_evidence,
    "set_styles": set_styles,
    "apply_color_scheme": apply_color_scheme,
    "generate_report": generate_report,
    "get_entity_report": get_entity_report,
    "discover_suppliers": discover_suppliers,
    "enrich_entity": enrich_entity,
}


async def dispatch(ctx: ToolContext, name: str, args: dict) -> ToolResult:
    fn = HANDLERS.get(name)
    if not fn:
        return ToolResult(ok=False, data={"error": f"unknown tool {name}"})
    try:
        return await fn(ctx, **(args or {}))
    except TypeError as e:
        return ToolResult(ok=False, data={"error": f"bad arguments for {name}: {e}"})
    except Exception as e:  # never let a handler take the transport down
        return ToolResult(ok=False, data={"error": f"{type(e).__name__}: {e}"})
