"""Parameterised templates for the named intents (D3).

Templates are faster and more reliable than free generation, so they are the
default and free generation is the fallback. Each template owns its Cypher and
knows how to turn its rows into style_ops.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import settings

MAX_DEPTH = settings.cypher_max_hops
MAX_SUBGRAPH_NODES = 1000


def _depth(v, default=3) -> int:
    try:
        d = int(v)
    except Exception:
        d = default
    return max(1, min(MAX_DEPTH, d))


def _subgraph_limit(v, default=400) -> int:
    try:
        limit = int(v)
    except (TypeError, ValueError):
        limit = default
    return max(1, min(MAX_SUBGRAPH_NODES, limit))


@dataclass
class Template:
    name: str
    description: str
    params: dict[str, dict]  # JSON-schema properties
    required: list[str]
    build: Callable[[dict], tuple[str, dict]]  # -> (cypher, bound params)
    style: Callable[[list[dict], dict], list[dict]] | None = None  # rows -> style_ops
    patterns: list[re.Pattern] = field(default_factory=list)  # regex fallback for no-key mode

    def schema(self) -> dict:
        return {"type": "object", "properties": self.params, "required": self.required}


# --- builders ---------------------------------------------------------------------

def _vendors_of(p):
    d = _depth(p.get("depth", 3))
    cy = (
        f"MATCH (root:Entity {{id:$id}})\n"
        f"MATCH path=(v:Entity)-[:SUPPLIES*1..{d}]->(root)\n"
        "WITH root, path, v, length(path) AS tier\n"
        "RETURN v.id AS id, v.name AS name, min(tier) AS tier, path\n"
        "ORDER BY tier, name LIMIT 500"
    )
    return cy, {"id": p["entity_id"]}


def _color_by_category(p):
    d = _depth(p.get("depth", 1))
    cy = (
        f"MATCH (root:Entity {{id:$id}})\n"
        f"MATCH path=(v:Entity)-[:SUPPLIES*1..{d}]->(root)\n"
        "OPTIONAL MATCH (v)-[:PROVIDES]->(c:Category)\n"
        "OPTIONAL MATCH (c)-[:SUBCATEGORY_OF*0..4]->(top:Category) WHERE NOT (top)-[:SUBCATEGORY_OF]->()\n"
        "RETURN v.id AS id, v.name AS name, collect(DISTINCT coalesce(top.kind, c.kind)) AS kinds, collect(DISTINCT path) AS paths\n"
        "LIMIT 500"
    )
    return cy, {"id": p["entity_id"]}


def _color_by_category_style(rows, p):
    goods = [r["id"] for r in rows if "goods" in (r.get("kinds") or []) ]
    services = [r["id"] for r in rows if "services" in (r.get("kinds") or []) and "goods" not in (r.get("kinds") or [])]
    both = [r["id"] for r in rows if "goods" in (r.get("kinds") or []) and "services" in (r.get("kinds") or [])]
    unknown = [r["id"] for r in rows if not (r.get("kinds") or [None])[0]]
    ops = [{"op": "clear", "scope": "all"}]
    if goods:
        ops.append({"op": "set", "ids": goods, "style": {"fill": p.get("goods_color", "purple"), "badge": "goods"}, "label": "Goods"})
    if services:
        ops.append({"op": "set", "ids": services, "style": {"fill": p.get("services_color", "yellow"), "badge": "services"}, "label": "Services"})
    if both:
        ops.append({"op": "set", "ids": both, "style": {"badge": "both"}, "label": "Goods + services"})
    if unknown:
        ops.append({"op": "dim", "ids": unknown})
    return ops


def _manufactures_in(p):
    d = _depth(p.get("depth", MAX_DEPTH))
    min_tier = int(p.get("min_tier", 1) or 1)
    cy = (
        f"MATCH (root:Entity {{id:$root}})\n"
        f"MATCH path=(v:Entity)-[:SUPPLIES*1..{d}]->(root)\n"
        "WITH v, min(length(path)) AS tier, collect(path)[0] AS path\n"
        "WHERE tier >= $min_tier\n"
        "MATCH (v)-[m:MANUFACTURES_IN]->(l:Location)\n"
        "WHERE l.code = $country OR l.code STARTS WITH ($country + '-') OR toLower(l.name) = toLower($country)\n"
        "RETURN v.id AS id, v.name AS name, tier, l.code AS location, path, m\n"
        "ORDER BY tier LIMIT 500"
    )
    return cy, {"root": p["root_id"], "country": p["country"].upper() if len(p["country"]) <= 3 else p["country"], "min_tier": min_tier}


def _manufactures_in_style(rows, p):
    ids = [r["id"] for r in rows]
    edge_ids = [r["m"]["id"] for r in rows if isinstance(r.get("m"), dict) and r["m"].get("id")]
    return [
        {"op": "clear", "scope": "all"},
        {"op": "set", "ids": ids, "style": {"fill": p.get("color", "red"), "badge": f"mfg {p['country']}"}, "label": f"Manufactures in {p['country']}"},
        {"op": "highlight", "ids": edge_ids, "style": {"stroke": p.get("color", "red")}, "label": "MANUFACTURES_IN"},
    ]


def _ownership_chain(p):
    cy = (
        "MATCH (e:Entity {id:$id})\n"
        f"OPTIONAL MATCH up=(e)<-[:OWNS|ULTIMATE_PARENT_OF*1..{MAX_DEPTH}]-(parent:Entity)\n"
        f"OPTIONAL MATCH down=(e)-[:OWNS*1..{MAX_DEPTH}]->(child:Entity)\n"
        "OPTIONAL MATCH (parent)-[inc:INCORPORATED_IN]->(pl:Location)\n"
        "RETURN e.id AS id, e.name AS name, up, down, parent.id AS parent_id, parent.name AS parent_name, pl.code AS parent_country\n"
        "LIMIT 200"
    )
    return cy, {"id": p["entity_id"]}


def _ownership_style(rows, p):
    parents = sorted({r["parent_id"] for r in rows if r.get("parent_id")})
    return [
        {"op": "set", "ids": [p["entity_id"]], "style": {"fill": "blue", "size": "lg"}, "label": "Subject"},
        {"op": "set", "ids": parents, "style": {"fill": "orange", "badge": "owner"}, "label": "Owners / parents"},
    ]


def _shared_directors(p):
    d = _depth(p.get("depth", MAX_DEPTH))
    cy = (
        f"MATCH (root:Entity {{id:$root}})\n"
        f"OPTIONAL MATCH (v:Entity)-[:SUPPLIES*1..{d}]->(root)\n"
        "WITH root, collect(DISTINCT v) AS vs\n"
        "WITH vs + [root] AS members\n"
        "UNWIND members AS a\n"
        "MATCH (per:Person)-[r1:HELD_ROLE]->(a)\n"
        "MATCH (per)-[r2:HELD_ROLE]->(b:Entity) WHERE b IN members AND a.id < b.id AND (a.lei IS NULL OR b.lei IS NULL OR a.lei <> b.lei)\n"
        "RETURN per.id AS person_id, per.name AS person, a.id AS a_id, a.name AS a, b.id AS b_id, b.name AS b, "
        "r1.title AS a_title, r1.current AS a_current, r2.title AS b_title, r2.current AS b_current, r1, r2, per, a AS a_node, b AS b_node\n"
        "LIMIT 200"
    )
    return cy, {"root": p["root_id"]}


def _shared_directors_style(rows, p):
    people = sorted({r["person_id"] for r in rows})
    ents = sorted({r["a_id"] for r in rows} | {r["b_id"] for r in rows})
    edges = sorted({r["r1"]["id"] for r in rows if isinstance(r.get("r1"), dict)} | {r["r2"]["id"] for r in rows if isinstance(r.get("r2"), dict)})
    return [
        {"op": "set", "ids": people, "style": {"fill": "teal", "shape": "diamond", "badge": "interlock"}, "label": "Shared director / officer"},
        {"op": "set", "ids": ents, "style": {"stroke": "teal"}, "label": "Entities sharing a person"},
        {"op": "highlight", "ids": edges, "style": {"stroke": "teal", "dashed": True}, "label": "HELD_ROLE"},
    ]


def _sole_source(p):
    d = _depth(p.get("depth", MAX_DEPTH))
    cy = (
        f"MATCH (root:Entity {{id:$root}})\n"
        f"MATCH path=(v:Entity)-[:SUPPLIES*1..{d}]->(root)\n"
        "WITH v, path, relationships(path)[0] AS r\n"
        "WHERE r.sole_source = true\n"
        "RETURN DISTINCT v.id AS id, v.name AS name, r.tier AS tier, r.psc AS psc, r.contract_ref AS contract_ref, r AS edge, path\n"
        "LIMIT 500"
    )
    return cy, {"root": p["root_id"]}


def _sole_source_style(rows, p):
    ids = [r["id"] for r in rows]
    edges = [r["edge"]["id"] for r in rows if isinstance(r.get("edge"), dict) and r["edge"].get("id")]
    return [
        {"op": "set", "ids": ids, "style": {"fill": "orange", "badge": "sole source"}, "label": "Sole-source suppliers"},
        {"op": "highlight", "ids": edges, "style": {"stroke": "orange"}, "label": "Sole-source award"},
    ]


def _foreign_parent(p):
    d = _depth(p.get("depth", MAX_DEPTH))
    cy = (
        f"MATCH (root:Entity {{id:$root}})\n"
        f"MATCH path=(v:Entity)-[:SUPPLIES*1..{d}]->(root)\n"
        "MATCH (v)-[ps:PARENT_SEATED_IN]->(l:Location)\n"
        "WHERE NOT l.code STARTS WITH $home\n"
        "OPTIONAL MATCH up=(v)<-[:OWNS|ULTIMATE_PARENT_OF*1..4]-(parent:Entity)\n"
        "RETURN DISTINCT v.id AS id, v.name AS name, l.code AS parent_country, min(length(path)) AS tier, path, up, ps\n"
        "LIMIT 500"
    )
    return cy, {"root": p["root_id"], "home": (p.get("home_country") or "US").upper()}


def _foreign_parent_style(rows, p):
    ids = [r["id"] for r in rows]
    return [
        {"op": "set", "ids": ids, "style": {"fill": "red", "badge": "foreign parent"}, "label": "Foreign ultimate parent"},
    ]


def _people_of(p):
    cy = (
        "MATCH (e:Entity {id:$id})<-[r:HELD_ROLE]-(per:Person)\n"
        "RETURN per.id AS person_id, per.name AS person, r.title AS title, r.role_type AS role_type, r.from AS from, r.to AS to, r.current AS current, r, per, e\n"
        "ORDER BY r.current DESC, r.from DESC LIMIT 200"
    )
    return cy, {"id": p["entity_id"]}


def _as_of_board(p):
    cy = (
        "MATCH (e:Entity {id:$id})<-[r:HELD_ROLE]-(per:Person)\n"
        "WHERE (r.from IS NULL OR r.from <= $date) AND (r.to IS NULL OR r.to >= $date)\n"
        "RETURN per.id AS person_id, per.name AS person, r.title AS title, r.role_type AS role_type, r.from AS from, r.to AS to, r, per, e\n"
        "ORDER BY r.role_type, per.name LIMIT 200"
    )
    return cy, {"id": p["entity_id"], "date": p["date"]}


def _neighbourhood(p):
    d = _depth(p.get("depth", 2))
    layers = p.get("layers") or {}
    rel_filter = ["SUPPLIES", "OWNS", "ULTIMATE_PARENT_OF"]
    if layers.get("categories", False):
        rel_filter += ["PROVIDES", "SUBCATEGORY_OF"]
    if layers.get("people", True):
        rel_filter += ["HELD_ROLE", "BENEFICIAL_OWNER_OF"]
    if layers.get("countries", False):
        rel_filter += ["INCORPORATED_IN", "OPERATES_IN", "MANUFACTURES_IN", "PARENT_SEATED_IN"]
    # Artifacts and sources share a label and its edges; the canvas hides whichever kind is off.
    if layers.get("artifacts", False) or layers.get("sources", False):
        rel_filter += ["EVIDENCES", "ABOUT"]
    if layers.get("claims", False):
        rel_filter += ["ASSERTS", "TARGETS", "EVIDENCES"]
    rel_filter = list(dict.fromkeys(rel_filter))
    rf = "|".join(rel_filter)
    bound = {"id": p["entity_id"], "limit": _subgraph_limit(p.get("limit", 400))}
    if p.get("program_id"):
        # Keep the walk inside one program. Suppliers sell to several programs, so an
        # unconstrained walk hops supplier -> another program -> that program's own
        # suppliers, and the single-program view quietly becomes the whole graph again.
        # Blacklisting every other program cuts those paths at the crossing point.
        bound["program"] = p["program_id"]
        cy = (
            "MATCH (root:Entity {id:$id})\n"
            "OPTIONAL MATCH (other:Entity) WHERE other.kind = 'program' AND other.id <> $program\n"
            "WITH root, collect(other) AS blocked\n"
            f"CALL apoc.path.subgraphAll(root, {{maxLevel:{d}, relationshipFilter:'{rf}', limit:$limit, blacklistNodes:blocked}}) YIELD nodes, relationships\n"
            "RETURN nodes, relationships LIMIT 1"
        )
        return cy, bound
    cy = (
        "MATCH (root:Entity {id:$id})\n"
        f"CALL apoc.path.subgraphAll(root, {{maxLevel:{d}, relationshipFilter:'{rf}', limit:$limit}}) YIELD nodes, relationships\n"
        "RETURN nodes, relationships LIMIT 1"
    )
    return cy, bound


TEMPLATES: dict[str, Template] = {
    t.name: t
    for t in [
        Template(
            "vendors_of",
            "All suppliers of an entity, transitively (include subcontractors) up to a depth. Use for 'suppliers of X', 'vendors of X', 'include all subcontractors'.",
            {"entity_id": {"type": "string"}, "depth": {"type": "integer", "minimum": 1, "maximum": MAX_DEPTH, "default": 3}},
            ["entity_id"], _vendors_of, None,
            [re.compile(r"\b(vendors?|suppliers?|subcontractors?)\b.*\b(of|for)\b", re.I)],
        ),
        Template(
            "color_by_category",
            "Partition an entity's vendors into goods vs services and colour them. Params: goods_color, services_color are palette names.",
            {"entity_id": {"type": "string"}, "depth": {"type": "integer", "default": 1}, "goods_color": {"type": "string", "default": "purple"}, "services_color": {"type": "string", "default": "yellow"}},
            ["entity_id"], _color_by_category, _color_by_category_style,
            [re.compile(r"\bgoods\b.*\bservices\b", re.I)],
        ),
        Template(
            "manufactures_in",
            "Highlight all entities in the root's supply chain that manufacture in a country (ISO2 code or name), optionally only tier >= min_tier ('tier 2 and below' → min_tier 2).",
            {"root_id": {"type": "string"}, "country": {"type": "string"}, "min_tier": {"type": "integer", "default": 1}, "depth": {"type": "integer", "default": MAX_DEPTH}, "color": {"type": "string", "default": "red"}},
            ["root_id", "country"], _manufactures_in, _manufactures_in_style,
            [re.compile(r"\bmanufactur\w*\s+in\b", re.I)],
        ),
        Template(
            "ownership_chain",
            "Owners and ultimate parent of an entity, and its subsidiaries.",
            {"entity_id": {"type": "string"}}, ["entity_id"], _ownership_chain, _ownership_style,
            [re.compile(r"\b(who owns|owner|ownership|parent)\b", re.I)],
        ),
        Template(
            "shared_directors",
            "Interlocking directorates: people who hold or held roles at two or more entities in the root's supply chain.",
            {"root_id": {"type": "string"}, "depth": {"type": "integer", "default": MAX_DEPTH}}, ["root_id"], _shared_directors, _shared_directors_style,
            [re.compile(r"\b(shared|interlock|same)\b.*\b(director|board|officer)", re.I)],
        ),
        Template(
            "sole_source",
            "Sole-source supply relationships in the root's supply chain.",
            {"root_id": {"type": "string"}, "depth": {"type": "integer", "default": MAX_DEPTH}}, ["root_id"], _sole_source, _sole_source_style,
            [re.compile(r"\bsole[- ]source", re.I)],
        ),
        Template(
            "foreign_parent",
            "Entities in the root's supply chain whose ultimate parent is seated outside the home country (default US).",
            {"root_id": {"type": "string"}, "home_country": {"type": "string", "default": "US"}, "depth": {"type": "integer", "default": MAX_DEPTH}}, ["root_id"], _foreign_parent, _foreign_parent_style,
            [re.compile(r"\bforeign\b.*\b(parent|own|control)", re.I)],
        ),
        Template(
            "people_of",
            "Executives and directors of an entity, current and former, one row per tenure.",
            {"entity_id": {"type": "string"}}, ["entity_id"], _people_of, None,
            [re.compile(r"\b(board|directors?|executives?|officers?)\b.*\bof\b", re.I)],
        ),
        Template(
            "as_of_board",
            "Who held roles at an entity on a given ISO date (as-of query over tenured HELD_ROLE edges).",
            {"entity_id": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"}}, ["entity_id", "date"], _as_of_board, None,
            [re.compile(r"\b(who (sat|was) on|as of)\b", re.I)],
        ),
        Template(
            "neighbourhood",
            "Subgraph around an entity to a depth, honouring layer toggles (people, countries, categories, artifacts, sources, claims).",
            {"entity_id": {"type": "string"}, "depth": {"type": "integer", "default": 2}, "limit": {"type": "integer", "default": 400}, "layers": {"type": "object"},
             "program_id": {"type": "string", "description": "confine the walk to this program's supply chain; other programs, and whatever hangs off only them, are left out"}},
            ["entity_id"], _neighbourhood, None,
        ),
    ]
}


def template_prompt() -> str:
    lines = ["TEMPLATES (prefer these over free Cypher; call run_template):"]
    for t in TEMPLATES.values():
        lines.append(f"  {t.name}({', '.join(t.params)}) — {t.description}")
    return "\n".join(lines)


def match_intent(text: str) -> str | None:
    """Regex fallback used when no model key is configured."""
    for t in TEMPLATES.values():
        for rx in t.patterns:
            if rx.search(text):
                return t.name
    return None
