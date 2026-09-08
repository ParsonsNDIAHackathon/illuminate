# Product Data and Software Bill of Materials

Inventory as of **2026-09-08**. Inventory information only, not legal advice. Verify upstream terms and pricing for the intended use.

**Supported runtime profile:** Linux CPython 3.12+ and Node.js 20+; conditional requiredness is evaluated for Linux CPython 3.12.

The JSON contract at [`docs/bom.json`](bom.json) is authoritative. Generated facts (IDs, resolved
versions, dependency class, and declaration membership) come from lockfiles and runtime/source
declarations. Licensing, costs, operational impacts, and mitigations are curated assessments.
Values marked `REVIEW_REQUIRED`, variable, or custom-contract are deliberately unresolved.

Validate with `make validate-bom`; regenerate this view with `make generate-bom`.

## Data sources

### Federal Spending (`usaspending.gov`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for procurement, supplier_identity
- **Coverage / limits:** Agency-submitted prime/subaward data may be delayed or omit lower tiers.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.usaspending.gov/about/our-data)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 7 days; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Federal Spending evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### NASA FIRMS (`nasa-firms`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for climate, facility, event
- **Coverage / limits:** Fire detections require coordinates and do not prove facility damage.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.earthdata.nasa.gov/data/tools/firms/faq)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** read-only FIRMS API; credentials/rate limits: NASA FIRMS MAP_KEY
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** 24 hours; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** NASA FIRMS evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Implement a bounded facility-coordinate adapter, then configure its FIRMS MAP_KEY.
- **Review:** `review_required`

### Global Maritime Pirate Attacks (`nga-pirate-attacks`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for logistics, route, event
- **Coverage / limits:** The catalog item has no reviewed bounded machine API for contextual route queries.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://msi.nga.mil/)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** source publication cycle; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Global Maritime Pirate Attacks evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Configure a reviewed NGA download URL and parser; do not scrape the portal.
- **Review:** `review_required`

### Budget Justification Books (`dod-budget-justification`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for program, budget
- **Coverage / limits:** Published books are document collections, not a stable entity-query API.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://comptroller.defense.gov/Budget-Materials/)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** annual; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Budget Justification Books evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Provide a program budget-line identifier and reviewed document manifest.
- **Review:** `review_required`

### Deep Sea Minerals (`deep-sea-minerals`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for critical_material, location
- **Coverage / limits:** No safe mapping exists without a material, deposit, or geographic context.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** publication cycle; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Deep Sea Minerals evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Attach a material identifier or geographic area and a reviewed USGS dataset endpoint.
- **Review:** `review_required`

### FEMA Supply Chain Climate Resilience (`fema-climate-resilience`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for climate, guidance
- **Coverage / limits:** Guidance is not an observational feed and cannot establish entity-specific risk.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.fema.gov/about/website-information)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** publication cycle; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** FEMA Supply Chain Climate Resilience evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Use as methodology only, or provide a facility hazard identifier.
- **Review:** `review_required`

### Global Tropical Cyclone Tracks (`ibtracs`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for climate, event, route
- **Coverage / limits:** The reviewed source is a large bulk archive; no bounded contextual adapter is configured.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.ncei.noaa.gov/products/international-best-track-archive)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** 3 hours to annual archive; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Global Tropical Cyclone Tracks evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Configure an approved IBTrACS subset service or local spatial index.
- **Review:** `review_required`

### Government Contract Award Data (`sam-entity-management`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for procurement, supplier_identity
- **Coverage / limits:** Registration is self-reported and personal keys have a small daily quota.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://sam.gov/content/terms-and-conditions)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** read-only SAM.gov API; credentials/rate limits: SAM.gov personal API key; provider/account limits apply and must be reviewed
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 24 hours; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Government Contract Award Data evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Add a SAM.gov personal API key in connector settings.
- **Review:** `review_required`

### World Port Index (`world-port-index`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for logistics, port, route
- **Coverage / limits:** The public source is a bulk publication without a reviewed bounded query endpoint.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://msi.nga.mil/)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** source publication cycle; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** World Port Index evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Configure a reviewed WPI download and local spatial index.
- **Review:** `review_required`

### NASA Earthdata (`nasa-earthdata`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for climate, earth_observation
- **Coverage / limits:** Earthdata is a catalog of collections; applicability requires a collection and geometry.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.earthdata.nasa.gov/engage/open-data-services-and-software/data-and-information-policy)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** read-only CMR/Earthdata APIs; credentials/rate limits: Earthdata Login token for protected collections
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** collection-specific; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** NASA Earthdata evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Implement a bounded collection-and-geometry adapter, then configure Earthdata credentials if required.
- **Review:** `review_required`

### U.S. Climate Normals (`noaa-climate-normals`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for climate, facility
- **Coverage / limits:** Normals describe historical climate, not forecasts or realized facility impact.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.noaa.gov/disclaimer)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** read-only NOAA CDO API; credentials/rate limits: NOAA CDO token
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** decennial normals; daily source updates; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** U.S. Climate Normals evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Implement a bounded station/coordinate adapter, then configure a NOAA CDO token.
- **Review:** `review_required`

### GDELT (`gdelt-2.x`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for adverse_media, event
- **Coverage / limits:** Automated matching, translation, tone, and coverage can be incorrect or incomplete.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.gdeltproject.org/about.html)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 15 minutes; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** GDELT evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### ACLED (`acled`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for event, geopolitical, route
- **Coverage / limits:** Reported-event coverage varies and does not prove impact on a supplier or route.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://acleddata.com/terms-of-use)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** read-only ACLED API; credentials/rate limits: ACLED account email and access key
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** weekly; source dependent; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** ACLED evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Implement a bounded geographic-event adapter, then configure ACLED credentials.
- **Review:** `review_required`

### NOAA Marine Cadastre AIS (`noaa-marine-cadastre-ais`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for logistics, route, vessel
- **Coverage / limits:** Historical AIS is distributed as very large bulk files, not a bounded live route API.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://coast.noaa.gov/disclaimer/)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** annual bulk releases; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** NOAA Marine Cadastre AIS evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Configure an approved regional/time-bounded AIS index.
- **Review:** `review_required`

### Overture Maps (`overture-maps`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for facility, location, logistics
- **Coverage / limits:** Cloud-native bulk data needs a release-pinned spatial query engine not present here.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://docs.overturemaps.org/attribution/)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only cloud object data; credentials/rate limits: none
- **Cost (2026-09-08):** Unavailable/not integrated; future provider cost REVIEW_REQUIRED
- **Freshness/storage:** monthly release; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Overture Maps evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Configure a release-pinned GeoParquet query service.
- **Review:** `review_required`

### OpenStreetMap (`openstreetmap`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for facility, location, logistics
- **Coverage / limits:** Community map data and reverse-geocoded nearby features do not prove ownership or operation.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.openstreetmap.org/copyright)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 7 days; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** OpenStreetMap evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### FAR Part 52 (`ecfr-title-48`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for regulatory, procurement
- **Coverage / limits:** Retrieval verifies cited clause text exists; legal applicability still requires contract review.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.ecfr.gov/reader-aids/government-policy-and-ofr-procedures/developer-resources)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 24 hours; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** FAR Part 52 evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### FIRST EPSS (`first-epss`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for cyber, vulnerability
- **Coverage / limits:** EPSS estimates exploitation probability; it does not prove exposure, compromise, or asset ownership.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.first.org/epss/model)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 24 hours; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** FIRST EPSS evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### SAM.gov Exclusions (`sam-exclusions-public-extract`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for sanctions, exclusions
- **Coverage / limits:** Results are only as current as the cached public extract.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://sam.gov/content/terms-and-conditions)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 24 hours; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** SAM.gov Exclusions evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### GLEIF LEI (`gleif-lei`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for supplier_identity, ownership
- **Coverage / limits:** Reported accounting parents are not necessarily beneficial owners.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.gleif.org/en/lei-data/gleif-data-terms-of-use)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 7 days; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** GLEIF LEI evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### SEC EDGAR (`sec-edgar`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for ownership, financial, regulatory
- **Coverage / limits:** Private entities and undisclosed relationships are outside EDGAR coverage.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://www.sec.gov/about/privacy-information#security)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 24 hours; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** SEC EDGAR evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### OFAC SDN (`ofac-sdn`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for sanctions
- **Coverage / limits:** Name matching needs identifier-based review and does not implement legal ownership analysis.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://ofac.treasury.gov/ofac-list-service)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 24 hours; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** OFAC SDN evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### OpenCorporates (`opencorporates`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for supplier_identity, ownership
- **Coverage / limits:** Registry coverage and freshness vary by jurisdiction.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://opencorporates.com/info/licence)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** read-only API; credentials/rate limits: OpenCorporates API token; provider/account limits apply and must be reviewed
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 7 days; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** OpenCorporates evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Add an OpenCorporates API token.
- **Review:** `review_required`

### LittleSis (`littlesis`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for ownership, lead
- **Coverage / limits:** Community-maintained relationships are investigative leads, not proof.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://littlesis.org/about)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** public read-only HTTPS; credentials/rate limits: none
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 7 days; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** LittleSis evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Continue without this optional source and show coverage limitations
- **Review:** `review_required`

### Finnhub market data (`finnhub`)

- **Class / required:** external-data; optional
- **Purpose:** Optional evidence capability for financial
- **Coverage / limits:** Only listed entities with a ticker apply; free-tier quotes may be delayed.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://finnhub.io/terms-of-service)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** read-only API; credentials/rate limits: Finnhub API key; provider/account limits apply and must be reviewed
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** 15 minutes; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Finnhub market data evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Add a Finnhub key and entity ticker.
- **Review:** `review_required`

### OpenAI API (`openai`)

- **Class / required:** model/API; optional
- **Purpose:** Optional evidence capability for model
- **Coverage / limits:** Optional model output is non-authoritative and usage is account-billed.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://openai.com/policies/service-terms/)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** user-owned API account; credentials/rate limits: OpenAI API key; provider/account limits apply and must be reviewed
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** request time; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** OpenAI API evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Configure an OpenAI key; deterministic workflows remain available.
- **Review:** `review_required`

### OpenAI-backed web search (`websearch`)

- **Class / required:** model/API; optional
- **Purpose:** Optional evidence capability for web_search
- **Coverage / limits:** Optional model output is non-authoritative and usage is account-billed.
- **Terms/license:** [Provider terms apply; REVIEW_REQUIRED before new redistribution or production use](https://openai.com/policies/service-terms/)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** user-owned API account; credentials/rate limits: OpenAI API key; provider/account limits apply and must be reviewed
- **Cost (2026-09-08):** Public/free or account-billed depending on provider tier; variable pricing REVIEW_REQUIRED
- **Freshness/storage:** request time; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** OpenAI-backed web search evidence/enrichment is unavailable; core deterministic graph remains usable
- **Fallback:** Configure an OpenAI key; deterministic workflows remain available.
- **Review:** `review_required`

### Committed offline fixture bundle (`fixture-bundle`)

- **Class / required:** bundled/fixture; required
- **Purpose:** Deterministic offline startup and judged demonstration
- **Coverage / limits:** Snapshots become stale and cover only the deterministic demonstration path.
- **Terms/license:** [Bundled snapshots retain each upstream source's terms and attribution; review before redistribution](api/illuminate/seed/fixtures/)
- **Attribution/redistribution:** Preserve source URL, retrieval time, and provider attribution; redistribution rights REVIEW_REQUIRED
- **Access:** bundled with source checkout; credentials/rate limits: none
- **Cost (2026-09-08):** Bundled; no per-request fee
- **Freshness/storage:** point-in-time retrieval timestamps in fixture records; cached records retain provenance; storage/retention terms REVIEW_REQUIRED
- **If omitted:** Offline deterministic mission data and startup readiness are unavailable
- **Fallback:** Refresh through reviewed connectors and preserve provenance before replacing snapshots.
- **Review:** `review_required`

## Software components

| Component | Resolved version | Supplier | Class | License | Required | Review | Scope / omission path |
|---|---:|---|---|---|:---:|---|---|
| `pypi:annotated-doc` | `0.0.5` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/annotated-doc/0.0.5/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:annotated-types` | `0.8.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/annotated-types/0.8.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:anyio` | `4.15.1` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/anyio/4.15.1/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:attrs` | `26.1.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/attrs/26.1.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:certifi` | `2026.7.22` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/certifi/2026.7.22/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:cffi` | `2.1.1` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/cffi/2.1.1/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:click` | `8.5.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/click/8.5.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:colorama` | `0.4.6` | PyPI project maintainers | optional | [REVIEW_REQUIRED](https://pypi.org/project/colorama/0.4.6/) | no | `review_required` | optional pypi component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:cryptography` | `50.0.1` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/cryptography/50.0.1/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:fastapi` | `0.141.1` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/fastapi/0.141.1/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:h11` | `0.16.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/h11/0.16.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:httpcore` | `1.0.9` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/httpcore/1.0.9/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:httpcore2` | `2.12.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/httpcore2/2.12.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:httptools` | `0.8.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/httptools/0.8.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:httpx` | `0.28.1` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/httpx/0.28.1/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:httpx2` | `2.12.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/httpx2/2.12.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:httpx2-jsfetch` | `1.0` | PyPI project maintainers | optional | [REVIEW_REQUIRED](https://pypi.org/project/httpx2-jsfetch/1.0/) | no | `review_required` | optional pypi component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:idna` | `3.19` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/idna/3.19/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:iniconfig` | `2.3.0` | PyPI project maintainers | development-only | [REVIEW_REQUIRED](https://pypi.org/project/iniconfig/2.3.0/) | no | `review_required` | development-only pypi component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:jiter` | `0.16.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/jiter/0.16.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:jsonschema` | `4.26.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/jsonschema/4.26.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:jsonschema-specifications` | `2025.9.1` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/jsonschema-specifications/2025.9.1/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:mcp` | `2.2.0` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/mcp/2.2.0/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:mcp-types` | `2.2.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/mcp-types/2.2.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:neo4j` | `6.3.0` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/neo4j/6.3.0/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:openai` | `3.8.0` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/openai/3.8.0/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:opentelemetry-api` | `1.44.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/opentelemetry-api/1.44.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:packaging` | `26.3` | PyPI project maintainers | development-only | [REVIEW_REQUIRED](https://pypi.org/project/packaging/26.3/) | no | `review_required` | development-only pypi component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pluggy` | `1.6.0` | PyPI project maintainers | development-only | [REVIEW_REQUIRED](https://pypi.org/project/pluggy/1.6.0/) | no | `review_required` | development-only pypi component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pycparser` | `3.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/pycparser/3.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pydantic` | `2.13.5` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/pydantic/2.13.5/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pydantic-core` | `2.46.5` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/pydantic-core/2.46.5/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pydantic-settings` | `2.15.0` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/pydantic-settings/2.15.0/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pygments` | `2.21.0` | PyPI project maintainers | development-only | [REVIEW_REQUIRED](https://pypi.org/project/pygments/2.21.0/) | no | `review_required` | development-only pypi component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pyjwt` | `2.13.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/pyjwt/2.13.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pytest` | `9.1.1` | PyPI project maintainers | development-only | [REVIEW_REQUIRED](https://pypi.org/project/pytest/9.1.1/) | no | `review_required` | development-only pypi component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pytest-asyncio` | `1.4.0` | PyPI project maintainers | development-only | [REVIEW_REQUIRED](https://pypi.org/project/pytest-asyncio/1.4.0/) | no | `review_required` | development-only pypi component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:python-dotenv` | `1.2.3` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/python-dotenv/1.2.3/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:python-multipart` | `0.0.32` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/python-multipart/0.0.32/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pytz` | `2026.3.post1` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/pytz/2026.3.post1/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pywin32` | `312` | PyPI project maintainers | optional | [REVIEW_REQUIRED](https://pypi.org/project/pywin32/312/) | no | `review_required` | optional pypi component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:pyyaml` | `6.0.3` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/pyyaml/6.0.3/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:rapidfuzz` | `3.14.6` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/rapidfuzz/3.14.6/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:referencing` | `0.37.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/referencing/0.37.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:rpds-py` | `2026.6.3` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/rpds-py/2026.6.3/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:sniffio` | `1.3.1` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/sniffio/1.3.1/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:sse-starlette` | `3.4.11` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/sse-starlette/3.4.11/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:starlette` | `1.6.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/starlette/1.6.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:truststore` | `0.10.4` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/truststore/0.10.4/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:typing-extensions` | `4.16.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/typing-extensions/4.16.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:typing-inspection` | `0.4.4` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/typing-inspection/0.4.4/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:uvicorn` | `0.52.4` | PyPI project maintainers | direct | [REVIEW_REQUIRED](https://pypi.org/project/uvicorn/0.52.4/) | yes | `review_required` | direct pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:uvloop` | `0.22.1` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/uvloop/0.22.1/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:watchfiles` | `1.2.0` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/watchfiles/1.2.0/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:websockets` | `17.1` | PyPI project maintainers | transitive | [REVIEW_REQUIRED](https://pypi.org/project/websockets/17.1/) | yes | `review_required` | transitive pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@babel/helper-string-parser@7.29.7` | `7.29.7` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@babel/helper-validator-identifier@7.29.7` | `7.29.7` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@babel/parser@7.29.8` | `7.29.8` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@babel/types@7.29.8` | `7.29.8` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@bufbuild/protobuf@2.14.1` | `2.14.1` | npm package maintainers | optional | [(Apache-2.0 AND BSD-3-Clause)](https://spdx.org/licenses/Apache-2.0.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/aix-ppc64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/android-arm@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/android-arm64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/android-x64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/darwin-arm64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/darwin-x64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/freebsd-arm64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/freebsd-x64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-arm@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-arm64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-ia32@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-loong64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-mips64el@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-ppc64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-riscv64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-s390x@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/linux-x64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/netbsd-arm64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/netbsd-x64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/openbsd-arm64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/openbsd-x64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/openharmony-arm64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/sunos-x64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/win32-arm64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/win32-ia32@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@esbuild/win32-x64@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@jridgewell/sourcemap-codec@1.6.0` | `1.6.0` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@mdi/font@7.4.47` | `7.4.47` | npm package maintainers | frontend-asset | [Apache-2.0](https://spdx.org/licenses/Apache-2.0.html) | yes | `lockfile_reviewed` | frontend-asset npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@napi-rs/lzma-linux-x64-gnu@1.5.1` | `1.5.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-android-arm64@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-darwin-arm64@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-darwin-x64@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-freebsd-x64@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-linux-arm-glibc@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-linux-arm-musl@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-linux-arm64-glibc@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-linux-arm64-musl@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-linux-x64-glibc@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-linux-x64-musl@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-win32-arm64@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@parcel/watcher-win32-x64@2.6.0` | `2.6.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-android-arm-eabi@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-android-arm64@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-darwin-arm64@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-darwin-x64@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-freebsd-arm64@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-freebsd-x64@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-arm-gnueabihf@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-arm-musleabihf@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-arm64-gnu@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-arm64-musl@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-loong64-gnu@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-loong64-musl@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-ppc64-gnu@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-ppc64-musl@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-riscv64-gnu@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-riscv64-musl@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-s390x-gnu@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-x64-gnu@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-linux-x64-musl@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-openbsd-x64@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-openharmony-arm64@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-win32-arm64-msvc@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-win32-ia32-msvc@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-win32-x64-gnu@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@rollup/rollup-win32-x64-msvc@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@types/cytoscape@3.21.9` | `3.21.9` | npm package maintainers | development-only | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | development-only npm component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@types/estree@1.0.9` | `1.0.9` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vitejs/plugin-vue@5.2.4` | `5.2.4` | npm package maintainers | development-only | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | development-only npm component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/compiler-core@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/compiler-dom@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/compiler-sfc@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/compiler-ssr@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/devtools-api@7.7.10` | `7.7.10` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/devtools-kit@7.7.10` | `7.7.10` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/devtools-shared@7.7.10` | `7.7.10` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/reactivity@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/runtime-core@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/runtime-dom@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/server-renderer@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/shared@3.5.42` | `3.5.42` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vuetify/loader-shared@2.1.2` | `2.1.2` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:birpc@2.9.0` | `2.9.0` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:chokidar@5.0.0` | `5.0.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:colorjs.io@0.7.1` | `0.7.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:copy-anything@4.1.0` | `4.1.0` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:cose-base@2.2.0` | `2.2.0` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:csstype@3.2.3` | `3.2.3` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:cytoscape@3.34.3` | `3.34.3` | npm package maintainers | direct | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | direct npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:cytoscape-cola@2.5.1` | `2.5.1` | npm package maintainers | direct | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | direct npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:cytoscape-fcose@2.2.0` | `2.2.0` | npm package maintainers | direct | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | direct npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:d3-dispatch@1.0.6` | `1.0.6` | npm package maintainers | transitive | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:d3-drag@1.2.5` | `1.2.5` | npm package maintainers | transitive | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:d3-path@1.0.9` | `1.0.9` | npm package maintainers | transitive | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:d3-selection@1.4.2` | `1.4.2` | npm package maintainers | transitive | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:d3-shape@1.3.7` | `1.3.7` | npm package maintainers | transitive | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:d3-timer@1.0.10` | `1.0.10` | npm package maintainers | transitive | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:debug@4.4.3` | `4.4.3` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:detect-libc@2.1.2` | `2.1.2` | npm package maintainers | optional | [Apache-2.0](https://spdx.org/licenses/Apache-2.0.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:entities@7.0.1` | `7.0.1` | npm package maintainers | transitive | [BSD-2-Clause](https://spdx.org/licenses/BSD-2-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:esbuild@0.25.12` | `0.25.12` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:estree-walker@2.0.2` | `2.0.2` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:fdir@6.5.0` | `6.5.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:fsevents@2.3.3` | `2.3.3` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:has-flag@4.0.0` | `4.0.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:hookable@5.5.3` | `5.5.3` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:immutable@5.1.9` | `5.1.9` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:is-extglob@2.1.1` | `2.1.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:is-glob@4.0.3` | `4.0.3` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:layout-base@2.0.1` | `2.0.1` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:magic-string@0.30.21` | `0.30.21` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:mitt@3.0.1` | `3.0.1` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:ms@2.1.3` | `2.1.3` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:nanoid@3.3.18` | `3.3.18` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:node-addon-api@7.1.1` | `7.1.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:perfect-debounce@1.0.0` | `1.0.0` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:picocolors@1.1.1` | `1.1.1` | npm package maintainers | transitive | [ISC](https://spdx.org/licenses/ISC.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:picomatch@4.0.7` | `4.0.7` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:pinia@3.0.4` | `3.0.4` | npm package maintainers | direct | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | direct npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:postcss@8.5.28` | `8.5.28` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:readdirp@5.1.1` | `5.1.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:rfdc@1.4.1` | `1.4.1` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:rollup@4.63.1` | `4.63.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:rxjs@7.8.2` | `7.8.2` | npm package maintainers | optional | [Apache-2.0](https://spdx.org/licenses/Apache-2.0.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded@1.104.0` | `1.104.0` | npm package maintainers | development-only | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | development-only npm component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-all-unknown@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-android-arm@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-android-arm64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-android-riscv64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-android-x64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-darwin-arm64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-darwin-x64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-linux-arm@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-linux-arm64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-linux-musl-arm@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-linux-musl-arm64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-linux-musl-riscv64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-linux-musl-x64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-linux-riscv64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-linux-x64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-unknown-all@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-win32-arm64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sass-embedded-win32-x64@1.104.0` | `1.104.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:source-map-js@1.2.1` | `1.2.1` | npm package maintainers | transitive | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:speakingurl@14.0.1` | `14.0.1` | npm package maintainers | transitive | [BSD-3-Clause](https://spdx.org/licenses/BSD-3-Clause.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:superjson@2.2.6` | `2.2.6` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:supports-color@8.1.1` | `8.1.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sync-child-process@1.0.2` | `1.0.2` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:sync-message-port@1.2.0` | `1.2.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:tinyglobby@0.2.17` | `0.2.17` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:tslib@2.8.1` | `2.8.1` | npm package maintainers | optional | [0BSD](https://www.npmjs.com/package/tslib/v/2.8.1) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:typescript@5.9.3` | `5.9.3` | npm package maintainers | development-only | [Apache-2.0](https://spdx.org/licenses/Apache-2.0.html) | no | `lockfile_reviewed` | development-only npm component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:upath@2.0.1` | `2.0.1` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:varint@6.0.0` | `6.0.0` | npm package maintainers | optional | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | optional npm component resolved from repository declarations. Only the platform-specific optional installation is affected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:vite@6.4.3` | `6.4.3` | npm package maintainers | development-only | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | development-only npm component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:vite-plugin-vuetify@2.1.3` | `2.1.3` | npm package maintainers | development-only | [MIT](https://spdx.org/licenses/MIT.html) | no | `lockfile_reviewed` | development-only npm component resolved from repository declarations. Development/build checks may be unavailable Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:vue@3.5.42` | `3.5.42` | npm package maintainers | direct | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | direct npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:vue-router@4.6.4` | `4.6.4` | npm package maintainers | direct | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | direct npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:@vue/devtools-api@6.6.4` | `6.6.4` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:vuetify@3.13.3` | `3.13.3` | npm package maintainers | direct | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | direct npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `npm:webcola@3.4.0` | `3.4.0` | npm package maintainers | transitive | [MIT](https://spdx.org/licenses/MIT.html) | yes | `lockfile_reviewed` | transitive npm component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `image:neo4j:5@sha256:037cf5756f0135cbfd66b739b6df7c7c4bb100f9ce11602f6f9538e17e02c74d` | `5@sha256:037cf5756f0135cbfd66b739b6df7c7c4bb100f9ce11602f6f9538e17e02c74d` | Neo4j, Inc. | database | [Composite container contents; REVIEW_REQUIRED](https://hub.docker.com/_/neo4j) | yes | `review_required` | database image component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `image:nginx:alpine@sha256:72ba65eb42c10344912a84ff42408db7d34f2feb642204570ab8fc5ffd29f1d3` | `alpine@sha256:72ba65eb42c10344912a84ff42408db7d34f2feb642204570ab8fc5ffd29f1d3` | Official container image maintainers | container-image | [Composite container contents; REVIEW_REQUIRED](https://hub.docker.com/_/nginx) | yes | `review_required` | container-image image component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `image:node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32` | `22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32` | Official container image maintainers | container-image | [Composite container contents; REVIEW_REQUIRED](https://hub.docker.com/_/node) | yes | `review_required` | container-image image component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `image:python:3.12-alpine@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a` | `3.12-alpine@sha256:b64631e04e4920160c50fbe8d8df828f7f35f06f425cb44aa09bca53e708a35a` | Official container image maintainers | container-image | [Composite container contents; REVIEW_REQUIRED](https://hub.docker.com/_/python) | yes | `review_required` | container-image image component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `image:python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea` | `3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea` | Official container image maintainers | container-image | [Composite container contents; REVIEW_REQUIRED](https://hub.docker.com/_/python) | yes | `review_required` | container-image image component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `plugin:apoc` | `image-managed by neo4j:5@sha256:037cf5756f0135cbfd66b739b6df7c7c4bb100f9ce11602f6f9538e17e02c74d` | Neo4j, Inc. | database-plugin | [Apache-2.0](https://github.com/neo4j/apoc/blob/5.26/LICENSE.txt) | yes | `curated_reviewed` | database-plugin plugin component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `service:restore` | `repository revision` | Illuminate project | runtime-service | [Project source license not declared; REVIEW_REQUIRED](REVIEW_REQUIRED) | yes | `review_required` | runtime-service service component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `service:backup` | `repository revision` | Illuminate project | runtime-tool | [Project source license not declared; REVIEW_REQUIRED](REVIEW_REQUIRED) | no | `review_required` | runtime-tool service component resolved from repository declarations. Manual portable backup creation is unavailable; normal application runtime is unaffected Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `service:neo4j` | `repository revision` | Illuminate project | runtime-service | [Project source license not declared; REVIEW_REQUIRED](REVIEW_REQUIRED) | yes | `review_required` | runtime-service service component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `service:api` | `repository revision` | Illuminate project | runtime-service | [Project source license not declared; REVIEW_REQUIRED](REVIEW_REQUIRED) | yes | `review_required` | runtime-service service component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `service:web` | `repository revision` | Illuminate project | runtime-service | [Project source license not declared; REVIEW_REQUIRED](REVIEW_REQUIRED) | yes | `review_required` | runtime-service service component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `runtime:neo4j-native` | `5.x Nix package; exact deployment derivation REVIEW_REQUIRED` | Neo4j, Inc. | database | [GPL-3.0-only / commercial terms REVIEW_REQUIRED](https://neo4j.com/licensing/) | yes | `review_required` | database runtime component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |
| `pypi:uv-build-tool` | `0.9.24` | PyPI project maintainers | build-tool | [Apache-2.0 OR MIT](https://github.com/astral-sh/uv/tree/0.9.24#license) | yes | `curated_reviewed` | build-tool pypi component resolved from repository declarations. Application build or the dependent runtime capability fails Replacement: Remove or replace the depending feature and regenerate the lockfile and BOM in the same change |

### Software cost and support

Each software row records: Open-source/community component; no support entitlement bundled; hosting and support costs are operator-dependent.
Supplier/project and review status remain available in the machine-readable JSON.
