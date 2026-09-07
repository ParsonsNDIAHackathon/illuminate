"""LittleSis — officers, directors and interlocks. Open API, no key (CC BY-SA).
Open-source trust: HELD_ROLE facts stage unless corroborated, but LittleSis is
the people layer for the demo so the seed commits them explicitly."""
from __future__ import annotations

from rapidfuzz import fuzz

from ..ids import name_match_score, normalize_name, normalize_person, person_id
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import HttpError, fetch_json

BASE = "https://littlesis.org/api"


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


async def find_org(name: str) -> dict | None:
    try:
        res = await fetch_json("GET", f"{BASE}/entities/search", params={"q": name[:80]})
    except HttpError:
        return None
    norm = normalize_name(name)
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


async def positions(org_id: int, pages: int = 3) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        try:
            res = await fetch_json("GET", f"{BASE}/entities/{org_id}/relationships", params={"category_id": 1, "page": page})
        except HttpError:
            break
        out.extend(res.get("data", []))
        if page >= (res.get("meta", {}).get("pageCount") or 1):
            break
    return out


async def person(pid: int) -> dict | None:
    try:
        return (await fetch_json("GET", f"{BASE}/entities/{pid}")).get("data", {}).get("attributes")
    except HttpError:
        return None


class LittleSisConnector(Connector):
    name = "littlesis"
    label = "LittleSis"
    description = "Officers, directors, interlocks"
    trust = "open"

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        facts: list[Fact] = []
        org = await find_org(entity.get("legal_name") or entity["name"])
        if not org:
            return facts
        subj = NodeRef("Entity", entity["id"])
        org_url = f"https://littlesis.org/org/{org['id']}"
        art = ArtifactRef(url=org_url, title=f"LittleSis: {org['name']}", kind="record", source="LittleSis")
        facts.append(Fact(subj, "attr:littlesis_id", value=str(org["id"]), artifact=art, confidence=0.9, method="fuzzy_match"))
        pc = (org.get("extensions") or {}).get("PublicCompany") or {}
        if pc.get("ticker"):
            facts.append(Fact(subj, "attr:ticker", value=pc["ticker"], artifact=art, confidence=0.9))
            facts.append(Fact(subj, "attr:public", value="true", artifact=art, confidence=0.9))
        if pc.get("sec_cik"):
            facts.append(Fact(subj, "attr:cik", value=str(pc["sec_cik"]), artifact=art, confidence=0.9))
        rels = await positions(org["id"])
        seen = 0
        for r in rels:
            a = r.get("attributes", {})
            pid = a.get("entity1_id")
            if not pid or a.get("entity2_id") != org["id"]:
                continue
            ca = a.get("category_attributes") or {}
            is_board, is_exec = bool(ca.get("is_board")), bool(ca.get("is_executive"))
            if not (is_board or is_exec):
                continue
            pdata = await person(pid)
            if not pdata:
                continue
            seen += 1
            pname = pdata.get("name")
            pref = NodeRef("Person", person_id(pname, f"littlesis:{pid}"), {"name": pname, "name_norm": normalize_person(pname), "source": "LittleSis",
                                                                           "source_ref": f"littlesis:{pid}", "source_url": f"https://littlesis.org/person/{pid}", "blurb": pdata.get("blurb")})
            title = a.get("description1") or ("Director" if is_board else "Executive")
            frm, to = _date(a.get("start_date")), _date(a.get("end_date"))
            current = a.get("is_current") if a.get("is_current") is not None else to is None
            role_type = "both" if (is_board and is_exec) else ("board" if is_board else "executive")
            rel_art = ArtifactRef(url=f"https://littlesis.org/relationships/{a['id']}", title=a.get("description") or f"{pname} — {title}", kind="record", source="LittleSis")
            facts.append(Fact(pref, "HELD_ROLE", object=subj, props={"title": title, "role_type": role_type, "from": frm, "to": to, "current": bool(current)},
                              artifact=rel_art, confidence=0.85, detail=a.get("description"), merge_keys=["from", "title"]))
            if seen >= 40:
                break
        return facts
