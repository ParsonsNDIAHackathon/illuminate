from __future__ import annotations

from .base import Connector
from .edgar import EDGARConnector
from .gdelt import GDELTConnector
from .gleif import GLEIFConnector
from .littlesis import LittleSisConnector
from .market import MarketConnector
from .ofac import OFACConnector
from .opencorporates import OpenCorporatesConnector
from .sam import SAMConnector
from .sam_exclusions import SAMExclusionsConnector
from .un_sanctions import UNSanctionsConnector
from .usaspending import USAspendingConnector
from .websearch import WebSearchConnector
from ..llm.client import check_key


# Stable, downstream-safe source descriptions.  Connector labels are presentation
# text; source_id and catalog_ids are the identifiers exports should rely on.
SOURCE_METADATA: dict[str, dict] = {
    "usaspending": {
        "source_id": "usaspending.gov",
        "catalog_ids": ["ndia:1"],
        "usage_note": "Public U.S. federal spending data; subject to USAspending.gov terms and attribution guidance.",
        "quality_note": "Award and recipient records reflect agency submissions; subaward reporting and competition fields can be incomplete or delayed.",
        "supports": "Federal spending, prime/subaward, recipient, PSC/NAICS, and contract competition evidence.",
        "unknowns": "Does not establish beneficial ownership or unreported lower-tier suppliers.",
    },
    "gdelt": {
        "source_id": "gdelt-2.x",
        "catalog_ids": ["ndia:62"],
        "usage_note": "Open GDELT-derived article metadata; linked publisher content retains its own terms.",
        "quality_note": "Automated media indexing and tone are leads, not verified adverse findings; cached results are time-bounded.",
        "supports": "Cached GKG/news discovery, article timestamps, organization mentions, and adverse-media observations.",
        "unknowns": "Coverage, entity matching, translation, and sentiment may be incomplete or incorrect.",
    },
    "opencorporates": {
        "source_id": "opencorporates",
        "catalog_ids": [],
        "usage_note": "Use and attribution are governed by OpenCorporates licensing and API terms.",
        "quality_note": "Aggregates official registers with jurisdiction-dependent freshness and field coverage.",
        "supports": "Company registry identifiers, status, incorporation, and officer leads.",
        "unknowns": "A registry match does not by itself prove current control or beneficial ownership.",
    },
    "gleif": {
        "source_id": "gleif-lei",
        "catalog_ids": [],
        "usage_note": "GLEIF LEI data is publicly available under GLEIF usage terms.",
        "quality_note": "Level 2 relationships may report exceptions or omit parents; legal-entity data follows LOU updates.",
        "supports": "LEI identity, legal jurisdiction, and reported direct/ultimate accounting parents.",
        "unknowns": "Does not necessarily identify beneficial owners or operational control.",
    },
    "edgar": {
        "source_id": "sec-edgar",
        "catalog_ids": [],
        "usage_note": "Public SEC filings; automated access must follow SEC fair-access policy.",
        "quality_note": "Authoritative filings for SEC registrants, but extracted roles and relationships remain interpretation-dependent.",
        "supports": "Public-company identity, filings, officers, directors, and disclosed ownership.",
        "unknowns": "Private entities and undisclosed relationships are outside EDGAR coverage.",
    },
    "littlesis": {
        "source_id": "littlesis",
        "catalog_ids": [],
        "usage_note": "Community-maintained open data; reuse is subject to LittleSis terms and attribution.",
        "quality_note": "Relationship records are investigative leads and may be historical, incomplete, or user-contributed.",
        "supports": "Officer, director, and organizational-interlock leads.",
        "unknowns": "A listed relationship does not prove current influence or wrongdoing.",
    },
    "ofac": {
        "source_id": "ofac-sdn",
        "catalog_ids": [],
        "usage_note": "Public U.S. Treasury sanctions data; screening is informational and not legal advice.",
        "quality_note": "Name screening can produce false positives/negatives and requires identifier-based review of hits.",
        "supports": "Point-in-time screening against OFAC SDN names and aliases.",
        "unknowns": "A clear result does not cover every sanctions program, ownership rule, or future designation.",
    },
    "un_sanctions": {
        "source_id": "un-sc-consolidated",
        "catalog_ids": [],
        "usage_note": "Public UN Security Council sanctions data; screening is informational and not legal advice.",
        "quality_note": "Transliterated names and aliases make fuzzy matching necessary; hits require identifier-based review and a clear result is point-in-time.",
        "supports": "Point-in-time screening against UN Consolidated List entity and individual designations, with committee regime and listing date.",
        "unknowns": "Covers UN designations only; national and EU lists, ownership-by-designated-party rules, and pending designations are out of scope.",
    },
    "sam_exclusions": {
        "source_id": "sam-exclusions-public-extract",
        "catalog_ids": [],
        "usage_note": "Public SAM.gov exclusions extract; use is subject to SAM.gov terms.",
        "quality_note": "Local screening is only as current as the cached daily extract and matching identifiers.",
        "supports": "Point-in-time federal exclusion, suspension, and debarment screening.",
        "unknowns": "A clear result does not establish responsibility or eligibility outside the extract scope.",
    },
    "sam": {
        "source_id": "sam-entity-management",
        "catalog_ids": ["ndia:49"],
        "usage_note": "SAM.gov entity data is subject to SAM.gov API terms and account limits.",
        "quality_note": "Registration data is self-reported and API access can be rate limited.",
        "supports": "UEI, CAGE, registration status, assertions, and NAICS.",
        "unknowns": "Registration does not prove performance, ownership, or absence of exclusions.",
    },
}


class OpenAIPseudoConnector(Connector):
    """Not a data source — listed so the settings screen shows the model key."""
    name = "openai"
    label = "OpenAI"
    description = "Optional guarded summaries and chat; deterministic findings remain authoritative"
    trust = "open"
    key_name = "openai"
    key_url = "https://platform.openai.com/api-keys"
    key_note = "Your key; inference cost sits with your account. Prompts use approved projections, never restricted raw payloads. Without it deterministic reports and templates remain available."

    async def enrich(self, entity, user):
        return []

    async def check_connectivity(self, user: str) -> dict:
        result = await check_key(user)
        if not result["ok"]:
            if result.get("error") == "no key":
                from .base import diagnostic_failure
                return diagnostic_failure("missing_credentials")
            raise result["error"]
        return {
            "ok": True,
            "status": "available",
            "detail": "OpenAI is available",
            "diagnostics": {
                "models": result["models"],
                "strong_available": result["strong_available"],
                "fast_available": result["fast_available"],
            },
        }


REGISTRY: list[Connector] = [
    SAMConnector(), SAMExclusionsConnector(), USAspendingConnector(), GLEIFConnector(), LittleSisConnector(), EDGARConnector(), GDELTConnector(),
    OFACConnector(), UNSanctionsConnector(), MarketConnector(), OpenCorporatesConnector(), WebSearchConnector(), OpenAIPseudoConnector(),
]

# Explicit, non-mutating probes. Parameters are intentionally minimal and never
# include user/entity data. "$credential" is substituted inside the connector.
_DIAGNOSTICS = {
    "sam": ("https://api.sam.gov/entity-information/v3/entities", {"api_key": "$credential", "registrationStatus": "A", "legalBusinessName": "a"}),
    "sam_exclusions": ("https://sam.gov/api/prod/fileextractservices/v1/api/listfiles", {"domain": "Exclusions/Public V2", "privacy": "Public"}),
    "usaspending": ("https://api.usaspending.gov/api/v2/references/toptier_agencies/", {}),
    "gleif": ("https://api.gleif.org/api/v1/lei-records", {"page[size]": "1"}),
    "littlesis": ("https://littlesis.org/api/entities/search", {"q": "a"}),
    "edgar": ("https://www.sec.gov/files/company_tickers.json", {}),
    "gdelt": ("https://api.gdeltproject.org/api/v2/doc/doc", {"query": "sourcecountry:US", "mode": "artlist", "format": "json", "maxrecords": "1"}),
    "ofac": ("https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV", {}),
    "un_sanctions": ("https://scsanctions.un.org/resources/xml/en/consolidated.xml", {}),
    "market": ("https://finnhub.io/api/v1/quote", {"symbol": "AAPL", "token": "$credential"}),
    "opencorporates": ("https://api.opencorporates.com/v0.4/companies/search", {"q": "a", "api_token": "$credential", "per_page": "1"}),
}
for _connector in REGISTRY:
    if _connector.name in _DIAGNOSTICS:
        _connector.diagnostic_url, _connector.diagnostic_params = _DIAGNOSTICS[_connector.name]
for _connector in REGISTRY:
    if _connector.name == "websearch":
        # Web search uses the same user-owned OpenAI capability.
        _connector.check_connectivity = OpenAIPseudoConnector.check_connectivity.__get__(_connector, Connector)
_BY_NAME = {c.name: c for c in REGISTRY}


def get_connector(name: str) -> Connector | None:
    return _BY_NAME.get(name)


def connector_names() -> list[str]:
    return [c.name for c in REGISTRY]

def source_metadata(name: str) -> dict:
    """Return a fresh normalized metadata mapping for a connector source."""
    meta = SOURCE_METADATA.get(name, {})
    return {
        "source_id": meta.get("source_id", name),
        "catalog_ids": list(meta.get("catalog_ids", [])),
        "usage_note": meta.get("usage_note"),
        "quality_note": meta.get("quality_note"),
        "supports": meta.get("supports"),
        "unknowns": meta.get("unknowns"),
    }
def capability_kind(name: str) -> str:
    """All registry capabilities are optional to the deterministic judged path."""
    return "model" if name == "openai" else "connector"
