"""Generated reports, kept in the graph beside what they are about.

A report used to be a page. You pressed Report on a vendor and the app rendered the UC-11
projection into a view that existed for as long as you looked at it: nothing was kept,
nothing could be handed to anyone, and the graph — which is where this application keeps
everything else it knows — had no idea a report had ever been made.

A Report is now a node. It carries the finished HTML document, when it was generated and
what it found; it points at its subject with REPORTS_ON and at every node it names with
CITES, so the document and the canvas cite the same evidence and a finding can be walked
back to the nodes that produced it. Regenerating rewrites that same node from current data
under a new timestamp, which is the only sane behaviour for a report about a graph that
keeps changing — the id is stable per (kind, subject) so a workspace never accumulates a
drift of near-identical documents nobody can tell apart.

Two kinds ship:

  risk_assessment  the default, and the one the chat is expected to be asked for. For a
                   program (or any consumer), every supply path into it that carries
                   significant risk: what the path is, what goods or services ride on it,
                   where the risk actually comes from, and what can be done about it.
  entity_profile   one organisation's standardised profile — the projection report.py
                   already computes — rendered as a document rather than a page.

Three rules this module answers to, two of them inherited from the scorer it reads:

1. **A supplier the scorer could say nothing about is not a safe supplier.** Coverage is
   stated in the document, and the sole-source suppliers that have never been screened get
   a section of their own rather than an absence.
2. **Nothing is asserted that cannot be shown.** Every finding carries the ids of the nodes
   and edges behind it, into CITES and into the canvas.
3. **The model is optional.** Findings, paths, goods and mitigations are computed from the
   graph. A key buys an executive summary and an analyst note on top; without one the
   report loses two paragraphs, never a section.

Generation writes to the graph without the permission gate, for the reason risk scoring
does not use it either (routers/risk.py): a report asserts nothing about the world that is
not already committed in the graph, it is recomputable from that graph at any time, and it
was asked for explicitly. What it writes is announced, so an open canvas draws it at once.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from . import db, events, report as entity_report, risk, riskdata
from .ids import edge_id, report_id

# How far back up the supply base an assessment looks. Four hops is program ← prime ← sub
# ← sub-sub, deeper than any sub-award data the connectors have produced, and the same
# ceiling risk.py's dependency sweep uses.
SUPPLY_DEPTH = 4

# What earns a supplier a place in the findings: the floor of risk.py's "elevated" band, not
# a number picked here. A report of everything is a report of nothing. A designated party is
# in whatever it scored — a hit is the finding, and it is never filtered out by a threshold.
FINDING_FLOOR = 25
MAX_FINDINGS = 25
MAX_GAPS = 20
# Nodes a report may CITE. The edges exist so the canvas can show what a document names;
# past a few dozen that stops being a citation and starts being a second copy of the graph.
MAX_CITED = 60

HOME = riskdata.HOME


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReportError(Exception):
    """The report cannot be built — no such subject, or the wrong kind of one."""


# --- gathering -------------------------------------------------------------------------

async def subject_of(subject_id: str) -> dict:
    rows = await db.read(
        """
        MATCH (e:Entity {id:$id})
        OPTIONAL MATCH (e)-[:INCORPORATED_IN]->(inc:Location)
        RETURN e.id AS id, e.name AS name, coalesce(e.kind,'organization') AS kind, e.uei AS uei, e.cage AS cage,
               e.lei AS lei, e.risk_score AS score, e.risk_band AS band, e.risk_confidence AS confidence,
               e.risk_top_factor AS top_factor, e.risk_note AS note, e.risk_scored_at AS scored_at,
               e.risk_dimensions_scored AS dimensions_scored, e.risk_dimensions_requested AS dimensions_requested,
               coalesce(e.simulated,false) AS simulated, coalesce(e.flagged,false) AS flagged,
               inc.code AS incorporated, e.summary AS summary
        LIMIT 1
        """,
        {"id": subject_id},
    )
    if not rows:
        raise ReportError(f"no entity {subject_id}")
    return rows[0]


async def _breakdowns(ids: list[str]) -> dict[str, list[dict]]:
    """The stored risk components for many nodes at once.

    risk.explain() is the usual way in, but it recomputes a node that has never been
    scored, and a report that quietly ran a scoring pass per finding would take minutes and
    write while claiming to read. What is stored is what the canvas and the entity list are
    showing, and a report has to agree with them; a node with nothing stored is reported as
    unscored, which is a finding of its own.
    """
    if not ids:
        return {}
    rows = await db.read(
        "MATCH (n) WHERE n.id IN $ids RETURN n.id AS id, n.risk_components AS components",
        {"ids": ids},
    )
    out: dict[str, list[dict]] = {}
    for r in rows:
        raw = r.get("components")
        if not raw:
            continue
        try:
            out[r["id"]] = json.loads(raw)
        except (TypeError, ValueError):
            continue
    return out


async def supply_findings(subject_id: str, depth: int = SUPPLY_DEPTH, floor: int = FINDING_FLOOR,
                          limit: int = MAX_FINDINGS) -> list[dict]:
    """Suppliers that reach the subject and carry risk, each with the path it reaches by.

    The path is the point. A tier-3 casting house scored severe is only actionable once you
    can see that it reaches the program through one prime on one sole-source award — that
    is the difference between a finding and a name on a list — so every row comes back with
    its shortest supply route and the contract references along it.
    """
    rows = await db.read(
        f"""
        MATCH (root:Entity {{id:$id}})
        MATCH (v:Entity)-[:SUPPLIES*1..{int(depth)}]->(root)
        WHERE v.id <> root.id AND (coalesce(v.risk_score, -1) >= $floor OR coalesce(v.flagged, false))
        WITH DISTINCT root, v
        ORDER BY coalesce(v.risk_score, 0) DESC, v.name
        LIMIT $limit
        MATCH path = shortestPath((v)-[:SUPPLIES*1..{int(depth)}]->(root))
        OPTIONAL MATCH (v)-[:PROVIDES]->(c:Category)
        OPTIONAL MATCH (v)-[:INCORPORATED_IN]->(inc:Location)
        OPTIONAL MATCH (v)-[:PARENT_SEATED_IN]->(seat:Location)
        OPTIONAL MATCH (v)-[:MANUFACTURES_IN]->(mfg:Location)
        RETURN v.id AS id, v.name AS name, v.risk_score AS score, v.risk_band AS band,
               v.risk_confidence AS confidence, v.risk_top_factor AS top_factor,
               v.risk_dimensions_scored AS dimensions_scored, v.risk_dimensions_requested AS dimensions_requested,
               coalesce(v.flagged,false) AS flagged, coalesce(v.simulated,false) AS simulated,
               v.uei AS uei, v.cage AS cage, length(path) AS tier,
               [n IN nodes(path) | {{id:n.id, name:n.name, kind:n.kind}}] AS chain,
               [r IN relationships(path) | {{id:r.id, tier:r.tier, sole_source:coalesce(r.sole_source,false),
                 amount:r.amount, contract_ref:r.contract_ref, psc:r.psc, naics:r.naics,
                 source:r.source, source_url:r.source_url, simulated:coalesce(r.simulated,false)}}] AS hops,
               collect(DISTINCT c{{.id,.name,.kind}}) AS categories,
               inc.code AS incorporated, seat.code AS parent_seat,
               collect(DISTINCT mfg.code) AS manufactures
        ORDER BY coalesce(score, 0) DESC, tier
        LIMIT $limit
        """,
        {"id": subject_id, "floor": floor, "limit": int(limit)},
    )
    breakdowns = await _breakdowns([r["id"] for r in rows])
    for r in rows:
        r["categories"] = [c for c in r["categories"] if c and c.get("id")]
        r["manufactures"] = [m for m in r["manufactures"] if m]
        r["hops"] = r["hops"] or []
        r["chain"] = r["chain"] or []
        r["simulated"] = bool(r["simulated"]) or any(h.get("simulated") for h in r["hops"])
        r["sole_source"] = any(h.get("sole_source") for h in r["hops"])
        # The graded dimensions, worst first. `clear` and no-data are dropped: a report
        # section headed "where the risk comes from" that lists what is fine is noise.
        comps = breakdowns.get(r["id"], [])
        r["drivers"] = sorted(
            [c for c in comps if c.get("severity") in ("high", "medium", "low")],
            key=lambda c: (-risk.SEVERITY_WEIGHT.get(c.get("severity") or "clear", 0.0), -(c.get("weight") or 0)),
        )
        r["mitigations"] = mitigations_for(r)
        r["element_ids"] = element_ids(r)
    return rows


def element_ids(finding: dict) -> list[str]:
    """Everything on the canvas this finding is made of: the supplier, its route into the
    subject, and whatever each graded dimension was computed from."""
    ids = [finding["id"]]
    ids += [n["id"] for n in finding.get("chain") or [] if n.get("id")]
    ids += [h["id"] for h in finding.get("hops") or [] if h.get("id")]
    for d in finding.get("drivers") or []:
        ids += [i for i in (d.get("element_ids") or []) if i]
    return list(dict.fromkeys(ids))


async def coverage(subject_id: str, depth: int = SUPPLY_DEPTH) -> dict:
    """How much of the supply base the assessment could actually see.

    Printed in the document because it is the difference between "three risky suppliers"
    and "three risky suppliers out of forty, of which nine have never been screened".
    """
    rows = await db.read(
        f"""
        MATCH (root:Entity {{id:$id}})
        MATCH (v:Entity)-[:SUPPLIES*1..{int(depth)}]->(root)
        WITH DISTINCT v
        RETURN count(*) AS suppliers,
               sum(CASE WHEN v.risk_score IS NULL THEN 0 ELSE 1 END) AS scored,
               sum(CASE WHEN v.risk_score IS NOT NULL AND coalesce(v.risk_confidence, 0) < 60 THEN 1 ELSE 0 END) AS thin,
               sum(CASE WHEN coalesce(v.flagged, false) THEN 1 ELSE 0 END) AS flagged
        LIMIT 1
        """,
        {"id": subject_id},
    )
    r = rows[0] if rows else {"suppliers": 0, "scored": 0, "thin": 0, "flagged": 0}
    r["unscored"] = (r["suppliers"] or 0) - (r["scored"] or 0)
    r["depth"] = int(depth)
    return r


async def unscreened_sole_sources(subject_id: str, depth: int = SUPPLY_DEPTH, limit: int = MAX_GAPS) -> list[dict]:
    """Irreplaceable and unexamined: sole-source suppliers in the chain the scorer has
    nothing on. Not a finding — there is nothing to find yet — which is exactly why it is
    the most useful list in the document."""
    return await db.read(
        f"""
        MATCH (root:Entity {{id:$id}})
        MATCH (v:Entity)-[:SUPPLIES*1..{int(depth)}]->(root)
        WITH DISTINCT root, v WHERE v.risk_score IS NULL
        MATCH (v)-[s:SUPPLIES]->(c:Entity) WHERE coalesce(s.sole_source, false)
        RETURN v.id AS id, v.name AS name, c.name AS consumer, s.contract_ref AS contract_ref,
               s.psc AS psc, s.tier AS tier, s.source AS source, s.source_url AS source_url
        ORDER BY coalesce(s.tier, 9), v.name
        LIMIT $limit
        """,
        {"id": subject_id, "limit": int(limit)},
    )


# --- mitigations -----------------------------------------------------------------------
# One list per risk dimension, in the vocabulary risk.py grades in. These are the actions a
# supply-chain officer can actually take, written to be true of the dimension rather than
# of any particular company — this tool flags, it does not accuse, and a recommendation
# that reads as an allegation would undo that in one sentence.
MITIGATIONS: dict[str, list[str]] = {
    "designation": [
        "Confirm the match against the issuing list before anything else — designations are recorded against "
        "names and identifiers that collide, and the first question is whether this is the same party.",
        "If it holds, treat it as a compliance event rather than a risk to weigh: stop new obligations on the "
        "affected line, and take it to counsel and the contracting officer.",
        "Trace what has already shipped on this path and over what period.",
    ],
    "proximity": [
        "Walk the connecting hops and confirm each still holds — a route through a former officer or a lapsed "
        "holding is a different exposure from a live one.",
        "Ask the supplier to disclose the relationship in writing, and record the answer as evidence against "
        "this path.",
        "Where the route runs through ownership, require notice of any change of control on the contract.",
    ],
    "foreign": [
        "Obtain a current registry extract for the ultimate parent and confirm the jurisdiction rather than "
        "inferring it from the trading name.",
        "Assess against the covered-nation sourcing rules (10 U.S.C. § 4872) and any program-specific "
        "supply-chain clauses before the next award.",
        "Where the position is otherwise sound, consider a mitigation agreement — proxy board, security "
        "control, or a domestic manufacturing condition — rather than removal.",
    ],
    "financial": [
        "Request current financials and confirm registration status directly in SAM before the next order.",
        "Assess time-to-replace for what this supplier provides, and hold buffer stock across that window.",
        "Add continuity terms — notice of insolvency proceedings, tooling and data escrow — at renewal.",
    ],
    "regional": [
        "Establish where the work is physically done, which is rarely where the company is registered.",
        "Ask for the continuity plan for the site, and for an alternate site that is not exposed to the same "
        "hazard or conflict.",
        "Where a single region carries several suppliers, treat it as one point of failure, not several.",
    ],
    "dependency": [
        "Quantify time-to-replace for the affected line and hold inventory across it.",
        "Qualify a second source; where qualification is long, start it now rather than at the first disruption.",
        "Make the dependency visible in the program's risk register with the supplier named.",
    ],
    "media": [
        "Read the underlying coverage rather than the count — adverse media is a prompt to look, not a finding.",
        "Where the reporting concerns conduct that would matter to the award, ask the supplier for its account "
        "and record it.",
    ],
}

# Every finding gets this one, in front of the dimension-specific ones: the thing to do
# with a report is to check it, and the graph makes that cheap.
VERIFY_FIRST = ("Verify the finding against the sources cited here before acting on it — every element is a node "
                "in the graph and each carries where it came from.")


def mitigations_for(finding: dict) -> list[str]:
    """Recommendations for one finding: the verification step, then whatever the graded
    dimensions call for, then the sole-source consequence when there is one."""
    out = [VERIFY_FIRST]
    seen: set[str] = set()
    for d in finding.get("drivers") or []:
        dim = d.get("dimension") or d.get("family")
        if dim in seen:
            continue
        seen.add(dim)
        out += MITIGATIONS.get(dim, [])
    if finding.get("flagged") and "designation" not in seen:
        out += MITIGATIONS["designation"]
    if finding.get("sole_source"):
        consumer = next((h for h in finding.get("hops") or [] if h.get("sole_source")), {})
        ref = f" ({consumer['contract_ref']})" if consumer.get("contract_ref") else ""
        out.append(
            f"This supplier is sole-source on at least one award{ref} on the path shown, so nothing on that path "
            "absorbs its problems: qualify an alternate for the affected goods or services, or accept the "
            "dependency explicitly in the program risk register."
        )
    if not finding.get("score"):
        out.append("Enrich this supplier so the finding can be scored: it is here on a designation or a flag, "
                   "with no graded dimensions behind it.")
    return list(dict.fromkeys(out))


# --- assembly --------------------------------------------------------------------------

async def assemble_risk_assessment(subject_id: str, depth: int = SUPPLY_DEPTH) -> dict:
    subject = await subject_of(subject_id)
    findings = await supply_findings(subject_id, depth=depth)
    cov = await coverage(subject_id, depth=depth)
    gaps = await unscreened_sole_sources(subject_id, depth=depth)
    sources = sorted({
        s for f in findings
        for s in [h.get("source") for h in f["hops"]] + [d.get("source") for d in f["drivers"]]
        if s
    })
    cited = list(dict.fromkeys([i for f in findings for i in f["element_ids"]] + [g["id"] for g in gaps]))
    # Relationship ids ride along in element_ids for the canvas trace; CITES is between
    # nodes, so only node ids can become edges here.
    cited_nodes = [i for i in cited if not i.startswith("rel_")][:MAX_CITED]
    return {
        "kind": "risk_assessment",
        "title": f"Supply-chain risk assessment — {subject['name']}",
        "subject": subject,
        "findings": findings,
        "coverage": cov,
        "gaps": gaps,
        "sources": sources,
        "cited_ids": cited_nodes,
        "element_ids": cited,
        "simulated": bool(subject.get("simulated")) or any(f["simulated"] for f in findings),
        "weights": {k: v[0] for k, v in risk.DIMENSIONS.items()},
        "reference": riskdata.refresh_note(),
        "depth": int(depth),
    }


async def assemble_entity_profile(subject_id: str) -> dict:
    rep = await entity_report.build_report(subject_id)
    if not rep:
        raise ReportError(f"no entity {subject_id}")
    ident = rep["identity"]
    cited = [subject_id]
    cited += [p["id"] for p in (rep["control"].get("ultimate_parents") or []) if p.get("id")]
    cited += [p["id"] for p in (rep["control"].get("direct_parents") or []) if p.get("id")]
    cited += [p["person_id"] for p in rep["people"]["current"][:20] if p.get("person_id")]
    element_ids = list(dict.fromkeys(cited + [i for ind in rep["risk"]["indicators"] for i in (ind.get("element_ids") or [])]))
    return {
        "kind": "entity_profile",
        "title": f"Vendor profile — {ident['name']}",
        "subject": {
            "id": ident["id"], "name": ident["name"], "kind": ident.get("kind") or "organization",
            "uei": ident.get("uei"), "cage": ident.get("cage"), "lei": ident.get("lei"),
            "score": rep["risk"].get("composite"), "band": rep["risk"].get("band"),
            "confidence": rep["risk"].get("confidence"), "top_factor": rep["risk"].get("top_factor"),
            "note": rep["risk"].get("note"), "simulated": bool(ident.get("simulated")),
        },
        "report": rep,
        "sources": rep["sources"],
        "cited_ids": list(dict.fromkeys(cited))[:MAX_CITED],
        "element_ids": element_ids,
        "simulated": bool(ident.get("simulated")),
        "reference": rep["risk"].get("reference"),
    }


# --- HTML --------------------------------------------------------------------------------
# The document is standalone: one file, no scripts, no external assets, styled for a screen
# and for paper. It is rendered in a sandboxed frame in the app and is meant to survive
# being saved and mailed to somebody who has never heard of this application.

def esc(v) -> str:
    return html.escape(str(v), quote=True) if v is not None else ""


CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #f6f7f9; color: #16181d; font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 32px 34px 64px; background: #fff; }
h1 { font-size: 25px; line-height: 1.2; margin: 0 0 4px; letter-spacing: -.01em; }
h2 { font-size: 16px; margin: 34px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #e3e6ea; letter-spacing: .01em; }
h3 { font-size: 15px; margin: 0 0 6px; }
p { margin: 0 0 10px; }
a { color: #1d4ed8; }
.eyebrow { font: 600 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .18em; text-transform: uppercase; color: #6b7280; margin: 0 0 10px; }
.meta { color: #5b616b; font-size: 13px; margin: 0 0 4px; }
.meta b { color: #16181d; font-weight: 600; }
.chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; letter-spacing: .02em; border: 1px solid; vertical-align: 1px; }
.sev-severe, .sev-high { background: #fef2f2; border-color: #dc2626; color: #991b1b; }
.sev-medium, .sev-elevated { background: #fffbeb; border-color: #d97706; color: #92400e; }
.sev-low { background: #f3f4f6; border-color: #9ca3af; color: #4b5563; }
.sev-clear { background: #f0fdf4; border-color: #16a34a; color: #166534; }
.sev-none { background: #f3f4f6; border-color: #d1d5db; color: #6b7280; }
.sim { background: #fff4cf; border: 1px solid #9a6700; color: #563b00; padding: 8px 12px; border-radius: 6px; font-size: 13px; margin: 14px 0; }
table { border-collapse: collapse; width: 100%; font-size: 13px; margin: 6px 0 4px; }
th { text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; border-bottom: 1px solid #e3e6ea; padding: 5px 8px 5px 0; font-weight: 600; }
td { padding: 6px 8px 6px 0; border-bottom: 1px solid #eef0f3; vertical-align: top; }
.finding { border: 1px solid #e3e6ea; border-left: 4px solid #cbd5e1; border-radius: 6px; padding: 14px 16px; margin: 0 0 14px; page-break-inside: avoid; }
.finding.severe, .finding.high { border-left-color: #dc2626; }
.finding.elevated { border-left-color: #d97706; }
.finding-head { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.finding-head .num { font: 600 12px ui-monospace, SFMono-Regular, Menlo, monospace; color: #6b7280; }
.label { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; font-weight: 600; margin: 12px 0 3px; }
.path { font-size: 13px; line-height: 2; }
.path .node { background: #f3f4f6; border: 1px solid #e3e6ea; border-radius: 4px; padding: 2px 7px; }
.path .node.root { background: #eef4ff; border-color: #bfd3ff; font-weight: 600; }
.path .hop { color: #6b7280; font: 11px ui-monospace, SFMono-Regular, Menlo, monospace; padding: 0 5px; white-space: nowrap; }
.path .hop.sole { color: #92400e; font-weight: 600; }
ul { margin: 4px 0 0; padding-left: 20px; }
li { margin-bottom: 4px; }
.driver { margin-bottom: 8px; }
.driver .detail { color: #4b5563; font-size: 13px; }
.src { font-size: 12px; color: #6b7280; }
.note { background: #f8fafc; border: 1px solid #e3e6ea; border-radius: 6px; padding: 12px 14px; font-size: 13px; color: #384049; margin: 12px 0; }
.disclaimer { font-size: 12px; color: #6b7280; border-top: 1px solid #e3e6ea; margin-top: 34px; padding-top: 12px; }
.empty { color: #6b7280; font-size: 13px; }
@media print { body { background: #fff; } main { max-width: none; padding: 0; } h2 { page-break-after: avoid; } }
"""

DISCLAIMER = ("Every finding here marks opacity, concentration, dependence or foreign control — conditions "
              "warranting human review. This tool flags; it does not accuse. Nothing in this document is an "
              "allegation of wrongdoing by any named party, and no finding should be acted on before the "
              "sources it cites have been checked.")


def _document(title: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{esc(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n"
    )


def _band_chip(band: str | None, score: int | None) -> str:
    if score is None and not band:
        return '<span class="chip sev-none">unscored</span>'
    cls = {"severe": "sev-severe", "high": "sev-high", "elevated": "sev-elevated", "low": "sev-low"}.get(band or "", "sev-none")
    text = f"{score} · {band}" if score is not None and band else (band or "unscored")
    return f'<span class="chip {cls}">{esc(text)}</span>'


def _sev_chip(sev: str | None) -> str:
    cls = {"high": "sev-high", "medium": "sev-medium", "low": "sev-low", "clear": "sev-clear"}.get(sev or "", "sev-none")
    return f'<span class="chip {cls}">{esc(sev or "no data")}</span>'


def _coverage_sentence(cov: dict) -> str:
    n, scored, unscored = cov.get("suppliers") or 0, cov.get("scored") or 0, cov.get("unscored") or 0
    if not n:
        return "No supply relationships reach this subject in the graph, so there was nothing to assess."
    parts = [f"{n} supplier{'s' if n != 1 else ''} reach this subject within {cov.get('depth', SUPPLY_DEPTH)} supply hops; "
             f"{scored} carr{'y' if scored != 1 else 'ies'} a risk score"]
    if unscored:
        parts.append(f"{unscored} ha{'ve' if unscored != 1 else 's'} never been scored and could not be assessed here — "
                     "unscored is not clear, it is unexamined")
    if cov.get("thin"):
        parts.append(f"{cov['thin']} scored on thin coverage, where fewer than 60% of the dimensions returned data")
    return ". ".join(p.rstrip(".") for p in parts) + "."


def _path_html(finding: dict) -> str:
    chain, hops = finding.get("chain") or [], finding.get("hops") or []
    if not chain:
        return '<p class="empty">No supply path recorded.</p>'
    out = []
    for i, node in enumerate(chain):
        root = i == len(chain) - 1
        out.append(f'<span class="node{" root" if root else ""}">{esc(node.get("name") or node.get("id"))}</span>')
        if i < len(hops):
            h = hops[i]
            bits = [f"T{h['tier']}"] if h.get("tier") else []
            if h.get("sole_source"):
                bits.append("sole source")
            if h.get("contract_ref"):
                bits.append(esc(h["contract_ref"]))
            label = " · ".join(bits) or "supplies"
            out.append(f'<span class="hop{" sole" if h.get("sole_source") else ""}">→ {label} →</span>')
    return '<div class="path">' + " ".join(out) + "</div>"


def _goods_html(finding: dict) -> str:
    cats = finding.get("categories") or []
    codes = []
    first = (finding.get("hops") or [{}])[0]
    if first.get("psc"):
        codes.append(f"PSC {esc(first['psc'])}")
    if first.get("naics"):
        codes.append(f"NAICS {esc(first['naics'])}")
    if cats:
        named = ", ".join(f"{esc(c['name'])} <span class=\"src\">({esc(c.get('kind') or '')})</span>" for c in cats)
        tail = f' <span class="src">· {" · ".join(codes)}</span>' if codes else ""
        return f"<p>{named}{tail}</p>"
    if codes:
        return (f'<p>{" · ".join(codes)} <span class="src">— coded on the award, not yet classified into the '
                f'goods/services taxonomy</span></p>')
    return ('<p class="empty">Not classified. The award records behind this path carry no product or service code, '
            'so what rides on it is unknown — which is itself worth closing.</p>')


def _drivers_html(finding: dict) -> str:
    drivers = finding.get("drivers") or []
    if not drivers:
        if finding.get("flagged"):
            return ('<p>Named on a designation or exclusion screen. The graded dimensions behind that hit are not '
                    'stored on this node, so the screen result is the whole of the evidence here — open the '
                    'supplier in the graph for the screen record.</p>')
        return '<p class="empty">No dimension returned data. This supplier is listed on a flag alone.</p>'
    out = []
    for d in drivers:
        src = esc(d.get("source") or "")
        if d.get("source_url"):
            src = f'<a href="{esc(d["source_url"])}" target="_blank" rel="noopener noreferrer">{src or esc(d["source_url"])}</a>'
        detail = f'<div class="detail">{esc(d.get("detail"))}</div>' if d.get("detail") else ""
        srcline = f'<div class="src">{src}</div>' if src else ""
        out.append(f'<div class="driver">{_sev_chip(d.get("severity"))} <b>{esc(d.get("label"))}</b>{detail}{srcline}</div>')
    return "".join(out)


def _confidence_sentence(f: dict) -> str:
    if f.get("score") is None:
        return "Unscored — listed on a flag rather than a graded score."
    scored, requested = f.get("dimensions_scored"), f.get("dimensions_requested")
    conf = f.get("confidence")
    if conf is None:
        return ""
    of = f" ({scored} of {requested} dimensions)" if scored is not None and requested is not None else ""
    lead = "Very thin — " if conf < 30 else "Thin — " if conf < 60 else ""
    return f"{lead}{conf}% of the risk model answered for this supplier{of}."


def render_risk_assessment(data: dict, narrative: dict | None = None, generated_at: str | None = None) -> str:
    s, cov = data["subject"], data["coverage"]
    findings, gaps = data["findings"], data["gaps"]
    ids = " · ".join(x for x in [f"UEI {esc(s['uei'])}" if s.get("uei") else "", f"CAGE {esc(s['cage'])}" if s.get("cage") else ""] if x)
    parts = [
        '<p class="eyebrow">Illuminate · Supply-chain risk assessment</p>',
        f"<h1>{esc(s['name'])}</h1>",
        f'<p class="meta"><b>{esc((s.get("kind") or "organization").title())}</b>'
        + (f" · {ids}" if ids else "")
        + f" · assessed to {cov.get('depth', SUPPLY_DEPTH)} supply hops"
        + f" · generated <b>{esc(generated_at or _now())}</b></p>",
        f'<p class="meta">Subject risk: {_band_chip(s.get("band"), s.get("score"))}'
        + (f' <span class="src">{esc(s.get("top_factor"))}</span>' if s.get("top_factor") else "")
        + "</p>",
    ]
    if data.get("simulated"):
        parts.append('<div class="sim"><b>Contains simulated data.</b> One or more nodes or relationships behind '
                     'this assessment are clearly-labelled scenario material for analysis — not observations, not '
                     'allegations, and not a verified finding.</div>')

    parts.append("<h2>Summary</h2>")
    if narrative and narrative.get("summary"):
        parts.append(f"<p>{esc(narrative['summary'])}</p>")
        parts.append(f'<p class="src">Written by {esc(narrative.get("model") or "the configured model")} from the '
                     f'findings below and nothing else.</p>')
    else:
        parts.append(f"<p>{esc(_deterministic_summary(data))}</p>")
    parts.append(f'<p class="meta">{esc(_coverage_sentence(cov))}</p>')

    parts.append("<h2>Findings</h2>")
    if not findings:
        parts.append('<p class="empty">No supplier reaching this subject scores at or above the elevated band '
                     f'({FINDING_FLOOR}/100) or carries a designation flag. That is a statement about what has been '
                     'screened, not a clean bill of health — see coverage above.</p>')
    else:
        rows = "".join(
            f"<tr><td>{i}</td><td>{esc(f['name'])}"
            + (' <span class="chip sev-severe">flagged</span>' if f.get("flagged") else "")
            + (' <span class="chip sev-medium">SIM</span>' if f.get("simulated") else "")
            + f"</td><td>T{f['tier']}</td><td>{_band_chip(f.get('band'), f.get('score'))}</td>"
            f"<td>{esc(f.get('top_factor') or '—')}</td><td>{'yes' if f.get('sole_source') else '—'}</td></tr>"
            for i, f in enumerate(findings, 1)
        )
        parts.append("<table><thead><tr><th>#</th><th>Supplier</th><th>Tier</th><th>Risk</th>"
                     "<th>Leading factor</th><th>Sole source</th></tr></thead><tbody>" + rows + "</tbody></table>")
        for i, f in enumerate(findings, 1):
            conf = _confidence_sentence(f)
            parts.append(
                f'<div class="finding {esc(f.get("band") or "")}">'
                f'<div class="finding-head"><span class="num">{i:02d}</span><h3>{esc(f["name"])}</h3>'
                f'{_band_chip(f.get("band"), f.get("score"))}'
                + (' <span class="chip sev-severe">flagged</span>' if f.get("flagged") else "")
                + "</div>"
                + (f'<p class="src">{esc(conf)}</p>' if conf else "")
                + '<div class="label">Path into ' + esc(s["name"]) + "</div>" + _path_html(f)
                + '<div class="label">Goods and services on this path</div>' + _goods_html(f)
                + '<div class="label">Where the risk comes from</div>' + _drivers_html(f)
                + '<div class="label">Recommended mitigations</div><ul>'
                + "".join(f"<li>{esc(m)}</li>" for m in f["mitigations"])
                + "</ul></div>"
            )

    parts.append("<h2>Irreplaceable and unexamined</h2>")
    if gaps:
        parts.append("<p>These suppliers hold at least one sole-source award on a path into the subject and have "
                     "never been scored. They are not findings — there is nothing yet to find — and that is the "
                     "point: a single point of failure nobody has looked at is the cheapest thing in this document "
                     "to fix.</p>")
        parts.append("<table><thead><tr><th>Supplier</th><th>Sole source into</th><th>Contract</th><th>PSC</th>"
                     "</tr></thead><tbody>" + "".join(
                         f"<tr><td>{esc(g['name'])}</td><td>{esc(g.get('consumer') or '—')}</td>"
                         f"<td>{esc(g.get('contract_ref') or '—')}</td><td>{esc(g.get('psc') or '—')}</td></tr>"
                         for g in gaps) + "</tbody></table>")
    else:
        parts.append('<p class="empty">None: every sole-source supplier on a path into this subject has been scored.</p>')

    parts.append("<h2>Method and limits</h2>")
    parts.append(
        "<p>Suppliers were taken from the graph by walking SUPPLIES edges into the subject up to "
        f"{cov.get('depth', SUPPLY_DEPTH)} hops, and each is shown on its shortest such path. A supplier appears as a "
        f"finding when its stored risk score is at or above {FINDING_FLOOR}/100 — the floor of the elevated band — or "
        "when a designation, debarment or restricted-list screen has flagged it. Scores are the ones computed by the "
        "risk model and stored on the node, so this document, the canvas and the entity list never disagree.</p>"
    )
    parts.append(
        "<p>A score is the weighted mean of the dimensions that returned data; a dimension that returned nothing is "
        "left out rather than counted as clear. So a high score on thin coverage means “everything known is bad”, not "
        "“everything is bad”, and a low score can mean little was asked. Dimension weights: "
        + esc(", ".join(f"{k} ×{v}" for k, v in (data.get("weights") or {}).items())) + ".</p>"
    )
    if narrative and narrative.get("analyst_note"):
        parts.append('<div class="note"><b>Analyst note.</b> ' + esc(narrative["analyst_note"])
                     + f' <span class="src">Written by {esc(narrative.get("model") or "the configured model")}.</span></div>')
    if data.get("sources"):
        parts.append("<h2>Sources</h2><p>" + esc(" · ".join(data["sources"])) + "</p>")
    if data.get("reference"):
        parts.append(f'<p class="src">{esc(data["reference"])}</p>')
    parts.append(f'<p class="disclaimer">{esc(DISCLAIMER)}</p>')
    return _document(data["title"], "\n".join(parts))


def _deterministic_summary(data: dict) -> str:
    """The summary when there is no model key. Says what was found, in the same order the
    document says it, and nothing the findings do not support."""
    s, findings, cov = data["subject"], data["findings"], data["coverage"]
    if not findings:
        return (f"No supplier reaching {s['name']} within {cov.get('depth', SUPPLY_DEPTH)} supply hops is scored at or "
                f"above the elevated band, and none carries a designation flag. "
                f"{_coverage_sentence(cov)}")
    worst = findings[0]
    bands: dict[str, int] = {}
    for f in findings:
        bands[f.get("band") or "unscored"] = bands.get(f.get("band") or "unscored", 0) + 1
    band_text = ", ".join(f"{n} {b}" for b, n in bands.items())
    sole = sum(1 for f in findings if f.get("sole_source"))
    flagged = sum(1 for f in findings if f.get("flagged"))
    out = (f"{len(findings)} supply path{'s' if len(findings) != 1 else ''} into {s['name']} carr{'y' if len(findings) != 1 else 'ies'} "
           f"significant risk ({band_text}). The most exposed is {worst['name']} at tier {worst['tier']}"
           # Never lower-cased: a leading factor is usually a sentence about a named company,
           # and "1 degree of separation from ningbo precision castings ltd" reads as a typo.
           + (f", whose leading factor is: {worst['top_factor']}" if worst.get("top_factor") else "")
           + ".")
    if sole:
        out += (f" {sole} of them {'is' if sole == 1 else 'are'} sole-source on the path shown, so nothing between "
                "the supplier and the program absorbs a disruption.")
    if flagged:
        out += f" {flagged} {'is' if flagged == 1 else 'are'} named on a designation, debarment or restricted-list screen."
    return out


def render_entity_profile(data: dict, narrative: dict | None = None, generated_at: str | None = None) -> str:
    rep = data["report"]
    ident, geo, ctrl, sup, ppl, rsk = rep["identity"], rep["geography"], rep["control"], rep["supply"], rep["people"], rep["risk"]
    ids = " · ".join(x for x in [
        f"UEI {esc(ident['uei'])}" if ident.get("uei") else "",
        f"CAGE {esc(ident['cage'])}" if ident.get("cage") else "",
        f"LEI {esc(ident['lei'])}" if ident.get("lei") else "",
    ] if x)
    parts = [
        '<p class="eyebrow">Illuminate · Vendor profile</p>',
        f"<h1>{esc(ident['name'])}</h1>",
        f'<p class="meta">{ids or "no registry identifiers resolved"} · '
        f'{"public" if ident.get("public") else "private"}'
        + (f" ({esc(ident['ticker'])})" if ident.get("ticker") else "")
        + (f" · {esc(ident['registration_status'])}" if ident.get("registration_status") else "")
        + f' · generated <b>{esc(generated_at or _now())}</b></p>',
        f'<p class="meta">Risk: {_band_chip(rsk.get("band"), rsk.get("composite"))}'
        + (f' <span class="src">{esc(rsk.get("top_factor"))}</span>' if rsk.get("top_factor") else "")
        + "</p>",
    ]
    if data.get("simulated"):
        parts.append('<div class="sim"><b>Simulated entity.</b> Clearly-labelled scenario material for analysis — '
                     'not an observation and not an allegation.</div>')
    parts.append("<h2>Summary</h2>")
    if narrative and narrative.get("summary"):
        parts.append(f"<p>{esc(narrative['summary'])}</p>")
    elif rep["summary"].get("text"):
        parts.append(f"<p>{esc(rep['summary']['text'])}</p>")
        parts.append(f'<p class="src">Written by {esc(rep["summary"].get("model") or "a model")} '
                     f'on {esc((rep["summary"].get("generated_at") or "")[:10])} from this profile\'s own facts.</p>')
    else:
        parts.append('<p class="empty">No model-written summary — the profile below stands on its own.</p>')

    parts.append("<h2>Identity and position</h2><table><tbody>")
    rows = [
        ("Kind", (ident.get("kind") or "organization").title()),
        ("Incorporated", (geo.get("incorporated") or {}).get("code")),
        ("Operates in", ", ".join(x["code"] for x in geo.get("operates") or [])),
        ("Manufactures in", ", ".join(x["code"] for x in geo.get("manufactures") or [])),
        ("Ultimate parent seat", (geo.get("parent_seat") or {}).get("code")),
        ("Direct owner", ", ".join(p["name"] + (" (%s%%)" % p["pct"] if p.get("pct") else "") for p in ctrl.get("direct_parents") or [])),
        ("Ultimate parent", ", ".join(p["name"] for p in ctrl.get("ultimate_parents") or [])),
        ("Categories", " › ".join(c["name"] for c in rep.get("categories") or [])),
        ("Suppliers on record", sup.get("suppliers_count")),
        ("Sole-source awards", sup.get("sole_source_edges")),
        ("Award records", (sup.get("awards") or {}).get("count")),
        ("Revenue", f"${int(ident['revenue']):,}" if ident.get("revenue") else None),
    ]
    parts += [f"<tr><th style=\"width:190px\">{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in rows if v not in (None, "", 0)]
    parts.append("</tbody></table>")

    parts.append("<h2>Supply relationships</h2>")
    if sup.get("supplies"):
        parts.append("<table><thead><tr><th>Supplies</th><th>Tier</th><th>PSC</th><th>Sole</th><th>Amount</th>"
                     "<th>Contract</th></tr></thead><tbody>" + "".join(
                         f"<tr><td>{esc(r.get('name'))}</td><td>{esc(r.get('tier'))}</td><td>{esc(r.get('psc') or '—')}</td>"
                         f"<td>{'yes' if r.get('sole_source') else '—'}</td>"
                         f"<td>{('$' + format(int(r['amount']), ',')) if r.get('amount') else '—'}</td>"
                         f"<td>{esc(r.get('contract_ref') or '—')}</td></tr>" for r in sup["supplies"][:30]) + "</tbody></table>")
    else:
        parts.append('<p class="empty">No award records place this entity in a supply chain.</p>')

    parts.append("<h2>Risk</h2>")
    scored = [i for i in rsk["indicators"] if i.get("scored") is not False]
    context = [i for i in rsk["indicators"] if i.get("scored") is False]
    parts.append("".join(
        f'<div class="driver">{_sev_chip(i.get("severity"))} <b>{esc(i.get("label"))}</b>'
        + (f'<div class="detail">{esc(i.get("detail"))}</div>' if i.get("detail") else "")
        + (f'<div class="src">{esc(i.get("source"))}</div>' if i.get("source") else "")
        + "</div>" for i in scored) or '<p class="empty">No dimension returned data.</p>')
    if context:
        parts.append('<div class="label">Context — leads, not findings; these do not move the score</div>')
        parts.append("".join(
            f'<div class="driver">{_sev_chip(i.get("severity"))} {esc(i.get("label"))}'
            + (f'<div class="detail">{esc(i.get("detail"))}</div>' if i.get("detail") else "")
            + "</div>" for i in context))
    if rsk.get("note"):
        parts.append(f'<div class="note">{esc(rsk["note"])}</div>')

    parts.append("<h2>People</h2>")
    if ppl["current"] or ppl["former"]:
        parts.append("<table><thead><tr><th>Name</th><th>Role</th><th>Tenure</th><th>Also at</th></tr></thead><tbody>"
                     + "".join(
                         f"<tr><td>{esc(p['name'])}</td><td>{esc(p.get('title') or '—')}</td>"
                         f"<td>{esc(p.get('from') or '?')} – {'now' if p.get('current') else esc(p.get('to') or '?')}</td>"
                         f"<td>{esc(', '.join(x['entity'] for x in (p.get('elsewhere') or [])[:4]) or '—')}</td></tr>"
                         for p in (ppl["current"] + ppl["former"])[:40]) + "</tbody></table>")
    else:
        parts.append('<p class="empty">No officers or directors resolved.</p>')

    if rep.get("artifacts"):
        parts.append("<h2>Evidence</h2><table><thead><tr><th>Kind</th><th>Title</th><th>Source</th><th>Date</th>"
                     "</tr></thead><tbody>" + "".join(
                         f"<tr><td>{esc(a.get('kind'))}</td><td>"
                         + (f'<a href="{esc(a["url"])}" target="_blank" rel="noopener noreferrer">{esc(a.get("title") or a["url"])}</a>' if a.get("url") else esc(a.get("title")))
                         + f"</td><td>{esc(a.get('source') or '—')}</td>"
                         f"<td>{esc((a.get('published_at') or a.get('retrieved_at') or '')[:10])}</td></tr>"
                         for a in rep["artifacts"][:40]) + "</tbody></table>")
    if data.get("sources"):
        parts.append("<h2>Sources</h2><p>" + esc(" · ".join(data["sources"])) + "</p>")
    parts.append(f'<p class="disclaimer">{esc(DISCLAIMER)}</p>')
    return _document(data["title"], "\n".join(parts))


# --- kinds ---------------------------------------------------------------------------------

KINDS: dict[str, dict] = {
    "risk_assessment": {
        "label": "Risk assessment",
        "description": "Supply-chain risk assessment for a program or any consuming organisation: every supply path "
                       "into it that carries significant risk, the goods and services on that path, where the risk "
                       "comes from, and recommended mitigations. The default report.",
        "assemble": assemble_risk_assessment,
        "render": render_risk_assessment,
        "default_subject": "program",
    },
    "entity_profile": {
        "label": "Vendor profile",
        "description": "One organisation's standardised profile: identity, supply position, geography, control, "
                       "people, risk indicators with citations and evidence.",
        "assemble": assemble_entity_profile,
        "render": render_entity_profile,
        "default_subject": "organization",
    },
}

DEFAULT_KIND = "risk_assessment"


def kinds() -> list[dict]:
    return [{"kind": k, "label": v["label"], "description": v["description"]} for k, v in KINDS.items()]


# --- persistence ----------------------------------------------------------------------------

REPORT_FIELDS = ("id", "kind", "title", "name", "subject_id", "subject_name", "subject_kind", "generated_at",
                 "generated_by", "model", "summary", "finding_count", "top_band", "cited_count", "simulated",
                 "source", "method")


async def generate(kind: str, subject_id: str, *, user: str = "local") -> dict:
    """Build a report and write it into the graph. Returns the stored row (without the html)."""
    spec = KINDS.get(kind)
    if not spec:
        raise ReportError(f"unknown report kind {kind!r}; known kinds: {', '.join(KINDS)}")
    data = await spec["assemble"](subject_id)
    narrative = await _narrative(user, data)
    generated_at = _now()
    doc = spec["render"](data, narrative, generated_at)
    summary = (narrative or {}).get("summary") or (
        _deterministic_summary(data) if kind == "risk_assessment" else (data["report"]["summary"].get("text") or ""))
    findings = data.get("findings") or []
    row = {
        "id": report_id(kind, subject_id),
        "kind": kind,
        "title": data["title"],
        "name": data["title"],
        "subject_id": data["subject"]["id"],
        "subject_name": data["subject"]["name"],
        "subject_kind": data["subject"].get("kind") or "organization",
        "generated_at": generated_at,
        "generated_by": (narrative or {}).get("model") or "derived",
        "model": (narrative or {}).get("model"),
        "summary": summary[:1200],
        "finding_count": len(findings),
        "top_band": (findings[0].get("band") if findings else None),
        "cited_count": len(data["cited_ids"]),
        "simulated": bool(data.get("simulated")),
        "source": "illuminate",
        "method": "generated",
        "html": doc,
        # The canvas trace wants relationship ids too, and CITES cannot carry those.
        "element_ids": json.dumps(data["element_ids"][:400]),
    }
    await _write(row, data["cited_ids"])
    await events.announce([row["id"], subject_id], reason="report", source="ui")
    return {k: row[k] for k in REPORT_FIELDS if k in row} | {"element_ids": data["element_ids"][:400]}


async def _write(row: dict, cited: list[str]) -> None:
    await db.write(
        """
        MATCH (subject:Entity {id:$subject_id})
        MERGE (r:Report {id:$id})
        SET r.kind=$kind, r.title=$title, r.name=$name, r.subject_id=$subject_id, r.subject_name=$subject_name,
            r.subject_kind=$subject_kind, r.generated_at=$generated_at, r.generated_by=$generated_by, r.model=$model,
            r.summary=$summary, r.finding_count=$finding_count, r.top_band=$top_band, r.cited_count=$cited_count,
            r.simulated=$simulated, r.html=$html, r.element_ids=$element_ids, r.source=$source, r.method=$method,
            r.retrieved_at=$generated_at
        MERGE (r)-[ro:REPORTS_ON]->(subject)
          ON CREATE SET ro.id=$reports_on_id, ro.source=$source, ro.method=$method, ro.retrieved_at=$generated_at
        RETURN r.id AS id
        """,
        {**row, "reports_on_id": edge_id()},
    )
    # Citations are rewritten wholesale: a regenerated report that kept the edges of the
    # findings it no longer makes would point the canvas at yesterday's evidence.
    await db.write("MATCH (:Report {id:$id})-[c:CITES]->() DELETE c", {"id": row["id"]})
    if cited:
        await db.write(
            """
            MATCH (r:Report {id:$id})
            MATCH (n) WHERE n.id IN $cited AND n.id <> $subject_id
            MERGE (r)-[c:CITES]->(n)
              ON CREATE SET c.id = 'rel_' + randomUUID(), c.source=$source, c.retrieved_at=$generated_at
            """,
            {"id": row["id"], "cited": cited, "subject_id": row["subject_id"], "source": row["source"],
             "generated_at": row["generated_at"]},
        )


async def _narrative(user: str, data: dict) -> dict | None:
    """The model's two paragraphs, or None. Never raises: a report is a graph projection
    first, and an unreachable model must cost it a summary, not the document."""
    try:
        from .llm.tasks import report_narrative
        return await report_narrative(user, data)
    except Exception:
        return None


LIST_QUERY = """
MATCH (r:Report)
OPTIONAL MATCH (r)-[:REPORTS_ON]->(s:Entity)
RETURN r.id AS id, r.kind AS kind, r.title AS title, r.subject_id AS subject_id,
       coalesce(s.name, r.subject_name) AS subject_name, r.subject_kind AS subject_kind,
       r.generated_at AS generated_at, r.generated_by AS generated_by, r.model AS model, r.summary AS summary,
       r.finding_count AS finding_count, r.top_band AS top_band, r.cited_count AS cited_count,
       coalesce(r.simulated,false) AS simulated
ORDER BY r.generated_at DESC
LIMIT $limit
"""


async def list_reports(limit: int = 100) -> list[dict]:
    return await db.read(LIST_QUERY, {"limit": int(limit)})


async def get_report(report_id_: str, *, with_html: bool = True) -> dict | None:
    rows = await db.read(
        """
        MATCH (r:Report {id:$id})
        OPTIONAL MATCH (r)-[:REPORTS_ON]->(s:Entity)
        OPTIONAL MATCH (r)-[:CITES]->(n)
        RETURN r{.*} AS r, coalesce(s.name, r.subject_name) AS subject_name,
               collect(DISTINCT {id:n.id, name:n.name, label:head(labels(n))}) AS cites
        LIMIT 1
        """,
        {"id": report_id_},
    )
    if not rows:
        return None
    r = dict(rows[0]["r"] or {})
    html_doc = r.pop("html", None)
    element_ids = r.pop("element_ids", None)
    out = {**r, "subject_name": rows[0]["subject_name"] or r.get("subject_name"),
           "cites": [c for c in rows[0]["cites"] if c.get("id")]}
    try:
        out["element_ids"] = json.loads(element_ids) if element_ids else []
    except (TypeError, ValueError):
        out["element_ids"] = []
    if with_html:
        out["html"] = html_doc
    return out


async def delete_report(report_id_: str) -> bool:
    rows = await db.read("MATCH (r:Report {id:$id}) RETURN r.subject_id AS subject_id LIMIT 1", {"id": report_id_})
    if not rows:
        return False
    await db.write("MATCH (r:Report {id:$id}) DETACH DELETE r", {"id": report_id_})
    await events.announce([rows[0]["subject_id"]], reason="report:deleted", source="ui")
    return True
