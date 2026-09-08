---
name: Readiness truth rules
description: Aggregate readiness semantics for deterministic mission workflows and optional services.
---

Primary workflow readiness requires both a completed, versioned seed stamp and a live check that the mission root still has prime and subcontractor paths. A reachable database or non-empty graph alone is insufficient. Stale data degrades aggregate status while preserving the primary-ready boolean when coverage is intact. Connector and model availability is always optional and never gates the deterministic workflow.

**Why:** Historical counters and arbitrary graph nodes can survive deletion of mission data, while judges must not see false-positive readiness. The core demo must also remain usable without credentials or external services.

**How to apply:** Keep future health endpoints, seed changes, and operator surfaces consistent with these rules. Validate current coverage under a bounded timeout and report optional failures separately with actionable, credential-safe diagnostics.