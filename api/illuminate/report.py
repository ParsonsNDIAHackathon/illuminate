"""Entity report — the UC-11 projection. One vendor's standardised profile:
identity, supply position, geography, control, people, risk indicators with
citations, artifacts. Signals that returned no data are shown as no-data, never
imputed to zero."""
from __future__ import annotations

import re
from datetime import date

from . import db, risk
from .risk import SEVERITY_WEIGHT   # noqa: F401 — the grading scale lives with the scorer now

HOME = risk.riskdata.HOME

# Families the scorer computes better than this module can, because it walks the whole
# graph rather than one entity's neighbourhood. When a scored breakdown is supplied they
# are dropped in its favour; the rest survive as context.
#
# 'concentration' is deliberately not on this list. Being a sole source is not a risk this
# entity carries — it is one its customers carry — so the scorer grades it on the consumer
# side as `dependency` and this module keeps describing it here as what it is for the
# supplier: a fact about the award, and a lead.
SUPERSEDED_BY_SCORER = ("ownership", "sanctions", "financial", "media")


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
        OPTIONAL MATCH (e)-[:PARENT_SEATED_IN]->(seat:Location)
        OPTIONAL MATCH (e)-[:MANUFACTURES_IN]->(mfg:Location)
        OPTIONAL MATCH (e)-[:OPERATES_IN]->(ops:Location)
        OPTIONAL MATCH (dp:Entity)-[o:OWNS]->(e)
        OPTIONAL MATCH (e)-[:PROVIDES]->(c:Category)
        RETURN e{.*} AS e,
               inc{.code,.name} AS incorporated,
               seat{.code,.name} AS parent_seat,
               collect(DISTINCT mfg{.code,.name}) AS manufactures,
               collect(DISTINCT ops{.code,.name}) AS operates,
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
    r["ultimate_parents"] = await ultimate_parents(entity_id)
    r["manufactures"] = [d for d in r["manufactures"] if d and d.get("code")]
    r["operates"] = [d for d in r["operates"] if d and d.get("code")]
    r["categories"] = [d for d in r["categories"] if d and d.get("id")]
    return r


async def supply_position(entity_id: str, root_id: str | None) -> dict:
    out: dict = {"supplies": [], "suppliers_count": 0, "tier_from_root": None, "sole_source_edges": 0}
    rows = await db.read(
        """
        MATCH (e:Entity {id:$id})-[s:SUPPLIES]->(c:Entity)
        RETURN c.id AS id, c.name AS name, s.tier AS tier, s.sole_source AS sole_source, s.psc AS psc, s.naics AS naics,
               s.contract_ref AS contract_ref, s.amount AS amount, s.source AS source, s.source_url AS source_url
        ORDER BY coalesce(s.amount, 0) DESC LIMIT 50
        """,
        {"id": entity_id},
    )
    out["supplies"] = rows
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
        WITH p, r, collect(DISTINCT {entity_id:o.id, entity:o.name, title:r2.title, current:r2.current, from:r2.from, to:r2.to, flagged: coalesce(o.flagged,false),
                                     kind: o.kind, federal: coalesce(o.federal,false), supplier: EXISTS { (o)-[:SUPPLIES]->() }}) AS elsewhere
        RETURN p.id AS person_id, p.name AS name, r.id AS edge_id, r.title AS title, r.role_type AS role_type, r.from AS from, r.to AS to,
               coalesce(r.current, r.to IS NULL) AS current, r.source AS source, r.source_url AS source_url, elsewhere,
               coalesce(p.public_official,false) AS public_official, p.person_types AS person_types
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
        suppliers = [x for x in r["elsewhere"] if x.get("supplier") and x.get("kind") != "agency"]
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
        MATCH (c:Claim)-[:ASSERTS]->(e:Entity {id:$id})
        WHERE c.predicate ENDS WITH '_screen' AND c.status = 'committed'
        OPTIONAL MATCH (a:Artifact)-[:EVIDENCES]->(c)
        RETURN c.predicate AS predicate, c.object_value AS result, c.source AS source, c.confidence AS confidence,
               c.retrieved_at AS retrieved_at, collect(a{.id,.title,.url})[0] AS artifact, c.detail AS detail
        ORDER BY c.retrieved_at DESC
        """,
        {"id": entity_id},
    )
    latest: dict[str, dict] = {}
    for r in rows:
        latest.setdefault(r["predicate"], r)
    return list(latest.values())


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


def _int(v) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _tie_label(t: dict) -> str:
    """'Membership: SHREC', 'Subsidiary: Raytheon Saudi Arabia'."""
    word = {"MEMBER_OF": "Membership", "TRANSACTS_WITH": "Business relationship", "LOBBIES": "Lobbying", "DONATED_TO": "Donation", "OWNS": "Subsidiary"}.get(t.get("type") or "", "Tie")
    return f"{word}: {t.get('entity')}"


async def risk_indicators(entity_id: str, core: dict, supply: dict, ppl: dict, scr: list[dict], aff: dict | None = None,
                          scored: dict | None = None) -> dict:
    """The Risk tab.

    `scored` is the node's breakdown from risk.py — the same score the canvas, the entity
    list and Cypher see, so a vendor never carries two different numbers. Without it (a
    direct call, or a unit test with no graph behind it) this module grades its own
    families and averages them, which is what it did before the scorer existed.
    """
    inds: list[dict] = []
    aff = aff or {"memberships": [], "transactions": [], "lobbying": [], "donations": [], "subsidiaries": [], "count": 0}
    e = core["e"]
    # 1. Ownership / foreign control
    seat = (core.get("parent_seat") or {}).get("code")
    ups = core.get("ultimate_parents") or []
    if seat:
        foreign = not seat.upper().startswith(HOME)
        detail = f"Ultimate parent seated in {seat}" + (f" — {ups[0]['name']}" if ups else "")
        # The whole chain, not just its endpoints: highlighting a derived parent is only
        # meaningful if the hops that lead to it light up with it.
        ownership_ids = list(dict.fromkeys(
            i for u in ups for i in (u.get("id"), *(u.get("relationship_ids") or ())) if i
        ))
        inds.append(_ind("ownership", "Foreign ultimate parent" if foreign else "Domestic ultimate parent", "high" if foreign else "clear",
                         e.get("ownership_source") or "GLEIF", detail, ids=ownership_ids))
    elif ups:
        inds.append(_ind("ownership", "Ultimate parent known, jurisdiction unresolved", "low", "GLEIF", ups[0]["name"], ids=[ups[0]["id"]]))
    elif core.get("direct_parents"):
        dp = core["direct_parents"][0]
        inds.append(_ind("ownership", "Parent recorded, jurisdiction unresolved", "low", e.get("ownership_source") or "LittleSis",
                         dp["name"] + (f" ({dp['pct']}%)" if dp.get("pct") else ""), ids=[dp["id"]]))
    else:
        inds.append(_ind("ownership", "Ownership chain", None, None, "No parent records resolved"))
    # 2. Sole-source position. Whose risk this is matters: being irreplaceable says nothing
    # about whether *this* company will fail, so it is described here and scored on the
    # customer, as risk.py's `dependency` dimension.
    if supply["supplies"]:
        ss = [s for s in supply["supplies"] if s.get("sole_source")]
        if ss:
            s0 = ss[0]
            customers = ", ".join(sorted({s["name"] for s in ss if s.get("name")})[:3])
            inds.append(_ind("concentration",
                             f"Sole source at tier {s0.get('tier') or '?'}" + (f" for PSC {s0['psc']}" if s0.get("psc") else ""),
                             "medium", s0.get("source") or "USAspending",
                             f"Irreplaceable for {customers or 'its customer'} — exposure carried by the customer, "
                             "not by this entity" + (f" · {s0['contract_ref']}" if s0.get("contract_ref") else ""),
                             s0.get("source_url")))
        else:
            inds.append(_ind("concentration", "No sole-source awards on record", "clear", "USAspending"))
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
        people_ids = [i for i in (who.get("person_id"), who.get("edge_id"), who.get("claim_id")) if i]
        if other:
            people_ids += [i for i in (other.get("entity_id"), other.get("role_edge_id"), other.get("claim_id")) if i]
        role = who["title"] or "officer"
        label = (f"Current {role} concurrently at flagged entity" if concurrent
                 else f"{'Former' if moved else 'Current'} {role} linked to flagged entity")
        inds.append(_ind("people", label + (f" ({other['entity']})" if other else ""),
                         "high" if concurrent else "medium",
                         who.get("source") or (other or {}).get("source") or "LittleSis", who["name"],
                         who.get("source_url") or (other or {}).get("source_url"), ids=people_ids))
    elif any(p.get("formerly_elsewhere") for p in ppl["current"]):
        p0 = next(p for p in ppl["current"] if p.get("formerly_elsewhere"))
        other = next((x for x in p0["elsewhere"] if not x["current"] and x.get("supplier")), None)
        inds.append(_ind("people", f"Former {(other['title'] if other['title'] and other['title'] != 'Position' else 'officer')} of {other['entity']} on current board" if other else "Former officer of another supplier on current board",
                         "medium", p0.get("source") or "LittleSis", f"{p0['name']} — {p0['title'] or 'role'} since {p0.get('from') or '?'}", p0.get("source_url"), ids=[p0["person_id"]]))
    elif interlocks:
        p0 = interlocks[0]
        other = next((x for x in p0["elsewhere"] if x["current"] and x.get("supplier")), None)
        inds.append(_ind("people", f"Board interlock — {p0['name']} also at {other['entity'] if other else 'another supplier'}", "low", p0.get("source") or "LittleSis",
                         "An interlock is a lead, not a finding", p0.get("source_url"), ids=[p0["person_id"]]))
    elif ppl["current"] or ppl["former"]:
        inds.append(_ind("people", "No interlocks or flagged movements among resolved people", "clear", "LittleSis · EDGAR"))
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
    # 4. Sanctions, debarment and restricted lists
    ran = [s for s in scr if s["predicate"] in risk.DESIGNATION_SCREENS]
    if ran:
        hit = any(s["result"] == "hit" for s in ran)
        src = " · ".join(sorted({s["source"] for s in ran if s.get("source")}))
        det = "; ".join(s["detail"] for s in ran if s.get("detail"))
        inds.append(_ind("sanctions", "Sanctions, debarment and restricted-list screens" + (" — HIT" if hit else ""),
                         "high" if hit else "clear", src, det or None))
    else:
        inds.append(_ind("sanctions", "Sanctions, debarment and restricted-list screens", None, None, "Not yet screened"))
    # 5. Financial health — only meaningful for listed entities with filings
    fin = next((s for s in scr if s["predicate"] == "financial_screen"), None)
    if fin:
        inds.append(_ind("financial", "Financial health", fin["result"] if fin["result"] in SEVERITY_WEIGHT else "low", fin["source"], fin.get("detail")))
    elif e.get("public") and e.get("ticker"):
        inds.append(_ind("financial", "Financial health — listed, filings available", "clear", "EDGAR", f"Ticker {e['ticker']}"))
    else:
        inds.append(_ind("financial", "Financial health — private entity, no filings", None, None))
    # 6. Adverse media
    adv = next((s for s in scr if s["predicate"] == "adverse_media_screen"), None)
    if adv:
        inds.append(_ind("media", "Adverse media", adv["result"] if adv["result"] in SEVERITY_WEIGHT else "low", adv["source"], adv.get("detail")))
    else:
        inds.append(_ind("media", "Adverse media — below coverage threshold", None, None))

    disclaimer = ("Every indicator marks opacity, concentration or foreign control — conditions warranting "
                  "human review. This tool flags; it does not accuse.")
    if scored and scored.get("components"):
        # The scored dimensions lead; what is left of this module's own families rides
        # along as context. Interlocks, revolving-door seats and lobbying are leads by
        # this report's own account, so they explain a score rather than move it.
        context = [{**i, "scored": False} for i in inds if i["family"] not in SUPERSEDED_BY_SCORER]
        dimensions = [{**c, "scored": True} for c in scored["components"]]
        return {
            "indicators": dimensions + context,
            "composite": scored.get("score"),
            "band": scored.get("band"),
            "top_factor": scored.get("top_factor"),
            "confidence": scored.get("confidence"),
            "families_requested": scored.get("dimensions_requested") or len(dimensions),
            "families_with_data": scored.get("dimensions_scored") or 0,
            "context_indicators": len(context),
            "weights": scored.get("weights") or {k: v[0] for k, v in risk.DIMENSIONS.items()},
            "scored_at": scored.get("scored_at"),
            "note": (scored.get("note") or "") + (
                f" A further {len(context)} signal famil{'ies' if len(context) != 1 else 'y'} — interlocks, government "
                "ties, affiliations and political exposure — are shown as context and do not move the score; this "
                "report calls them leads, not findings." if context else ""),
            "reference": scored.get("reference"),
            "disclaimer": disclaimer,
        }
    with_data = [i for i in inds if not i["no_data"]]
    total = sum(SEVERITY_WEIGHT[i["severity"]] for i in with_data)
    maxv = 3.0 * len(with_data) if with_data else 0
    composite = round(100 * total / maxv) if maxv else None
    return {
        "indicators": inds,
        "composite": composite,
        "families_requested": len(inds),
        "families_with_data": len(with_data),
        "note": (
            f"Composite is computed on available indicators only. {len(inds) - len(with_data)} of {len(inds)} requested signal families returned no data; the score reflects {len(with_data)}."
            if with_data else "No signal families returned data; no composite is computed."
        ),
        "disclaimer": disclaimer,
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
    # The stored breakdown, or a fresh one when this entity has never been through a pass.
    scored = await risk.explain(entity_id)
    risk_block = await risk_indicators(entity_id, core, supply, ppl, scr, aff, scored=scored)
    e = core["e"]
    sources = sorted({s for s in [e.get("source")] + [a.get("source") for a in arts] + [p.get("source") for p in ppl["current"] + ppl["former"]] if s})
    return {
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
        "screens": scr,
        "risk": risk_block,
        "artifacts": arts,
        "news": nws,
        "summary": {"text": e.get("summary"), "generated_at": e.get("summary_at"), "model": e.get("summary_model"), "source_count": len(arts)},
        "sources": sources,
        "generated_at": date.today().isoformat(),
    }
