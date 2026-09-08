"""Entity report — the UC-11 projection. One vendor's standardised profile:
identity, supply position, geography, control, people, risk indicators with
citations, artifacts. Signals that returned no data are shown as no-data, never
imputed to zero."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

from . import db

HOME = "US"

SEVERITY_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0, "clear": 0.0}
IMMUTABLE_AI_FIELDS = (
    "score", "band", "disposition", "confidence", "completeness", "freshness",
    "categories", "truth_status", "simulated",
)

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


"""How far up a control chain the ultimate-parent walk will go before giving up."""
ULTIMATE_PARENT_DEPTH = 6


async def ultimate_parents(entity_id: str) -> list[dict]:
    """Who ultimately controls this entity, derived rather than asserted.

    Nothing in the graph declares an ultimate parent — an :ULTIMATE_PARENT_OF edge only ever
    arrives when a registry (GLEIF) states one outright. The answer is the root of the control
    chain, so it is found by walking OWNS upstream to an owner nobody owns. That is what makes
    an ownership risk *discoverable*: the chain is the evidence, and a party that only appears
    two or three hops up is exactly the one a single-hop lookup would miss.

    Simulation status propagates down the chain: a derived parent is simulated if any hop or
    node along the path to it is. The path itself is returned as provenance, and every element
    id on it goes into `relationship_ids` so a report can highlight the whole chain.
    """
    rows = await db.read(
        f"""
        MATCH path=(up:Entity)-[:OWNS|ULTIMATE_PARENT_OF*1..{ULTIMATE_PARENT_DEPTH}]->(e:Entity {{id:$id}})
        WHERE up.id <> $id AND NOT EXISTS {{ (:Entity)-[:OWNS|ULTIMATE_PARENT_OF]->(up) }}
        WITH up, path, relationships(path) AS hops, nodes(path) AS chain
        // Shortest first: the nearest root wins when a node is reachable by several routes.
        ORDER BY length(path), up.name
        WITH up, head(collect({{hops: hops, chain: chain}})) AS best
        RETURN up.id AS id, up.name AS name,
               coalesce(up.simulated, false) AS simulated,
               size(best.hops) AS hops,
               [h IN best.hops | coalesce(h.id, elementId(h))] AS relationship_ids,
               [n IN best.chain | n.name] AS chain,
               coalesce(head(best.hops).id, elementId(head(best.hops))) AS relationship_id,
               any(h IN best.hops WHERE coalesce(h.simulated, false))
                 OR any(n IN best.chain WHERE coalesce(n.simulated, false)) AS relationship_simulated,
               head([h IN best.hops WHERE h.claim_id IS NOT NULL | h.claim_id]) AS claim_id,
               head([h IN best.hops WHERE h.source IS NOT NULL | h.source]) AS source,
               head([h IN best.hops WHERE h.source_url IS NOT NULL | h.source_url]) AS source_url
        ORDER BY hops, name
        """,
        {"id": entity_id},
    )
    for row in rows:
        # A single stated hop is the registry's claim; anything longer is our inference, and the
        # report should say so rather than borrow the top link's source as if it named the parent.
        if row["hops"] > 1:
            row["source"] = f"derived: ownership chain via {' → '.join(row['chain'][1:-1])}" if len(row["chain"]) > 2 else "derived: ownership chain"
    return [r for r in rows if r.get("id")]


async def entity_core(entity_id: str) -> dict | None:
    rows = await db.read(
        """
        MATCH (e:Entity {id:$id})
        OPTIONAL MATCH (e)-[:INCORPORATED_IN]->(inc:Location)
        OPTIONAL MATCH (e)-[ps:PARENT_SEATED_IN]->(seat:Location)
        OPTIONAL MATCH (e)-[:MANUFACTURES_IN]->(mfg:Location)
        OPTIONAL MATCH (e)-[:OPERATES_IN]->(ops:Location)
        OPTIONAL MATCH (dp:Entity)-[o:OWNS]->(e)
        OPTIONAL MATCH (e)-[:PROVIDES]->(c:Category)
        RETURN e{.*} AS e,
               inc{.code,.name} AS incorporated,
               seat{.id,.code,.name, simulated:coalesce(seat.simulated,false),
                   relationship_id:coalesce(ps.id, elementId(ps)),
                   relationship_simulated:coalesce(ps.simulated,false),
                   source:ps.source, source_url:ps.source_url} AS parent_seat,
               collect(DISTINCT mfg{.code,.name}) AS manufactures,
               collect(DISTINCT ops{.code,.name}) AS operates,
               collect(DISTINCT {id: dp.id, name: dp.name, pct: o.pct,
                   simulated:coalesce(dp.simulated,false),
                   relationship_id:coalesce(o.id, elementId(o)),
                   relationship_simulated:coalesce(o.simulated,false),
                   source:o.source, source_url:o.source_url}) AS direct_parents,
               collect(DISTINCT c{.id,.name,.kind}) AS categories
        LIMIT 1
        """,
        {"id": entity_id},
    )
    if not rows:
        return None
    r = rows[0]
    r["direct_parents"] = [d for d in r["direct_parents"] if d.get("id")]
    r["ultimate_parents"] = await ultimate_parents(entity_id)
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
          source:ps.source, source_url:ps.source_url,
          retrieved_at:coalesce(ps.latest_retrieved_at,ps.retrieved_at),
          first_retrieved_at:ps.retrieved_at, latest_retrieved_at:ps.latest_retrieved_at,
          confidence:ps.confidence,
          status:ps.status, simulated:coalesce(ps.simulated,false),
          seat_code:seat.code, seat_simulated:coalesce(seat.simulated,false),
          claim_status:pc.status, claim_method:pc.method, claim_simulated:coalesce(pc.simulated,false),
          artifact_simulated:CASE WHEN pc IS NULL THEN false ELSE EXISTS {
            MATCH (pa:Artifact)-[:EVIDENCES]->(pc) WHERE coalesce(pa.simulated,false)
          } END,
          evidence_simulated:CASE WHEN pc IS NULL THEN false ELSE EXISTS {
            MATCH (:Artifact)-[pe:EVIDENCES]->(pc) WHERE coalesce(pe.simulated,false)
          } END
        }) AS evidence
        """,
        {"id": entity_id},
    )
    r["parent_seat_evidence"] = [
        x for x in (ownership[0].get("evidence") if ownership else []) if x.get("id")
    ]
    r["ownership"] = await ownership_records(entity_id)
    return r


OWNERSHIP_TYPES = {
    "OWNS": "direct",
    "ULTIMATE_PARENT_OF": "ultimate_parent",
    "BENEFICIAL_OWNER_OF": "beneficial_owner",
}


def _ownership_freshness(retrieved_at: str | None) -> str:
    if not retrieved_at:
        return "unavailable"
    try:
        observed = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return "unavailable"
    return "stale" if (datetime.now(timezone.utc) - observed).days > 365 else "current"
async def supply_position(entity_id: str, root_id: str | None) -> dict:
    out: dict = {"supplies": [], "suppliers_count": 0, "tier_from_root": None, "sole_source_edges": 0}
    rows = await db.read(
        """
        MATCH (e:Entity {id:$id})-[s:SUPPLIES]->(c:Entity)
         RETURN c.id AS id, c.name AS name, coalesce(s.id, elementId(s)) AS edge_id,
                 s.tier AS tier, s.sole_source AS sole_source, s.psc AS psc, s.naics AS naics,
                s.contract_ref AS contract_ref, s.amount AS amount, s.source AS source,
                s.source_id AS source_id, s.source_identifier AS source_identifier,
                s.catalog_ids AS catalog_ids, s.source_url AS source_url,
                s.usage_note AS usage_note, s.quality_note AS quality_note,
                s.supports AS supports, s.unknowns AS unknowns,
                s.source_status AS source_status, s.connector_error AS connector_error,
                s.connector_error_type AS connector_error_type,
                s.connector_error_status AS connector_error_status,
                coalesce(s.id, elementId(s)) AS evidence_id, s.claim_id AS claim_id, s.status AS status,
                 coalesce(s.latest_retrieved_at,s.retrieved_at) AS retrieved_at,
                 s.retrieved_at AS first_retrieved_at,
                 s.latest_retrieved_at AS latest_retrieved_at, s.confidence AS confidence,
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
          supplier_id:e.id, consumer_id:c.id,
          source:sc.source, source_id:s.source_id, source_identifier:s.source_identifier,
          catalog_ids:s.catalog_ids, source_url:s.source_url,
          usage_note:s.usage_note, quality_note:s.quality_note,
          supports:s.supports, unknowns:s.unknowns, source_status:s.source_status,
          connector_error:s.connector_error, connector_error_type:s.connector_error_type,
          connector_error_status:s.connector_error_status,
          evidence_id:coalesce(s.id, elementId(s)), claim_id:s.claim_id,
          status:s.status, relationship_retrieved_at:coalesce(s.latest_retrieved_at,s.retrieved_at),
          retrieved_at:coalesce(sc.latest_retrieved_at,sc.retrieved_at),
          first_retrieved_at:sc.retrieved_at, latest_retrieved_at:sc.latest_retrieved_at,
          confidence:sc.confidence, method:sc.method,
          simulated:coalesce(s.simulated,false),
          entity_simulated:coalesce(e.simulated,false) OR coalesce(c.simulated,false),
          claim_status:sc.status, claim_simulated:coalesce(sc.simulated,false),
          claim_predicate:sc.predicate, claim_object_value:sc.object_value,
          claim_source_url:sc.source_url,
          claim_subject_id:head([(sc)-[:ASSERTS]->(claim_subject) | claim_subject.id]),
          claim_target_id:head([(sc)-[:TARGETS]->(claim_target) | claim_target.id]),
          claim_conflicting:CASE WHEN sc IS NULL THEN false ELSE EXISTS {
            MATCH (other:Claim {predicate:'supply_sole_source'})-[:ASSERTS]->(e)
            MATCH (other)-[:TARGETS]->(c)
            WHERE other.id <> sc.id AND other.status='committed'
              AND coalesce(other.simulated,false)=false
              AND other.object_value <> sc.object_value
          } END,
          artifacts:CASE WHEN sc IS NULL THEN [] ELSE
            [(sa:Artifact)-[se:EVIDENCES]->(sc) | {
              id:sa.id, kind:sa.kind, title:sa.title, url:sa.url, award_id:sa.award_id,
              source:sa.source,
              retrieved_at:coalesce(sa.latest_retrieved_at,sa.retrieved_at),
              first_retrieved_at:sa.retrieved_at, latest_retrieved_at:sa.latest_retrieved_at,
              evidence_retrieved_at:coalesce(se.latest_retrieved_at,se.retrieved_at),
              method:se.method, confidence:se.confidence,
              simulated:coalesce(sa.simulated,false),
              evidence_simulated:coalesce(se.simulated,false)
            }] END,
          artifact_simulated:CASE WHEN sc IS NULL THEN false ELSE EXISTS {
            MATCH (sa:Artifact)-[:EVIDENCES]->(sc) WHERE coalesce(sa.simulated,false)
          } END,
          evidence_simulated:CASE WHEN sc IS NULL THEN false ELSE EXISTS {
            MATCH (:Artifact)-[se:EVIDENCES]->(sc) WHERE coalesce(se.simulated,false)
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
        OPTIONAL MATCH (rc:Claim {id:r.claim_id})
        OPTIONAL MATCH (p)-[r2:HELD_ROLE]->(o:Entity) WHERE o.id <> e.id AND (o.lei IS NULL OR e.lei IS NULL OR o.lei <> e.lei)
        OPTIONAL MATCH (rc2:Claim {id:r2.claim_id})
        WITH p, r, rc, collect(DISTINCT {entity_id:o.id, entity:o.name, title:r2.title, current:r2.current,
            flagged:coalesce(o.flagged,false),
            from:r2.from, to:r2.to, kind:o.kind, federal:coalesce(o.federal,false), supplier:EXISTS { (o)-[:SUPPLIES]->() },
            simulated:coalesce(o.simulated,false) OR coalesce(r2.simulated,false) OR coalesce(rc2.simulated,false)
              OR CASE WHEN rc2 IS NULL THEN false ELSE EXISTS {
                MATCH (r2a:Artifact)-[:EVIDENCES]->(rc2) WHERE coalesce(r2a.simulated,false)
              } END
              OR CASE WHEN rc2 IS NULL THEN false ELSE EXISTS {
                MATCH (:Artifact)-[r2e:EVIDENCES]->(rc2) WHERE coalesce(r2e.simulated,false)
              } END,
            role_edge_id:coalesce(r2.id,elementId(r2)), claim_id:r2.claim_id,
            claim_simulated:coalesce(rc2.simulated,false),
            artifact_simulated:CASE WHEN rc2 IS NULL THEN false ELSE EXISTS {
              MATCH (r2a:Artifact)-[:EVIDENCES]->(rc2) WHERE coalesce(r2a.simulated,false)
            } END,
            evidence_simulated:CASE WHEN rc2 IS NULL THEN false ELSE EXISTS {
              MATCH (:Artifact)-[r2e:EVIDENCES]->(rc2) WHERE coalesce(r2e.simulated,false)
            } END,
            source:coalesce(r2.source,rc2.source),
            source_id:coalesce(r2.source_id,rc2.source_id),
            source_identifier:coalesce(r2.source_identifier,rc2.source_identifier),
            catalog_ids:coalesce(r2.catalog_ids,rc2.catalog_ids),
            retrieved_at:coalesce(r2.latest_retrieved_at,rc2.latest_retrieved_at,r2.retrieved_at,rc2.retrieved_at),
            first_retrieved_at:coalesce(r2.retrieved_at,rc2.retrieved_at),
            latest_retrieved_at:coalesce(r2.latest_retrieved_at,rc2.latest_retrieved_at),
            usage_note:coalesce(r2.usage_note,rc2.usage_note),
            quality_note:coalesce(r2.quality_note,rc2.quality_note),
            supports:coalesce(r2.supports,rc2.supports),
            unknowns:coalesce(r2.unknowns,rc2.unknowns),
            source_status:coalesce(r2.source_status,rc2.source_status),
            connector_error:coalesce(r2.connector_error,rc2.connector_error),
            connector_error_type:coalesce(r2.connector_error_type,rc2.connector_error_type),
            connector_error_status:coalesce(r2.connector_error_status,rc2.connector_error_status),
            source_url:coalesce(r2.source_url,head([(r2a:Artifact)-[:EVIDENCES]->(rc2) | r2a.url]))}) AS elsewhere
        RETURN p.id AS person_id, p.name AS name, coalesce(r.id,elementId(r)) AS edge_id,
               r.claim_id AS claim_id, r.title AS title, r.role_type AS role_type, r.from AS from, r.to AS to,
               coalesce(r.current, r.to IS NULL) AS current, coalesce(r.source,rc.source) AS source,
               coalesce(r.source_id,rc.source_id) AS source_id,
               coalesce(r.source_identifier,rc.source_identifier) AS source_identifier,
               coalesce(r.catalog_ids,rc.catalog_ids) AS catalog_ids,
               coalesce(r.source_url,head([(ra:Artifact)-[:EVIDENCES]->(rc) | ra.url])) AS source_url,
               coalesce(r.latest_retrieved_at,rc.latest_retrieved_at,r.retrieved_at,rc.retrieved_at) AS retrieved_at,
               coalesce(r.retrieved_at,rc.retrieved_at) AS first_retrieved_at,
               coalesce(r.latest_retrieved_at,rc.latest_retrieved_at) AS latest_retrieved_at,
               coalesce(r.usage_note,rc.usage_note) AS usage_note,
               coalesce(r.quality_note,rc.quality_note) AS quality_note,
               coalesce(r.supports,rc.supports) AS supports,
               coalesce(r.unknowns,rc.unknowns) AS unknowns,
               coalesce(r.source_status,rc.source_status) AS source_status,
               coalesce(r.connector_error,rc.connector_error) AS connector_error,
               coalesce(r.connector_error_type,rc.connector_error_type) AS connector_error_type,
               coalesce(r.connector_error_status,rc.connector_error_status) AS connector_error_status,
               coalesce(rc.simulated,false) AS claim_simulated,
               CASE WHEN rc IS NULL THEN false ELSE EXISTS {
                 MATCH (ra:Artifact)-[:EVIDENCES]->(rc) WHERE coalesce(ra.simulated,false)
               } END AS artifact_simulated,
               CASE WHEN rc IS NULL THEN false ELSE EXISTS {
                 MATCH (:Artifact)-[re:EVIDENCES]->(rc) WHERE coalesce(re.simulated,false)
               } END AS evidence_simulated,
               coalesce(p.simulated,false) OR coalesce(r.simulated,false) OR coalesce(rc.simulated,false)
                 OR CASE WHEN rc IS NULL THEN false ELSE EXISTS {
                   MATCH (ra:Artifact)-[:EVIDENCES]->(rc) WHERE coalesce(ra.simulated,false)
                 } END
                 OR CASE WHEN rc IS NULL THEN false ELSE EXISTS {
                   MATCH (:Artifact)-[re:EVIDENCES]->(rc) WHERE coalesce(re.simulated,false)
                 } END AS simulated,
               coalesce(p.public_official,false) AS public_official, p.person_types AS person_types,
               elsewhere
        ORDER BY current DESC, r.from DESC
        LIMIT 200
        """,
        {"id": entity_id},
    )
    current = [r for r in rows if r["current"]]
    former = [r for r in rows if not r["current"]]
    for r in rows:
        r["elsewhere"] = [x for x in r["elsewhere"] if x.get("entity_id")]
        gov = [x for x in r["elsewhere"] if x.get("kind") == "agency"]
        # An interlock is a seat at another *supplier* in the network. LittleSis also records
        # seats at banks, law firms and think tanks; those stay visible but do not score.
        suppliers = [x for x in r["elsewhere"] if x.get("supplier", True) and x.get("kind") != "agency"]
        r["interlock"] = any(x["current"] for x in suppliers) and r["current"]
        r["moved_to_flagged"] = any(x["flagged"] and x["current"] for x in r["elsewhere"]) and not r["current"]
        r["formerly_elsewhere"] = bool(r["current"]) and any(not x["current"] for x in suppliers)
        r["government"] = gov
        r["concurrent_government"] = bool(r["current"]) and any(x["current"] for x in gov)
        r["former_government"] = bool(r["current"]) and any(not x["current"] for x in gov)
    seats = await db.read("MATCH (e:Entity {id:$id}) RETURN e.board_size AS n", {"id": entity_id})
    return {"current": current, "former": former, "board_size": seats[0]["n"] if seats else None, "resolved_current_count": len(current)}

# Country and nationality tokens that suggest a counterparty is foreign when no jurisdiction is
# resolved for it. A hint only: it feeds a "low" indicator that says so, never a finding.
_FOREIGN_HINTS = re.compile(
    r"\b(russia|russian|china|chinese|hong kong|iran|iranian|north korea|saudi|emirates|uae|qatar|turkey|turkish|israel|israeli|jordan|jordanian|"
    r"egypt|egyptian|india|indian|pakistan|korea|korean|japan|japanese|taiwan|german|germany|france|french|british|united kingdom|italy|italian|"
    r"spain|spanish|brazil|mexico|canada|canadian|australia|australian|singapore|malaysia|indonesia|vietnam|philippines|kuwait|bahrain|oman|iraq|"
    r"afghanistan|ukraine|poland|polish|sweden|swedish|norway|norwegian|dutch|netherlands|belgium|swiss|switzerland|austria|greece|greek|royal)\b")


def _foreign_hint(name: str | None) -> bool:
    return bool(_FOREIGN_HINTS.search((name or "").lower()))


async def affiliations(entity_id: str) -> dict:
    """The entity's recorded ties beyond supply and ownership: memberships, lobbying,
    transactions and donations, with the counterparty's kind, jurisdiction and flag."""
    rows = await db.read(
        """
        MATCH (e:Entity {id:$id})-[r:MEMBER_OF|TRANSACTS_WITH|LOBBIES|DONATED_TO]-(o:Entity)
        OPTIONAL MATCH (o)-[:INCORPORATED_IN]->(inc:Location)
        OPTIONAL MATCH (o)-[:PARENT_SEATED_IN]->(seat:Location)
        RETURN type(r) AS type, r.id AS edge_id, startNode(r).id = e.id AS outbound, o.id AS entity_id, o.name AS entity, o.kind AS kind,
               coalesce(o.federal,false) AS federal, coalesce(o.flagged,false) AS flagged, o.org_types AS org_types,
               inc.code AS incorporated, seat.code AS parent_seat, r.from AS from, r.to AS to, coalesce(r.current, r.to IS NULL) AS current,
               r.amount AS amount, r.description AS description, r.source AS source, r.source_url AS source_url
        ORDER BY current DESC, coalesce(r.from,'') DESC LIMIT 200
        """,
        {"id": entity_id},
    )
    # Subsidiaries sit here too: the ownership family looks *up* the chain, and a unit
    # seated abroad is exposure the parent chain never shows.
    subs = await db.read(
        """
        MATCH (e:Entity {id:$id})-[r:OWNS]->(o:Entity)
        OPTIONAL MATCH (o)-[:INCORPORATED_IN]->(inc:Location)
        RETURN 'OWNS' AS type, r.id AS edge_id, true AS outbound, o.id AS entity_id, o.name AS entity, o.kind AS kind, false AS federal,
               coalesce(o.flagged,false) AS flagged, o.org_types AS org_types, inc.code AS incorporated, null AS parent_seat,
               r.from AS from, r.to AS to, coalesce(r.current, r.to IS NULL) AS current, r.pct AS amount, r.description AS description,
               r.source AS source, r.source_url AS source_url
        ORDER BY current DESC LIMIT 100
        """,
        {"id": entity_id},
    )
    rows += subs
    for r in rows:
        code = r.get("incorporated") or r.get("parent_seat")
        r["foreign"] = (not code.upper().startswith(HOME)) if code else None
        r["foreign_hint"] = r["foreign"] is None and _foreign_hint(r.get("entity"))
    by_type: dict[str, list[dict]] = {"MEMBER_OF": [], "TRANSACTS_WITH": [], "LOBBIES": [], "DONATED_TO": [], "OWNS": []}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r)
    return {"memberships": by_type["MEMBER_OF"], "transactions": by_type["TRANSACTS_WITH"], "lobbying": by_type["LOBBIES"],
            "donations": by_type["DONATED_TO"], "subsidiaries": by_type["OWNS"], "count": len(rows)}


async def screens(entity_id: str) -> list[dict]:
    """Sanctions / exclusion / registry screens are Claims with predicate *_screen."""
    rows = await db.read(
        """
        MATCH (c:Claim)-[asserts:ASSERTS]->(e:Entity {id:$id})
        WHERE c.predicate ENDS WITH '_screen'
        OPTIONAL MATCH (a:Artifact)-[evidences:EVIDENCES]->(c)
        WITH c, asserts, collect(DISTINCT a{.id,.title,.url,.source,.source_id,.source_identifier,
          .catalog_ids,.retrieved_at,.latest_retrieved_at,.as_of,.latest_as_of,
          .usage_note,.quality_note,.supports,.unknowns,.source_status,
          .connector_error,.connector_error_type,.connector_error_status,.simulated,
          evidence_edge_id:evidences.id, evidence_source:evidences.source,
          evidence_source_id:evidences.source_id, evidence_source_identifier:evidences.source_identifier,
           evidence_catalog_ids:evidences.catalog_ids,
           evidence_retrieved_at:coalesce(evidences.latest_retrieved_at,evidences.retrieved_at),
           evidence_first_retrieved_at:evidences.retrieved_at,
           evidence_latest_retrieved_at:evidences.latest_retrieved_at,
          evidence_usage_note:evidences.usage_note, evidence_quality_note:evidences.quality_note,
          evidence_supports:evidences.supports, evidence_unknowns:evidences.unknowns,
          evidence_source_status:evidences.source_status,
          evidence_connector_error:evidences.connector_error,
          evidence_connector_error_type:evidences.connector_error_type,
          evidence_connector_error_status:evidences.connector_error_status,
          evidence_simulated:coalesce(evidences.simulated,false)}) AS artifacts
        ORDER BY coalesce(c.latest_retrieved_at,c.retrieved_at) DESC, c.id
        RETURN collect({
          claim_id:c.id, predicate:c.predicate, result:c.object_value, source:c.source, method:c.method,
          source_id:c.source_id, source_identifier:c.source_identifier, catalog_ids:c.catalog_ids,
          source_url:c.source_url, usage_note:c.usage_note, quality_note:c.quality_note,
          supports:c.supports, unknowns:c.unknowns, source_status:c.source_status,
          connector_error:c.connector_error, connector_error_type:c.connector_error_type,
          connector_error_status:c.connector_error_status,
          confidence:c.confidence, status:c.status, asserts_edge_id:asserts.id,
          simulated:coalesce(c.simulated,false) OR coalesce(asserts.simulated,false),
          retrieved_at:coalesce(c.latest_retrieved_at,c.retrieved_at),
          first_retrieved_at:c.retrieved_at, latest_retrieved_at:c.latest_retrieved_at,
          as_of:coalesce(c.latest_as_of,c.as_of), artifacts:artifacts, detail:c.detail
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


def _factor_freshness(value: str | None, max_age_days: int, as_of: date) -> str:
    retrieved = _parse_date(value)
    if not retrieved:
        return "unavailable"
    return "stale" if (as_of - retrieved).days > max_age_days else "current"

def _retrieval_time(item: dict) -> str | None:
    return item.get("latest_retrieved_at") or item.get("retrieved_at")
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

def _graph_fact_simulated(fact: dict) -> bool:
    return bool(
        fact.get("simulated")
        or fact.get("relationship_simulated")
        or fact.get("entity_simulated")
        or fact.get("claim_simulated")
        or fact.get("artifact_simulated")
        or fact.get("evidence_simulated")
    )
def _eligible_graph_fact(fact: dict, *nodes: dict) -> bool:
    if _graph_fact_simulated(fact) or any(n.get("simulated") for n in nodes):
        return False
    if fact.get("claim_id"):
        if fact.get("claim_status") != "committed":
            return False
    elif (
        fact.get("status") not in (None, "committed")
        or not fact.get("source")
        or not _retrieval_time(fact)
        or fact.get("confidence") is None
    ):
        return False
    return True


def _safe_https_url(value: object) -> bool:
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
    )


def _canonical_usaspending_award_url(value: object) -> bool:
    if not _safe_https_url(value):
        return False
    parsed = urlparse(str(value))
    path_parts = [part for part in parsed.path.split("/") if part]
    return bool(
        parsed.hostname == "www.usaspending.gov"
        and len(path_parts) == 2
        and path_parts[0] == "award"
        and path_parts[1].startswith("CONT_AWD_")
        and not parsed.query
        and not parsed.fragment
    )


def _eligible_supply_artifacts(fact: dict, max_age_days: int, as_of: date) -> list[dict]:
    source_url = fact.get("source_url")
    if not _canonical_usaspending_award_url(source_url):
        return []
    return sorted([
        artifact for artifact in fact.get("artifacts", [])
        if artifact.get("id")
        and artifact.get("kind") == "award"
        and artifact.get("url") == source_url
        and _canonical_usaspending_award_url(artifact.get("url"))
        and artifact.get("award_id") == fact.get("contract_ref")
        and artifact.get("source") == "USAspending"
        and artifact.get("method")
        and artifact.get("confidence") is not None
        and not artifact.get("simulated")
        and not artifact.get("evidence_simulated")
        and _factor_freshness(artifact.get("retrieved_at"), max_age_days, as_of) == "current"
        and _factor_freshness(artifact.get("evidence_retrieved_at"), max_age_days, as_of) == "current"
    ], key=lambda artifact: str(artifact["id"]))


def _eligible_supply_fact(fact: dict, entity: dict, max_age_days: int, as_of: date) -> bool:
    return bool(
        fact.get("evidence_id")
        and fact.get("status") == "committed"
        and fact.get("claim_id")
        and fact.get("claim_status") == "committed"
        and fact.get("claim_predicate") == "supply_sole_source"
        and fact.get("claim_subject_id") == fact.get("supplier_id")
        and fact.get("claim_target_id") == fact.get("consumer_id")
        and isinstance(fact.get("sole_source"), bool)
        and isinstance(fact.get("claim_object_value"), bool)
        and fact["claim_object_value"] == fact["sole_source"]
        and not fact.get("claim_conflicting")
        and fact.get("source") == "USAspending"
        and fact.get("method")
        and fact.get("confidence") is not None
        and fact.get("claim_source_url") == fact.get("source_url")
        and _factor_freshness(_retrieval_time(fact), max_age_days, as_of) == "current"
        and _eligible_supply_artifacts(fact, max_age_days, as_of)
        and _eligible_graph_fact(fact, entity)
    )


def _screen_artifacts(item: dict) -> list[dict]:
    evidence = [a for a in item.get("artifacts", []) if a]
    legacy = item.get("artifact")
    if legacy and legacy not in evidence:
        evidence.insert(0, legacy)
    return evidence
def _screen_simulated(item: dict) -> bool:
    return bool(
        item.get("simulated")
        or item.get("artifact_simulated")
        or any(a.get("simulated") or a.get("evidence_simulated") for a in _screen_artifacts(item))
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
        eligible_supply: list[dict] = []
        approved = [
            s for s in candidates
            if s.get("status") == "committed"
            and not _screen_simulated(s)
            and not core.get("e", {}).get("simulated")
            and _severity(s.get("result")) is not None
        ]
        approved.sort(key=lambda s: str(_retrieval_time(s) or ""), reverse=True)
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
                                 "claim_status": evidence.get("claim_status") if evidence.get("claim_id") else None,
                                 "freshness": _factor_freshness(_retrieval_time(evidence), spec["max_age_days"], as_of),
                                "provenance": {
                                    "source": evidence.get("source") or "graph",
                                    "retrieved_at": _retrieval_time(evidence),
                                     "confidence": _confidence(evidence.get("confidence"), default=0.0),
                                     "method": evidence.get("claim_method"),
                                },
                                "explanation": f"Ultimate parent jurisdiction is {seat}."})
        elif category == "supply_criticality" and supply.get("risk_evidence"):
            eligible_supply = [
                s for s in supply["risk_evidence"]
                if _eligible_supply_fact(s, core.get("e", {}), spec["max_age_days"], as_of)
            ]
            for ref in eligible_supply:
                severity = "medium" if ref["sole_source"] else "clear"
                eligible_artifacts = _eligible_supply_artifacts(ref, spec["max_age_days"], as_of)
                artifact_refs = [str(a["id"]) for a in eligible_artifacts]
                refs = [str(ref["claim_id"]), *artifact_refs, str(ref["evidence_id"])]
                factors.append({"rule_id": "supply.sole-source.v1", "severity": severity,
                                "evidence_refs": refs, "truth_status": "committed",
                                 "claim_status": ref.get("claim_status"),
                                 "artifacts": eligible_artifacts,
                                 "graph_path": {
                                     "relationship_id": str(ref["evidence_id"]),
                                     "supplier_id": ref.get("supplier_id"),
                                     "consumer_id": ref.get("consumer_id"),
                                 },
                                 "freshness": _factor_freshness(_retrieval_time(ref), spec["max_age_days"], as_of),
                                "provenance": {"source": ref.get("source") or "graph",
                                               "retrieved_at": _retrieval_time(ref),
                                               "confidence": _confidence(ref.get("confidence"), default=0.0),
                                               "method": ref.get("method")},
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
                "claim_status": item.get("status"),
                "freshness": _factor_freshness(_retrieval_time(item), spec["max_age_days"], as_of),
                "provenance": {"source": item.get("source"), "retrieved_at": _retrieval_time(item),
                               "confidence": _confidence(item.get("confidence"), default=0.0),
                               "method": item.get("method")},
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
            excluded_items = [s for s in candidates if s not in approved]
            if category == "supply_criticality":
                excluded_items += [
                    {
                        **s,
                        "status": (
                            "stale" if _factor_freshness(_retrieval_time(s), spec["max_age_days"], as_of) == "stale"
                            else s.get("claim_status") or ("claimless" if not s.get("claim_id") else "missing_artifact")
                        ),
                        "simulated": _graph_fact_simulated(s),
                        "claim_id": s.get("claim_id"),
                    }
                    for s in supply.get("risk_evidence", [])
                    if s not in eligible_supply
                ]
            excluded = sorted({str(s.get("status") or "unknown") for s in excluded_items})
            diligence.append({"category": category, "code": "missing_approved_evidence",
                              "excluded_truth_statuses": excluded,
                              "excluded_evidence": [{
                                  "evidence_ref": s.get("claim_id") or s.get("evidence_id") or f"claim:{s.get('predicate')}",
                                  "truth_status": s.get("status") or "unknown",
                                  "simulated": bool(_screen_simulated(s) or core.get("e", {}).get("simulated")),
                              } for s in excluded_items],
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
                    "provenance_fields": ["source", "confidence", "retrieved_at", "method", "detail"],
                    "artifact_fields": ["id", "source", "retrieved_at", "simulated"],
                    "artifact_container": "artifacts (plural); legacy artifact is also validated",
                },
                "ownership_graph_evidence": {
                    "container": "parent_seat_evidence",
                    "fields": ["id", "claim_id", "claim_status", "claim_simulated",
                               "artifact_simulated", "evidence_simulated", "seat_code", "seat_simulated",
                               "source", "retrieved_at", "method", "confidence", "status", "simulated"],
                },
                "supply_graph_evidence": {
                    "container": "risk_evidence",
                    "fields": ["evidence_id", "claim_id", "claim_status", "claim_simulated",
                               "artifact_simulated", "evidence_simulated", "sole_source", "entity_simulated",
                               "source", "retrieved_at", "method", "confidence", "status", "simulated",
                               "supplier_id", "consumer_id", "claim_predicate", "claim_object_value",
                               "claim_subject_id", "claim_target_id", "claim_conflicting",
                               "source_url", "claim_source_url", "artifacts"],
                    "artifact_fields": ["id", "kind", "award_id", "url", "source",
                                        "retrieved_at", "evidence_retrieved_at", "method",
                                        "confidence", "simulated", "evidence_simulated"],
                    "claimless_trusted_fact_contract": "not supported; a committed claim and exact source artifact are required",
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
        RETURN a.id AS id, a.kind AS kind, a.title AS title, a.url AS url, a.source AS source,
               coalesce(a.latest_retrieved_at,a.retrieved_at) AS retrieved_at,
               a.retrieved_at AS first_retrieved_at, a.latest_retrieved_at AS latest_retrieved_at,
               coalesce(a.simulated,false) AS simulated,
               a.published_at AS published_at, a.sentiment AS sentiment, a.amount AS amount, a.summary AS summary
        ORDER BY coalesce(a.published_at, a.latest_retrieved_at, a.retrieved_at) DESC LIMIT $limit
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


def _ind(family: str, label: str, severity: str | None, source: str | None, detail: str | None = None,
         url: str | None = None, ids: list[str] | None = None, simulated: bool = False) -> dict:
    return {
        "family": family,
        "label": label,
        "severity": severity,
        "source": source,
        "detail": detail,
        "source_url": url,
        "element_ids": [i for i in (ids or []) if i],
        "simulated": bool(simulated),
        "no_data": severity is None,
    }

def _int(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
def _tie_label(t: dict) -> str:
    """'Membership: SHREC', 'Subsidiary: Raytheon Saudi Arabia'."""
    word = {"MEMBER_OF": "Membership", "TRANSACTS_WITH": "Business relationship", "LOBBIES": "Lobbying", "DONATED_TO": "Donation", "OWNS": "Subsidiary"}.get(t.get("type") or "", "Tie")
    return f"{word}: {t.get('entity')}"


def _screen_refs(screen: dict) -> tuple[list[str], str | None, bool]:
    evidence = _screen_artifacts(screen)
    ids = [screen.get("claim_id"), screen.get("asserts_edge_id")]
    ids.extend(ref for artifact in evidence for ref in (artifact.get("id"), artifact.get("evidence_edge_id")))
    url = next((artifact.get("url") for artifact in evidence if artifact.get("url")), None)
    return list(dict.fromkeys(i for i in ids if i)), url, _screen_simulated(screen)
async def risk_indicators(entity_id: str, core: dict, supply: dict, ppl: dict, scr: list[dict], aff: dict | None = None) -> dict:
    inds: list[dict] = []
    aff = aff or {"memberships": [], "transactions": [], "lobbying": [], "donations": [], "subsidiaries": [], "count": 0}
    e = core["e"]
    # 1. Ownership / foreign control
    seat = (core.get("parent_seat") or {}).get("code")
    seat_ref = core.get("parent_seat") or {}
    ups = core.get("ultimate_parents") or []
    if seat:
        foreign = not seat.upper().startswith(HOME)
        detail = f"Ultimate parent seated in {seat}" + (f" — {ups[0]['name']}" if ups else "")
        seat_evidence = [
            fact for fact in core.get("parent_seat_evidence", [])
            if fact.get("id") == seat_ref.get("relationship_id") or fact.get("seat_code") == seat
        ]
        # The whole chain, not just its endpoints: highlighting a derived parent is only
        # meaningful if the hops that lead to it light up with it.
        ownership_ids = [
            i for u in ups
            for i in (u.get("id"), u.get("relationship_id"), u.get("claim_id"), *(u.get("relationship_ids") or ()))
            if i
        ]
        ownership_ids += [i for i in (seat_ref.get("id"), seat_ref.get("relationship_id")) if i]
        ownership_ids += [
            i for fact in seat_evidence for i in (fact.get("claim_id"), fact.get("id")) if i
        ]
        ownership_ids = list(dict.fromkeys(ownership_ids))
        ownership_url = next((u.get("source_url") for u in ups if u.get("source_url")), None) or seat_ref.get("source_url")
        ownership_url = ownership_url or next(
            (fact.get("source_url") for fact in seat_evidence if fact.get("source_url")),
            None,
        )
        ownership_simulated = (
            any(_graph_fact_simulated(u) for u in ups)
            or bool(seat_ref.get("simulated") or seat_ref.get("relationship_simulated"))
            or any(_graph_fact_simulated(fact) for fact in seat_evidence)
        )
        inds.append(_ind("ownership", "Foreign ultimate parent" if foreign else "Domestic ultimate parent", "high" if foreign else "clear",
                         e.get("ownership_source") or "GLEIF", detail, ownership_url, ownership_ids, ownership_simulated))
    elif ups:
        u0 = ups[0]
        inds.append(_ind(
            "ownership",
            "Ultimate parent known, jurisdiction unresolved",
            "low",
            u0.get("source") or "GLEIF",
            u0["name"],
            u0.get("source_url"),
            [u0.get("id"), u0.get("relationship_id"), u0.get("claim_id")],
            _graph_fact_simulated(u0),
        ))
    elif core.get("direct_parents"):
        dp = core["direct_parents"][0]
        inds.append(_ind("ownership", "Parent recorded, jurisdiction unresolved", "low", e.get("ownership_source") or "LittleSis",
                         dp["name"] + (f" ({dp['pct']}%)" if dp.get("pct") else ""), ids=[dp["id"]]))
    else:
        inds.append(_ind("ownership", "Ownership chain", None, None, "No parent records resolved"))
    # 2. Concentration / sole source
    if supply["supplies"]:
        def backing_for(display: dict) -> list[dict]:
            return [
                fact for fact in supply.get("risk_evidence", [])
                if (
                    fact.get("evidence_id") == display.get("edge_id")
                    or (
                        fact.get("contract_ref")
                        and fact.get("contract_ref") == display.get("contract_ref")
                    )
                )
            ]

        ss = [s for s in supply["supplies"] if s.get("sole_source")]
        if ss:
            s0 = ss[0]
            backing = backing_for(s0)
            supply_ids = [s0.get("edge_id")]
            supply_ids += [
                i for fact in backing for i in (fact.get("claim_id"), fact.get("evidence_id")) if i
            ]
            supply_url = s0.get("source_url") or next(
                (fact.get("source_url") for fact in backing if fact.get("source_url")),
                None,
            )
            inds.append(_ind("concentration", f"Sole source at tier {s0.get('tier') or '?'}" + (f" for PSC {s0['psc']}" if s0.get("psc") else ""),
                             "medium", s0.get("source") or "USAspending", s0.get("contract_ref"), supply_url,
                             ids=list(dict.fromkeys(i for i in supply_ids if i)),
                             simulated=bool(s0.get("simulated") or any(_graph_fact_simulated(fact) for fact in backing))))
        else:
            backing = [fact for display in supply["supplies"] for fact in backing_for(display)]
            supply_ids = [display.get("edge_id") for display in supply["supplies"]]
            supply_ids += [
                i for fact in backing for i in (fact.get("claim_id"), fact.get("evidence_id")) if i
            ]
            supply_url = next(
                (display.get("source_url") for display in supply["supplies"] if display.get("source_url")),
                None,
            ) or next((fact.get("source_url") for fact in backing if fact.get("source_url")), None)
            inds.append(_ind(
                "concentration",
                "No sole-source awards on record",
                "clear",
                "USAspending",
                url=supply_url,
                ids=list(dict.fromkeys(i for i in supply_ids if i)),
                simulated=bool(
                    any(display.get("simulated") for display in supply["supplies"])
                    or any(_graph_fact_simulated(fact) for fact in backing)
                ),
            ))
    else:
        inds.append(_ind("concentration", "Supply position", None, None, "No award records for this entity"))
    # 3. People
    interlocks = [p for p in ppl["current"] if p.get("interlock")]
    moved = [p for p in ppl["former"] if p.get("moved_to_flagged")]
    # Someone on staff *now* who also sits inside a flagged entity *now*. This is the
    # sharpest form of the tie and it used to fall through: flagged_in below only caught
    # a lapsed role at the flagged entity, so a concurrent one scored as clear.
    flagged_now = [p for p in ppl["current"] if any(x["flagged"] and x["current"] for x in p["elsewhere"])]
    flagged_in = [p for p in ppl["current"] if any(x["flagged"] and not x["current"] for x in p["elsewhere"])]
    if moved or flagged_now or flagged_in:
        who = (moved or flagged_now or flagged_in)[0]
        concurrent = not moved and bool(flagged_now)
        # Prefer the live role at the flagged entity when the person holds more than one.
        flagged_roles = [x for x in who["elsewhere"] if x["flagged"]]
        other = next((x for x in flagged_roles if x["current"]), None) if concurrent else None
        other = other or next(iter(flagged_roles), None)
        people_ids = [who.get("person_id"), who.get("edge_id"), who.get("claim_id")]
        if other:
            people_ids += [other.get("entity_id"), other.get("role_edge_id"), other.get("claim_id")]
        role = who["title"] or "officer"
        label = (f"Current {role} concurrently at flagged entity" if concurrent
                 else f"{'Former' if moved else 'Current'} {role} linked to flagged entity")
        inds.append(_ind("people", label + (f" ({other['entity']})" if other else ""),
                         "high" if concurrent else "medium",
                         who.get("source") or (other or {}).get("source") or "LittleSis", who["name"],
                         who.get("source_url") or (other or {}).get("source_url"), ids=people_ids,
                          simulated=bool(_graph_fact_simulated(who) or _graph_fact_simulated(other or {}))))
    elif any(p.get("formerly_elsewhere") for p in ppl["current"]):
        p0 = next(p for p in ppl["current"] if p.get("formerly_elsewhere"))
        other = next((x for x in p0["elsewhere"] if not x["current"] and x.get("supplier", True)), None)
        people_ids = [p0.get("person_id"), p0.get("edge_id"), p0.get("claim_id")]
        if other:
            people_ids += [other.get("entity_id"), other.get("role_edge_id"), other.get("claim_id")]
        inds.append(_ind("people", f"Former {(other['title'] if other['title'] and other['title'] != 'Position' else 'officer')} of {other['entity']} on current board" if other else "Former officer of another supplier on current board",
                         "medium", p0.get("source") or (other or {}).get("source") or "LittleSis",
                         f"{p0['name']} — {p0['title'] or 'role'} since {p0.get('from') or '?'}",
                         p0.get("source_url") or (other or {}).get("source_url"), ids=people_ids,
                          simulated=bool(_graph_fact_simulated(p0) or _graph_fact_simulated(other or {}))))
    elif interlocks:
        p0 = interlocks[0]
        other = next((x for x in p0["elsewhere"] if x["current"] and x.get("supplier", True)), None)
        people_ids = [p0.get("person_id"), p0.get("edge_id"), p0.get("claim_id")]
        if other:
            people_ids += [other.get("entity_id"), other.get("role_edge_id"), other.get("claim_id")]
        inds.append(_ind("people", f"Board interlock — {p0['name']} also at {other['entity'] if other else 'another supplier'}", "low", p0.get("source") or "LittleSis",
                         "An interlock is a lead, not a finding", p0.get("source_url") or (other or {}).get("source_url"),
                          ids=people_ids, simulated=bool(_graph_fact_simulated(p0) or _graph_fact_simulated(other or {}))))
    elif ppl["current"] or ppl["former"]:
        resolved_people = ppl["current"] + ppl["former"]
        people_ids = [
            i for person in resolved_people
            for i in (person.get("person_id"), person.get("edge_id"), person.get("claim_id")) if i
        ]
        people_ids += [
            i for person in resolved_people for other in person.get("elsewhere", [])
            for i in (other.get("entity_id"), other.get("role_edge_id"), other.get("claim_id")) if i
        ]
        people_url = next(
            (person.get("source_url") for person in resolved_people if person.get("source_url")),
            None,
        ) or next(
            (
                other.get("source_url")
                for person in resolved_people
                for other in person.get("elsewhere", [])
                if other.get("source_url")
            ),
            None,
        )
        people_simulated = any(
            _graph_fact_simulated(person)
            or any(_graph_fact_simulated(other) for other in person.get("elsewhere", []))
            for person in resolved_people
        )
        inds.append(_ind(
            "people",
            "No interlocks or flagged movements among resolved people",
            "clear",
            "LittleSis · EDGAR",
            url=people_url,
            ids=list(dict.fromkeys(people_ids)),
            simulated=people_simulated,
        ))
    else:
        inds.append(_ind("people", "People", None, None, "No officers or directors resolved"))
    # 3b. Government ties — the revolving door and public-office holders on the board
    concurrent = [p for p in ppl["current"] if p.get("concurrent_government")]
    former_gov = [p for p in ppl["current"] if p.get("former_government")]
    officials = [p for p in ppl["current"] if p.get("public_official")]
    if concurrent:
        p0 = concurrent[0]
        g = next(x for x in p0["government"] if x["current"])
        inds.append(_ind("government", f"Current {p0['title'] or 'officer'} also holds a post at {g['entity']}", "medium", p0.get("source") or "LittleSis",
                         f"{p0['name']} — concurrent {'federal ' if g.get('federal') else ''}government position; conflict-of-interest lead", p0.get("source_url"), ids=[p0["person_id"], g["entity_id"]]))
    elif former_gov or officials:
        p0 = (former_gov or officials)[0]
        g = next((x for x in p0["government"] if not x["current"]), None)
        n = len(former_gov)
        label = (f"{n} current officer{'s' if n != 1 else ''} previously in government" if former_gov
                 else f"{p0['name']} is a {', '.join(t for t in (p0.get('person_types') or []) if t in ('Public Official', 'Elected Representative', 'Political Candidate', 'Lobbyist')) or 'public-office holder'}")
        inds.append(_ind("government", label, "low", p0.get("source") or "LittleSis",
                         f"{p0['name']} — formerly {g['title'] or 'at'} {g['entity']}" + (f" until {g['to']}" if g and g.get("to") else "") if g else "Revolving-door exposure is a lead, not a finding",
                         p0.get("source_url"), ids=[p0["person_id"]] + ([g["entity_id"]] if g else [])))
    elif ppl["current"]:
        inds.append(_ind("government", "No government posts among resolved current officers", "clear", "LittleSis"))
    else:
        inds.append(_ind("government", "Government ties", None, None, "No officers resolved to check"))
    # 3c. Affiliations — memberships and transactions with flagged or foreign counterparties
    ties = aff["memberships"] + aff["transactions"] + aff.get("subsidiaries", [])
    flagged_ties = [t for t in ties if t.get("flagged")]
    foreign_ties = [t for t in ties if t.get("foreign")]
    hinted = [t for t in ties if t.get("foreign_hint")]
    if flagged_ties:
        t0 = flagged_ties[0]
        inds.append(_ind("affiliations", f"{_tie_label(t0)} — flagged entity", "high", t0.get("source") or "LittleSis", t0.get("description"), t0.get("source_url"), ids=[t0["entity_id"]]))
    elif foreign_ties:
        t0 = foreign_ties[0]
        inds.append(_ind("affiliations", f"{_tie_label(t0)} — seated in {t0.get('incorporated') or t0.get('parent_seat')}", "medium",
                         t0.get("source") or "LittleSis", t0.get("description"), t0.get("source_url"), ids=[t0["entity_id"]]))
    elif hinted:
        t0 = hinted[0]
        inds.append(_ind("affiliations", f"{_tie_label(t0)} — name suggests a foreign counterparty", "low", t0.get("source") or "LittleSis",
                         (t0.get("description") or "") + " · jurisdiction unresolved; verify before weighting", t0.get("source_url"), ids=[t0["entity_id"]]))
    elif ties:
        inds.append(_ind("affiliations", f"{len(ties)} recorded affiliation{'s' if len(ties) != 1 else ''}, none foreign or flagged", "clear", "LittleSis"))
    else:
        inds.append(_ind("affiliations", "Affiliations", None, None, "No memberships or transactions on record"))
    # 3d. Political exposure — lobbying and giving
    lob = aff["lobbying"]
    don = aff["donations"]
    if lob:
        cur = [l for l in lob if l.get("current")]
        bodies = sorted({l["entity"] for l in lob})
        inds.append(_ind("political", f"Lobbies {len(bodies)} government bod{'ies' if len(bodies) != 1 else 'y'}" + (f", {len(cur)} ongoing" if cur else ""), "low",
                         lob[0].get("source") or "LittleSis", ", ".join(bodies[:4]) + ("…" if len(bodies) > 4 else "") + (f" · LDA registrant {e['lda_registrant_id']}" if e.get("lda_registrant_id") else ""),
                         lob[0].get("source_url"), ids=[l["entity_id"] for l in lob[:6]]))
    elif don:
        inds.append(_ind("political", f"{len(don)} recorded donation{'s' if len(don) != 1 else ''}, no lobbying on record", "clear", don[0].get("source") or "LittleSis",
                         ", ".join(sorted({d['entity'] for d in don})[:4]), don[0].get("source_url")))
    elif e.get("lda_registrant_id"):
        inds.append(_ind("political", "Registered lobbying entity, no relationships recorded", "low", "LittleSis", f"LDA registrant {e['lda_registrant_id']}"))
    else:
        inds.append(_ind("political", "Political exposure", None, None, "No lobbying or donation records"))
    # 4. Sanctions & debarment
    # Report committed findings even when simulated; the separate score contract excludes
    # simulated evidence from numeric contributions.
    reported_scr = [s for s in scr if s.get("status", "committed") == "committed"]
    sanc = next((s for s in reported_scr if s["predicate"] == "sanctions_screen"), None)
    excl = next((s for s in reported_scr if s["predicate"] == "exclusion_screen"), None)
    if sanc or excl:
        hit = (sanc and sanc["result"] == "hit") or (excl and excl["result"] == "hit")
        src = " · ".join(x["source"] for x in (sanc, excl) if x)
        det = "; ".join(filter(None, [(sanc or {}).get("detail"), (excl or {}).get("detail")]))
        refs = [_screen_refs(screen) for screen in (sanc, excl) if screen]
        ids = list(dict.fromkeys(i for screen_ids, _, _ in refs for i in screen_ids))
        url = next((screen_url for _, screen_url, _ in refs if screen_url), None)
        simulated = any(screen_simulated for _, _, screen_simulated in refs)
        inds.append(_ind("sanctions", "Sanctions and debarment screen" + (" — HIT" if hit else ""), "high" if hit else "clear", src, det or None, url, ids, simulated))
    else:
        inds.append(_ind("sanctions", "Sanctions and debarment screen", None, None, "Not yet screened"))
    # 5. Financial health — only meaningful for listed entities with filings
    fin = next((s for s in reported_scr if s["predicate"] == "financial_screen"), None)
    if fin:
        ids, url, simulated = _screen_refs(fin)
        inds.append(_ind("financial", "Financial health", fin["result"] if fin["result"] in SEVERITY_WEIGHT else "low", fin["source"], fin.get("detail"), url, ids, simulated))
    elif e.get("public") and e.get("ticker"):
        inds.append(_ind("financial", "Financial health — listed, filings available", "clear", "EDGAR", f"Ticker {e['ticker']}"))
    else:
        inds.append(_ind("financial", "Financial health — private entity, no filings", None, None))
    # 6. Adverse media
    adv = next((s for s in reported_scr if s["predicate"] == "adverse_media_screen"), None)
    if adv:
        ids, url, simulated = _screen_refs(adv)
        inds.append(_ind("media", "Adverse media", adv["result"] if adv["result"] in SEVERITY_WEIGHT else "low", adv["source"], adv.get("detail"), url, ids, simulated))
    else:
        inds.append(_ind("media", "Adverse media — below coverage threshold", None, None))

    if e.get("simulated"):
        for indicator in inds:
            indicator["simulated"] = True
    observed = [i for i in inds if not i["no_data"]]
    return {
        "indicators": inds,
        "families_requested": len(inds),
        "families_with_data": len(observed),
        "note": "Risk score uses approved, non-simulated evidence only. Missing, staged, rejected, and simulated evidence does not contribute.",
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
    aff = await affiliations(entity_id)
    risk = await risk_indicators(entity_id, core, supply, ppl, scr, aff)
    risk.update(evaluate_risk_contract(core, supply, scr))
    e = core["e"]
    sources = sorted({s for s in [e.get("source")] + [a.get("source") for a in arts] + [p.get("source") for p in ppl["current"] + ppl["former"]] if s})
    report = {
        "entity": e,
        "identity": {
            "id": e.get("id"), "name": e.get("name"), "uei": e.get("uei"), "cage": e.get("cage"), "lei": e.get("lei"),
            "aliases": e.get("aliases") or [], "kind": e.get("kind"), "registration_status": e.get("registration_status"),
            "public": e.get("public"), "ticker": e.get("ticker"), "simulated": bool(e.get("simulated")),
            "revenue": _int(e.get("revenue")), "lda_registrant_id": e.get("lda_registrant_id"), "org_types": e.get("org_types"), "blurb": e.get("blurb"),
        },
        "affiliations": aff,
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
        "sources": sources,
        "generated_at": date.today().isoformat(),
    }
    fallback = deterministic_summary(report)
    persisted = validate_model_summary(
        {"finding_ids": e.get("summary_finding_ids")},
        report,
        e.get("summary_model") or "model",
    )
    report["summary"] = {
        **(persisted or fallback),
        "generated_at": e.get("summary_at"),
        "source_count": len(arts),
    }
    return report


def approved_summary_findings(report: dict) -> list[dict]:
    """Project only truth-validated risk-contract factors for summarization."""
    findings: list[dict] = []
    for index, category in enumerate(report.get("risk", {}).get("categories") or []):
        family = category.get("id") or str(index + 1)
        factors = [
            factor for factor in category.get("factors") or []
            if factor.get("truth_status") == "committed"
        ]
        evidence_ids = sorted({
            str(ref)
            for factor in factors
            for ref in factor.get("evidence_refs") or []
            if ref
        })
        severity = category.get("severity") if evidence_ids else None
        finding_id = f"finding:risk:{family}"
        label = (
            f"{family.replace('_', ' ')} risk is {severity}"
            if severity else f"{family.replace('_', ' ')} evidence is missing"
        )
        findings.append({
            "id": finding_id,
            "family": family,
            "label": label,
            "severity": severity,
            "detail": "; ".join(
                str(factor["explanation"])
                for factor in factors
                if factor.get("explanation")
            ) or None,
            "no_data": severity is None,
            "evidence_ids": evidence_ids,
            "freshness": category.get("freshness"),
        })
    return findings


def approved_risk_projection(report: dict) -> dict:
    """Return only the validated risk contract for model and MCP transports."""
    risk = report.get("risk") or {}
    categories = []
    for category in risk.get("categories") or []:
        categories.append({
            key: category.get(key)
            for key in ("id", "weight", "severity", "contribution", "confidence", "freshness")
        } | {
            "factors": [{
                key: factor.get(key)
                for key in ("rule_id", "severity", "evidence_refs", "truth_status", "claim_status", "freshness", "provenance", "explanation")
            } for factor in category.get("factors") or [] if factor.get("truth_status") == "committed"],
        })
    return {
        key: risk.get(key)
        for key in (
            "contract_version", "score", "band", "disposition", "confidence",
            "completeness", "freshness",
        )
    } | {
        "categories": categories,
        "diligence_flags": [{
            key: flag.get(key)
            for key in ("category", "code", "message", "excluded_truth_statuses")
            if key in flag
        } for flag in risk.get("diligence_flags") or []],
    }


async def persist_summary(entity_id: str, summary: dict) -> bool:
    """Persist only validated model selections; clear stale selections on fallback."""
    if summary.get("generated_by") == "model-assisted":
        await db.write(
            "MATCH (e:Entity {id:$id}) "
            "SET e.summary_finding_ids=$f, e.summary_model=$m, e.summary_at=$t "
            "REMOVE e.summary, e.summary_citations",
            {
                "id": entity_id,
                "f": summary["selected_finding_ids"],
                "m": summary["model"],
                "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        return True
    await clear_persisted_summary(entity_id)
    return False


async def clear_persisted_summary(entity_id: str) -> None:
    """Remove model selection metadata so reports render deterministic fallback."""
    await db.write(
        "MATCH (e:Entity {id:$id}) "
        "REMOVE e.summary_finding_ids, e.summary_model, e.summary_at, e.summary, e.summary_citations",
        {"id": entity_id},
    )


def _render_summary(report: dict, selected_ids: list[str], generated_by: str, model: str | None, reason: str | None) -> dict:
    """Narrative that remains available without a model and preserves uncertainty."""
    identity = report.get("identity") or {}
    name = identity.get("name") or identity.get("id") or "This entity"
    risk = report.get("risk") or {}
    findings = approved_summary_findings(report)
    supported = [f for f in findings if not f["no_data"]]
    missing = [f for f in findings if f["no_data"]]
    selected = [f for finding_id in selected_ids for f in findings if f["id"] == finding_id]
    notable = [f for f in selected if not f["no_data"] and f.get("severity") in {"high", "medium", "low"}]
    all_notable = [f for f in supported if f.get("severity") in {"high", "medium", "low"}]
    sentences = [f"{name} has {len(supported)} of {len(findings)} requested risk signal families with deterministic data."]
    if identity.get("simulated"):
        sentences.append("This is a simulated scenario entity, not an observed supplier fact.")
    if notable:
        lead = notable[0]
        sentences.append(f"A prioritized review condition is {lead['label']}.")
    if all_notable:
        counts = {severity: sum(1 for f in all_notable if f.get("severity") == severity) for severity in ("high", "medium", "low")}
        sentences.append(
            "Deterministic review conditions include "
            + ", ".join(f"{count} {severity}" for severity, count in counts.items() if count)
            + "."
        )
    elif supported:
        sentences.append("Available deterministic screens do not identify a non-clear review condition.")
    if missing:
        family_word = "family" if len(missing) == 1 else "families"
        sentences.append(f"Evidence is missing for {len(missing)} signal {family_word}; those gaps are not treated as clear results.")
    sentences.append("Scores, simulation status, and dispositions remain deterministic and require human review.")
    cited_findings = selected or findings
    citations = sorted({eid for f in cited_findings for eid in f["evidence_ids"]})
    return {
        "text": " ".join(sentences),
        "citations": citations,
        "generated_by": generated_by,
        "model": model,
        "fallback_reason": reason,
        "immutable_fields": list(IMMUTABLE_AI_FIELDS),
        "selected_finding_ids": [f["id"] for f in selected],
    }

def validate_model_summary(output: Any, report: dict, model: str) -> dict | None:
    """Accept only model-selected approved finding IDs; render prose locally."""
    if not isinstance(output, dict) or set(output) != {"finding_ids"}:
        return None
    selected_ids = output.get("finding_ids")
    if not isinstance(selected_ids, list) or not 1 <= len(selected_ids) <= 3:
        return None
    if not all(isinstance(x, str) for x in selected_ids) or len(set(selected_ids)) != len(selected_ids):
        return None
    allowed = {
        f["id"]
        for f in approved_summary_findings(report)
        if not f["no_data"] and f.get("severity") in {"high", "medium", "low"}
    }
    if any(finding_id not in allowed for finding_id in selected_ids):
        return None
    return _render_summary(report, selected_ids, "model-assisted", model, None)

def deterministic_summary(report: dict, reason: str | None = None) -> dict:
    findings = approved_summary_findings(report)
    notable_ids = [f["id"] for f in findings if not f["no_data"] and f.get("severity") in {"high", "medium", "low"}]
    return _render_summary(report, notable_ids[:3], "deterministic", None, reason)

def _ownership_record(row: dict, *, relationship_present: bool) -> dict:
    artifacts = [a for a in (row.get("artifacts") or []) if a and a.get("id")]
    claim_status = row.get("claim_status")
    evidence_present = bool(row.get("claim_id") and artifacts)
    freshness = _ownership_freshness(row.get("claim_retrieved_at"))
    conflicting = bool(relationship_present and claim_status and claim_status != "committed")
    simulated = any((
        row.get("owner_simulated"),
        row.get("relationship_simulated"),
        row.get("claim_simulated"),
        any(a.get("simulated") or a.get("evidence_simulated") for a in artifacts),
    ))
    return {
        "owner": {
            "id": row.get("owner_id"),
            "name": row.get("owner_name") or "Unavailable",
            "kind": row.get("owner_kind") or "Unavailable",
        },
        "relationship_type": OWNERSHIP_TYPES.get(row.get("predicate"), "unknown"),
        "predicate": row.get("predicate"),
        "percentage": row.get("percentage"),
        "effective_date": row.get("effective_date"),
        "as_of_date": row.get("as_of_date"),
        "relationship": {
            "id": row.get("relationship_id"),
            "present": relationship_present,
        },
        "claim": {
            "id": row.get("claim_id"),
            "status": claim_status or "unavailable",
            "source": row.get("claim_source"),
            "retrieved_at": row.get("claim_retrieved_at"),
            "method": row.get("claim_method"),
            "confidence": row.get("claim_confidence"),
        } if row.get("claim_id") else None,
        "artifacts": artifacts,
        "truth_status": (
            "conflicting" if conflicting
            else "superseded" if claim_status == "committed" and not relationship_present
            else "stale" if claim_status == "committed" and evidence_present and freshness == "stale"
            else "unsupported" if claim_status == "committed" and not evidence_present
            else claim_status or "unsupported"
        ),
        "freshness": freshness,
        "conflicting": conflicting,
        "current": bool(relationship_present and claim_status == "committed"),
        "evidence_present": evidence_present,
        "simulated": bool(simulated),
    }

async def ownership_records(entity_id: str) -> list[dict]:
    """Return claim-current ownership facts without treating copied edge metadata as evidence."""
    claim_rows = await db.read(
        """
        MATCH (c:Claim)-[:ASSERTS]->(owner)
        MATCH (c)-[:TARGETS]->(target)
        WHERE target.id=$id AND c.predicate IN ['OWNS','ULTIMATE_PARENT_OF','BENEFICIAL_OWNER_OF']
        OPTIONAL MATCH (owner)-[r]->(target)
          WHERE type(r)=c.predicate AND r.claim_id=c.id
        OPTIONAL MATCH (a:Artifact)-[ev:EVIDENCES]->(c)
        WITH c, owner, r, collect(DISTINCT a{
          .id,.title,.url,.kind,.source,.retrieved_at,.source_status,.simulated,
          evidence_id:coalesce(ev.id, elementId(ev)),
          evidence_simulated:coalesce(ev.simulated,false)
        }) AS artifacts
        RETURN owner.id AS owner_id, owner.name AS owner_name,
               coalesce(owner.kind, head(labels(owner))) AS owner_kind,
               coalesce(owner.simulated,false) AS owner_simulated,
               c.predicate AS predicate, c.id AS claim_id, c.status AS claim_status,
               c.source AS claim_source, c.retrieved_at AS claim_retrieved_at,
               c.method AS claim_method, c.confidence AS claim_confidence,
               coalesce(c.simulated,false) AS claim_simulated,
               coalesce(r.id, elementId(r)) AS relationship_id,
               coalesce(r.simulated,false) AS relationship_simulated,
               coalesce(r.pct, apoc.convert.fromJsonMap(coalesce(c.rel_props,'{}')).pct) AS percentage,
               coalesce(r.effective_date, r.from, apoc.convert.fromJsonMap(coalesce(c.rel_props,'{}')).effective_date,
                        apoc.convert.fromJsonMap(coalesce(c.rel_props,'{}')).from) AS effective_date,
               coalesce(r.as_of_date, r.to, apoc.convert.fromJsonMap(coalesce(c.rel_props,'{}')).as_of_date,
                        apoc.convert.fromJsonMap(coalesce(c.rel_props,'{}')).to) AS as_of_date,
               artifacts
        ORDER BY c.retrieved_at DESC, owner.name
        """,
        {"id": entity_id},
    )
    edge_rows = await db.read(
        """
        MATCH (owner)-[r:OWNS|ULTIMATE_PARENT_OF|BENEFICIAL_OWNER_OF]->(target:Entity {id:$id})
        WHERE r.claim_id IS NULL
        RETURN owner.id AS owner_id, owner.name AS owner_name,
               coalesce(owner.kind, head(labels(owner))) AS owner_kind,
               coalesce(owner.simulated,false) AS owner_simulated,
               type(r) AS predicate, null AS claim_id, null AS claim_status,
               null AS claim_source, null AS claim_retrieved_at,
               null AS claim_method, null AS claim_confidence, false AS claim_simulated,
               coalesce(r.id, elementId(r)) AS relationship_id,
               coalesce(r.simulated,false) AS relationship_simulated,
               r.pct AS percentage, coalesce(r.effective_date,r.from) AS effective_date,
               coalesce(r.as_of_date,r.to) AS as_of_date, [] AS artifacts
        ORDER BY owner.name
        """,
        {"id": entity_id},
    )
    return (
        [_ownership_record(row, relationship_present=bool(row.get("relationship_id"))) for row in claim_rows]
        + [_ownership_record(row, relationship_present=True) for row in edge_rows]
    )
