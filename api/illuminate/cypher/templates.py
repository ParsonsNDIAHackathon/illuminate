"""Parameterised templates for the named intents (D3).

Templates are faster and more reliable than free generation, so they are the
default and free generation is the fallback. Each template owns its Cypher and
knows how to turn its rows into style_ops.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import RISK_PIN_FLOOR, settings

MAX_DEPTH = settings.cypher_max_hops


def _depth(v, default=3) -> int:
    try:
        d = int(v)
    except Exception:
        d = default
    return max(1, min(MAX_DEPTH, d))


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


def _risk_ranked(p):
    """The root's supply chain ordered by the stored risk score.

    Unscored vendors sort last and are still returned: a null score means no dimension
    returned data, which is a reason to enrich the vendor rather than to drop it from the
    answer. The band filter is optional so "show me the severe ones" narrows the same query.
    """
    d = _depth(p.get("depth", MAX_DEPTH))
    band = (p.get("band") or "").strip().lower()
    where = "\nWHERE v.risk_band = $band" if band else ""
    cy = (
        f"MATCH (root:Entity {{id:$root}})\n"
        f"MATCH path=(v:Entity)-[:SUPPLIES*1..{d}]->(root){where}\n"
        "WITH v, min(length(path)) AS tier\n"
        "RETURN v.id AS id, v.name AS name, tier, v.risk_score AS score, v.risk_band AS band,\n"
        "       v.risk_confidence AS confidence, v.risk_top_factor AS top_factor, v\n"
        "ORDER BY v.risk_score IS NULL, v.risk_score DESC, v.risk_confidence DESC, name\n"
        "LIMIT $limit"
    )
    bound = {"root": p["root_id"], "limit": int(p.get("limit", 100))}
    if band:
        bound["band"] = band
    return cy, bound


# Band -> palette name. Mirrors web/src/styles/risk.ts; low is neutral because a low score
# is "clear on the little we asked", which is not an all-clear.
_BAND_SWATCH = {"severe": "red", "high": "orange", "elevated": "yellow", "low": "neutral"}


def _risk_ranked_style(rows, p):
    ops = []
    for band, swatch in _BAND_SWATCH.items():
        ids = [r["id"] for r in rows if r.get("band") == band]
        if ids:
            ops.append({"op": "set", "ids": ids, "style": {"fill": swatch, "badge": band},
                        "label": f"Risk: {band}"})
    unscored = [r["id"] for r in rows if r.get("score") is None]
    if unscored:
        # Named, not hidden: "we could not grade this" is a finding of its own.
        ops.append({"op": "set", "ids": unscored, "style": {"stroke": "neutral", "dashed": True, "badge": "unscored"},
                    "label": "Unscored — no dimension returned data"})
    return ops


def _near_designated(p):
    """Everything within N hops of a designated party, with the route that reaches it.

    The same walk risk.py scores `proximity` from, exposed as a question you can ask: it is
    the one thing a supplier list cannot answer and a graph can.
    """
    hops = max(1, min(MAX_DEPTH, int(p.get("hops", 2) or 2)))
    rels = "OWNS|ULTIMATE_PARENT_OF|BENEFICIAL_OWNER_OF|HELD_ROLE|SUPPLIES|TRANSACTS_WITH|MEMBER_OF"
    cy = (
        "MATCH (seed:Entity|Person)\n"
        "WHERE coalesce(seed.flagged, false) = true\n"
        f"CALL apoc.path.expandConfig(seed, {{relationshipFilter:'{rels}', minLevel:1, maxLevel:{hops},\n"
        "                                    bfs:true, uniqueness:'NODE_GLOBAL'}) YIELD path\n"
        "WITH seed, last(nodes(path)) AS n, length(path) AS hops, path\n"
        "WHERE n.id <> seed.id\n"
        "RETURN n.id AS id, n.name AS name, hops, seed.name AS designated, n, path\n"
        "ORDER BY hops, name LIMIT $limit"
    )
    return cy, {"limit": int(p.get("limit", 200))}


def _near_designated_style(rows, p):
    ops = []
    for hops, swatch in ((1, "red"), (2, "orange"), (3, "yellow")):
        ids = [r["id"] for r in rows if r.get("hops") == hops]
        if ids:
            ops.append({"op": "set", "ids": ids, "style": {"fill": swatch, "badge": f"{hops} hop{'s' if hops != 1 else ''}"},
                        "label": f"{hops} degree{'s' if hops != 1 else ''} from a designated party"})
    return ops


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


# Appended to the program-focused walk. The depth control says how much context to draw; it does
# not get to say that a scored node is out of sight. Depth 2 around the V-22 program stops one hop
# short of the director scored 100 inside a second-tier supplier, and three short of the metals
# group at the bottom of that chain — exactly the nodes the whole tool exists to surface. So after
# the depth-bounded walk, every node over the pin floor is brought in on its shortest path back to
# the root (config.RISK_PIN_FLOOR, mirrored by RISK_PIN_FLOOR in graphLayers.ts, which decides what
# is actually drawn). The path comes with it: a risky node with no way back to the chain is one the
# canvas cannot pin and would draw as a lone dot. `{inside}` keeps the sweep inside this program,
# the way blacklistNodes keeps the walk there.
_RISK_SWEEP = (
    "WITH {carry}, nodes AS base, relationships AS rels\n"
    "OPTIONAL MATCH (hot) WHERE (hot:Entity OR hot:Person) AND coalesce(hot.risk_score, 0) > $risk_floor AND NOT hot IN base\n"
    "WITH {carry}, base, rels, collect(hot) AS hot\n"
    "UNWIND (CASE WHEN hot = [] THEN [NULL] ELSE hot END) AS one\n"
    "OPTIONAL MATCH back = shortestPath((root)-[:{rf}*1..{k}]-(one))\n"
    "{inside}"
    "WITH root, base, rels, collect(back) AS paths\n"
    "WITH root, base + apoc.coll.flatten([q IN paths | nodes(q)]) AS nodes,\n"
    "     rels + apoc.coll.flatten([q IN paths | relationships(q)]) AS relationships\n"
)

# Appended when the people layer is off. The walk crosses HELD_ROLE and BENEFICIAL_OWNER_OF either
# way; this drops every person it met who is not scored over the pin floor, so a designated director
# stays on the canvas whatever the layer says, and so does a risky company on the far side of one.
# The last line then drops whatever an ordinary director was the only route to: those companies
# would otherwise arrive with no edges at all, and an edgeless organization is one the canvas keeps
# — turning people off would add nodes.
_RISKY_PEOPLE_ONLY = (
    "WITH root, [n IN nodes WHERE NOT n:Person OR coalesce(n.risk_score, 0) > $risk_floor] AS kept, relationships\n"
    "WITH root, kept, [r IN relationships WHERE startNode(r) IN kept AND endNode(r) IN kept] AS relationships\n"
    "WITH [n IN kept WHERE n = root OR any(r IN relationships WHERE startNode(r) = n OR endNode(r) = n)] AS nodes, relationships\n"
)


def _neighbourhood(p):
    d = _depth(p.get("depth", 2))
    layers = p.get("layers") or {}
    # Entity-to-entity ties are always followed: supply, control, and the affiliations
    # LittleSis records (memberships, lobbying, transactions, donations).
    rel_filter = ["SUPPLIES", "OWNS", "ULTIMATE_PARENT_OF", "MEMBER_OF", "TRANSACTS_WITH", "LOBBIES", "DONATED_TO"]
    if layers.get("categories", False):
        rel_filter += ["PROVIDES", "SUBCATEGORY_OF"]
    # Personnel edges are walked either way; with the layer off, _RISKY_PEOPLE_ONLY cuts the
    # ordinary people back out of the result and leaves the risky ones.
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
    # Reports hang off what they are about, and they are walked *inwards only*: from a subject or a
    # cited node you arrive at the report, and from the report you arrive nowhere. A report cites up
    # to sixty nodes, and expanding through one would quietly re-import the findings it was written
    # about as if the user had asked for them. Only the apoc filters take these — the risk sweep
    # builds a Cypher pattern, where a direction prefix is not valid syntax.
    report_rels = ["<REPORTS_ON", "<CITES"] if layers.get("reports", False) else []
    # Ownership is walked upwards in a program view: who owns a company on the contract is
    # material, its owner's other subsidiaries are not — Raytheon Visual Analytics arrives only
    # because its parent sells to the V-22, which says nothing about the V-22. Two dozen sister
    # companies come in that way per program, none of them supplying anything. Expanding a bare
    # entity keeps both directions: there the user is pointing at the node and asking what is
    # around it. SUPPLIES stays two-way either way — the recorded direction is not consistent
    # enough to hang the supply base on.
    rf_up = "|".join([("<" + r if r in ("OWNS", "ULTIMATE_PARENT_OF") else r) for r in rel_filter] + report_rels)
    rf_out = "|".join(rel_filter + report_rels)
    bound = {"id": p["entity_id"], "limit": int(p.get("limit", 400)), "risk_floor": RISK_PIN_FLOOR}
    tail = _RISKY_PEOPLE_ONLY if not layers.get("people", False) else ""
    if p.get("program_id"):
        # Keep the walk inside one program. Suppliers sell to several programs, so an
        # unconstrained walk hops supplier -> another program -> that program's own
        # suppliers, and the single-program view quietly becomes the whole graph again.
        # Blacklisting every other program cuts those paths at the crossing point.
        bound["program"] = p["program_id"]
        sweep = _RISK_SWEEP.format(carry="root, blocked", rf=rf, k=MAX_DEPTH,
                                   inside="WHERE none(n IN nodes(back) WHERE n IN blocked)\n")
        cy = (
            "MATCH (root:Entity {id:$id})\n"
            "OPTIONAL MATCH (other:Entity) WHERE other.kind = 'program' AND other.id <> $program\n"
            "WITH root, collect(other) AS blocked\n"
            f"CALL apoc.path.subgraphAll(root, {{maxLevel:{d}, relationshipFilter:'{rf_up}', limit:$limit, blacklistNodes:blocked}}) YIELD nodes, relationships\n"
            f"{sweep}"
            f"{tail}"
            "RETURN nodes, relationships LIMIT 1"
        )
        return cy, bound
    # No sweep off a bare entity: that walk is someone expanding one node, and the whole graph's
    # risk set arriving with it is not what they asked for. Unfocused, /graph/all has already sent
    # every entity anyway, and the canvas pins from there.
    cy = (
        "MATCH (root:Entity {id:$id})\n"
        f"CALL apoc.path.subgraphAll(root, {{maxLevel:{d}, relationshipFilter:'{rf_out}', limit:$limit}}) YIELD nodes, relationships\n"
        f"{tail}"
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
            "risk_ranked",
            "The root's supply chain ordered by computed risk score, optionally narrowed to one band "
            "(severe, high, elevated, low). Use for 'riskiest suppliers', 'which vendors are highest risk', "
            "'show me the severe ones'. Unscored vendors are returned last, never dropped.",
            {"root_id": {"type": "string"}, "band": {"type": "string", "description": "severe | high | elevated | low"},
             "depth": {"type": "integer", "default": MAX_DEPTH}, "limit": {"type": "integer", "default": 100}},
            ["root_id"], _risk_ranked, _risk_ranked_style,
            [re.compile(r"\b(riskiest|highest[- ]risk|risk score|most at risk|risky)\b", re.I)],
        ),
        Template(
            "near_designated",
            "Entities and people within N hops of a designated party (sanctioned, debarred or named on a "
            "restricted list), over ownership, personnel and commercial edges. Use for 'who is connected to a "
            "sanctioned entity', 'degrees of separation from a designated party', 'exposure to flagged parties'.",
            {"hops": {"type": "integer", "minimum": 1, "maximum": MAX_DEPTH, "default": 2}, "limit": {"type": "integer", "default": 200}},
            [], _near_designated, _near_designated_style,
            [re.compile(r"\b(degrees? of separation|connected to a (sanctioned|designated|flagged)|near a (sanctioned|designated|flagged))\b", re.I)],
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
