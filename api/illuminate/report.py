"""Entity report — the UC-11 projection. One vendor's standardised profile:
identity, supply position, geography, control, people, risk indicators with
citations, artifacts. Signals that returned no data are shown as no-data, never
imputed to zero."""
from __future__ import annotations

from datetime import date, datetime, timezone

from . import db

HOME = "US"

SEVERITY_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0, "clear": 0.0}

RISK_CONTRACT_VERSION = "uc11.vendor-risk.v1"
RISK_CATEGORIES = {
    "ownership": {"weight": 15, "predicates": ("ownership_screen",), "max_age_days": 365},
    "financial": {"weight": 15, "predicates": ("financial_screen",), "max_age_days": 180},
    "legal": {"weight": 10, "predicates": ("legal_screen",), "max_age_days": 365},
    "sanctions_regulatory": {"weight": 20, "predicates": ("sanctions_screen", "exclusion_screen", "regulatory_screen"), "max_age_days": 30},
    "cyber": {"weight": 15, "predicates": ("cyber_screen",), "max_age_days": 180},
    "adverse_media": {"weight": 10, "predicates": ("adverse_media_screen",), "max_age_days": 30},
    "supply_criticality": {"weight": 15, "predicates": ("supply_criticality_screen",), "max_age_days": 365},
}
RISK_BANDS = (
    {"id": "low", "min": 0, "max": 24},
    {"id": "moderate", "min": 25, "max": 49},
    {"id": "high", "min": 50, "max": 74},
    {"id": "critical", "min": 75, "max": 100},
)
RISK_DISPOSITIONS = {
    "low": "standard_monitoring",
    "moderate": "enhanced_diligence",
    "high": "escalate_for_review",
    "critical": "hold_and_escalate",
}


async def entity_core(entity_id: str) -> dict | None:
    rows = await db.read(
        """
        MATCH (e:Entity {id:$id})
        OPTIONAL MATCH (e)-[:INCORPORATED_IN]->(inc:Location)
        OPTIONAL MATCH (e)-[:PARENT_SEATED_IN]->(seat:Location)
        OPTIONAL MATCH (e)-[:MANUFACTURES_IN]->(mfg:Location)
        OPTIONAL MATCH (e)-[:OPERATES_IN]->(ops:Location)
        OPTIONAL MATCH (up:Entity)-[:ULTIMATE_PARENT_OF]->(e)
        OPTIONAL MATCH (dp:Entity)-[o:OWNS]->(e)
        OPTIONAL MATCH (e)-[:PROVIDES]->(c:Category)
        RETURN e{.*} AS e,
               inc{.code,.name} AS incorporated,
               seat{.code,.name,.simulated} AS parent_seat,
               collect(DISTINCT mfg{.code,.name}) AS manufactures,
               collect(DISTINCT ops{.code,.name}) AS operates,
               collect(DISTINCT up{.id,.name,.simulated}) AS ultimate_parents,
               collect(DISTINCT {id: dp.id, name: dp.name, pct: o.pct}) AS direct_parents,
               collect(DISTINCT c{.id,.name,.kind}) AS categories
        LIMIT 1
        """,
        {"id": entity_id},
    )
    if not rows:
        return None
    r = rows[0]
    r["direct_parents"] = [d for d in r["direct_parents"] if d.get("id")]
    r["ultimate_parents"] = [d for d in r["ultimate_parents"] if d and d.get("id")]
    r["manufactures"] = [d for d in r["manufactures"] if d and d.get("code")]
    r["operates"] = [d for d in r["operates"] if d and d.get("code")]
    r["categories"] = [d for d in r["categories"] if d and d.get("id")]
    ownership = await db.read(
        """
        MATCH (e:Entity {id:$id})
        OPTIONAL MATCH (e)-[ps:PARENT_SEATED_IN]->(seat:Location)
        OPTIONAL MATCH (pc:Claim {id:ps.claim_id})
        WITH e, ps, seat, pc ORDER BY seat.code, coalesce(ps.id, elementId(ps))
        RETURN collect({
          id:coalesce(ps.id, elementId(ps)), claim_id:ps.claim_id,
          source:ps.source, retrieved_at:ps.retrieved_at, confidence:ps.confidence,
          status:ps.status, simulated:coalesce(ps.simulated,false),
          seat_code:seat.code, seat_simulated:coalesce(seat.simulated,false),
          claim_status:pc.status, claim_simulated:coalesce(pc.simulated,false),
          artifact_simulated:CASE WHEN pc IS NULL THEN false ELSE EXISTS {
            MATCH (pa:Artifact)-[:EVIDENCES]->(pc) WHERE coalesce(pa.simulated,false)
          } END
        }) AS evidence
        """,
        {"id": entity_id},
    )
    r["parent_seat_evidence"] = [
        x for x in (ownership[0].get("evidence") if ownership else []) if x.get("id")
    ]
    return r


async def supply_position(entity_id: str, root_id: str | None) -> dict:
    out: dict = {"supplies": [], "suppliers_count": 0, "tier_from_root": None, "sole_source_edges": 0}
    rows = await db.read(
        """
        MATCH (e:Entity {id:$id})-[s:SUPPLIES]->(c:Entity)
         RETURN c.id AS id, c.name AS name, s.tier AS tier, s.sole_source AS sole_source, s.psc AS psc, s.naics AS naics,
                s.contract_ref AS contract_ref, s.amount AS amount, s.source AS source, s.source_url AS source_url,
                coalesce(s.id, elementId(s)) AS evidence_id, s.claim_id AS claim_id, s.status AS status,
                s.retrieved_at AS retrieved_at, s.confidence AS confidence,
                coalesce(s.simulated,false) OR coalesce(c.simulated,false) AS simulated
        ORDER BY coalesce(s.amount, 0) DESC LIMIT 50
        """,
        {"id": entity_id},
    )
    out["supplies"] = rows
    risk_rows = await db.read(
        """
        MATCH (e:Entity {id:$id})-[s:SUPPLIES]->(c:Entity)
        OPTIONAL MATCH (sc:Claim {id:s.claim_id})
        WITH e, s, c, sc ORDER BY coalesce(s.id, elementId(s))
        RETURN collect({
          sole_source:s.sole_source, contract_ref:s.contract_ref,
          source:s.source, source_url:s.source_url,
          evidence_id:coalesce(s.id, elementId(s)), claim_id:s.claim_id,
          status:s.status, retrieved_at:s.retrieved_at, confidence:s.confidence,
          simulated:coalesce(s.simulated,false),
          entity_simulated:coalesce(e.simulated,false) OR coalesce(c.simulated,false),
          claim_status:sc.status, claim_simulated:coalesce(sc.simulated,false),
          artifact_simulated:CASE WHEN sc IS NULL THEN false ELSE EXISTS {
            MATCH (sa:Artifact)-[:EVIDENCES]->(sc) WHERE coalesce(sa.simulated,false)
          } END
        }) AS evidence
        """,
        {"id": entity_id},
    )
    out["risk_evidence"] = risk_rows[0].get("evidence", []) if risk_rows else []
    out["sole_source_edges"] = sum(1 for r in rows if r.get("sole_source"))
    cnt = await db.read("MATCH (:Entity)-[:SUPPLIES]->(e:Entity {id:$id}) RETURN count(*) AS n", {"id": entity_id})
    out["suppliers_count"] = cnt[0]["n"] if cnt else 0
    if root_id and root_id != entity_id:
        t = await db.read(
            "MATCH p=shortestPath((e:Entity {id:$id})-[:SUPPLIES*1..6]->(r:Entity {id:$root})) RETURN length(p) AS tier LIMIT 1",
            {"id": entity_id, "root": root_id},
        )
        out["tier_from_root"] = t[0]["tier"] if t else None
    awards = await db.read(
        "MATCH (a:Artifact {kind:'award'})-[:ABOUT]->(e:Entity {id:$id}) RETURN count(a) AS n, sum(a.amount) AS total",
        {"id": entity_id},
    )
    out["awards"] = {"count": awards[0]["n"], "total": awards[0]["total"]} if awards else {"count": 0, "total": None}
    return out


async def people(entity_id: str) -> dict:
    rows = await db.read(
        """
        MATCH (p:Person)-[r:HELD_ROLE]->(e:Entity {id:$id})
        OPTIONAL MATCH (p)-[r2:HELD_ROLE]->(o:Entity) WHERE o.id <> e.id AND (o.lei IS NULL OR e.lei IS NULL OR o.lei <> e.lei)
        WITH p, r, collect(DISTINCT {entity_id:o.id, entity:o.name, title:r2.title, current:r2.current, flagged: coalesce(o.flagged,false)}) AS elsewhere
        RETURN p.id AS person_id, p.name AS name, r.id AS edge_id, r.title AS title, r.role_type AS role_type, r.from AS from, r.to AS to,
               coalesce(r.current, r.to IS NULL) AS current, r.source AS source, r.source_url AS source_url, elsewhere
        ORDER BY current DESC, r.from DESC
        LIMIT 200
        """,
        {"id": entity_id},
    )
    current = [r for r in rows if r["current"]]
    former = [r for r in rows if not r["current"]]
    for r in rows:
        r["elsewhere"] = [x for x in r["elsewhere"] if x.get("entity_id")]
        r["interlock"] = any(x["current"] for x in r["elsewhere"]) and r["current"]
        r["moved_to_flagged"] = any(x["flagged"] and x["current"] for x in r["elsewhere"]) and not r["current"]
        r["formerly_elsewhere"] = bool(r["current"]) and any(not x["current"] for x in r["elsewhere"])
    seats = await db.read("MATCH (e:Entity {id:$id}) RETURN e.board_size AS n", {"id": entity_id})
    return {"current": current, "former": former, "board_size": seats[0]["n"] if seats else None, "resolved_current_count": len(current)}


async def screens(entity_id: str) -> list[dict]:
    """Sanctions / exclusion / registry screens are Claims with predicate *_screen."""
    rows = await db.read(
        """
        MATCH (c:Claim)-[:ASSERTS]->(e:Entity {id:$id})
        WHERE c.predicate ENDS WITH '_screen'
        OPTIONAL MATCH (a:Artifact)-[:EVIDENCES]->(c)
        WITH c, collect(DISTINCT a{.id,.title,.url,.source,.retrieved_at,.simulated}) AS artifacts
        ORDER BY c.retrieved_at DESC, c.id
        RETURN collect({
          claim_id:c.id, predicate:c.predicate, result:c.object_value, source:c.source,
          confidence:c.confidence, status:c.status, simulated:coalesce(c.simulated,false),
          retrieved_at:c.retrieved_at, artifacts:artifacts, detail:c.detail
        }) AS screens
        """,
        {"id": entity_id},
    )
    items = rows[0].get("screens", []) if rows else []
    for item in items:
        item["artifacts"] = sorted(
            [a for a in item.get("artifacts", []) if a and a.get("id")],
            key=lambda a: a["id"],
        )
        item["artifact"] = item["artifacts"][0] if item["artifacts"] else None
        item["artifact_simulated"] = any(a.get("simulated") for a in item["artifacts"])
    return items


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def _severity(value: str | None) -> str | None:
    value = (value or "").lower()
    if value in SEVERITY_WEIGHT:
        return value
    if value in {"hit", "positive", "fail"}:
        return "high"
    if value in {"clear", "no_hit", "negative", "pass"}:
        return "clear"
    return None


def _confidence(value: object, default: float = 1.0) -> float:
    try:
        return max(0.0, min(1.0, float(default if value is None else value)))
    except (TypeError, ValueError):
        return 0.0


def _eligible_graph_fact(fact: dict, *nodes: dict) -> bool:
    if fact.get("simulated") or fact.get("entity_simulated") or any(n.get("simulated") for n in nodes):
        return False
    if fact.get("claim_simulated") or fact.get("artifact_simulated"):
        return False
    if fact.get("claim_id"):
        if fact.get("claim_status") != "committed":
            return False
    elif (
        fact.get("status") not in (None, "committed")
        or not fact.get("source")
        or not fact.get("retrieved_at")
        or fact.get("confidence") is None
    ):
        return False
    return True


def _screen_simulated(item: dict) -> bool:
    return bool(
        item.get("simulated")
        or item.get("artifact_simulated")
        or (item.get("artifact") or {}).get("simulated")
        or any(a.get("simulated") for a in item.get("artifacts", []) if a)
    )


def evaluate_risk_contract(
    core: dict, supply: dict, screens_data: list[dict], *, as_of: date | None = None
) -> dict:
    """Pure, deterministic UC-11 evaluation. Missing evidence never reduces risk."""
    as_of = as_of or datetime.now(timezone.utc).date()
    outputs: list[dict] = []
    diligence: list[dict] = []
    total = 0.0
    confidence_numerator = 0.0
    covered_weight = 0
    complete = 0

    for category, spec in RISK_CATEGORIES.items():
        candidates = [s for s in screens_data if s.get("predicate") in spec["predicates"]]
        approved = [
            s for s in candidates
            if s.get("status") == "committed"
            and not _screen_simulated(s)
            and not core.get("e", {}).get("simulated")
            and _severity(s.get("result")) is not None
        ]
        approved.sort(key=lambda s: str(s.get("retrieved_at") or ""), reverse=True)
        factors: list[dict] = []

        # Ownership and supply criticality can also be established by approved graph facts.
        if category == "ownership":
            for evidence in core.get("parent_seat_evidence", []):
                seat = evidence.get("seat_code")
                seat_node = {"simulated": evidence.get("seat_simulated")}
                if not seat or not _eligible_graph_fact(evidence, core.get("e", {}), seat_node):
                    continue
                severity = "high" if not seat.upper().startswith(HOME) else "clear"
                refs = [x for x in (evidence.get("claim_id"), evidence.get("id")) if x]
                factors.append({"rule_id": "ownership.foreign-parent.v1", "severity": severity,
                                "evidence_refs": refs, "truth_status": "committed",
                                "provenance": {
                                    "source": evidence.get("source") or "graph",
                                    "retrieved_at": evidence.get("retrieved_at"),
                                    "confidence": _confidence(evidence.get("confidence"), default=0.0),
                                },
                                "explanation": f"Ultimate parent jurisdiction is {seat}."})
        elif category == "supply_criticality" and supply.get("risk_evidence"):
            eligible_supply = [
                s for s in supply["risk_evidence"]
                if s.get("evidence_id")
                and isinstance(s.get("sole_source"), bool)
                and _eligible_graph_fact(s, core.get("e", {}))
            ]
            for ref in eligible_supply:
                severity = "medium" if ref["sole_source"] else "clear"
                refs = [str(x) for x in (ref.get("claim_id"), ref.get("evidence_id")) if x]
                factors.append({"rule_id": "supply.sole-source.v1", "severity": severity,
                                "evidence_refs": refs, "truth_status": "committed",
                                "provenance": {"source": ref.get("source") or "graph",
                                               "retrieved_at": ref.get("retrieved_at"),
                                               "confidence": _confidence(ref.get("confidence"), default=0.0)},
                                "explanation": "A sole-source supply relationship exists." if ref["sole_source"] else "The supply relationship is explicitly recorded as non-sole-source."})

        for item in approved:
            severity = _severity(item.get("result"))
            refs = [item.get("claim_id")] + [
                a["id"] for a in item.get("artifacts", []) if a.get("id")
            ]
            refs = [x for x in refs if x]
            factors.append({
                "rule_id": f"{category}.screen-result.v1",
                "severity": severity,
                "evidence_refs": refs or [f"claim:{item.get('predicate')}"],
                "truth_status": "committed",
                "provenance": {"source": item.get("source"), "retrieved_at": item.get("retrieved_at"),
                               "confidence": _confidence(item.get("confidence"), default=0.0)},
                "explanation": item.get("detail") or f"{item.get('predicate')} returned {item.get('result')}.",
            })

        has_evidence = bool(factors)
        if has_evidence:
            complete += 1
            severity = max((f["severity"] for f in factors), key=lambda x: SEVERITY_WEIGHT[x])
            contribution = spec["weight"] * SEVERITY_WEIGHT[severity] / 3.0
            covered_weight += spec["weight"]
            supporting = [f for f in factors if f["severity"] == severity]
            confidences = [_confidence((f.get("provenance") or {}).get("confidence"), default=0.0) for f in supporting]
            category_confidence = min(confidences)
            confidence_numerator += spec["weight"] * min(confidences)
            raw_dates = [(f.get("provenance") or {}).get("retrieved_at") for f in supporting]
            dates = [_parse_date(value) for value in raw_dates]
            ages = [(as_of - d).days for d in dates if d]
            freshness = (
                "unknown" if not ages or len(ages) != len(raw_dates)
                else ("stale" if max(ages) > spec["max_age_days"] else "current")
            )
            if freshness in {"stale", "unknown"}:
                diligence.append({"category": category, "code": f"{freshness}_evidence",
                                  "message": f"{category} evidence freshness is {freshness}."})
        else:
            severity, contribution, freshness, category_confidence = None, 0.0, "missing", 0.0
            excluded = sorted({str(s.get("status") or "unknown") for s in candidates if s not in approved})
            diligence.append({"category": category, "code": "missing_approved_evidence",
                              "excluded_truth_statuses": excluded,
                              "excluded_evidence": [{
                                  "evidence_ref": s.get("claim_id") or f"claim:{s.get('predicate')}",
                                  "truth_status": s.get("status") or "unknown",
                                  "simulated": bool(_screen_simulated(s) or core.get("e", {}).get("simulated")),
                              } for s in candidates if s not in approved],
                              "message": f"No approved, non-simulated evidence covers {category}."})
        total += contribution
        outputs.append({"id": category, "weight": spec["weight"], "severity": severity,
                        "contribution": round(contribution, 2), "confidence": round(category_confidence, 3),
                        "freshness": freshness, "factors": factors})

    score = round(100 * total / covered_weight) if covered_weight else None
    band = (
        next(b["id"] for b in RISK_BANDS if b["min"] <= score <= b["max"])
        if score is not None else "not_assessed"
    )
    completeness = round(complete / len(RISK_CATEGORIES), 3)
    disposition = (
        "complete_diligence" if score is None or (completeness < 1 and band in {"low", "moderate"})
        else RISK_DISPOSITIONS[band]
    )
    return {
        "contract_version": RISK_CONTRACT_VERSION,
        "score": score,
        "band": band,
        "disposition": disposition,
        "confidence": round(confidence_numerator / covered_weight, 3) if covered_weight else 0.0,
        "completeness": completeness,
        "freshness": "diligence_required" if diligence else "current",
        "categories": outputs,
        "diligence_flags": diligence,
        "policy": {
            "weights": {k: v["weight"] for k, v in RISK_CATEGORIES.items()},
            "category_contracts": RISK_CATEGORIES,
            "bands": list(RISK_BANDS),
            "severity_points": SEVERITY_WEIGHT,
            "input_contract": {
                "screen_evidence": {
                    "required_fields": ["claim_id", "predicate", "result", "status", "simulated"],
                    "provenance_fields": ["source", "confidence", "retrieved_at", "detail"],
                    "artifact_fields": ["id", "source", "retrieved_at", "simulated"],
                    "artifact_container": "artifacts (plural); legacy artifact is also validated",
                },
                "ownership_graph_evidence": {
                    "container": "parent_seat_evidence",
                    "fields": ["id", "claim_id", "claim_status", "claim_simulated",
                               "artifact_simulated", "seat_code", "seat_simulated",
                               "source", "retrieved_at", "confidence", "status", "simulated"],
                },
                "supply_graph_evidence": {
                    "container": "risk_evidence",
                    "fields": ["evidence_id", "claim_id", "claim_status", "claim_simulated",
                               "artifact_simulated", "sole_source", "entity_simulated",
                               "source", "retrieved_at", "confidence", "status", "simulated"],
                },
            },
            "eligible_truth_status": "committed",
            "simulated_evidence_scores": False,
            "missing_evidence_behavior": "zero contribution; reduce completeness; create diligence flag",
            "aggregate_behavior": "normalize observed contributions over covered category weights; no score when no categories are covered",
        },
    }


async def artifacts(entity_id: str, limit: int = 50) -> list[dict]:
    return await db.read(
        """
        MATCH (e:Entity {id:$id})
        OPTIONAL MATCH (a1:Artifact)-[:ABOUT]->(e)
        OPTIONAL MATCH (a2:Artifact)-[:EVIDENCES]->(c:Claim)-[:ASSERTS]->(e)
        WITH collect(DISTINCT a1) + collect(DISTINCT a2) AS arts
        UNWIND arts AS a
        WITH DISTINCT a WHERE a IS NOT NULL
        RETURN a.id AS id, a.kind AS kind, a.title AS title, a.url AS url, a.source AS source, a.retrieved_at AS retrieved_at,
               a.published_at AS published_at, a.sentiment AS sentiment, a.amount AS amount, a.summary AS summary
        ORDER BY coalesce(a.published_at, a.retrieved_at) DESC LIMIT $limit
        """,
        {"id": entity_id, "limit": limit},
    )


async def news(entity_id: str, limit: int = 10) -> list[dict]:
    return await db.read(
        """
        MATCH (a:Artifact {kind:'news'})-[:ABOUT]->(e:Entity {id:$id})
        RETURN a.id AS id, a.title AS title, a.url AS url, a.source AS source, a.published_at AS published_at, a.sentiment AS sentiment, a.domain AS domain
        ORDER BY a.published_at DESC LIMIT $limit
        """,
        {"id": entity_id, "limit": limit},
    )


def _ind(family: str, label: str, severity: str | None, source: str | None, detail: str | None = None, url: str | None = None, ids: list[str] | None = None) -> dict:
    return {"family": family, "label": label, "severity": severity, "source": source, "detail": detail, "source_url": url, "element_ids": ids or [], "no_data": severity is None}


async def risk_indicators(entity_id: str, core: dict, supply: dict, ppl: dict, scr: list[dict]) -> dict:
    inds: list[dict] = []
    e = core["e"]
    # 1. Ownership / foreign control
    seat = (core.get("parent_seat") or {}).get("code")
    ups = core.get("ultimate_parents") or []
    if seat:
        foreign = not seat.upper().startswith(HOME)
        detail = f"Ultimate parent seated in {seat}" + (f" — {ups[0]['name']}" if ups else "")
        inds.append(_ind("ownership", "Foreign ultimate parent" if foreign else "Domestic ultimate parent", "high" if foreign else "clear",
                         e.get("ownership_source") or "GLEIF", detail, ids=[u["id"] for u in ups]))
    elif ups:
        inds.append(_ind("ownership", "Ultimate parent known, jurisdiction unresolved", "low", "GLEIF", ups[0]["name"], ids=[ups[0]["id"]]))
    else:
        inds.append(_ind("ownership", "Ownership chain", None, None, "No parent records resolved"))
    # 2. Concentration / sole source
    if supply["supplies"]:
        ss = [s for s in supply["supplies"] if s.get("sole_source")]
        if ss:
            s0 = ss[0]
            inds.append(_ind("concentration", f"Sole source at tier {s0.get('tier') or '?'}" + (f" for PSC {s0['psc']}" if s0.get("psc") else ""),
                             "medium", s0.get("source") or "USAspending", s0.get("contract_ref"), s0.get("source_url")))
        else:
            inds.append(_ind("concentration", "No sole-source awards on record", "clear", "USAspending"))
    else:
        inds.append(_ind("concentration", "Supply position", None, None, "No award records for this entity"))
    # 3. People
    interlocks = [p for p in ppl["current"] if p.get("interlock")]
    moved = [p for p in ppl["former"] if p.get("moved_to_flagged")]
    flagged_in = [p for p in ppl["current"] if any(x["flagged"] and not x["current"] for x in p["elsewhere"])]
    if moved or flagged_in:
        who = (moved or flagged_in)[0]
        other = next((x for x in who["elsewhere"] if x["flagged"]), None)
        inds.append(_ind("people", f"{'Former' if moved else 'Current'} {who['title'] or 'officer'} linked to flagged entity" + (f" ({other['entity']})" if other else ""),
                         "medium", who.get("source") or "LittleSis", who["name"], who.get("source_url"), ids=[who["person_id"]]))
    elif any(p.get("formerly_elsewhere") for p in ppl["current"]):
        p0 = next(p for p in ppl["current"] if p.get("formerly_elsewhere"))
        other = next((x for x in p0["elsewhere"] if not x["current"]), None)
        inds.append(_ind("people", f"Former {other['title'] or 'officer'} of {other['entity']} on current board" if other else "Former officer of another supplier on current board",
                         "medium", p0.get("source") or "LittleSis", f"{p0['name']} — {p0['title'] or 'role'} since {p0.get('from') or '?'}", p0.get("source_url"), ids=[p0["person_id"]]))
    elif interlocks:
        p0 = interlocks[0]
        other = next((x for x in p0["elsewhere"] if x["current"]), None)
        inds.append(_ind("people", f"Board interlock — {p0['name']} also at {other['entity'] if other else 'another supplier'}", "low", p0.get("source") or "LittleSis",
                         "An interlock is a lead, not a finding", p0.get("source_url"), ids=[p0["person_id"]]))
    elif ppl["current"] or ppl["former"]:
        inds.append(_ind("people", "No interlocks or flagged movements among resolved people", "clear", "LittleSis · EDGAR"))
    else:
        inds.append(_ind("people", "People", None, None, "No officers or directors resolved"))
    # 4. Sanctions & debarment
    eligible_scr = [
        s for s in scr
        if s.get("status") == "committed" and not _screen_simulated(s) and not e.get("simulated")
    ]
    sanc = next((s for s in eligible_scr if s["predicate"] == "sanctions_screen"), None)
    excl = next((s for s in eligible_scr if s["predicate"] == "exclusion_screen"), None)
    if sanc or excl:
        hit = (sanc and sanc["result"] == "hit") or (excl and excl["result"] == "hit")
        src = " · ".join(x["source"] for x in (sanc, excl) if x)
        det = "; ".join(filter(None, [(sanc or {}).get("detail"), (excl or {}).get("detail")]))
        inds.append(_ind("sanctions", "Sanctions and debarment screen" + (" — HIT" if hit else ""), "high" if hit else "clear", src, det or None))
    else:
        inds.append(_ind("sanctions", "Sanctions and debarment screen", None, None, "Not yet screened"))
    # 5. Financial health — only meaningful for listed entities with filings
    fin = next((s for s in eligible_scr if s["predicate"] == "financial_screen"), None)
    if fin:
        inds.append(_ind("financial", "Financial health", fin["result"] if fin["result"] in SEVERITY_WEIGHT else "low", fin["source"], fin.get("detail")))
    elif e.get("public") and e.get("ticker"):
        inds.append(_ind("financial", "Financial health — listed, filings available", "clear", "EDGAR", f"Ticker {e['ticker']}"))
    else:
        inds.append(_ind("financial", "Financial health — private entity, no filings", None, None))
    # 6. Adverse media
    adv = next((s for s in eligible_scr if s["predicate"] == "adverse_media_screen"), None)
    if adv:
        inds.append(_ind("media", "Adverse media", adv["result"] if adv["result"] in SEVERITY_WEIGHT else "low", adv["source"], adv.get("detail")))
    else:
        inds.append(_ind("media", "Adverse media — below coverage threshold", None, None))

    scored = [i for i in inds if not i["no_data"]]
    total = sum(SEVERITY_WEIGHT[i["severity"]] for i in scored)
    maxv = 3.0 * len(scored) if scored else 0
    composite = round(100 * total / maxv) if maxv else None
    return {
        "indicators": inds,
        "composite": composite,
        "families_requested": len(inds),
        "families_with_data": len(scored),
        "note": (
            f"Composite is computed on available indicators only. {len(inds) - len(scored)} of {len(inds)} requested signal families returned no data; the score reflects {len(scored)}."
            if scored else "No signal families returned data; no composite is computed."
        ),
        "disclaimer": "Every indicator marks opacity, concentration or foreign control — conditions warranting human review. This tool flags; it does not accuse.",
    }


async def build_report(entity_id: str, root_id: str | None = None) -> dict | None:
    core = await entity_core(entity_id)
    if not core:
        return None
    supply = await supply_position(entity_id, root_id)
    ppl = await people(entity_id)
    scr = await screens(entity_id)
    arts = await artifacts(entity_id)
    nws = await news(entity_id)
    risk = await risk_indicators(entity_id, core, supply, ppl, scr)
    risk.update(evaluate_risk_contract(core, supply, scr))
    e = core["e"]
    sources = sorted({s for s in [e.get("source")] + [a.get("source") for a in arts] + [p.get("source") for p in ppl["current"] + ppl["former"]] if s})
    return {
        "entity": e,
        "identity": {
            "id": e.get("id"), "name": e.get("name"), "uei": e.get("uei"), "cage": e.get("cage"), "lei": e.get("lei"),
            "aliases": e.get("aliases") or [], "kind": e.get("kind"), "registration_status": e.get("registration_status"),
            "public": e.get("public"), "ticker": e.get("ticker"), "simulated": bool(e.get("simulated")),
        },
        "geography": {
            "incorporated": core.get("incorporated"), "parent_seat": core.get("parent_seat"),
            "manufactures": core.get("manufactures"), "operates": core.get("operates"),
        },
        "control": {"direct_parents": core.get("direct_parents"), "ultimate_parents": core.get("ultimate_parents")},
        "categories": core.get("categories"),
        "supply": supply,
        "people": ppl,
        "screens": [] if e.get("simulated") else [
            s for s in scr if s.get("status") == "committed" and not _screen_simulated(s)
        ],
        "screen_evidence": scr,
        "risk": risk,
        "artifacts": arts,
        "news": nws,
        "summary": {"text": e.get("summary"), "generated_at": e.get("summary_at"), "model": e.get("summary_model"), "source_count": len(arts)},
        "sources": sources,
        "generated_at": date.today().isoformat(),
    }
