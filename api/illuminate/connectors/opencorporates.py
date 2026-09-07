"""OpenCorporates — registry and officer records across jurisdictions. Key-gated."""
from __future__ import annotations

from ..ids import location_id, normalize_person, person_id
from ..vault import vault
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import HttpError, fetch_json

BASE = "https://api.opencorporates.com/v0.4"


class OpenCorporatesConnector(Connector):
    name = "opencorporates"
    label = "OpenCorporates"
    description = "Registry and officer records"
    trust = "authoritative"
    key_name = "opencorporates"
    key_url = "https://opencorporates.com/api_accounts/new"
    key_note = "Free tier requires an approved account; requests without a key are heavily throttled."

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        key = vault().get(user, self.key_name)
        facts: list[Fact] = []
        if not key:
            return facts
        subj = NodeRef("Entity", entity["id"])
        try:
            res = await fetch_json("GET", f"{BASE}/companies/search", params={"q": entity["name"], "api_token": key, "order": "score"}, ttl=86400)
        except HttpError as e:
            raise RuntimeError(f"OpenCorporates: {e}")
        comps = (res.get("results") or {}).get("companies") or []
        if not comps:
            return facts
        c = comps[0]["company"]
        url = c.get("opencorporates_url")
        art = ArtifactRef(url=url, title=f"OpenCorporates: {c.get('name')}", kind="registry", source="OpenCorporates")
        facts.append(Fact(subj, "attr:opencorporates_id", value=f"{c.get('jurisdiction_code')}/{c.get('company_number')}", artifact=art, confidence=0.8, method="fuzzy_match"))
        jur = (c.get("jurisdiction_code") or "").upper().replace("_", "-")
        if jur:
            facts.append(Fact(subj, "INCORPORATED_IN", object=NodeRef("Location", location_id(jur), {"code": jur, "name": jur, "kind": "region" if "-" in jur else "country"}), artifact=art, confidence=0.8))
        if c.get("incorporation_date"):
            facts.append(Fact(subj, "attr:incorporation_date", value=c["incorporation_date"], artifact=art, confidence=0.8))
        for o in (c.get("officers") or [])[:30]:
            off = o.get("officer") or {}
            if not off.get("name"):
                continue
            pref = NodeRef("Person", person_id(off["name"], f"oc:{off.get('id')}"), {"name": off["name"], "name_norm": normalize_person(off["name"]), "source": "OpenCorporates", "source_ref": f"oc:{off.get('id')}"})
            pos = (off.get("position") or "officer").lower()
            role_type = "board" if "director" in pos else "executive"
            facts.append(Fact(pref, "HELD_ROLE", object=subj, props={"title": off.get("position") or "Officer", "role_type": role_type, "from": off.get("start_date"), "to": off.get("end_date"), "current": off.get("end_date") is None},
                              artifact=art, confidence=0.8, merge_keys=["from", "title"]))
        return facts
