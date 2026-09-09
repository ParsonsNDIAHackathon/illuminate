"""Node risk scoring: one number per organisation and per person, with the reasons kept.

The entity report (report.py) has always graded a vendor's signals, but only for the one
vendor whose page was open, and only in memory. A supply chain is scored the other way
round: you want to look at the canvas and see which of two hundred nodes deserves the next
hour. So this module computes the same kind of judgement for *every* Entity and Person in
one pass and writes it onto the node, where the canvas, the entity list, the people list
and Cypher can all reach it.

Five dimensions, each graded in the report's own severity vocabulary and each carrying its
own evidence:

  designation    the node's own screens — OFAC SDN, the UN Consolidated List, SAM
                 exclusions, DoD §1260H. A hit here is the finding; nothing else competes.
  proximity      degrees of separation from a designated party, walked over control,
                 personnel and commercial edges. This is what catches the vendor whose own
                 record is spotless and whose network operations engineer sits inside a
                 designated group — the exposure exists only in the graph.
  foreign        ownership and operations by jurisdiction class: covered nations
                 (10 U.S.C. § 4872), embargoed states, opaque registries, allies.
  regional       armed conflict and natural-hazard exposure where the entity actually
                 operates and manufactures, not where it is registered.
  financial      distress: lapsed registration, late or absent filings, collapsed market
                 value, no award activity for a firm that lives on awards.

  dependency     what a consumer inherits from the suppliers it cannot replace. Being a
                 sole source is not a risk the supplier carries — it says nothing about
                 whether that company is likely to fail or to be designated. It is a risk
                 its *customer* carries, and only in proportion to how irreplaceable the
                 supplier is: a high-risk sole source is a single point of failure, the
                 same company as one of six competed vendors is a fraction of one.

`media` (the adverse-media screen) comes along because the graph already holds it, and
carries the least weight.

Three rules the whole module answers to:

1. **A signal that returned no data is not a zero.** Every dimension can say "no data",
   and the score is the weighted mean over the dimensions that *did* answer. A node with
   one dimension of data gets a score and a loud note about how thin it is, never a
   flattering 8/100 built out of silence.
2. **Nothing is scored that cannot be shown.** Every component carries the ids of the
   nodes and edges that produced it, so the canvas can light up the reason.
3. **Simulated data scores exactly like observed data.** The scenario overlay is disclosed
   in the app bar and nowhere else; a scorer that skipped it would be marking its own
   homework.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from . import db, riskdata
from .connectors.base import now_iso

# Shared with report.py, which grades its narrative families on the same scale.
SEVERITY_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0, "clear": 0.0}
MAX_SEVERITY = 3.0

# dimension -> (weight, human label). Weight is relative importance among the dimensions
# that returned data; a node scored on three of seven is scored on those three's weights.
DIMENSIONS: dict[str, tuple[float, str]] = {
    "designation": (3.0, "Designation"),
    "proximity": (2.0, "Proximity to designated parties"),
    "dependency": (2.0, "Dependence on risky suppliers"),
    "foreign": (1.5, "Foreign ownership and operations"),
    "financial": (1.5, "Financial distress"),
    "regional": (1.0, "Regional conflict and natural hazard"),
    "media": (0.75, "Adverse media"),
}

# How far the designated-party walk goes, and what it is allowed to walk over. Ownership
# and personnel edges carry exposure; INCORPORATED_IN or PROVIDES do not — two companies
# that make the same widget in the same country are not thereby connected.
PROXIMITY_MAX_HOPS = 3
HOP_SEVERITY = {1: "high", 2: "medium", 3: "low"}

# Contamination along a supply edge is not symmetric. Buying from a designated party puts
# its problem inside your product; selling to one is a concern of a different kind and a
# smaller one for supply-chain integrity. So the walk runs twice.
#
# `SUPPLIES>` leaves the designated seed along the direction it supplies, reaching the
# companies that buy from it, and from them the companies that buy from *them* — the
# chain the risk actually travels. Control and personnel edges stay undirected: owning a
# designated subsidiary and being owned by a designated parent are both severe, and a
# shared officer has no direction at all.
_UNDIRECTED = "OWNS|ULTIMATE_PARENT_OF|BENEFICIAL_OWNER_OF|HELD_ROLE|TRANSACTS_WITH|MEMBER_OF"
PROXIMITY_RELS_DOWNSTREAM = f"{_UNDIRECTED}|SUPPLIES>"
PROXIMITY_RELS_ANY = f"{_UNDIRECTED}|SUPPLIES"
# A route that only exists against the flow of supply is graded one step softer. Low
# becomes clear: three hops upstream of a designated buyer is not a finding.
WEAKER = {"high": "medium", "medium": "low", "low": "clear", "clear": "clear"}

# Screens whose 'hit' means the party is designated by someone with authority to designate.
DESIGNATION_SCREENS = ("sanctions_screen", "exclusion_screen", "restricted_list_screen")

BANDS = [(75, "severe"), (50, "high"), (25, "elevated"), (0, "low")]

# Supplier risk flows to the consumer, decayed by how substitutable the supplier is. Run as
# a fixed number of passes rather than a recursion: SUPPLIES can hold a cycle in imperfect
# data, and a bounded sweep is what carries a deep sole-source chain up to the program
# without letting a loop run away. Four covers program ← tier 1 ← tier 2 ← tier 3 ← tier 4,
# which is deeper than any sub-award data the seed has ever produced.
DEPENDENCY_PASSES = 4
# Exposure is on the same 0-100 scale as a score; these are where it changes severity.
DEPENDENCY_SEVERITY = [(50, "high"), (25, "medium"), (10, "low")]

# A registration this close to lapsing is already a continuity question.
REGISTRATION_WARN_DAYS = 60
# A listed company that has filed nothing in this long has stopped reporting.
FILING_STALE_DAYS = 550
NT_FORMS = ("NT 10-K", "NT 10-Q", "NT 20-F")


def component(dimension: str, label: str, severity: str | None, *, source: str | None = None,
              detail: str | None = None, url: str | None = None, ids: list[str] | None = None) -> dict:
    """One graded signal. `severity=None` means the signal returned no data — which is a
    result, not a zero, and is rendered as such everywhere."""
    return {
        "family": dimension, "dimension": dimension, "label": label, "severity": severity,
        "source": source, "detail": detail, "source_url": url,
        "element_ids": ids or [], "no_data": severity is None,
        "weight": DIMENSIONS[dimension][0],
    }


def band(score: int | None) -> str | None:
    if score is None:
        return None
    for floor, name in BANDS:
        if score >= floor:
            return name
    return "low"


def composite(components: list[dict]) -> tuple[int | None, list[dict]]:
    """Weighted mean over the dimensions that returned data, on 0-100."""
    scored = [c for c in components if not c["no_data"]]
    if not scored:
        return None, scored
    total = sum(c["weight"] * SEVERITY_WEIGHT[c["severity"]] for c in scored)
    ceiling = sum(c["weight"] for c in scored) * MAX_SEVERITY
    return round(100 * total / ceiling) if ceiling else 0, scored


def _worst(*severities: str | None) -> str | None:
    """The most severe of several gradings, ignoring the ones that said nothing."""
    known = [s for s in severities if s in SEVERITY_WEIGHT]
    if not known:
        return None
    return max(known, key=lambda s: SEVERITY_WEIGHT[s])


def _parse_date(value) -> date | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


# --- Graph reads ------------------------------------------------------------------

_ID_FILTER = "($ids IS NULL OR n.id IN $ids)"


async def _entities(ids: list[str] | None) -> list[dict]:
    return await db.read(
        f"""
        MATCH (n:Entity) WHERE {_ID_FILTER}
        OPTIONAL MATCH (n)-[:INCORPORATED_IN]->(inc:Location)
        OPTIONAL MATCH (n)-[:PARENT_SEATED_IN]->(seat:Location)
        OPTIONAL MATCH (n)-[:OPERATES_IN]->(ops:Location)
        OPTIONAL MATCH (n)-[:MANUFACTURES_IN]->(mfg:Location)
        OPTIONAL MATCH (a:Artifact)-[:ABOUT]->(n) WHERE a.kind IN ['award', 'filing']
        RETURN n.id AS id, n.name AS name, coalesce(n.kind, 'organization') AS kind,
               coalesce(n.flagged, false) AS flagged, n.flag_reason AS flag_reason,
               n.registration_status AS registration_status, n.registration_expires AS registration_expires,
               n.entity_status AS entity_status, coalesce(n.public, false) AS public, n.ticker AS ticker,
               n.market_cap AS market_cap, n.price_change_12m AS price_change_12m, n.revenue AS revenue,
               [x IN collect(DISTINCT inc.code) WHERE x IS NOT NULL] AS incorporated,
               [x IN collect(DISTINCT seat.code) WHERE x IS NOT NULL] AS parent_seat,
               [x IN collect(DISTINCT ops.code) WHERE x IS NOT NULL] AS operates,
               [x IN collect(DISTINCT mfg.code) WHERE x IS NOT NULL] AS manufactures,
               [x IN collect(DISTINCT {{kind: a.kind, form: a.form, at: coalesce(a.published_at, a.retrieved_at)}}) WHERE x.at IS NOT NULL] AS docs
        """,
        {"ids": ids},
    )


async def _people(ids: list[str] | None) -> list[dict]:
    return await db.read(
        f"""
        MATCH (n:Person) WHERE {_ID_FILTER}
        OPTIONAL MATCH (n)-[r:HELD_ROLE|BENEFICIAL_OWNER_OF]->(e:Entity)
        RETURN n.id AS id, n.name AS name, coalesce(n.flagged, false) AS flagged, n.flag_reason AS flag_reason,
               coalesce(n.public_official, false) AS public_official,
               [x IN collect(DISTINCT {{id: e.id, name: e.name, title: r.title,
                                        current: coalesce(r.current, r.to IS NULL)}}) WHERE x.id IS NOT NULL] AS roles
        """,
        {"ids": ids},
    )


async def _screens(ids: list[str] | None) -> dict[str, dict[str, dict]]:
    """Latest committed screen per node per predicate."""
    rows = await db.read(
        f"""
        MATCH (c:Claim)-[:ASSERTS]->(n)
        WHERE c.predicate ENDS WITH '_screen' AND c.status = 'committed' AND {_ID_FILTER}
        OPTIONAL MATCH (a:Artifact)-[:EVIDENCES]->(c)
        RETURN n.id AS id, c.predicate AS predicate, c.object_value AS result, c.source AS source,
               c.detail AS detail, c.retrieved_at AS retrieved_at, head(collect(a.url)) AS url
        ORDER BY c.retrieved_at DESC
        """,
        {"ids": ids},
    )
    out: dict[str, dict[str, dict]] = {}
    for row in rows:
        out.setdefault(row["id"], {}).setdefault(row["predicate"], row)
    return out


async def _ultimate_parents(ids: list[str] | None) -> dict[str, list[dict]]:
    """Roots of each entity's control chain with the jurisdiction each is seated in.

    Bulk counterpart of report.ultimate_parents: the same walk, run once for the whole
    graph instead of once per page view.
    """
    rows = await db.read(
        f"""
        MATCH path = (up:Entity)-[:OWNS|ULTIMATE_PARENT_OF*1..6]->(n:Entity)
        WHERE {_ID_FILTER} AND up.id <> n.id AND NOT EXISTS {{ (:Entity)-[:OWNS|ULTIMATE_PARENT_OF]->(up) }}
        OPTIONAL MATCH (up)-[:INCORPORATED_IN]->(l:Location)
        WITH n.id AS id, up, length(path) AS hops, [h IN relationships(path) | h.id] AS rel_ids,
             head(collect(l.code)) AS code
        ORDER BY hops
        RETURN id, collect(DISTINCT {{id: up.id, name: up.name, code: code, hops: hops, rel_ids: rel_ids}}) AS parents
        """,
        {"ids": ids},
    )
    return {r["id"]: r["parents"] for r in rows}


async def _proximity(seeds: list[str], ids: list[str] | None, rels: str) -> dict[str, dict]:
    """Shortest walk from each designated party to everything within reach.

    apoc.path.expandConfig with bfs + NODE_GLOBAL gives each reachable node once, by its
    shortest route, which is exactly "degrees of separation" and avoids enumerating the
    combinatorial pile of longer paths that lead to the same place.
    """
    if not seeds:
        return {}
    rows = await db.read(
        """
        UNWIND $seeds AS sid
        MATCH (seed {id: sid})
        CALL apoc.path.expandConfig(seed, {relationshipFilter: $rels, minLevel: 1, maxLevel: $max,
                                           bfs: true, uniqueness: 'NODE_GLOBAL'}) YIELD path
        WITH seed, sid, last(nodes(path)) AS n, length(path) AS hops,
             [x IN nodes(path) | x.id] AS node_ids,
             [x IN relationships(path) | coalesce(x.id, elementId(x))] AS rel_ids,
             [x IN nodes(path) | coalesce(x.name, x.id)] AS chain
        WHERE (n:Entity OR n:Person) AND n.id <> sid AND ($ids IS NULL OR n.id IN $ids)
        WITH n.id AS id, hops, sid, seed.name AS seed_name, node_ids, rel_ids, chain
        ORDER BY hops, seed_name
        WITH id, collect({seed_id: sid, seed: seed_name, hops: hops, node_ids: node_ids,
                          rel_ids: rel_ids, chain: chain}) AS paths
        RETURN id, paths[0] AS nearest, size(paths) AS reachable
        """,
        {"seeds": seeds, "ids": ids, "rels": rels, "max": PROXIMITY_MAX_HOPS},
    )
    return {r["id"]: {**r["nearest"], "reachable": r["reachable"]} for r in rows}


def merge_proximity(downstream: dict[str, dict], any_direction: dict[str, dict]) -> dict[str, dict]:
    """Pick the route that grades worst, and remember which direction produced it.

    A node can be one hop from a designated party against the flow of supply and three
    hops with it. Neither reading is the whole answer, so both are graded and the worse
    one wins — which keeps the asymmetry from hiding a close reverse tie, and keeps a
    reverse tie from being reported as though the risk were flowing the usual way.
    """
    out: dict[str, dict] = {}
    for nid in set(downstream) | set(any_direction):
        options = []
        if nid in downstream:
            d = downstream[nid]
            options.append((HOP_SEVERITY.get(d["hops"], "low"), {**d, "downstream": True}))
        if nid in any_direction:
            a = any_direction[nid]
            # Only meaningful as the reverse reading; if the downstream walk found the same
            # route it is already in the list above and grades higher.
            options.append((WEAKER[HOP_SEVERITY.get(a["hops"], "low")], {**a, "downstream": False}))
        severity, best = max(options, key=lambda o: SEVERITY_WEIGHT[o[0]])
        out[nid] = {**best, "severity": severity}
    return out


async def _supply_edges() -> dict[str, list[dict]]:
    """Every SUPPLIES edge, grouped by consumer.

    Never filtered by the ids being rescored: a consumer's exposure is a property of its
    whole supplier base, and scoring it from the subset in hand would report a dilution
    that is not real.
    """
    rows = await db.read(
        """
        MATCH (s:Entity)-[r:SUPPLIES]->(c:Entity)
        WHERE s.id <> c.id
        RETURN c.id AS consumer, s.id AS supplier, s.name AS supplier_name, r.id AS edge_id,
               coalesce(r.sole_source, false) AS sole_source, coalesce(r.amount, 0) AS amount
        """
    )
    by_consumer: dict[str, list[dict]] = {}
    for row in rows:
        by_consumer.setdefault(row["consumer"], []).append(row)
    return by_consumer


async def _designated_ids() -> list[str]:
    """Every party the graph considers designated, graph-wide — the seeds of the walk.

    Always global, even when scoring one node: proximity to a designated party three hops
    away is not a property of the subset being rescored.
    """
    rows = await db.read(
        """
        MATCH (n) WHERE (n:Entity OR n:Person) AND (
              coalesce(n.flagged, false) = true
              OR EXISTS { MATCH (c:Claim)-[:ASSERTS]->(n)
                          WHERE c.predicate IN $screens AND c.status = 'committed' AND c.object_value = 'hit' })
        RETURN n.id AS id
        """,
        {"screens": list(DESIGNATION_SCREENS)},
    )
    return [r["id"] for r in rows]


# --- Dimensions -------------------------------------------------------------------

def _designation(row: dict, screens: dict[str, dict]) -> dict:
    hits = [s for p, s in screens.items() if p in DESIGNATION_SCREENS and s["result"] == "hit"]
    ran = [s for p, s in screens.items() if p in DESIGNATION_SCREENS]
    if hits:
        first = hits[0]
        sources = " · ".join(sorted({h["source"] for h in hits if h.get("source")}))
        return component("designation", f"Designated — {sources or 'listed'}", "high", source=sources or None,
                         detail=first.get("detail"), url=first.get("url"), ids=[row["id"]])
    if row.get("flagged"):
        # Flagged without a screen behind it: something asserted the designation directly.
        return component("designation", "Flagged in the graph", "high", source="graph",
                         detail=row.get("flag_reason"), ids=[row["id"]])
    if ran:
        sources = " · ".join(sorted({s["source"] for s in ran if s.get("source")}))
        return component("designation", f"Screened clear against {len(ran)} list{'s' if len(ran) != 1 else ''}", "clear",
                         source=sources or None, detail="; ".join(s["detail"] for s in ran if s.get("detail")) or None,
                         ids=[row["id"]])
    return component("designation", "Not yet screened against any designation list", None,
                     detail="OFAC SDN, UN Consolidated List, SAM exclusions and DoD §1260H have not run for this node")


def _proximity_component(row: dict, near: dict | None) -> dict:
    if not near:
        return component("proximity", "No designated party within "
                         f"{PROXIMITY_MAX_HOPS} hops of ownership, personnel or commercial ties", "clear",
                         source="graph", ids=[row["id"]])
    hops = int(near["hops"])
    downstream = near.get("downstream", True)
    severity = near.get("severity") or HOP_SEVERITY.get(hops, "low")
    chain = " → ".join(near.get("chain") or [])
    more = near.get("reachable", 1) - 1
    detail = f"{hops} hop{'s' if hops != 1 else ''}: {chain}"
    if not downstream:
        detail += (" · reached only against the flow of supply — the designated party buys from this chain "
                   "rather than selling into it, so the grading is one step softer")
    if more > 0:
        detail += f" · {more} further designated part{'ies' if more != 1 else 'y'} within reach"
    ids = list(dict.fromkeys((near.get("node_ids") or []) + (near.get("rel_ids") or [])))
    label = f"{hops} degree{'s' if hops != 1 else ''} of separation from {near.get('seed') or 'a designated party'}"
    if not downstream:
        label += " (downstream of it)"
    return component("proximity", label, severity, source="graph", detail=detail, ids=ids)


def _foreign(row: dict, parents: list[dict]) -> dict:
    """Jurisdiction exposure across incorporation, control and physical presence.

    Where an entity is registered, who ultimately owns it and where it actually builds
    things are three different questions; a Delaware shell that manufactures in a covered
    nation answers the first one reassuringly and the third one not at all. All three are
    read, and the worst wins.
    """
    seats = [(c, "ultimate parent seated in") for c in (row.get("parent_seat") or [])]
    seats += [(p["code"], "ultimate parent incorporated in") for p in parents if p.get("code")]
    places = ([(c, "incorporated in") for c in (row.get("incorporated") or [])] + seats
              + [(c, "manufactures in") for c in (row.get("manufactures") or [])]
              + [(c, "operates in") for c in (row.get("operates") or [])])
    known = [(code, why) for code, why in places if riskdata.jurisdiction_class(code)]
    if not known:
        return component("foreign", "Jurisdiction", None,
                         detail="No incorporation, parent seat or place of operation resolved to a jurisdiction")
    graded = [(riskdata.CLASS_SEVERITY[riskdata.jurisdiction_class(code)], code, why) for code, why in known]
    # Opacity is its own finding: a chain that enters a non-disclosing registry cannot be
    # walked to its end, so "no adverse jurisdiction found" would be an overstatement.
    opaque = [(code, why) for code, why in known if riskdata.is_opaque(code)]
    worst = max(graded, key=lambda g: SEVERITY_WEIGHT[g[0]])
    severity, code, why = worst
    if severity in ("clear", "low") and opaque:
        severity = "medium"
        code, why = opaque[0]
        label = f"Control chain passes through {code}, a non-disclosing registry"
        detail = "Beneficial ownership is not published there, so the chain cannot be walked to its end"
    else:
        cls = riskdata.jurisdiction_class(code)
        label = f"{why.capitalize()} {code} — {riskdata.CLASS_LABEL[cls]}"
        others = sorted({c for c, _ in known if c != code})
        detail = (f"Also resolved: {', '.join(others)}" if others else None)
        if severity == "clear" and not opaque:
            label = f"Domestic or allied throughout ({', '.join(sorted({c for c, _ in known}))})"
            detail = None
    ids = [row["id"]] + [p["id"] for p in parents if p.get("code") == code]
    return component("foreign", label, severity, source=riskdata.JURISDICTION_SOURCE, detail=detail, ids=ids)


def _regional(row: dict) -> dict:
    """Conflict and natural hazard where the entity physically is.

    Deliberately blind to incorporation: a hurricane does not care where the paperwork was
    filed. Only OPERATES_IN and MANUFACTURES_IN count, and manufacture counts double —
    losing a plant is not the same as losing a sales office.
    """
    places = ([(c, "manufactures") for c in (row.get("manufactures") or [])]
              + [(c, "operates") for c in (row.get("operates") or [])])
    graded: list[tuple[str, str, str, str]] = []   # severity, code, kind, why
    for code, why in places:
        conflict = riskdata.conflict_level(code)
        hazard = riskdata.hazard_level(code)
        if conflict:
            sev = "high" if conflict == "high" and why == "manufactures" else ("medium" if conflict == "high" else "low")
            graded.append((sev, code, "armed conflict or sustained political violence", why))
        if hazard and hazard != "low":
            sev = "medium" if hazard == "high" and why == "manufactures" else "low"
            graded.append((sev, code, "elevated natural-hazard exposure", why))
        if not conflict and hazard == "low":
            graded.append(("clear", code, "low conflict and hazard exposure", why))
    if not graded:
        if places:
            return component("regional", "Regional exposure", None,
                             detail=f"No conflict or hazard reference for {', '.join(sorted({c for c, _ in places}))}"
                                    f" (tables as of {riskdata.AS_OF})")
        return component("regional", "Regional exposure", None,
                         detail="No place of operation or manufacture recorded")
    worst = max(graded, key=lambda g: SEVERITY_WEIGHT[g[0]])
    severity, code, kind, why = worst
    if severity == "clear":
        return component("regional", f"Operates in low-exposure regions ({', '.join(sorted({c for c, _ in places}))})",
                         "clear", source=riskdata.HAZARD_SOURCE)
    label = f"{why.capitalize()} in {code} — {kind}"
    others = [f"{c} ({k})" for s, c, k, _ in graded if c != code and s != "clear"]
    return component("regional", label, severity,
                     source=riskdata.CONFLICT_SOURCE if "conflict" in kind else riskdata.HAZARD_SOURCE,
                     detail=("Also: " + "; ".join(sorted(set(others))) if others else None) or
                            f"Reference tables as of {riskdata.AS_OF}",
                     ids=[row["id"]])


def _financial(row: dict, screens: dict[str, dict], today: date) -> dict:
    """Distress signals, each of which is a reason someone stops delivering.

    A private company with no filings and no registration record produces no signal at all,
    and says so. That is the common case in a sub-tier supply base and the report has always
    refused to guess at it.
    """
    findings: list[tuple[str, str]] = []
    status = (row.get("registration_status") or "").strip().lower()
    if status and status not in ("active", "registered"):
        findings.append(("medium", f"SAM registration is {row['registration_status']}"))
    expires = _parse_date(row.get("registration_expires"))
    if expires:
        if expires < today:
            findings.append(("high", f"SAM registration expired {expires.isoformat()}"))
        elif expires - today < timedelta(days=REGISTRATION_WARN_DAYS):
            findings.append(("low", f"SAM registration expires {expires.isoformat()}"))
    entity_status = (row.get("entity_status") or "").strip().lower()
    if entity_status and any(w in entity_status for w in ("dissolved", "inactive", "terminated", "struck", "liquidat")):
        findings.append(("high", f"Registry status: {row['entity_status']}"))

    forms = {d.get("form") for d in (row.get("docs") or []) if d.get("form")}
    late = sorted(forms & set(NT_FORMS))
    if late:
        findings.append(("medium", f"Late-filing notification on record ({', '.join(late)})"))
    filings = [_parse_date(d["at"]) for d in (row.get("docs") or []) if d.get("kind") == "filing"]
    filings = [f for f in filings if f]
    if row.get("public") and filings and today - max(filings) > timedelta(days=FILING_STALE_DAYS):
        findings.append(("medium", f"Listed but nothing filed since {max(filings).isoformat()}"))

    change = row.get("price_change_12m")
    try:
        change = float(change) if change not in (None, "") else None
    except (TypeError, ValueError):
        change = None
    if change is not None:
        if change <= -50:
            findings.append(("high", f"Market value down {abs(change):.0f}% over 12 months"))
        elif change <= -25:
            findings.append(("medium", f"Market value down {abs(change):.0f}% over 12 months"))

    fin = screens.get("financial_screen")
    if fin and fin["result"] in SEVERITY_WEIGHT and fin["result"] != "clear":
        findings.append((fin["result"], fin.get("detail") or "financial screen"))

    if findings:
        severity = _worst(*[f[0] for f in findings]) or "low"
        return component("financial", findings[0][1] if len(findings) == 1 else f"{len(findings)} distress signals",
                         severity, source=(fin or {}).get("source") or "SAM.gov · EDGAR",
                         detail="; ".join(f[1] for f in findings), ids=[row["id"]])
    if fin and fin["result"] == "clear":
        return component("financial", "Financial screen clear", "clear", source=fin.get("source"), detail=fin.get("detail"))
    if row.get("public") and filings:
        return component("financial", "Listed and filing on time", "clear", source="EDGAR",
                         detail=f"Most recent filing {max(filings).isoformat()}")
    if status in ("active", "registered"):
        return component("financial", "Registration active, no filings to analyse", "clear", source="SAM.gov",
                         detail="A private entity's finances are not visible here; this grades continuity, not solvency")
    return component("financial", "Financial health", None,
                     detail="Private entity with no filings, market data or registration record")


def dependence_weights(edges: list[dict]) -> list[tuple[dict, float]]:
    """How much of a consumer's exposure each of its suppliers carries.

    A sole-source award means nothing else was competed for that scope, so the supplier is
    irreplaceable and carries the consumer's full exposure to whatever is wrong with it —
    weight 1.0, and several sole sources each carry their own.

    Everything else is substitutable within its group, so the group shares one unit of
    exposure between them, split by obligated amount where the awards say and evenly where
    they do not. That is the dilution: the same troubled company is a whole problem when
    it is the only option and a sixth of one when it is one of six.
    """
    sole = [e for e in edges if e.get("sole_source")]
    competed = [e for e in edges if not e.get("sole_source")]
    out: list[tuple[dict, float]] = [(e, 1.0) for e in sole]
    total = sum(float(e.get("amount") or 0) for e in competed)
    for e in competed:
        # Amounts are missing on plenty of sub-award rows; an even split is the honest
        # fallback, not a reason to drop the supplier from the calculation.
        out.append((e, (float(e["amount"]) / total) if total > 0 else 1.0 / len(competed)))
    return out


def _dependency(row: dict, weighted: list[tuple[dict, float]], scores: dict[str, int | None]) -> dict:
    """A consumer's exposure through the suppliers it cannot replace.

    Exposure is the worst of two readings, not the sum of everything:

    * each **sole source** contributes its own risk undiluted, because it is a single
      point of failure in its own right. They are not added together — a consumer with two
      irreplaceable suppliers at 80 is 80 exposed twice over, not 160 exposed, and adding
      them would let a long list of unremarkable sole sources manufacture a severe finding
      out of nothing. How many there are is a structural fact, reported in the detail.
    * the **substitutable group** shares one unit of dependence between its members, so
      what it contributes is their share-weighted average: as bad as its worst member only
      when they are all that bad, and a quarter of it when three of the four are fine.

    So a single-point-of-failure vendor at 80 hands its customer 80; the same vendor as one
    of four equal competed suppliers hands over 20.
    """
    if not weighted:
        return component("dependency", "Supplier dependence", None,
                         detail="No supplier relationships recorded for this consumer")
    graded = [(e, w, scores[e["supplier"]]) for e, w in weighted if scores.get(e["supplier"]) is not None]
    unscored = [e for e, _ in weighted if scores.get(e["supplier"]) is None]
    if not graded:
        return component("dependency", "Supplier dependence", None,
                         detail=f"{len(weighted)} supplier{'s' if len(weighted) != 1 else ''} on record, none of them scored yet")

    sole = [(e, w, s) for e, w, s in graded if e.get("sole_source")]
    competed = [(e, w, s) for e, w, s in graded if not e.get("sole_source")]
    options: list[tuple[float, dict, float]] = [(s * w, e, w) for e, w, s in sole]
    if competed:
        lead_e, lead_w, _ = max(competed, key=lambda c: c[2] * c[1])
        options.append((sum(s * w for _, w, s in competed), lead_e, lead_w))
    exposure, lead_edge, lead_weight = max(options, key=lambda o: o[0])
    exposure = min(100.0, exposure)
    severity = next((sev for floor, sev in DEPENDENCY_SEVERITY if exposure >= floor), "clear")
    lead_score = scores.get(lead_edge["supplier"])
    n_sole = sum(1 for e, _ in weighted if e.get("sole_source"))

    if lead_edge.get("sole_source"):
        label = f"Sole-source dependence on {lead_edge['supplier_name']} (risk {lead_score})"
    elif lead_weight >= 0.99:
        label = f"Single supplier — {lead_edge['supplier_name']} (risk {lead_score})"
    else:
        label = (f"Supply base carries {exposure:.0f} risk — {lead_edge['supplier_name']} is its largest share "
                 f"at {lead_weight:.0%} (risk {lead_score})")
    parts = [f"Exposure {exposure:.0f}/100 across {len(weighted)} supplier{'s' if len(weighted) != 1 else ''}"]
    if n_sole:
        parts.append(f"{n_sole} sole-source, graded on the worst rather than added up")
    if unscored:
        # Named, because unscored suppliers can only understate this dimension and the
        # reader has to know the exposure is a floor rather than a total.
        parts.append(f"{len(unscored)} unscored and contributing nothing")
    top = sorted(graded, key=lambda c: c[2] * c[1], reverse=True)[:3]
    parts.append("; ".join(f"{e['supplier_name']} {w:.0%}×{s}" for e, w, s in top))
    ids = [row["id"]] + [i for e, _, _ in top for i in (e["supplier"], e.get("edge_id")) if i]
    return component("dependency", label, severity, source="USAspending",
                     detail=" · ".join(parts), ids=list(dict.fromkeys(ids)))


def _media(screens: dict[str, dict]) -> dict:
    adv = screens.get("adverse_media_screen")
    if not adv:
        return component("media", "Adverse media", None, detail="No media screen has run")
    severity = adv["result"] if adv["result"] in SEVERITY_WEIGHT else "low"
    return component("media", "Adverse media" + ("" if severity == "clear" else f" — {severity}"), severity,
                     source=adv.get("source"), detail=adv.get("detail"), url=adv.get("url"))


# --- The pass ---------------------------------------------------------------------

def confidence(components: list[dict]) -> int:
    """How much of the model actually answered, as a percentage of dimension weight.

    The score alone cannot be read safely without this. A node one hop from a designated
    party, seated in a covered nation and screened by nobody scores 100 on two dimensions
    and outranks a party that is itself designated but graded on six — because a mean over
    what answered is the only average that does not impute zeros. That ordering is
    defensible (all we know about it is bad) but only if the thinness travels with it,
    so confidence is stored, returned and drawn everywhere the score is.
    """
    scored = [c for c in components if not c["no_data"]]
    total = sum(c["weight"] for c in components)
    return round(100 * sum(c["weight"] for c in scored) / total) if total else 0


def _score(components: list[dict], row: dict, label: str) -> dict:
    value, scored = composite(components)
    worst = max(scored, key=lambda c: c["weight"] * SEVERITY_WEIGHT[c["severity"]], default=None) if scored else None
    missing = [c["label"] for c in components if c["no_data"]]
    conf = confidence(components)
    return {
        "id": row["id"], "name": row.get("name"), "label": label,
        "score": value, "band": band(value), "confidence": conf,
        "components": components,
        "dimensions_scored": len(scored), "dimensions_requested": len(components),
        "top_factor": worst["label"] if worst and worst["severity"] != "clear" else None,
        "note": (
            f"Scored on {len(scored)} of {len(components)} dimensions ({conf}% of the model's weight); "
            f"{len(missing)} returned no data and were left out rather than counted as clear"
            + (f" — {', '.join(missing)}." if missing else ".")
            + (" Enrich this node to raise the confidence before acting on the score." if conf < 60 else "")
            if scored else "No dimension returned data; this node is unscored, not clear."
        ),
        "reference": riskdata.refresh_note(),
    }


async def score_nodes(ids: list[str] | None = None) -> dict[str, dict]:
    """Score every Entity and Person, or just the given ids. Reads only; see persist().

    Two phases, because one dimension depends on the others. Everything a node carries in
    its own right is graded first; only then can a consumer be graded on what it inherits
    from suppliers, since that needs their scores to exist. The inherited dimension is then
    swept a few times so exposure travels the length of a sole-source chain rather than
    stopping one hop from the vendor that caused it.
    """
    today = date.today()
    seeds = await _designated_ids()
    entities = await _entities(ids)
    persons = await _people(ids)
    screens = await _screens(ids)
    parents = await _ultimate_parents(ids)
    near = merge_proximity(await _proximity(seeds, ids, PROXIMITY_RELS_DOWNSTREAM),
                           await _proximity(seeds, ids, PROXIMITY_RELS_ANY))
    supply = await _supply_edges()

    # --- phase 1: what each node is, on its own ---------------------------------
    intrinsic: dict[str, list[dict]] = {}
    rows_by_id: dict[str, dict] = {}
    labels: dict[str, str] = {}
    for row in entities:
        s = screens.get(row["id"], {})
        intrinsic[row["id"]] = [
            _designation(row, s),
            _proximity_component(row, near.get(row["id"])),
            _foreign(row, parents.get(row["id"], [])),
            _financial(row, s, today),
            _regional(row),
            _media(s),
        ]
        rows_by_id[row["id"]] = row
        labels[row["id"]] = "Entity"

    # A person is graded on the dimensions that mean something for a person. Financial
    # distress, regional exposure and supplier dependence belong to organisations; a person
    # meets them only through the entity, where they are already scored.
    entity_by_id = {e["id"]: e for e in entities}
    for row in persons:
        s = screens.get(row["id"], {})
        intrinsic[row["id"]] = [
            _designation(row, s),
            _proximity_component(row, near.get(row["id"])),
            _person_foreign(row, entity_by_id, parents),
            _media(s),
        ]
        rows_by_id[row["id"]] = row
        labels[row["id"]] = "Person"

    # --- phase 2: what a consumer inherits from its suppliers --------------------
    # Suppliers outside the rescored subset still have to contribute, so the starting
    # scores come from the graph for anything phase 1 did not compute.
    scores: dict[str, int | None] = {nid: composite(comps)[0] for nid, comps in intrinsic.items()}
    if ids is not None:
        scores = {**await _stored_scores(), **scores}
    weights = {cid: dependence_weights(edges) for cid, edges in supply.items()}
    dep: dict[str, dict] = {}
    for _ in range(DEPENDENCY_PASSES):
        dep = {cid: _dependency(rows_by_id.get(cid, {"id": cid}), w, scores) for cid, w in weights.items()}
        for nid, comps in intrinsic.items():
            if labels[nid] == "Entity":
                scores[nid] = composite(comps + [dep.get(nid) or _dependency({"id": nid}, [], scores)])[0]

    out: dict[str, dict] = {}
    for nid, comps in intrinsic.items():
        full = comps + ([dep.get(nid) or _dependency(rows_by_id[nid], [], scores)] if labels[nid] == "Entity" else [])
        out[nid] = _score(full, rows_by_id[nid], labels[nid])
    return out


async def _stored_scores() -> dict[str, int | None]:
    """Scores already on the graph, for suppliers a targeted rescore does not recompute."""
    rows = await db.read(
        "MATCH (n:Entity) WHERE n.risk_score IS NOT NULL RETURN n.id AS id, n.risk_score AS score")
    return {r["id"]: r["score"] for r in rows}


def _person_foreign(row: dict, entity_by_id: dict[str, dict], parents: dict[str, list[dict]]) -> dict:
    """A person's jurisdiction exposure is the seats they hold, not their nationality.

    The graph records no nationality for most people and guessing one from a name is how a
    screening tool turns into a discrimination engine. What it does record is which
    organisations someone sits in, and where those are.
    """
    current = [r for r in (row.get("roles") or []) if r.get("current")]
    seats = current or (row.get("roles") or [])
    graded: list[tuple[str, str, str]] = []      # severity, code, entity name
    for seat in seats:
        ent = entity_by_id.get(seat["id"])
        if not ent:
            continue
        codes = ((ent.get("incorporated") or []) + (ent.get("parent_seat") or [])
                 + [p["code"] for p in parents.get(ent["id"], []) if p.get("code")])
        for code in codes:
            cls = riskdata.jurisdiction_class(code)
            if cls:
                graded.append((riskdata.CLASS_SEVERITY[cls], code, seat.get("name") or ent.get("name") or ""))
    if not graded:
        return component("foreign", "Jurisdiction of seats", None,
                         detail="No role at an entity with a resolved jurisdiction")
    severity, code, where = max(graded, key=lambda g: SEVERITY_WEIGHT[g[0]])
    tense = "Holds" if current else "Held"
    if severity == "clear":
        return component("foreign", "Seats are domestic or allied throughout", "clear",
                         source=riskdata.JURISDICTION_SOURCE, ids=[row["id"]])
    cls = riskdata.jurisdiction_class(code)
    return component("foreign", f"{tense} a seat at {where} — {code}, {riskdata.CLASS_LABEL[cls]}", severity,
                     source=riskdata.JURISDICTION_SOURCE, ids=[row["id"]])


async def persist(ids: list[str] | None = None) -> dict:
    """Score and write back. Returns a summary of what changed."""
    scores = await score_nodes(ids)
    rows = [{
        "id": s["id"], "score": s["score"], "band": s["band"], "confidence": s["confidence"],
        "components": json.dumps(s["components"]), "scored": s["dimensions_scored"],
        "requested": s["dimensions_requested"], "top": s["top_factor"], "note": s["note"],
    } for s in scores.values()]
    if rows:
        await db.write(
            """
            UNWIND $rows AS row
            MATCH (n {id: row.id})
            SET n.risk_score = row.score, n.risk_band = row.band, n.risk_components = row.components,
                n.risk_confidence = row.confidence, n.risk_dimensions_scored = row.scored,
                n.risk_dimensions_requested = row.requested, n.risk_top_factor = row.top,
                n.risk_note = row.note, n.risk_scored_at = $now
            """,
            {"rows": rows, "now": now_iso()},
        )
    bands: dict[str, int] = {}
    for s in scores.values():
        bands[s["band"] or "unscored"] = bands.get(s["band"] or "unscored", 0) + 1
    thin = sum(1 for s in scores.values() if (s["confidence"] or 0) < 60)
    return {"scored": len(rows), "bands": bands, "low_confidence": thin, "scored_at": now_iso(),
            "max_hops": PROXIMITY_MAX_HOPS, "reference": riskdata.refresh_note()}


async def explain(node_id: str) -> dict | None:
    """The stored breakdown for one node, recomputed if it has never been scored."""
    rows = await db.read(
        "MATCH (n {id:$id}) RETURN n.id AS id, n.name AS name, head(labels(n)) AS label, n.risk_score AS score, "
        "n.risk_band AS band, n.risk_confidence AS confidence, n.risk_components AS components, n.risk_note AS note, "
        "n.risk_scored_at AS scored_at, n.risk_top_factor AS top_factor, n.risk_dimensions_scored AS dimensions_scored, "
        "n.risk_dimensions_requested AS dimensions_requested",
        {"id": node_id},
    )
    if not rows:
        return None
    row = rows[0]
    if row.get("components"):
        return {**row, "components": json.loads(row["components"]), "reference": riskdata.refresh_note(),
                "weights": {k: v[0] for k, v in DIMENSIONS.items()}}
    fresh = (await score_nodes([node_id])).get(node_id)
    if not fresh:
        return None
    return {**fresh, "scored_at": None, "weights": {k: v[0] for k, v in DIMENSIONS.items()}}
