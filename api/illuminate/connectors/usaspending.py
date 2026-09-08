"""USAspending — prime and sub awards, recipients (UEI), NAICS/PSC, competition.
Open API, no key. Authoritative for supply relationships and award records.

The connector answers two different questions depending on what it is pointed at.
For an organisation it asks "what has this recipient won?"; for a *program* it asks
"who is paid to work on this?" — a keyword award search whose prime recipients and
sub-awardees become the tier-1 and tier-2 SUPPLIES edges of the program's network.
The program branch is the only place in the system that proposes SUPPLIES facts, so
a program added from chat can grow the same network the seeder builds for V-22."""
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


def is_sole_source(detail: dict) -> tuple[bool | None, str | None]:
    ltx = detail.get("latest_transaction_contract_data") or {}
    ext = (ltx.get("extent_competed_description") or "").upper()
    sol = (ltx.get("solicitation_procedures_description") or "").upper()
    offers = ltx.get("number_of_offers_received")
    if not ext and not sol and offers is None:
        return None, None
    sole = "NOT COMPETED" in ext or "ONLY ONE SOURCE" in sol or (offers in (1, "1"))
    why = ext or sol or (f"{offers} offers received" if offers is not None else None)
    return sole, why


# Defaults for a program supplier search. Each is overridable per program by the
# matching property on the program node, which is what discover_suppliers writes.
PROGRAM_SINCE = "2019-10-01"
PROGRAM_UNTIL = "2026-09-30"
PROGRAM_AGENCY = "Department of Defense"
MAX_PRIMES = 20
MAX_SUBS = 40
PRIME_PAGES = 4
SUB_PAGES = 5


def program_search(entity: dict) -> dict:
    """The award search a program node describes. Keywords fall back to the program's
    own name, which is usually too broad — discover_suppliers is how a caller narrows it."""
    kws = [str(k).strip() for k in (entity.get("keywords") or []) if str(k).strip()]
    return {
        "keywords": kws or [entity.get("name") or ""],
        "since": entity.get("award_since") or PROGRAM_SINCE,
        "until": entity.get("award_until") or PROGRAM_UNTIL,
        # an explicit empty award_agency means "every agency"; an absent one means the default
        "agency": (entity.get("award_agency") or None) if "award_agency" in entity else PROGRAM_AGENCY,
        "max_primes": _limit(entity.get("max_primes"), MAX_PRIMES, 1, 100),
        "max_subs": _limit(entity.get("max_subs"), MAX_SUBS, 0, 200),   # 0 skips the tier-2 pass
    }


def _limit(value, default: int, lo: int, hi: int) -> int:
    try:
        n = default if value is None else int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def _amount(row: dict, field: str) -> float:
    try:
        return float(row.get(field) or 0)
    except (TypeError, ValueError):
        return 0.0


def _supplier_ref(*, name: str, uei: str | None, source_url: str | None) -> NodeRef:
    """A recipient as the claims module will merge it. Props apply ON CREATE only, so
    an entity the graph already holds keeps what it has."""
    return NodeRef("Entity", entity_id(uei=uei, name=name),
                   {"name": name, "name_norm": normalize_name(name), "kind": "organization",
                    "uei": (uei or None) and uei.upper(), "source": "USAspending", "source_url": source_url})


def _award_artifact(row: dict, gid: str, *, psc: str | None = None, naics: str | None = None) -> ArtifactRef:
    return ArtifactRef(url=award_url(gid), title=f"{row.get('Award ID')} — {(row.get('Description') or '')[:120]}", kind="award",
                       source="USAspending", published_at=row.get("Start Date"),
                       props={"amount": row.get("Award Amount"), "agency": row.get("Awarding Sub Agency"), "award_id": row.get("Award ID"),
                              "psc": psc or row.get("PSC"), "naics": naics or row.get("NAICS")})


class USAspendingConnector(Connector):
    name = "usaspending"
    label = "USAspending"
    description = "Prime and sub awards, recipients, NAICS/PSC, competition"
    trust = "authoritative"
    kinds = ("organization", "program", "agency")

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        if (entity.get("kind") or "organization") == "program":
            return await self._enrich_program(entity)
        return await self._enrich_recipient(entity)

    # -- program: who is paid to work on this? ------------------------------------
    async def _enrich_program(self, entity: dict) -> list[Fact]:
        cfg = program_search(entity)
        if not any(cfg["keywords"]):
            return []
        program = NodeRef("Entity", entity["id"])
        facts: list[Fact] = []
        primes = await self._prime_facts(entity, program, cfg, facts)
        if cfg["max_subs"]:
            await self._sub_facts(entity, program, cfg, primes, facts)
        return facts

    async def _prime_facts(self, entity: dict, program: NodeRef, cfg: dict, facts: list[Fact]) -> dict[str, NodeRef]:
        """Rank prime recipients by total award value and propose one tier-1 edge each.
        One aggregate edge per recipient, not one per contract: the network question is
        who supplies the program, and the individual awards stay reachable as artifacts."""
        by_recipient: dict[str, dict] = {}
        page = 1
        while len(by_recipient) < cfg["max_primes"] * 3 and page <= PRIME_PAGES:
            res = await search_awards(cfg["keywords"], start=cfg["since"], end=cfg["until"], agency=cfg["agency"], limit=100, page=page)
            for a in res.get("results", []):
                rid = a.get("recipient_id")
                if not rid:
                    continue
                slot = by_recipient.setdefault(rid, {"awards": [], "total": 0.0})
                slot["awards"].append(a)
                slot["total"] += _amount(a, "Award Amount")
            if not res.get("page_metadata", {}).get("hasNext"):
                break
            page += 1

        ranked = sorted(by_recipient.items(), key=lambda kv: -kv[1]["total"])[: cfg["max_primes"]]
        primes: dict[str, NodeRef] = {}
        for n, (rid, slot) in enumerate(ranked):
            top = sorted(slot["awards"], key=lambda a: -_amount(a, "Award Amount"))[0]
            name = top.get("Recipient Name") or ""
            ref = _supplier_ref(name=name, uei=top.get("Recipient UEI"), source_url=recipient_url(rid))
            if not name or ref.id == entity["id"]:
                continue          # a program cannot supply itself
            primes[rid] = ref
            gid = top.get("generated_internal_id")
            psc, naics, sole, why = top.get("PSC"), top.get("NAICS"), None, None
            art = _award_artifact(top, gid) if gid else None
            if gid:
                try:
                    det = await award_detail(gid)
                except Exception:
                    det = {}
                if det:
                    ltx = det.get("latest_transaction_contract_data") or {}
                    psc = ltx.get("product_or_service_code") or psc
                    naics = ltx.get("naics") or naics
                    sole, why = is_sole_source(det)
                    art = _award_artifact(top, gid, psc=psc, naics=naics)
            facts.append(Fact(ref, "SUPPLIES", object=program, artifact=art, confidence=0.95,
                              detail=f"{len(slot['awards'])} prime award(s) matching {', '.join(cfg['keywords'])}",
                              props={"tier": 1, "sole_source": sole, "competition": why, "amount": round(slot["total"], 2),
                                     "award_count": len(slot["awards"]), "contract_ref": top.get("Award ID"), "psc": psc, "naics": naics}))
            cat = psc_category(psc)
            if cat:
                facts.append(Fact(ref, "PROVIDES", object=NodeRef("Category", cat), artifact=art, confidence=0.7, detail=f"PSC {psc}"))
            if art and n < 5:
                # the program itself deserves evidence, not only its suppliers
                facts.append(Fact(program, "mention", artifact=art, confidence=0.95, detail="award record"))
        return primes

    async def _sub_facts(self, entity: dict, program: NodeRef, cfg: dict, primes: dict[str, NodeRef], facts: list[Fact]) -> None:
        """Reported sub-awards become tier-2 edges under the prime that reported them.
        A prime that only surfaces here is brought in at tier 1 as well, so the path to
        the program exists — a tier-2 supplier hanging off nothing is unreadable."""
        subs: dict[str, dict] = {}
        page = 1
        while len(subs) < cfg["max_subs"] and page <= SUB_PAGES:
            res = await search_awards(cfg["keywords"], start=cfg["since"], end=cfg["until"], agency=None, limit=100, page=page, subawards=True)
            for row in res.get("results", []):
                key = (row.get("Sub-Awardee Name") or "").strip().upper()
                if not key:
                    continue
                slot = subs.setdefault(key, {"rows": [], "total": 0.0})
                slot["rows"].append(row)
                slot["total"] += _amount(row, "Sub-Award Amount")
            if not res.get("page_metadata", {}).get("hasNext"):
                break
            page += 1

        for _, slot in sorted(subs.items(), key=lambda kv: -kv[1]["total"])[: cfg["max_subs"]]:
            rows = slot["rows"]
            r0 = rows[0]
            display, uei = r0.get("Sub-Awardee Name") or "", None
            src_url = award_url(r0["prime_award_generated_internal_id"]) if r0.get("prime_award_generated_internal_id") else None
            if r0.get("sub_award_recipient_id"):
                try:
                    rec = await recipient(r0["sub_award_recipient_id"])
                    uei, display = rec.get("uei"), rec.get("name") or display
                    src_url = recipient_url(r0["sub_award_recipient_id"])
                except Exception:
                    pass
            if not display:
                continue
            sub_ref = _supplier_ref(name=display, uei=uei, source_url=src_url)
            if sub_ref.id == entity["id"]:
                continue
            # One edge per prime, not per prime *award*: the same sub-awardee often appears
            # under several contracts of the same prime, and those are one relationship.
            per_prime: dict[str, list[dict]] = {}
            for row in rows:
                per_prime.setdefault(row.get("prime_award_recipient_id") or f"name:{(row.get('Prime Recipient Name') or '').upper()}", []).append(row)
            for prid, group in per_prime.items():
                top = max(group, key=lambda r: _amount(r, "Sub-Award Amount"))
                pgid, paward = top.get("prime_award_generated_internal_id"), top.get("Prime Award ID")
                prime_ref = primes.get(prid)
                if prime_ref is None:
                    prime_ref = await self._prime_of_subaward(entity, program, top.get("prime_award_recipient_id"),
                                                              top.get("Prime Recipient Name"), pgid, paward, facts)
                    if prime_ref is None:
                        continue
                    primes[prid] = prime_ref
                if prime_ref.id == sub_ref.id:
                    continue      # a recipient reported as its own sub-awardee
                art = ArtifactRef(url=award_url(pgid), kind="award", source="USAspending", published_at=top.get("Sub-Award Date"),
                                  title=f"Subaward {top.get('Sub-Award ID')} — {(top.get('Sub-Award Description') or '')[:120]}",
                                  props={"amount": top.get("Sub-Award Amount"), "award_id": paward}) if pgid else None
                facts.append(Fact(sub_ref, "SUPPLIES", object=prime_ref, artifact=art, confidence=0.9,
                                  detail=(top.get("Sub-Award Description") or "")[:200] or "reported sub-award",
                                  props={"tier": 2, "sole_source": False, "amount": round(sum(_amount(r, "Sub-Award Amount") for r in group), 2),
                                         "contract_ref": paward, "award_count": len(group),
                                         "sub_award_ids": [r.get("Sub-Award ID") for r in group if r.get("Sub-Award ID")][:10]}))

    async def _prime_of_subaward(self, entity: dict, program: NodeRef, prid: str | None, pname: str | None,
                                 pgid: str | None, paward: str | None, facts: list[Fact]) -> NodeRef | None:
        name, uei, src_url = pname or "", None, None
        if prid:
            try:
                rec = await recipient(prid)
                name, uei, src_url = rec.get("name") or name, rec.get("uei"), recipient_url(prid)
            except Exception:
                pass
        if not name:
            return None
        ref = _supplier_ref(name=name, uei=uei, source_url=src_url or (award_url(pgid) if pgid else None))
        if ref.id == entity["id"]:
            return None
        facts.append(Fact(ref, "SUPPLIES", object=program, confidence=0.9, detail="prime of a reported sub-award",
                          props={"tier": 1, "sole_source": False, "contract_ref": paward},
                          artifact=ArtifactRef(url=award_url(pgid), title=f"{paward} — prime award", kind="award", source="USAspending") if pgid else None))
        return ref

    # -- organisation: what has this recipient won? -------------------------------
    async def _enrich_recipient(self, entity: dict) -> list[Fact]:
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
