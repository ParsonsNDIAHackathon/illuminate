"""SAM.gov Entity Management and Exclusions — the vendor spine and the authoritative
negative of 'approved'. Needs a SAM.gov *personal* API key (SAM.gov workspace → Profile →
API Key, behind a login.gov sign-in). api.data.gov keys are NOT accepted — the edge
answers every request with a bare 404 (verified 2026-09-07)."""
from __future__ import annotations

import time

from ..ids import location_id
from ..vault import vault
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import HttpError, fetch_json

ENTITY = "https://api.sam.gov/entity-information/v3/entities"
EXCL = "https://api.sam.gov/entity-information/v4/exclusions"
# Personal (non-federal) keys get ~10 requests/day; a 429 means the day's budget is spent.
_rate_limited_until: float = 0.0
COOLDOWN_S = 6 * 3600


class SAMRateLimited(RuntimeError):
    pass


def _check_budget() -> None:
    if time.time() < _rate_limited_until:
        raise SAMRateLimited(f"SAM.gov daily request budget exhausted (personal key ≈10/day); retry after {time.strftime('%H:%M UTC', time.gmtime(_rate_limited_until))}")


def _note_429() -> None:
    global _rate_limited_until
    _rate_limited_until = time.time() + COOLDOWN_S


class SAMConnector(Connector):
    name = "sam"
    label = "SAM.gov Entity Management"
    description = "Registered vendors: UEI, CAGE, status, incorporation, NAICS (≈10 lookups/day on a personal key)"
    trust = "authoritative"
    key_name = "sam"
    key_url = "https://sam.gov/workspace/profile"
    key_note = "SAM.gov personal API key: sign in (login.gov), create an Individual account, then Workspace → Profile → API Key. api.data.gov keys do not work here. Personal keys are limited to ~10 requests/day."

    async def status(self, user: str) -> dict:
        st = await super().status(user)
        if st.get("connected") and time.time() < _rate_limited_until:
            st["detail"] += f" · rate limited until {time.strftime('%H:%M UTC', time.gmtime(_rate_limited_until))}"
        return st

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        key = vault().get(user, self.key_name)
        facts: list[Fact] = []
        if not key:
            return facts
        _check_budget()
        subj = NodeRef("Entity", entity["id"])
        params = {"api_key": key, "includeSections": "entityRegistration,coreData,assertions"}
        if entity.get("uei"):
            params["ueiSAM"] = entity["uei"]
        elif entity.get("cage"):
            params["cageCode"] = entity["cage"]
        else:
            params["legalBusinessName"] = entity["name"]
        try:
            res = await fetch_json("GET", ENTITY, params=params, ttl=30 * 86400)
        except HttpError as e:
            if e.status == 429:
                _note_429()
                raise SAMRateLimited("SAM.gov returned 429 — daily request budget exhausted (personal key ≈10/day)")
            raise RuntimeError(f"SAM entity API: {e}")
        for ent in (res.get("entityData") or [])[:1]:
            reg = ent.get("entityRegistration") or {}
            core = ent.get("coreData") or {}
            gi = core.get("generalInformation") or {}
            uei = reg.get("ueiSAM")
            url = f"https://sam.gov/entity/{uei}/coreData" if uei else "https://sam.gov/"
            art = ArtifactRef(url=url, title=f"SAM.gov registration — {reg.get('legalBusinessName')}", kind="registry", source="SAM.gov",
                              props={"registration_status": reg.get("registrationStatus"), "expires": reg.get("registrationExpirationDate")})
            if uei:
                facts.append(Fact(subj, "attr:uei", value=uei, artifact=art, confidence=1.0))
            if reg.get("cageCode"):
                facts.append(Fact(subj, "attr:cage", value=reg["cageCode"], artifact=art, confidence=1.0))
            if reg.get("legalBusinessName"):
                facts.append(Fact(subj, "attr:legal_name", value=reg["legalBusinessName"], artifact=art, confidence=1.0))
            if reg.get("registrationStatus"):
                facts.append(Fact(subj, "attr:registration_status", value=reg["registrationStatus"], artifact=art, confidence=1.0))
            if reg.get("registrationExpirationDate"):
                facts.append(Fact(subj, "attr:registration_expires", value=reg["registrationExpirationDate"], artifact=art, confidence=1.0))
            facts.append(Fact(subj, "attr:sam_registered", value="true", artifact=art, confidence=1.0))
            if gi.get("organizationStructureDesc"):
                facts.append(Fact(subj, "attr:organization_structure", value=gi["organizationStructureDesc"], artifact=art, confidence=1.0))
            start = (core.get("entityInformation") or {}).get("entityStartDate")
            if start:
                facts.append(Fact(subj, "attr:incorporation_date", value=start, artifact=art, confidence=0.9, detail="SAM entity start date"))
            addr = core.get("physicalAddress") or {}
            cc = (addr.get("countryCode") or "").replace("USA", "US")
            if cc:
                code = f"US-{addr['stateOrProvinceCode']}" if cc == "US" and addr.get("stateOrProvinceCode") else cc
                facts.append(Fact(subj, "OPERATES_IN", object=NodeRef("Location", location_id(code), {"code": code, "name": code, "kind": "region" if "-" in code else "country"}),
                                  artifact=art, confidence=0.95, detail="SAM physical address"))
            incc = (gi.get("countryOfIncorporationCode") or "").replace("USA", "US")
            if incc:
                code = f"US-{gi['stateOfIncorporationCode']}" if incc == "US" and gi.get("stateOfIncorporationCode") else incc
                facts.append(Fact(subj, "INCORPORATED_IN", object=NodeRef("Location", location_id(code), {"code": code, "name": code, "kind": "region" if "-" in code else "country"}),
                                  artifact=art, confidence=1.0, detail="SAM incorporation"))
            naics = [n.get("naicsCode") for n in ((ent.get("assertions") or {}).get("goodsAndServices") or {}).get("naicsList", []) if n.get("naicsCode")]
            if naics:
                facts.append(Fact(subj, "attr:naics_codes", value=",".join(naics[:20]), artifact=art, confidence=1.0))
            if reg.get("exclusionStatusFlag") == "Y":
                facts.append(Fact(subj, "exclusion_screen", value="hit", artifact=art, confidence=0.95, detail="SAM registration carries exclusionStatusFlag=Y"))
        # Exclusions are screened by the key-free sam_exclusions connector (public daily extract);
        # calling the per-entity API here would spend the daily budget twice.
        return facts
