# Interoperability consumer guide

Illuminate's reusable product is a set of versioned findings, not its user
interface or its Neo4j representation. This guide describes how partner teams
should consume the planned public export contract while preserving provenance,
classification, quality, and simulation state.

> **Implementation status:** the versioned export and human-confirmed NDIA
> catalog publisher are available. The publisher validates the official event-3
> dataset metadata shape and supports a dry run until organizer-provided write
> endpoints and a public deployment URL are configured. Use the running
> deployment's OpenAPI document and published export schema as the authority.

## Best-fit consumer journeys

| Partner workflow | Useful exported content | Safe outcome |
| --- | --- | --- |
| Program and logistics planning | supplier and ownership paths, tier, geography, sole-source and concentration findings | Prioritize dependencies for review or contingency planning |
| Vendor due diligence | subject identifiers, risk factors, recommendations, confidence, completeness, and evidence | Build a review queue; do not automate an adverse decision |
| Alternate-source and procurement analysis | affected supplier/category, typed paths, criticality and recommendation | Identify candidates for sourcing research |
| Data fusion and analyst tooling | stable finding IDs, source records, timestamps, truth status, and classifications | Join Illuminate findings to another system without copying the UI graph |

The highest-value joins use stable identifiers carried by the export, such as
UEI, CAGE, LEI, award IDs, and Illuminate finding IDs. Names are display values,
not reliable join keys.

## Field-to-use map

The published JSON Schema is authoritative. Consumers should expect the
versioned contract to represent these concepts even if final property names
differ from the illustrative examples:

| Export concept | Consumer use |
| --- | --- |
| contract/schema version and generation time | Reject unsupported major versions and record when the snapshot was made |
| stable finding and subject identifiers | Idempotent upsert, deduplication, and cross-system joins |
| finding type, severity/risk, recommendation | Routing and prioritization, subject to the handling rules below |
| typed supplier/ownership path | Explain which dependency produced a finding |
| provenance/source records | Show the source identifier, retrieval time, evidence link, license/usage note, and quality note |
| confidence, completeness, and truth/claim status | Distinguish confidence in a supported assertion from gaps in source coverage |
| classification | Enforce the most restrictive handling rule on the finding and its evidence |
| simulation flags | Exclude scenario data from verified-intelligence workflows |
| update time and incremental watermark | Repeatable synchronization without relying on record order |

Do not derive a verified relationship from the frontend subgraph serializer in
`graphio.py`. That shape is optimized for drawing nodes and edges and does not
constitute the durable findings contract. MCP is useful for interactive agents,
but its current tool response is also not a substitute for a complete export:
it summarizes returned subgraph counts.

## Portable retrieval patterns

The following examples use a conventional `/api/exports/v1` prefix only to make
the workflow concrete. Confirm the actual paths and parameters in `/docs`.

### Full JSON page

```http
GET /api/exports/v1/findings?format=json&limit=100
Accept: application/json
```

Response shape (abridged from schema 1.1):

```json
{
  "meta": {
    "schema_version": "1.1",
    "generated_at": "2026-09-08T15:30:00Z",
    "count": 1,
    "limit": 100,
    "next_cursor": "opaque-signed-cursor",
    "watermark": "opaque-signed-watermark"
  },
  "findings": [
    {
      "finding_id": "fnd_…",
      "subject_id": "entity:uei:…",
      "subject_type": "Entity",
      "subject_name": "Example Supplier",
      "predicate": "foreign_ultimate_parent",
      "risk": {"score": 91, "level": "high", "category": "ownership"},
      "recommendation": "Review ownership and sourcing exposure.",
      "paths": [],
      "provenance": [{
        "scope": "claim",
        "source": "GLEIF",
        "source_identifier": "…",
        "retrieved_at": "2026-09-08T13:00:00Z",
        "usage_note": "See source terms",
        "quality_note": "Identifier-backed ownership record"
      }],
      "classification": "UNCLASSIFIED",
      "quality": {"score": 0.91, "completeness": 0.8, "notes": "Tier depth varies"},
      "truth_status": "committed",
      "simulated": false,
      "deleted": false,
      "observed_at": "2026-09-08T14:10:00Z"
    }
  ]
}
```

Treat cursors and watermarks as opaque strings. Follow `next_cursor` until it is
absent, and store the final watermark only after every page has been committed.

### Incremental synchronization

```http
GET /api/exports/v1/findings/incremental?since=opaque%3Aprevious-watermark&limit=100
Accept: application/json
```

An incremental response may contain updates to a previously seen
`finding_id`. Upsert by stable ID; do not append blindly or infer change order
from timestamps. Advance the local watermark atomically after processing all
pages. If the server rejects an expired or incompatible watermark, obtain a new
full snapshot rather than guessing a time range.

### Provenance, classification, and simulation

```json
{
  "finding_id": "fnd_scenario-example",
  "subject_id": "ent_scenario",
  "subject_type": "Entity",
  "predicate": "scenario_dependency",
  "classification": "UNCLASSIFIED",
  "truth_status": "staged",
  "quality": {"score": 1.0, "completeness": 1.0, "notes": "Complete for this scenario only"},
  "simulated": true,
  "provenance": [{
    "source": "Illuminate demo scenario",
    "confidence": 1.0,
    "quality_note": "Synthetic relationship; not source-verified"
  }]
}
```

`provenance.confidence: 1.0` in this example means the scenario was encoded
deterministically; it does **not** make the scenario true. Simulation and truth
status take precedence over confidence. Preserve these fields through every
transform, including CSV or a data warehouse. Use canonical JSON or NDJSON when
a convenience format cannot represent nested paths and provenance losslessly.

## Catalog datasets and the official interoperability criterion

Illuminate intentionally uses a narrow catalog slice rather than expanding into
unrelated event challenges:

| NDIA catalog dataset | Illuminate use |
| --- | --- |
| **1 — Federal Spending Data** | Primary award, recipient, obligation, sub-award, agency, NAICS/PSC, and competition evidence, consumed through USAspending |
| **49 — Government Contract Award Data** | SAM.gov reference source for supplier identity, registration, and contract validation; the demo must not depend on a login-gated live call |
| **62 — GDELT 2.0 — Global Knowledge Graph and Events** | Adverse-media/event evidence, using a cached representative result for a deterministic demo |

Ownership and screening are supplemented by challenge-named or public sources
including OpenCorporates, GLEIF, SEC EDGAR, LittleSis, OFAC SDN, the UN Security
Council Consolidated List, and SAM exclusions.
Each source supports only the claims evidenced by its own records.

The catalog contribution is a reusable, schema-valid Illuminate findings
dataset for event ID 3. It is previewed, explicitly confirmed, submitted
server-side, and tracked by export identity/version and returned remote dataset
ID. A dry run demonstrates the same metadata when portal access or write
permission is unavailable. Until submission succeeds and a catalog identity is
returned, describe it as a **planned or validated-dry-run contribution**, not a
published dataset.

This satisfies the official 1% interoperability criterion narrowly: Illuminate
consumes catalog datasets 1, 49, and 62 and makes derived findings retrievable by
another team without the Illuminate UI. It does not claim integration with all
event datasets or implementation of a partner application.

## Required handling and safe-use rules

1. **Enforce classification first.** Apply the most restrictive classification
   and source-use rule in a finding. Do not assume the deployment, transport, or
   catalog entry is an authorization boundary.
2. **Never strip provenance.** Keep source identifiers, retrieval time,
   license/usage notes, quality notes, and evidence references with the finding.
   A finding without its lineage is incomplete.
3. **Keep lifecycle state.** Staged, rejected, disputed, or scenario claims must
   not be promoted to approved findings. A recommendation is decision support,
   not a verified accusation.
4. **Keep simulation contagious.** If any material node, relationship, or
   evidence item on the derivation path is simulated, the resulting finding
   remains simulated. Do not relabel it by joining it to real data.
5. **Do not confuse confidence and completeness.** Confidence describes support
   for a particular assertion; completeness describes coverage. High confidence
   does not prove that no undiscovered suppliers, owners, events, or risks exist.
6. **Expect uneven coverage.** Sub-award depth varies by program, people data is
   biased toward prominent firms, SAM.gov details may be rate-limited, and
   adverse-media matches require analyst review.
7. **Use stable IDs, not names.** Fuzzy entity matches are leads with method and
   confidence. Never turn a name-only match into an automated adverse action.
8. **Minimize redistribution.** Do not export secrets or restricted raw source
   payloads. Respect each provenance record's license and usage terms.

## Deployment-neutral operation

The contract is the same in Docker and Replit. Consumers configure only the API
base URL:

```bash
# Docker example
ILLUMINATE_BASE_URL=http://localhost:8000

# Replit example: use the API URL exposed by the running Replit workflow
ILLUMINATE_BASE_URL=https://your-runtime-host.example

curl -fsS "$ILLUMINATE_BASE_URL/api/exports/v1/findings?limit=100"
```

Do not hardcode container names, Neo4j addresses, Replit development domains, or
frontend URLs into a consumer. Discover the live contract at
`$ILLUMINATE_BASE_URL/docs`, negotiate the published schema version, use HTTPS
outside a local machine, and apply the same authentication and classification
controls in either deployment.