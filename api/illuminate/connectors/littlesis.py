"""LittleSis — the people-and-power layer. Open API, no key (CC BY-SA 4.0).

What it contributes, per supplier:

* the org record: revenue, lobbying registrant id, USAspending recipient id, aliases,
  blurb, LittleSis types and tags (all as `attr:` facts on the entity);
* officers and directors as Person nodes with one tenured HELD_ROLE edge per term,
  plus a board_size count from the position rows we do not turn into people;
* each officer's *other* seats — government bodies, other companies, law and lobbying
  firms — as HELD_ROLE edges to entities that need not be suppliers, which is what
  makes revolving-door and cross-board findings possible;
* the org's own affiliations: OWNS (ownership and hierarchy rows), MEMBER_OF,
  TRANSACTS_WITH, LOBBIES and DONATED_TO.

LittleSis is crowd-sourced: dates are often partial, amounts are usually missing and the
same firm can exist twice. Every fact stays an open-source lead (trust "open") that stages
unless corroborated; the seed commits the demo program's explicitly.
"""
from __future__ import annotations

import asyncio
import re

from ..ids import entity_id, name_match_score, normalize_name, normalize_person, person_id
from .base import ArtifactRef, Connector, Fact, NodeRef, now_iso
from .http import HttpError, fetch_json

BASE = "https://littlesis.org/api"

# LittleSis relationship categories (category_id).
POSITION, EDUCATION, MEMBERSHIP, FAMILY, DONATION, TRANSACTION, LOBBYING, SOCIAL, PROFESSIONAL, OWNERSHIP, HIERARCHY, GENERIC = range(1, 13)

# An officer's other seats worth an entity of their own. Schools, philanthropies and
# membership clubs are left out: they say little about control or influence over a supplier.
FOLLOW_TYPES = {"Government Body", "Business", "Public Company", "Private Company", "Lobbying Firm", "Law Firm",
                "Political Fundraising", "Industry/Trade Association", "Government Advisory Body"}
# Person types that mark a public-office holder or registered influencer.
PUBLIC_OFFICE_TYPES = {"Public Official", "Elected Representative", "Political Candidate", "Lobbyist"}

# Caps keep a Boeing-sized record from flooding the graph and the API from throttling us.
LIMITS = {"position_pages": 4, "people": 30, "follow_per_person": 12, "membership": 12, "donation": 10,
          "transaction": 15, "lobbying": 15, "ownership": 15, "hierarchy": 15}

_URL_RE = re.compile(r"^https?://")


def _date(s: str | None) -> str | None:
    if not s:
        return None
    parts = s.split("-")
    y = parts[0]
    if not y or y == "0000":
        return None
    m = parts[1] if len(parts) > 1 and parts[1] != "00" else "01"
    d = parts[2] if len(parts) > 2 and parts[2] != "00" else "01"
    return f"{y}-{m}-{d}"


async def _get(path: str, params: dict | None = None) -> dict | None:
    """GET with a short retry on throttling (LittleSis answers 503/429 under load).
    Offline fixture misses (status 0) are not retried."""
    for attempt in range(3):
        try:
            return await fetch_json("GET", f"{BASE}{path}", params=params)
        except HttpError as e:
            if e.status in (429, 503) and attempt < 2:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue
            return None
    return None


async def find_org(name: str) -> dict | None:
    res = await _get("/entities/search", {"q": name[:80]})
    if not res:
        return None
    best, best_s = None, 0
    for d in res.get("data", []):
        a = d.get("attributes", {})
        if a.get("primary_ext") != "Org":
            continue
        cands = [a.get("name", "")] + list(a.get("aliases") or [])
        s = max((name_match_score(name, c) for c in cands if c), default=0)
        if s > best_s:
            best, best_s = a, s
    return best if best and best_s >= 90 else None


async def relationships(eid: int, category: int, pages: int = 1) -> list[dict]:
    """Relationship rows (attributes) for one entity in one category, newest first."""
    out: list[dict] = []
    for page in range(1, pages + 1):
        res = await _get(f"/entities/{eid}/relationships", {"category_id": category, "page": page})
        if not res:
            break
        out.extend(d.get("attributes", {}) for d in res.get("data", []))
        if page >= (res.get("meta", {}).get("pageCount") or 1):
            break
    return out


async def connections(eid: int, category: int) -> dict[int, dict]:
    """The entities on the other end of one category's relationships, keyed by
    LittleSis id. One call gives name, types and extensions for every counterparty,
    which spares a record fetch per row."""
    res = await _get(f"/entities/{eid}/connections", {"category_id": category})
    if not res:
        return {}
    return {d["id"]: d.get("attributes", {}) for d in res.get("data", []) if d.get("id")}


async def entity(eid: int) -> dict | None:
    res = await _get(f"/entities/{eid}")
    return (res or {}).get("data", {}).get("attributes")


def positions(org_id: int, pages: int = 3):
    """Kept for callers that want raw position rows."""
    return relationships(org_id, POSITION, pages)


def org_url(oid: int) -> str:
    return f"https://littlesis.org/org/{oid}"


def person_url(pid: int) -> str:
    return f"https://littlesis.org/person/{pid}"


def rel_url(rid: int) -> str:
    return f"https://littlesis.org/relationships/{rid}"


def _org_ref(a: dict) -> NodeRef:
    """An Entity proposal for a LittleSis org that may not be in the graph yet. The claims
    layer resolves it against known entities by name before merging."""
    types = list(a.get("types") or [])
    gov = (a.get("extensions") or {}).get("GovernmentBody") or {}
    kind = "agency" if "Government Body" in types else "organization"
    props = {"name": a.get("name"), "name_norm": normalize_name(a.get("name") or ""), "kind": kind, "org_types": types,
             "littlesis_id": str(a["id"]), "source": "LittleSis", "source_url": org_url(a["id"]), "retrieved_at": now_iso(),
             "method": "connector", "confidence": 0.8, "blurb": a.get("blurb")}
    if gov:
        props["federal"] = bool(gov.get("is_federal"))
    return NodeRef("Entity", entity_id(name=a.get("name")), props)


def _person_ref(a: dict) -> NodeRef:
    pname = a.get("name")
    types = list(a.get("types") or [])
    return NodeRef("Person", person_id(pname, f"littlesis:{a['id']}"),
                   {"name": pname, "name_norm": normalize_person(pname), "source": "LittleSis", "source_ref": f"littlesis:{a['id']}",
                    "source_url": person_url(a["id"]), "blurb": a.get("blurb"), "person_types": types,
                    "public_official": bool(set(types) & PUBLIC_OFFICE_TYPES)})


def _role(r: dict, fallback: str = "Position") -> tuple[str, str, str | None, str | None, bool]:
    ca = r.get("category_attributes") or {}
    is_board, is_exec = bool(ca.get("is_board")), bool(ca.get("is_executive"))
    role_type = "both" if (is_board and is_exec) else ("board" if is_board else "executive" if is_exec else "position")
    title = r.get("description1") or ("Director" if is_board else "Executive" if is_exec else fallback)
    frm, to = _date(r.get("start_date")), _date(r.get("end_date"))
    current = r.get("is_current") if r.get("is_current") is not None else to is None
    return title, role_type, frm, to, bool(current)


def org_attr_facts(subj: NodeRef, org: dict, art: ArtifactRef) -> list[Fact]:
    """Everything the org record itself says, as attribute facts."""
    f: list[Fact] = [Fact(subj, "attr:littlesis_id", value=str(org["id"]), artifact=art, confidence=0.9, method="fuzzy_match")]
    ext = org.get("extensions") or {}
    pc = ext.get("PublicCompany") or {}
    o = ext.get("Org") or {}
    if pc.get("ticker"):
        f.append(Fact(subj, "attr:ticker", value=pc["ticker"], artifact=art, confidence=0.9))
        f.append(Fact(subj, "attr:public", value="true", artifact=art, confidence=0.9))
    if pc.get("sec_cik"):
        f.append(Fact(subj, "attr:cik", value=str(pc["sec_cik"]), artifact=art, confidence=0.9))
    if o.get("revenue"):
        f.append(Fact(subj, "attr:revenue", value=str(int(o["revenue"])), artifact=art, confidence=0.7, detail="LittleSis Org.revenue; year not recorded"))
    if o.get("employees"):
        f.append(Fact(subj, "attr:employees", value=str(int(o["employees"])), artifact=art, confidence=0.7))
    if o.get("lda_registrant_id"):
        f.append(Fact(subj, "attr:lda_registrant_id", value=str(o["lda_registrant_id"]), artifact=art, confidence=0.9, detail="Senate LDA registrant id"))
    if o.get("fedspending_id"):
        f.append(Fact(subj, "attr:fedspending_id", value=str(o["fedspending_id"]), artifact=art, confidence=0.85, detail="legacy USAspending recipient id"))
    if org.get("website") and _URL_RE.match(org["website"]):
        f.append(Fact(subj, "attr:website", value=org["website"], artifact=art, confidence=0.8))
    aliases = [x for x in (org.get("aliases") or []) if x]
    if aliases:
        f.append(Fact(subj, "attr:aliases_text", value=" | ".join(dict.fromkeys(aliases)), artifact=art, confidence=0.85))
    if org.get("blurb"):
        f.append(Fact(subj, "attr:blurb", value=org["blurb"][:500], artifact=art, confidence=0.7))
    if org.get("types"):
        f.append(Fact(subj, "attr:org_types", value=" | ".join(org["types"]), artifact=art, confidence=0.8))
    if org.get("tags"):
        f.append(Fact(subj, "attr:littlesis_tags", value=" | ".join(org["tags"]), artifact=art, confidence=0.8))
    return f


async def people_facts(subj: NodeRef, org: dict) -> tuple[list[Fact], int | None]:
    """Board and executive positions at the org, and each such person's other seats.
    Returns the facts and the current board size counted over *all* position rows."""
    facts: list[Fact] = []
    rows = await relationships(org["id"], POSITION, LIMITS["position_pages"])
    board = 0
    officers: list[tuple[int, dict]] = []
    for r in rows:
        pid = r.get("entity1_id")
        if not pid or r.get("entity2_id") != org["id"]:
            continue
        ca = r.get("category_attributes") or {}
        _, _, _, to, current = _role(r)
        if ca.get("is_board") and current and to is None:
            board += 1
        if ca.get("is_board") or ca.get("is_executive"):
            officers.append((pid, r))
    seen = 0
    for pid, r in officers:
        pdata = await entity(pid)
        if not pdata:
            continue
        seen += 1
        pref = _person_ref(pdata)
        pname = pdata.get("name")
        title, role_type, frm, to, current = _role(r)
        ca = r.get("category_attributes") or {}
        rel_art = ArtifactRef(url=rel_url(r["id"]), title=r.get("description") or f"{pname} — {title}", kind="record", source="LittleSis")
        facts.append(Fact(pref, "HELD_ROLE", object=subj,
                          props={"title": title, "role_type": role_type, "from": frm, "to": to, "current": current, "compensation": ca.get("compensation")},
                          artifact=rel_art, confidence=0.85, detail=r.get("description"), merge_keys=["from", "title"]))
        if pref.props.get("public_official"):
            facts.append(Fact(pref, "attr:public_official", value="true", artifact=ArtifactRef(url=person_url(pid), title=f"LittleSis: {pname}", kind="record", source="LittleSis"),
                              confidence=0.8, detail=" | ".join(pref.props.get("person_types") or [])))
        facts.extend(await other_seats(pref, pid, org["id"]))
        if seen >= LIMITS["people"]:
            break
    return facts, (board or None)


async def other_seats(pref: NodeRef, pid: int, org_id: int) -> list[Fact]:
    """A person's positions at orgs other than the supplier: agencies, other companies,
    law and lobbying firms. Two calls: the relationship rows carry tenure, the
    connections carry the org records."""
    rows = await relationships(pid, POSITION, 2)
    others = [r for r in rows if r.get("entity1_id") == pid and r.get("entity2_id") not in (org_id, None)]
    if not others:
        return []
    orgs = await connections(pid, POSITION)
    out: list[Fact] = []
    for r in others:
        a = orgs.get(r["entity2_id"])
        if not a or a.get("primary_ext") != "Org":
            continue
        types = set(a.get("types") or [])
        if not (types & FOLLOW_TYPES):
            continue
        oref = _org_ref(a)
        title, role_type, frm, to, current = _role(r)
        rel_art = ArtifactRef(url=rel_url(r["id"]), title=r.get("description") or f"{pref.props.get('name')} — {title}", kind="record", source="LittleSis")
        out.append(Fact(pref, "HELD_ROLE", object=oref, props={"title": title, "role_type": role_type, "from": frm, "to": to, "current": current},
                        artifact=rel_art, confidence=0.8, detail=r.get("description"), merge_keys=["from", "title"]))
        if len(out) >= LIMITS["follow_per_person"]:
            break
    return out


# category -> (relationship type, direction, limit key, merge keys)
# direction "12": entity1 -> entity2 as LittleSis records it; "21": reversed (a hierarchy row
# lists the subordinate first, and OWNS points parent -> child).
_AFFILIATIONS = {
    MEMBERSHIP: ("MEMBER_OF", "12", "membership", []),
    DONATION: ("DONATED_TO", "12", "donation", ["from"]),
    TRANSACTION: ("TRANSACTS_WITH", "12", "transaction", ["from"]),
    LOBBYING: ("LOBBIES", "12", "lobbying", ["from"]),
    OWNERSHIP: ("OWNS", "12", "ownership", []),
    HIERARCHY: ("OWNS", "21", "hierarchy", []),
}


async def affiliation_facts(subj: NodeRef, org: dict) -> list[Fact]:
    """The org's own ties: ownership and hierarchy, memberships, transactions, lobbying
    and donations. Counterparties become Entity proposals; people on the far side are
    kept only as beneficial owners with a recorded stake."""
    facts: list[Fact] = []
    oid = org["id"]
    for cat, (rel, direction, limit_key, merge_keys) in _AFFILIATIONS.items():
        rows = await relationships(oid, cat, 1)
        if not rows:
            continue
        others = await connections(oid, cat)
        n = 0
        for r in rows:
            e1, e2 = r.get("entity1_id"), r.get("entity2_id")
            other_id = e2 if e1 == oid else e1 if e2 == oid else None
            if other_id is None:
                continue
            a = others.get(other_id)
            if not a:
                continue
            ca = r.get("category_attributes") or {}
            frm, to = _date(r.get("start_date")), _date(r.get("end_date"))
            current = r.get("is_current") if r.get("is_current") is not None else to is None
            props: dict = {"from": frm, "to": to, "current": bool(current), "category": limit_key, "description": (r.get("description") or "")[:200] or None}
            if r.get("amount"):
                props["amount"] = r["amount"]
                props["currency"] = r.get("currency")
            art = ArtifactRef(url=rel_url(r["id"]), title=(r.get("description") or f"LittleSis relationship {r['id']}")[:200], kind="record", source="LittleSis")
            if a.get("primary_ext") == "Person":
                # A person on the far side only matters as an owner with a stake on record.
                if cat == OWNERSHIP and ca.get("percent_stake") and e2 == oid:
                    pref = _person_ref(a)
                    facts.append(Fact(pref, "BENEFICIAL_OWNER_OF", object=subj, props={"pct": ca["percent_stake"], "from": frm, "to": to},
                                      artifact=art, confidence=0.75, detail=r.get("description")))
                continue
            oref = _org_ref(a)
            if cat == OWNERSHIP and ca.get("percent_stake"):
                props["pct"] = ca["percent_stake"]
            if cat == OWNERSHIP and ca.get("shares"):
                props["shares"] = ca["shares"]
            if cat == HIERARCHY:
                props["via"] = "hierarchy"
            if cat == TRANSACTION and ca.get("is_lobbying"):
                props["is_lobbying"] = True
            # Who is on the left of the edge for this row.
            left_is_org = (e1 == oid) if direction == "12" else (e2 == oid)
            s, o = (subj, oref) if left_is_org else (oref, subj)
            if rel == "OWNS":
                conf = 0.8 if cat == OWNERSHIP else 0.7
            else:
                conf = 0.8
            facts.append(Fact(s, rel, object=o, props=props, artifact=art, confidence=conf, detail=r.get("description"), merge_keys=merge_keys))
            n += 1
            if n >= LIMITS[limit_key]:
                break
    return facts


class LittleSisConnector(Connector):
    name = "littlesis"
    label = "LittleSis"
    description = "Officers, directors, other seats, ownership, memberships, lobbying, transactions"
    trust = "open"

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        org = await find_org(entity.get("legal_name") or entity["name"])
        if not org:
            return []
        subj = NodeRef("Entity", entity["id"])
        art = ArtifactRef(url=org_url(org["id"]), title=f"LittleSis: {org['name']}", kind="record", source="LittleSis")
        facts = org_attr_facts(subj, org, art)
        ppl, board = await people_facts(subj, org)
        facts.extend(ppl)
        if board:
            facts.append(Fact(subj, "attr:board_size", value=str(board), artifact=art, confidence=0.7, detail="current directors counted over LittleSis position rows"))
        facts.extend(await affiliation_facts(subj, org))
        return facts
