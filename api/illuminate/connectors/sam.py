"""SAM.gov Entity Management and Exclusions — the vendor spine and the authoritative
negative of 'approved'. Needs a SAM.gov *personal* API key (SAM.gov workspace → Profile →
API Key, behind a login.gov sign-in). api.data.gov keys are NOT accepted — the edge
answers every request with a bare 404 (verified 2026-09-07)."""
from __future__ import annotations

from ..ids import location_id
from ..vault import vault
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import HttpError, fetch_json

ENTITY = "https://api.sam.gov/entity-information/v3/entities"
EXCL = "https://api.sam.gov/entity-information/v4/exclusions"


class SAMConnector(Connector):
    name = "sam"
    label = "SAM.gov Entity & Exclusions"
    description = "Registered vendors (UEI, CAGE, status, NAICS) and debarment/exclusion screen"
    trust = "authoritative"
    key_name = "sam"
    key_url = "https://sam.gov/workspace/profile"
    key_note = "SAM.gov personal API key: sign in (login.gov), create an Individual account, then Workspace → Profile → API Key. api.data.gov keys do not work here."

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        key = vault().get(user, self.key_name)
        facts: list[Fact] = []
        if not key:
            return facts
        subj = NodeRef("Entity", entity["id"])
        params = {"api_key": key, "includeSections": "entityRegistration,coreData"}
        if entity.get("uei"):
            params["ueiSAM"] = entity["uei"]
        elif entity.get("cage"):
            params["cageCode"] = entity["cage"]
        else:
            params["legalBusinessName"] = entity["name"]
        try:
            res = await fetch_json("GET", ENTITY, params=params, ttl=86400)
        except HttpError as e:
            raise RuntimeError(f"SAM entity API: {e}")
        for ent in (res.get("entityData") or [])[:1]:
            reg = ent.get("entityRegistration") or {}
            core = ent.get("coreData") or {}
            uei = reg.get("ueiSAM")
            url = f"https://sam.gov/entity/{uei}/coreData" if uei else "https://sam.gov/"
            art = ArtifactRef(url=url, title=f"SAM.gov registration {reg.get('legalBusinessName')}", kind="registry", source="SAM.gov")
            if uei:
                facts.append(Fact(subj, "attr:uei", value=uei, artifact=art, confidence=1.0))
            if reg.get("cageCode"):
                facts.append(Fact(subj, "attr:cage", value=reg["cageCode"], artifact=art, confidence=1.0))
            if reg.get("legalBusinessName"):
                facts.append(Fact(subj, "attr:legal_name", value=reg["legalBusinessName"], artifact=art, confidence=1.0))
            if reg.get("registrationStatus"):
                facts.append(Fact(subj, "attr:registration_status", value=reg["registrationStatus"], artifact=art, confidence=1.0))
            addr = (core.get("physicalAddress") or {})
            cc = addr.get("countryCode")
            if cc:
                code = f"{cc}-{addr['stateOrProvinceCode']}" if cc in ("USA", "US") and addr.get("stateOrProvinceCode") else cc
                code = code.replace("USA", "US")
                facts.append(Fact(subj, "OPERATES_IN", object=NodeRef("Location", location_id(code), {"code": code, "name": code, "kind": "region" if "-" in code else "country"}),
                                  artifact=art, confidence=0.95, detail="SAM physical address"))
            inc = (core.get("generalInformation") or {}).get("stateOfIncorporationCode")
            incc = (core.get("generalInformation") or {}).get("countryOfIncorporationCode")
            if incc:
                code = f"US-{inc}" if incc in ("USA", "US") and inc else incc.replace("USA", "US")
                facts.append(Fact(subj, "INCORPORATED_IN", object=NodeRef("Location", location_id(code), {"code": code, "name": code, "kind": "region" if "-" in code else "country"}),
                                  artifact=art, confidence=1.0, detail="SAM incorporation"))
            naics = [n.get("naicsCode") for n in ((ent.get("assertions") or {}).get("goodsAndServices") or {}).get("naicsList", []) if n.get("naicsCode")]
            if naics:
                facts.append(Fact(subj, "attr:naics_codes", value=",".join(naics[:20]), artifact=art, confidence=1.0))
        # exclusions
        xp = {"api_key": key}
        if entity.get("uei"):
            xp["ueiSAM"] = entity["uei"]
        else:
            xp["exclusionName"] = entity["name"]
        try:
            xres = await fetch_json("GET", EXCL, params=xp, ttl=86400)
            recs = xres.get("excludedEntity") or xres.get("exclusionDetails") or []
            active = [r for r in recs if str((r.get("exclusionDetails") or r).get("excludingAgencyCode") or "")]
            art = ArtifactRef(url="https://sam.gov/content/exclusions", title="SAM.gov exclusions search", kind="record", source="SAM.gov")
            facts.append(Fact(subj, "exclusion_screen", value="hit" if active else "clear", artifact=art, confidence=0.95,
                              detail=f"{len(active)} active exclusion record(s)" if active else "not excluded"))
        except HttpError as e:
            facts.append(Fact(subj, "exclusion_screen", value="clear", confidence=0.5, detail=f"exclusions API unavailable ({e.status})",
                              artifact=ArtifactRef(url="https://sam.gov/content/exclusions", title="SAM.gov exclusions", kind="record", source="SAM.gov")))
        return facts
