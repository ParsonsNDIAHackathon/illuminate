# Integration and Operations Review

Date: 2026-09-08

## Scope and mode under test

This review adopted two supporting personas:

- **Partner data engineer** — technically capable, new to Illuminate, and responsible for consuming findings without losing lifecycle or evidence semantics.
- **Deployment/data operator** — responsible for database and source readiness, credentials, refreshes, safe publication, and recovery without exposing secrets.

The running Replit workflow was evaluated in its current **deterministic offline/scenario seed mode**. The live health response reported:

- required database and seed ready;
- 1,848 nodes and 1,809 relationships;
- seed version `uc7-fixtures-v1`, with offline and scenario flags set;
- primary workflow ready;
- operational live readiness false and a live refresh required;
- global freshness unknown;
- optional connector status reported separately from required readiness.

No destructive NDIA submission, private-data retrieval, or optional-service requirement was introduced during the review.

## Integration persona outcome

### Result

**Pass with one medium-priority policy gap.**

A new partner can discover the contract from the in-product interoperability page, the consumer guide, OpenAPI, field dictionary, JSON Schema, and sample endpoint. The running export returned schema version `1.1`, a bounded page, an opaque signed watermark, and matching response headers. The empty page was truthful for the currently exportable dataset rather than populated with placeholder findings.

### Validated capabilities

- The UI identifies the export, available JSON/NDJSON/CSV formats, page bound, pagination state, schema version, and opaque watermark.
- The consumer guide explains stable identifiers, idempotent upserts, signed cursors and watermarks, atomic watermark advancement, and full resynchronization after an invalid watermark.
- The schema carries classification, truth status, simulation, provenance, typed paths, quality, completeness, recommendation, and deletion state.
- Simulation is contagious across material path participants and remains distinct from confidence.
- Full exports omit rejected findings by default, classify public records explicitly, and keep the graph drawing projection outside the durable partner contract.
- The catalog preview describes event 3, export identity/version/watermark, metadata, credential and operator-authorization configuration, publication readiness, contribution state, and remote dataset identity.
- The live preview reported `not_submitted`, no remote dataset ID, and `publication_ready: false`. The Settings UI repeated that no remote dataset was recorded and disabled live publication while dry-run validation remained available.
- Dry-run and live publication have distinct behavior. Live publication requires an exact reviewed preview, a short-lived signed confirmation, server-side credential, operator authorization, public URL, configured write path, and idempotent/reconciled remote identity.
- Portal failures are sanitized; uncertain outcomes block automatic duplicate submission.
- Public-network and authorization boundaries are explicit: consumers use the configured API base URL, while secrets and catalog writes stay server-side.

### Validated gap

#### Medium — routine incremental sync includes rejected findings by default

The full endpoint defaults to excluding rejected records, while the incremental endpoint defaults to including them. A partner following the ordinary incremental example can ingest rejected intelligence without knowingly opting into review-state reconciliation.

Follow-up: **Task #131 (Keep rejected findings out of routine partner syncs)**.

## Operator persona outcome

### Result

**Pass with two medium-priority clarity/reliability gaps.**

The backend contract gives an operator enough truthful data to distinguish required startup readiness, deterministic seed readiness, operational live readiness, source freshness, source coverage, optional-service status, and recovery action. Connector and catalog pages preserve secret boundaries and clearly show credential, diagnostic, source-access, dry-run, and publication states.

The human-facing operator handoff is fragmented, however: full readiness is summarized in the analyst mission rather than Administration, and model settings save without visible confirmation or failure.

### Validated capabilities

- Required database/seed state is separate from optional connectors and models.
- A ready deterministic workflow is not mislabeled as operationally live; the running response truthfully reported that live refresh was still required.
- Offline/scenario seed state is explicit in the health API.
- Freshness uses recorded successful live retrievals rather than cache ingestion time.
- Source records expose status, record count, latest successful retrieval, cache/unknown state, simulation flag, sanitized reason, and recovery action.
- Optional connector probes are bounded and degrade independently.
- Connector credentials are entered as passwords, stored outside prompts, and never returned in clear text. Diagnostics show only safe details.
- Approved-source coverage shows policy state, limitations, freshness, access, adapter availability, and operator action.
- Catalog metadata displays planned/dry-run/published state separately and never treats deployment or transport as an authorization boundary.
- Required database failure makes readiness unavailable, while optional-service failures preserve deterministic operation.
- Recovery guidance exists for seed rebuild, readiness retry, source refresh, and uncertain catalog outcomes.

### Validated gaps

#### Medium — model configuration can appear saved after a failed request

Model names and the optional compatible base URL save silently on blur. There is no busy, success, or failure state, so an operator cannot tell whether the persisted deployment configuration matches the visible edited value.

Follow-up: **Task #132 (Tell operators whether model settings were saved)**.

#### Medium — no operator-focused deployment readiness destination

Administration presents connector and catalog state but not required database/seed readiness, offline/scenario mode, operational refresh requirement, or the complete sanitized recovery guidance. Those details are available through the health API and partially summarized inside the analyst-oriented mission page, requiring operators to know where to look.

Follow-up: **Task #133 (Give operators one place to assess deployment readiness)**.

## Existing work referenced, not duplicated

- **Task #45 (Verify a connector automatically after its credential is saved)** covers connector save-and-test behavior.
- **Task #46 (Prevent simultaneous connector checks from overwriting each other)** covers diagnostic concurrency.
- **Task #70 (Let operators resume interrupted source refreshes from the jobs screen)** covers refresh progress and safe job recovery.
- **Task #71 (Use each source’s own freshness window before calling data stale)** covers per-source freshness policy.
- **Task #72 (Prevent custom model checks from reaching private services)** covers model endpoint network boundaries.
- **Task #73 (Keep valid model keys working with very large catalogs)** covers bounded model-key verification.
- **Task #102 (Keep expected graph notices from hiding real deployment errors)** covers the non-fatal Neo4j schema notices observed in workflow logs.

## Verification evidence

- Running Replit workflow restarted successfully and served the application on the configured preview port.
- Live `GET /api/health?refresh=true` returned a truthful degraded operational state while preserving primary readiness.
- Live `GET /api/exports/v1/findings?limit=1` returned HTTP 200, schema version `1.1`, content disposition, signed watermark header, and a bounded empty page.
- Live `GET /api/catalog/ndia/preview` returned schema-valid metadata, `not_submitted`, no remote dataset ID, and publication disabled.
- Backend focused contract suite: **74 passed** across exports, catalog, fault-injection recovery, and readiness worker tests.
- Frontend suite: **48 passed**.
- Frontend production build completed successfully.
- Visual checks covered the mission readiness summary, findings interoperability page, Administration/catalog state, and connector status page.

## Combined conclusion

The partner handoff is usable without undocumented graph knowledge and preserves the required classification, provenance, stable-ID, quality, pagination, idempotency, simulation, and authorization boundaries. The operator contract is technically complete and truthful, including degraded/offline operation and optional-service isolation. The three linked follow-ups address the remaining unsafe default and human-facing operational clarity gaps without duplicating already planned connector, refresh, freshness, or model-boundary work.