"""Machine-readable coverage contract for approved live evidence sources.

This is deliberately a policy inventory, not a claim that every catalog item has
an entity-query API.  Entries without a safe contextual adapter carry an
actionable baseline status instead of being silently omitted.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Literal, TypedDict

CoverageStatus = Literal["available", "credential_required", "unavailable", "not_applicable"]


class SourceCoverage(TypedDict):
    source_id: str
    catalog_ids: list[str]
    label: str
    approved: bool
    adapter: str | None
    policy_status: CoverageStatus
    endpoint: str
    access: str
    credentials: str
    freshness: str
    entity_kinds: list[str]
    categories: list[str]
    limitations: str
    action: str | None


def _source(source_id: str, label: str, *, catalog_id: int | None = None,
            adapter: str | None = None, policy_status: CoverageStatus = "available",
            endpoint: str, access: str = "public read-only HTTPS",
            credentials: str = "none", freshness: str,
            kinds: tuple[str, ...] = ("organization",),
            categories: tuple[str, ...], limitations: str,
            action: str | None = None) -> SourceCoverage:
    return {
        "source_id": source_id, "catalog_ids": [f"ndia:{catalog_id}"] if catalog_id else [],
        "label": label, "approved": True, "adapter": adapter, "policy_status": policy_status,
        "endpoint": endpoint, "access": access, "credentials": credentials,
        "freshness": freshness, "entity_kinds": list(kinds), "categories": list(categories),
        "limitations": limitations, "action": action,
    }


# Keep this tuple stable: consumers can measure coverage without scraping prose.
SOURCE_COVERAGE: tuple[SourceCoverage, ...] = (
    _source("usaspending.gov", "Federal Spending", catalog_id=1, adapter="usaspending",
            endpoint="https://api.usaspending.gov/api/v2", freshness="7 days",
            kinds=("organization", "program", "agency"), categories=("procurement", "supplier_identity"),
            limitations="Agency-submitted prime/subaward data may be delayed or omit lower tiers."),
    _source("nasa-firms", "NASA FIRMS", catalog_id=36, policy_status="unavailable",
            endpoint="https://firms.modaps.eosdis.nasa.gov/api/area/csv",
            access="read-only FIRMS API", credentials="NASA FIRMS MAP_KEY",
            freshness="24 hours", kinds=("program", "facility"), categories=("climate", "facility", "event"),
            limitations="Fire detections require coordinates and do not prove facility damage.",
            action="Implement a bounded facility-coordinate adapter, then configure its FIRMS MAP_KEY."),
    _source("nga-pirate-attacks", "Global Maritime Pirate Attacks", catalog_id=38, policy_status="unavailable",
            endpoint="https://msi.nga.mil/Piracy", freshness="source publication cycle",
            kinds=("program", "route", "facility"), categories=("logistics", "route", "event"),
            limitations="The catalog item has no reviewed bounded machine API for contextual route queries.",
            action="Configure a reviewed NGA download URL and parser; do not scrape the portal."),
    _source("dod-budget-justification", "Budget Justification Books", catalog_id=40, policy_status="not_applicable",
            endpoint="https://comptroller.defense.gov/Budget-Materials/", freshness="annual",
            kinds=("program", "agency"), categories=("program", "budget"),
            limitations="Published books are document collections, not a stable entity-query API.",
            action="Provide a program budget-line identifier and reviewed document manifest."),
    _source("deep-sea-minerals", "Deep Sea Minerals", catalog_id=43, policy_status="not_applicable",
            endpoint="https://www.usgs.gov/centers/national-minerals-information-center", freshness="publication cycle",
            kinds=("program", "material", "location"), categories=("critical_material", "location"),
            limitations="No safe mapping exists without a material, deposit, or geographic context.",
            action="Attach a material identifier or geographic area and a reviewed USGS dataset endpoint."),
    _source("fema-climate-resilience", "FEMA Supply Chain Climate Resilience", catalog_id=45, policy_status="not_applicable",
            endpoint="https://www.fema.gov/emergency-managers/risk-management", freshness="publication cycle",
            kinds=("program", "facility"), categories=("climate", "guidance"),
            limitations="Guidance is not an observational feed and cannot establish entity-specific risk.",
            action="Use as methodology only, or provide a facility hazard identifier."),
    _source("ibtracs", "Global Tropical Cyclone Tracks", catalog_id=47, policy_status="unavailable",
            endpoint="https://www.ncei.noaa.gov/products/international-best-track-archive", freshness="3 hours to annual archive",
            kinds=("program", "facility", "route"), categories=("climate", "event", "route"),
            limitations="The reviewed source is a large bulk archive; no bounded contextual adapter is configured.",
            action="Configure an approved IBTrACS subset service or local spatial index."),
    _source("sam-entity-management", "Government Contract Award Data", catalog_id=49, adapter="sam",
            policy_status="credential_required", endpoint="https://api.sam.gov/entity-information/v3/entities",
            access="read-only SAM.gov API", credentials="SAM.gov personal API key", freshness="24 hours",
            kinds=("organization",), categories=("procurement", "supplier_identity"),
            limitations="Registration is self-reported and personal keys have a small daily quota.",
            action="Add a SAM.gov personal API key in connector settings."),
    _source("world-port-index", "World Port Index", catalog_id=56, policy_status="unavailable",
            endpoint="https://msi.nga.mil/Publications/WPI", freshness="source publication cycle",
            kinds=("program", "facility", "route"), categories=("logistics", "port", "route"),
            limitations="The public source is a bulk publication without a reviewed bounded query endpoint.",
            action="Configure a reviewed WPI download and local spatial index."),
    _source("nasa-earthdata", "NASA Earthdata", catalog_id=57, policy_status="unavailable",
            endpoint="https://cmr.earthdata.nasa.gov/search", access="read-only CMR/Earthdata APIs",
            credentials="Earthdata Login token for protected collections", freshness="collection-specific",
            kinds=("program", "facility", "route", "location"), categories=("climate", "earth_observation"),
            limitations="Earthdata is a catalog of collections; applicability requires a collection and geometry.",
            action="Implement a bounded collection-and-geometry adapter, then configure Earthdata credentials if required."),
    _source("noaa-climate-normals", "U.S. Climate Normals", catalog_id=61, policy_status="unavailable",
            endpoint="https://www.ncei.noaa.gov/cdo-web/api/v2/data", access="read-only NOAA CDO API",
            credentials="NOAA CDO token", freshness="decennial normals; daily source updates",
            kinds=("facility", "location"), categories=("climate", "facility"),
            limitations="Normals describe historical climate, not forecasts or realized facility impact.",
            action="Implement a bounded station/coordinate adapter, then configure a NOAA CDO token."),
    _source("gdelt-2.x", "GDELT", catalog_id=62, adapter="gdelt",
            endpoint="https://api.gdeltproject.org/api/v2/doc/doc", freshness="15 minutes",
            kinds=("organization", "program", "agency"), categories=("adverse_media", "event"),
            limitations="Automated matching, translation, tone, and coverage can be incorrect or incomplete."),
    _source("acled", "ACLED", catalog_id=64, policy_status="unavailable",
            endpoint="https://api.acleddata.com/acled/read", access="read-only ACLED API",
            credentials="ACLED account email and access key", freshness="weekly; source dependent",
            kinds=("program", "facility", "route", "location"), categories=("event", "geopolitical", "route"),
            limitations="Reported-event coverage varies and does not prove impact on a supplier or route.",
            action="Implement a bounded geographic-event adapter, then configure ACLED credentials."),
    _source("noaa-marine-cadastre-ais", "NOAA Marine Cadastre AIS", catalog_id=70, policy_status="unavailable",
            endpoint="https://marinecadastre.gov/ais/", freshness="annual bulk releases",
            kinds=("program", "route", "facility"), categories=("logistics", "route", "vessel"),
            limitations="Historical AIS is distributed as very large bulk files, not a bounded live route API.",
            action="Configure an approved regional/time-bounded AIS index."),
    _source("overture-maps", "Overture Maps", catalog_id=114, policy_status="unavailable",
            endpoint="https://docs.overturemaps.org/getting-data/", access="public read-only cloud object data",
            freshness="monthly release", kinds=("facility", "route", "location"),
            categories=("facility", "location", "logistics"),
            limitations="Cloud-native bulk data needs a release-pinned spatial query engine not present here.",
            action="Configure a release-pinned GeoParquet query service."),
    _source("openstreetmap", "OpenStreetMap", catalog_id=115, adapter="openstreetmap",
            endpoint="https://nominatim.openstreetmap.org/reverse", freshness="7 days",
            kinds=("organization", "program", "agency", "facility", "route"), categories=("facility", "location", "logistics"),
            limitations="Community map data and reverse-geocoded nearby features do not prove ownership or operation."),
    _source("ecfr-title-48", "FAR Part 52", catalog_id=118, adapter="far",
            endpoint="https://www.ecfr.gov/current/title-48/chapter-1/subchapter-H/part-52", freshness="24 hours",
            kinds=("organization", "program", "agency"), categories=("regulatory", "procurement"),
            limitations="Retrieval verifies cited clause text exists; legal applicability still requires contract review."),
    _source("first-epss", "FIRST EPSS", catalog_id=128, adapter="epss",
            endpoint="https://api.first.org/data/v1/epss", freshness="24 hours",
            kinds=("organization", "program", "agency"), categories=("cyber", "vulnerability"),
            limitations="EPSS estimates exploitation probability; it does not prove exposure, compromise, or asset ownership."),
    # Supplemental sources retained by the existing enrichment path.
    _source("sam-exclusions-public-extract", "SAM.gov Exclusions", adapter="sam_exclusions",
            endpoint="https://sam.gov/api/prod/fileextractservices/v1/api/listfiles", freshness="24 hours",
            categories=("sanctions", "exclusions"), limitations="Results are only as current as the cached public extract."),
    _source("gleif-lei", "GLEIF LEI", adapter="gleif", endpoint="https://api.gleif.org/api/v1/lei-records",
            freshness="7 days", categories=("supplier_identity", "ownership"),
            limitations="Reported accounting parents are not necessarily beneficial owners."),
    _source("sec-edgar", "SEC EDGAR", adapter="edgar", endpoint="https://data.sec.gov/submissions/",
            freshness="24 hours", categories=("ownership", "financial", "regulatory"),
            limitations="Private entities and undisclosed relationships are outside EDGAR coverage."),
    _source("ofac-sdn", "OFAC SDN", adapter="ofac", endpoint="https://sanctionslistservice.ofac.treas.gov/",
            freshness="24 hours", categories=("sanctions",), limitations="Name matching needs identifier-based review and does not implement legal ownership analysis."),
    _source("opencorporates", "OpenCorporates", adapter="opencorporates", policy_status="credential_required",
            endpoint="https://api.opencorporates.com/v0.4/companies/search", access="read-only API",
            credentials="OpenCorporates API token", freshness="7 days", categories=("supplier_identity", "ownership"),
            limitations="Registry coverage and freshness vary by jurisdiction.",
            action="Add an OpenCorporates API token."),
    _source("littlesis", "LittleSis", adapter="littlesis", endpoint="https://littlesis.org/api/entities/search",
            freshness="7 days", categories=("ownership", "lead"),
            limitations="Community-maintained relationships are investigative leads, not proof."),
    _source("finnhub", "Finnhub market data", adapter="market", policy_status="credential_required",
            endpoint="https://finnhub.io/api/v1", access="read-only API", credentials="Finnhub API key",
            freshness="15 minutes", categories=("financial",),
            limitations="Only listed entities with a ticker apply; free-tier quotes may be delayed.",
            action="Add a Finnhub key and entity ticker."),
)


def coverage_contract() -> list[SourceCoverage]:
    """Return a defensive copy suitable for API serialization."""
    return deepcopy(list(SOURCE_COVERAGE))


def coverage_for_adapter(name: str) -> SourceCoverage | None:
    entry = next((item for item in SOURCE_COVERAGE if item["adapter"] == name), None)
    return deepcopy(entry) if entry else None


def validate_coverage_contract() -> None:
    expected = {f"ndia:{value}" for value in (1, 36, 38, 40, 43, 45, 47, 49, 56, 57, 61, 62, 64, 70, 114, 115, 118, 128)}
    actual = {catalog_id for item in SOURCE_COVERAGE for catalog_id in item["catalog_ids"]}
    if actual != expected:
        raise RuntimeError(f"NDIA coverage contract mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    for item in SOURCE_COVERAGE:
        if not item["adapter"] and (item["policy_status"] not in {"unavailable", "not_applicable"} or not item["action"]):
            raise RuntimeError(f"{item['source_id']} needs an adapter or actionable unavailable status")


validate_coverage_contract()