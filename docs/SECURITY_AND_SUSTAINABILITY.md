# Security and sustainability boundary

## Release assumptions

Illuminate is a single-workspace, unclassified demonstration system. It is not
accredited for classified, controlled, personal, export-controlled, or
procurement-sensitive payloads. Operators must use public or explicitly
authorized sources and must confirm each source's license and terms before
publication.

## Trust and write boundaries

- Process secrets stay in environment variables or the workspace credential
  store. API responses, logs, exports, catalog metadata, and cached fixture URLs
  must never contain them.
- Browser and MCP tool results expose allowlisted projections, not cached raw
  connector payloads. Connector failures expose only type and HTTP status.
- Graph reads are bounded by row, traversal, and transaction time limits.
  Writes use the permission gate. Human and open-source evidence is staged;
  only explicit review, authoritative confidence, or independent
  corroboration may commit a claim.
- Network MCP is disabled unless `ILLUMINATE_MCP_HTTP_TOKEN` is configured and
  every request presents that bearer token. Local stdio MCP remains
  process-bound.
- NDIA catalog writes are disabled unless organizer-provided write paths and
  operator authorization are configured. Read catalog metadata is public.

## Classification, simulation, and export rules

Only public/unclassified source material belongs in this workspace. Simulated
records remain marked through claims, evidence, reports, and exports and must
not be represented as observed facts. Public releases should export committed,
non-simulated findings and retain source license and provenance fields.

## Bounded and deterministic operation

Cypher transactions, connector diagnostics, enrichment jobs, summaries,
documents, exports, and readiness probes have explicit time, row, page, byte,
or retry ceilings. The seeded graph, deterministic risk/report logic, claim
review, and exports remain usable when model and live connector services are
unavailable; failures must be reported as unavailable, staged, or unknown
rather than silently fabricated.

## Residual risk accepted for the demonstration

- Identity is a single-workspace user label, not production authentication or
  tenant isolation. Deploy only behind a trusted access boundary.
- Connector caches contain upstream public payloads on local storage. They are
  not a publication surface; production use needs retention, access-control,
  and encryption policy.
- Source independence is connector-name based. Production assurance should use
  curated provider identities and transactional claim state transitions.
- Container images use floating upstream tags. Production delivery should pin
  reviewed digests, scan images, use a private service network, inject unique
  secrets, restrict APOC, and enforce read-only filesystems/capability drops.
- Docker Compose runs the API as the invoking host UID/GID; its startup init
  repairs bind-mounted data ownership before the non-root process starts.
- Artifact document retrieval is intended for URLs created by trusted
  connectors or approved users. Production exposure requires a strict source
  host allowlist and private-network/redirect blocking.

## Review result

Focused dependency, static-analysis, and privacy/dataflow scans found no
critical, high, medium, low, or informational findings on 2026-09-08. Manual
review found application trust-boundary issues not detectable by those tools;
network MCP fail-closed authentication, staged human evidence, bounded claim
lists and dry runs, raw payload isolation, and non-root application containers
were hardened. The residual demonstration constraints above remain explicit
release conditions.