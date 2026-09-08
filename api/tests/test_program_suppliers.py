"""The program branch of the USAspending connector — the only source of SUPPLIES
facts. No network: the award search is stubbed with the shape the API returns."""
import pytest

from illuminate.connectors import usaspending as ua
from illuminate.connectors.registry import REGISTRY
from illuminate.ids import entity_id

PROGRAM = {"id": "ent_prog", "name": "E-2D Advanced Hawkeye Program", "kind": "program", "keywords": ["E-2D"]}

PRIMES = [
    {"recipient_id": "r-ng", "Recipient Name": "NORTHROP GRUMMAN SYSTEMS CORPORATION", "Recipient UEI": "NG000000001", "Award Amount": 8_000_000_000,
     "Award ID": "N0001920C0001", "generated_internal_id": "gid-ng-1", "PSC": "1510", "NAICS": "336411", "Description": "E-2D airframe"},
    {"recipient_id": "r-ng", "Recipient Name": "NORTHROP GRUMMAN SYSTEMS CORPORATION", "Recipient UEI": "NG000000001", "Award Amount": 500_000_000,
     "Award ID": "N0001921C0002", "generated_internal_id": "gid-ng-2", "PSC": "1510", "Description": "E-2D spares"},
    {"recipient_id": "r-rc", "Recipient Name": "ROCKWELL COLLINS SIMULATION & TRAINING SOLUTIONS LLC", "Recipient UEI": "RC000000001", "Award Amount": 70_000_000,
     "Award ID": "N0001922C0003", "generated_internal_id": "gid-rc-1", "PSC": "6910", "Description": "E-2D training"},
]

SUBS = [
    {"Sub-Awardee Name": "DATA DEVICE CORP", "Sub-Award Amount": 54_000_000, "Sub-Award ID": "S1", "Sub-Award Description": "bus interface",
     "sub_award_recipient_id": "r-ddc", "prime_award_recipient_id": "r-ray", "Prime Recipient Name": "RAYTHEON COMPANY",
     "prime_award_generated_internal_id": "gid-ray-1", "Prime Award ID": "N0001920C0009"},
    {"Sub-Awardee Name": "AERO SIMULATION, INC.", "Sub-Award Amount": 6_900_000, "Sub-Award ID": "S2", "Sub-Award Description": "simulator",
     "sub_award_recipient_id": None, "prime_award_recipient_id": "r-rc", "Prime Recipient Name": "ROCKWELL COLLINS SIMULATION & TRAINING SOLUTIONS LLC",
     "prime_award_generated_internal_id": "gid-rc-1", "Prime Award ID": "N0001922C0003"},
]

RECIPIENTS = {
    "r-ddc": {"name": "DATA DEVICE CORPORATION", "uei": "DDC000000001"},
    "r-ray": {"name": "RAYTHEON COMPANY", "uei": "RAY000000001"},
}


@pytest.fixture
def stub_api(monkeypatch):
    calls = {"search": [], "detail": [], "recipient": []}

    async def search_awards(keywords, *, start, end, agency=None, limit=100, page=1, subawards=False):
        calls["search"].append({"keywords": keywords, "start": start, "end": end, "agency": agency, "page": page, "subawards": subawards})
        rows = SUBS if subawards else PRIMES
        return {"results": rows if page == 1 else [], "page_metadata": {"hasNext": False}}

    async def award_detail(gid):
        calls["detail"].append(gid)
        return {"latest_transaction_contract_data": {"product_or_service_code": "1510", "naics": "336411",
                                                     "extent_competed_description": "NOT COMPETED", "number_of_offers_received": 1}}

    async def recipient(rid):
        calls["recipient"].append(rid)
        return RECIPIENTS[rid]

    monkeypatch.setattr(ua, "search_awards", search_awards)
    monkeypatch.setattr(ua, "award_detail", award_detail)
    monkeypatch.setattr(ua, "recipient", recipient)
    return calls


def supplies(facts):
    return {(f.subject.id, f.object.id): f for f in facts if f.predicate == "SUPPLIES"}


# --- the search a program describes ----------------------------------------------
def test_program_search_defaults_and_overrides():
    cfg = ua.program_search(PROGRAM)
    assert cfg["keywords"] == ["E-2D"] and cfg["agency"] == ua.PROGRAM_AGENCY
    assert cfg["since"] == ua.PROGRAM_SINCE and cfg["max_primes"] == ua.MAX_PRIMES

    over = ua.program_search({**PROGRAM, "award_since": "2021-01-01", "award_agency": "", "max_primes": 5, "max_subs": 0})
    assert over["since"] == "2021-01-01" and over["max_primes"] == 5 and over["max_subs"] == 0
    assert over["agency"] is None, "an explicit empty agency searches every agency"


def test_program_search_falls_back_to_the_name():
    assert ua.program_search({"name": "X Program", "kind": "program"})["keywords"] == ["X Program"]


def test_program_search_clamps_limits():
    assert ua.program_search({**PROGRAM, "max_primes": 9999, "max_subs": 9999})["max_primes"] == 100


# --- tier 1 -----------------------------------------------------------------------
async def test_primes_become_tier_one_suppliers_of_the_program(stub_api):
    facts = await ua.USAspendingConnector().enrich(PROGRAM, "local")
    ng = entity_id(uei="NG000000001")
    edge = supplies(facts)[(ng, "ent_prog")]
    assert edge.props["tier"] == 1
    assert edge.props["amount"] == 8_500_000_000, "one aggregate edge per recipient, not one per contract"
    assert edge.props["award_count"] == 2
    assert edge.props["contract_ref"] == "N0001920C0001", "the largest award identifies the edge"
    assert edge.props["sole_source"] is True and edge.props["psc"] == "1510"
    assert edge.subject.props["kind"] == "organization" and edge.subject.props["uei"] == "NG000000001"
    assert edge.artifact.url.endswith("gid-ng-1")


async def test_supplies_facts_carry_no_merge_keys_so_the_edge_is_upserted(stub_api):
    facts = await ua.USAspendingConnector().enrich(PROGRAM, "local")
    assert all(f.merge_keys == [] for f in facts if f.predicate == "SUPPLIES")


async def test_psc_becomes_a_category_and_awards_evidence_the_program(stub_api):
    facts = await ua.USAspendingConnector().enrich(PROGRAM, "local")
    provides = [f for f in facts if f.predicate == "PROVIDES"]
    assert ("cat_structures", 0.7) in [(f.object.id, f.confidence) for f in provides]
    mentions = [f for f in facts if f.predicate == "mention"]
    assert mentions and all(f.subject.id == "ent_prog" for f in mentions), "the program gets its own award evidence"


async def test_the_search_uses_the_programs_keywords_and_window(stub_api):
    await ua.USAspendingConnector().enrich({**PROGRAM, "award_since": "2021-01-01"}, "local")
    prime_call = stub_api["search"][0]
    assert prime_call["keywords"] == ["E-2D"] and prime_call["start"] == "2021-01-01"
    assert prime_call["agency"] == "Department of Defense" and prime_call["subawards"] is False
    assert any(c["subawards"] and c["agency"] is None for c in stub_api["search"]), "sub-awards are not agency-filtered"


# --- tier 2 -----------------------------------------------------------------------
async def test_subawardees_hang_off_their_prime_not_the_program(stub_api):
    facts = await ua.USAspendingConnector().enrich(PROGRAM, "local")
    edges = supplies(facts)
    ddc, ray = entity_id(uei="DDC000000001"), entity_id(uei="RAY000000001")
    tier2 = edges[(ddc, ray)]
    assert tier2.props["tier"] == 2 and tier2.props["amount"] == 54_000_000
    assert tier2.props["contract_ref"] == "N0001920C0009" and tier2.props["sub_award_ids"] == ["S1"]
    assert tier2.subject.props["name"] == "DATA DEVICE CORPORATION", "resolved to the recipient record's name"
    assert (ddc, "ent_prog") not in edges, "a sub-awardee does not supply the program directly"


async def test_a_prime_seen_only_in_subawards_is_added_at_tier_one(stub_api):
    facts = await ua.USAspendingConnector().enrich(PROGRAM, "local")
    ray = entity_id(uei="RAY000000001")
    assert supplies(facts)[(ray, "ent_prog")].props["tier"] == 1, "so the path to the program exists"


async def test_a_subawardee_of_a_known_prime_reuses_that_prime(stub_api):
    facts = await ua.USAspendingConnector().enrich(PROGRAM, "local")
    aero = entity_id(name="AERO SIMULATION, INC.")
    rc = entity_id(uei="RC000000001")
    assert (aero, rc) in supplies(facts), "the tier-1 Rockwell Collins node is reused, not duplicated by name"
    assert "r-rc" not in stub_api["recipient"], "and no second lookup is spent on it"


async def test_one_edge_per_prime_not_per_prime_award(monkeypatch):
    """The same sub-awardee under two contracts of the same prime is one relationship
    worth the sum, not two facts whose commits overwrite each other."""
    rows = [{"Sub-Awardee Name": "VERTIV CORPORATION", "Sub-Award Amount": amt, "Sub-Award ID": sid, "Sub-Award Description": "power",
             "sub_award_recipient_id": None, "prime_award_recipient_id": "r-rc", "Prime Recipient Name": "ROCKWELL COLLINS SIMULATION & TRAINING SOLUTIONS LLC",
             "prime_award_generated_internal_id": gid, "Prime Award ID": award}
            for amt, sid, gid, award in ((114_635, "S3", "gid-rc-1", "N0001922C0003"), (94_865, "S4", "gid-rc-9", "N6134021C0017"))]

    async def search_awards(keywords, *, start, end, agency=None, limit=100, page=1, subawards=False):
        return {"results": (rows if subawards else PRIMES) if page == 1 else [], "page_metadata": {"hasNext": False}}

    async def award_detail(gid):
        return {}

    monkeypatch.setattr(ua, "search_awards", search_awards)
    monkeypatch.setattr(ua, "award_detail", award_detail)
    facts = await ua.USAspendingConnector().enrich(PROGRAM, "local")
    edge = supplies(facts)[(entity_id(name="VERTIV CORPORATION"), entity_id(uei="RC000000001"))]
    assert edge.props["amount"] == 209_500 and edge.props["award_count"] == 2
    assert edge.props["contract_ref"] == "N0001922C0003", "the largest sub-award identifies the edge"
    assert sorted(edge.props["sub_award_ids"]) == ["S3", "S4"]


async def test_max_subs_zero_skips_the_tier_two_pass(stub_api):
    facts = await ua.USAspendingConnector().enrich({**PROGRAM, "max_subs": 0}, "local")
    assert all(f.props.get("tier") == 1 for f in facts if f.predicate == "SUPPLIES")
    assert not any(c["subawards"] for c in stub_api["search"])


async def test_a_program_never_supplies_itself(stub_api, monkeypatch):
    async def search_awards(keywords, *, start, end, agency=None, limit=100, page=1, subawards=False):
        if subawards:
            return {"results": [], "page_metadata": {"hasNext": False}}
        return {"results": [{**PRIMES[0], "Recipient Name": PROGRAM["name"], "Recipient UEI": None}], "page_metadata": {"hasNext": False}}

    monkeypatch.setattr(ua, "search_awards", search_awards)
    prog = {**PROGRAM, "id": entity_id(name=PROGRAM["name"])}
    assert not supplies(await ua.USAspendingConnector().enrich(prog, "local"))


# --- which sources speak about a program -----------------------------------------
def test_company_shaped_connectors_skip_programs():
    by_name = {c.name: c for c in REGISTRY}
    assert by_name["usaspending"].applies_to(PROGRAM)
    assert by_name["gdelt"].applies_to(PROGRAM)
    for name in ("ofac", "sam_exclusions", "gleif", "littlesis", "edgar", "websearch"):
        assert not by_name[name].applies_to(PROGRAM), f"{name} would only manufacture noise about a program"
        assert by_name[name].applies_to({"id": "e", "name": "Co", "kind": "organization"})


def test_an_entity_without_a_kind_is_treated_as_an_organization():
    assert ua.USAspendingConnector().applies_to({"id": "e", "name": "Co"})


async def test_an_organization_still_gets_the_recipient_search(monkeypatch):
    seen = {}

    async def awards_for_recipient(key, *, start, end, limit=25):
        seen["key"] = key
        return {"results": []}

    monkeypatch.setattr(ua, "awards_for_recipient", awards_for_recipient)
    await ua.USAspendingConnector().enrich({"id": "ent_c", "name": "Co", "kind": "organization", "uei": "CO000000001"}, "local")
    assert seen["key"] == "CO000000001"
