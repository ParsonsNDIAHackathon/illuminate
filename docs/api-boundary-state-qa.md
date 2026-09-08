# API boundary and state QA

Scope: mission readiness, claims, enrichment jobs, exports, and NDIA catalog
publication. This review uses local requests and mocked portal calls only; it
never performs a live destructive NDIA write.

## State models

### Claims

| Current | Operation | Result |
|---|---|---|
| staged | commit | committed |
| staged | reject | rejected |
| committed | commit again | committed (idempotent) |
| rejected | reject again | rejected (idempotent) |
| rejected | commit | remains rejected |
| committed | reject | `409`, no write |
| missing | commit or reject | `404`, no write |
| any unexpected state | commit or reject | `409`, no write |

Reject uses a conditional state update, so a concurrent terminal decision cannot
be overwritten by a stale pre-check.

### Enrichment jobs

`queued -> running -> succeeded | empty | partial | failed | timed_out`.
Jobs are read-only after enqueue. Unknown job IDs return `404`. Worker tests cover
duplicate enqueue behavior, connector failures, timeouts, partial results,
summary degradation, and terminal status reporting.

### Exports

Full pages are bounded to 1–1000 records. A cursor resumes one immutable export
snapshot. Incremental pages use a signed watermark and upper bound. Malformed
cursors/watermarks return `400`; invalid limits/formats return `422`. Reusing a
valid cursor or watermark is read-only and repeatable.

### Catalog publication

`not_submitted -> validated_dry_run` never writes local publication state or
calls the portal. Live submission requires an exact confirmation phrase, a
signed preview token bound to user/metadata/watermark, operator authorization,
server-side portal credentials, and configured endpoints.

Live progression is `not_submitted -> submitting -> submitted/pending_review`.
An uncertain remote response becomes `unknown`, blocks automatic retries, and
requires lookup reconciliation. A recorded dataset identity makes repeated
submission idempotent.

## Boundary matrix

| Surface | Positive cases | Negative cases |
|---|---|---|
| Claims | valid filters; bounded maximum; staged decisions; repeated terminal decisions | bad status/type; zero/oversized limit; missing claim; invalid transition |
| Jobs/readiness | successful, empty, partial, failed, timeout; cached and refreshed readiness | unknown job; connector/db degradation; incomplete seed coverage |
| Exports | schema/sample; page continuation; incremental watermark; JSON/NDJSON/CSV | zero/oversized limit; bad format; malformed cursor; malformed/stale watermark shape |
| Catalog | preview; confirmed dry-run; authorized live mocked submission; status refresh | missing/extra fields; wrong confirmation; short/stale token; absent credentials; unauthorized operator; timeout/malformed remote response |
| MCP/shared tools | shared tool list/schema; shared dispatcher result | unknown tool; missing required arguments; traceback/secret-safe projection |

## Defects and retest evidence

### Committed claims could be rejected

- **Request:** `POST /api/claims/{committed-id}/reject` with `{}`.
- **Previous response:** `200 {"status":"rejected"}`.
- **Expected contract:** terminal committed evidence must not drift; return `409`
  and leave the claim unchanged.
- **Security relevance:** integrity. A repeated or out-of-order review request
  could suppress approved evidence and change downstream exports/readiness.
- **Reproduction:** create or mock a committed claim, issue the request once, and
  read its status.
- **Retest:** covered by `test_reject_cannot_rewrite_non_staged_claim` and
  `test_claim_decisions_explain_missing_and_invalid_transitions`.

### Missing claims appeared successfully rejected

- **Request:** `POST /api/claims/missing/reject` with `{}`.
- **Previous response:** `200 {"status":"rejected"}` despite no matching node.
- **Expected contract:** `404 {"detail":"no such claim"}` with no write.
- **Security relevance:** auditability. False success can make an operator
  believe a review action was recorded when it was not.
- **Reproduction:** issue the request for an unknown identifier.
- **Retest:** covered by `test_reject_missing_claim_fails_without_write` and the
  router error-contract test.

### Claim list accepted unsafe query bounds

- **Request:** `GET /api/claims?status=unknown&limit=1000000` (also applies to
  source records).
- **Previous response:** request reached the database with arbitrary status and
  limit.
- **Expected contract:** unsupported status and limits outside 1–500 return
  `422` before database access.
- **Security relevance:** availability and contract integrity. Unbounded reads
  can amplify database work; invalid states make consumers depend on typos.
- **Reproduction:** issue each invalid query against the HTTP endpoint.
- **Retest:** covered by the parameterized claim boundary tests.

## Verification

The focused contract suite exercises claims, exports, catalog, readiness/worker,
permission confirmation, and MCP parity. All portal writes in tests are mocked,
and negative catalog tests assert malformed requests never reach the portal.