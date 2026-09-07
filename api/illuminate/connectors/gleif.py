"""GLEIF — LEI records and level-2 parent relationships. Open, no key. Authoritative
for legal identity, jurisdiction and ownership chains."""
from __future__ import annotations

from rapidfuzz import fuzz

from ..ids import entity_id, location_id, name_match_score, normalize_name
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import HttpError, fetch_json

BASE = "https://api.gleif.org/api/v1"


def record_url(lei: str) -> str:
    return f"https://search.gleif.org/#/record/{lei}"


async def lookup_lei_by_name(name: str) -> dict | None:
    """Fuzzy completion, then accept only a strong normalised-name match."""
    try:
        res = await fetch_json("GET", f"{BASE}/fuzzycompletions", params={"field": "entity.legalName", "q": name[:100]})
    except HttpError:
        return None
    norm = normalize_name(name)
    best, best_s = None, 0
    for d in res.get("data", []):
        val = d.get("attributes", {}).get("value") or ""
        s = name_match_score(name, val)
        if s > best_s:
            best, best_s = d, s
    if best and best_s >= 90:
        lei = best.get("relationships", {}).get("lei-records", {}).get("data", {}).get("id")
        if lei:
            return {"lei": lei, "name": best["attributes"]["value"], "score": best_s}
    return None


async def lei_record(lei: str) -> dict | None:
    try:
        return (await fetch_json("GET", f"{BASE}/lei-records/{lei}")).get("data")
    except HttpError:
        return None


async def parent(lei: str, which: str) -> dict | None:
    """which ∈ {direct-parent, ultimate-parent}. 404 means no reported parent."""
    try:
        return (await fetch_json("GET", f"{BASE}/lei-records/{lei}/{which}")).get("data")
    except HttpError:
        return None


def _entity_ref_from_record(rec: dict) -> NodeRef:
    lei = rec["id"]
    ent = rec["attributes"]["entity"]
    name = ent["legalName"]["name"]
    country = (ent.get("legalAddress") or {}).get("country")
    return NodeRef("Entity", entity_id(lei=lei), {"name": name, "name_norm": normalize_name(name), "lei": lei, "kind": "organization",
                                                   "source": "GLEIF", "source_url": record_url(lei), "country": country})


class GLEIFConnector(Connector):
    name = "gleif"
    label = "GLEIF"
    description = "LEI level-2 parent records, legal jurisdiction"
    trust = "authoritative"

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        facts: list[Fact] = []
        subj = NodeRef("Entity", entity["id"])
        lei = entity.get("lei")
        conf = 1.0
        if not lei:
            hit = await lookup_lei_by_name(entity.get("legal_name") or entity["name"])
            if not hit:
                return facts
            lei = hit["lei"]
            conf = 0.85 if hit["score"] < 97 else 0.95
        rec = await lei_record(lei)
        if not rec:
            return facts
        art = ArtifactRef(url=record_url(lei), title=f"GLEIF LEI record {lei}", kind="registry", source="GLEIF")
        ent = rec["attributes"]["entity"]
        if not entity.get("lei"):
            facts.append(Fact(subj, "attr:lei", value=lei, artifact=art, confidence=conf, method="fuzzy_match" if conf < 1 else "connector",
                              detail=f"matched legal name {ent['legalName']['name']}"))
        facts.append(Fact(subj, "attr:legal_name", value=ent["legalName"]["name"], artifact=art, confidence=conf))
        country = (ent.get("legalAddress") or {}).get("country")
        region = (ent.get("legalAddress") or {}).get("region")
        if country:
            code = region if region and region.startswith(country + "-") and country == "US" else country
            facts.append(Fact(subj, "INCORPORATED_IN", object=NodeRef("Location", location_id(code), {"code": code, "name": code, "kind": "region" if "-" in code else "country"}),
                              artifact=art, confidence=conf, detail="GLEIF legal address"))
        status = (rec["attributes"].get("registration") or {}).get("status")
        if status:
            facts.append(Fact(subj, "attr:entity_status", value=ent.get("status") or status, artifact=art, confidence=conf))
        dp = await parent(lei, "direct-parent")
        up = await parent(lei, "ultimate-parent")
        if dp:
            pref = _entity_ref_from_record(dp)
            facts.append(Fact(pref, "OWNS", object=subj, artifact=ArtifactRef(url=record_url(dp["id"]), title=f"GLEIF direct parent {dp['id']}", kind="registry", source="GLEIF"),
                              confidence=conf, detail="GLEIF level-2 direct parent"))
            if pref.props.get("country"):
                c = pref.props["country"]
                facts.append(Fact(pref, "INCORPORATED_IN", object=NodeRef("Location", location_id(c), {"code": c, "name": c, "kind": "country"}), artifact=art, confidence=conf))
        if up:
            uref = _entity_ref_from_record(up)
            facts.append(Fact(uref, "ULTIMATE_PARENT_OF", object=subj, artifact=ArtifactRef(url=record_url(up["id"]), title=f"GLEIF ultimate parent {up['id']}", kind="registry", source="GLEIF"),
                              confidence=conf, detail="GLEIF level-2 ultimate parent"))
            c = uref.props.get("country")
            if c:
                loc = NodeRef("Location", location_id(c), {"code": c, "name": c, "kind": "country"})
                facts.append(Fact(uref, "INCORPORATED_IN", object=loc, artifact=art, confidence=conf))
                facts.append(Fact(subj, "PARENT_SEATED_IN", object=loc, artifact=art, confidence=conf, detail=f"ultimate parent {uref.props['name']} seated in {c}"))
        elif country and not dp:
            # No reported parent: the entity is its own ultimate parent; seat = its own jurisdiction.
            facts.append(Fact(subj, "PARENT_SEATED_IN", object=NodeRef("Location", location_id(country), {"code": country, "name": country, "kind": "country"}),
                              artifact=art, confidence=conf * 0.9, detail="no parent reported to GLEIF; seat is own jurisdiction"))
        return facts
