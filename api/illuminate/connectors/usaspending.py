"""USAspending — prime and sub awards, recipients (UEI), NAICS/PSC, competition.
Open API, no key. Authoritative for supply relationships and award records."""
from __future__ import annotations

from ..ids import entity_id, location_id, normalize_name
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import fetch_json

BASE = "https://api.usaspending.gov/api/v2"
CONTRACT_TYPES = ["A", "B", "C", "D"]
AWARD_FIELDS = ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency", "Awarding Sub Agency", "recipient_id", "generated_internal_id",
                "Description", "Start Date", "End Date", "NAICS", "PSC", "Contract Award Type", "Recipient UEI"]
SUB_FIELDS = ["Sub-Award ID", "Sub-Awardee Name", "Sub-Award Amount", "Prime Recipient Name", "Prime Award ID", "Sub-Award Date", "Sub-Award Description",
              "sub_award_recipient_id", "prime_award_recipient_id", "prime_award_generated_internal_id"]

# PSC prefix → taxonomy id. Coarse on purpose; the fast model refines when a key exists.
PSC_MAP = [
    ("15", "cat_structures"), ("16", "cat_aircraft_components"), ("28", "cat_engines"), ("29", "cat_engines"), ("58", "cat_avionics"), ("59", "cat_avionics"),
    ("61", "cat_avionics"), ("66", "cat_avionics"), ("70", "cat_it_hardware"), ("53", "cat_hardware"), ("47", "cat_hardware"), ("95", "cat_metals"), ("96", "cat_metals"),
    ("10", "cat_weapons"), ("11", "cat_weapons"), ("12", "cat_weapons"), ("13", "cat_weapons"), ("14", "cat_weapons"), ("23", "cat_vehicles"), ("24", "cat_vehicles"),
    ("J", "cat_maintenance"), ("R", "cat_professional"), ("A", "cat_rdte"), ("D", "cat_it_services"), ("U", "cat_training"), ("V", "cat_logistics"), ("W", "cat_logistics"),
    ("Y", "cat_construction"), ("Z", "cat_construction"), ("H", "cat_engineering"), ("L", "cat_engineering"), ("K", "cat_engineering"), ("N", "cat_maintenance"),
    ("S", "cat_other_services"), ("T", "cat_professional"), ("Q", "cat_professional"), ("B", "cat_professional"), ("C", "cat_engineering"), ("E", "cat_professional"),
    ("F", "cat_other_services"), ("G", "cat_other_services"), ("M", "cat_other_services"), ("P", "cat_other_services"), ("X", "cat_other_services"),
]


def psc_category(psc: str | None) -> str | None:
    if not psc:
        return None
    p = psc.upper()
    for pre, cat in PSC_MAP:
        if p.startswith(pre):
            return cat
    return "cat_other_goods" if p[0].isdigit() else "cat_other_services"


def award_url(generated_id: str) -> str:
    return f"https://www.usaspending.gov/award/{generated_id}"


def recipient_url(rid: str) -> str:
    return f"https://www.usaspending.gov/recipient/{rid}/latest"


async def search_awards(keywords: list[str], *, start: str, end: str, agency: str | None = "Department of Defense", limit: int = 100, page: int = 1, subawards: bool = False) -> dict:
    filters: dict = {"keywords": keywords, "award_type_codes": CONTRACT_TYPES, "time_period": [{"start_date": start, "end_date": end}]}
    if agency:
        filters["agencies"] = [{"type": "awarding", "tier": "toptier", "name": agency}]
    body = {"filters": filters, "fields": SUB_FIELDS if subawards else AWARD_FIELDS, "limit": limit, "page": page,
            "sort": "Sub-Award Amount" if subawards else "Award Amount", "order": "desc"}
    if subawards:
        body["subawards"] = True
    return await fetch_json("POST", f"{BASE}/search/spending_by_award/", json_body=body)


async def award_detail(generated_id: str) -> dict:
    return await fetch_json("GET", f"{BASE}/awards/{generated_id}/")


async def recipient(recipient_id: str) -> dict:
    return await fetch_json("GET", f"{BASE}/recipient/{recipient_id}/")


async def awards_for_recipient(name_or_uei: str, *, start: str, end: str, limit: int = 25) -> dict:
    body = {"filters": {"recipient_search_text": [name_or_uei], "award_type_codes": CONTRACT_TYPES, "time_period": [{"start_date": start, "end_date": end}]},
            "fields": AWARD_FIELDS, "limit": limit, "page": 1, "sort": "Award Amount", "order": "desc"}
    return await fetch_json("POST", f"{BASE}/search/spending_by_award/", json_body=body)


def is_sole_source(detail: dict) -> tuple[bool, str | None]:
    ltx = detail.get("latest_transaction_contract_data") or {}
    ext = (ltx.get("extent_competed_description") or "").upper()
    sol = (ltx.get("solicitation_procedures_description") or "").upper()
    offers = ltx.get("number_of_offers_received")
    sole = "NOT COMPETED" in ext or "ONLY ONE SOURCE" in sol or (offers in (1, "1"))
    why = ext or sol or None
    return sole, why


class USAspendingConnector(Connector):
    name = "usaspending"
    label = "USAspending"
    description = "Prime and sub awards, recipients, NAICS/PSC, competition"
    trust = "authoritative"

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        facts: list[Fact] = []
        key = entity.get("uei") or entity.get("name")
        if not key:
            return facts
        res = await awards_for_recipient(key, start="2019-10-01", end="2026-09-30")
        subj = NodeRef("Entity", entity["id"])
        for a in res.get("results", [])[:15]:
            gid = a.get("generated_internal_id")
            if not gid:
                continue
            art = ArtifactRef(url=award_url(gid), title=f"{a.get('Award ID')} — {(a.get('Description') or '')[:120]}", kind="award", source="USAspending",
                              published_at=a.get("Start Date"), props={"amount": a.get("Award Amount"), "agency": a.get("Awarding Sub Agency"), "award_id": a.get("Award ID"),
                                                                        "psc": a.get("PSC"), "naics": a.get("NAICS")})
            uei = a.get("Recipient UEI")
            if uei and not entity.get("uei"):
                facts.append(Fact(subj, "attr:uei", value=uei.upper(), artifact=art, confidence=0.95))
            cat = psc_category(a.get("PSC"))
            if cat:
                facts.append(Fact(subj, "PROVIDES", object=NodeRef("Category", cat), artifact=art, confidence=0.7, detail=f"PSC {a.get('PSC')}"))
            # award artifact about the entity even without a new relationship
            facts.append(Fact(subj, "mention", artifact=art, confidence=0.95, detail="award record"))
        return facts
