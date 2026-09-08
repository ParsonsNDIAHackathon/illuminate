# Fault Injection and Recovery QA

This matrix is exercised with development fixtures and monkeypatched service
boundaries only. It does not call or damage production services.

| Failure | Class | Expected state and safe behavior |
|---|---|---|
| Neo4j unavailable or timed out | Required | Health is `unavailable`, `ok` and primary workflow readiness are false; a refreshed probe recovers without restarting the API. |
| Connector timeout or partial fact write | Optional | Connector/job reports timeout or partial completion; stored facts remain counted and deterministic graph/report functionality remains available. |
| Model timeout, exception, or invalid selection | Optional | Deterministic summary remains authoritative and stale model-selected findings are cleared. |
| Cached health followed by dependency failure | Required | Cached result is labeled; `refresh=true` bypasses it and cannot report healthy after Neo4j fails. |
| Stale source timestamps | Optional data freshness | Overall state is degraded and refresh action is explicit, while the validated deterministic mission stays available. |
| Malformed NDIA response or portal timeout | Optional write integration | Outcome becomes unknown and automatic duplicate POST is blocked until lookup reconciliation. |
| Interrupted worker operation | Optional background work | Queue accounting completes once; cancellation does not enqueue or execute a second job. |

Automated assertions are in `api/tests/test_fault_injection_recovery.py`, with
additional partial-write, retry, model-fallback, and portal-timeout cases in the
existing readiness/worker and catalog test modules.