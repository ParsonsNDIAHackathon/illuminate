---
name: Seed evidence timestamps
description: Why repeated fixture ingestion must not refresh evidence retrieval timestamps.
---

Idempotent seed operations must preserve the original `retrieved_at` timestamp on existing evidence-bearing records. Record repeated ingestion separately with first/last ingestion timestamps.

**Why:** Risk freshness and diligence are derived from when the source evidence was retrieved. Replacing that timestamp during a seed rerun can silently turn stale evidence into current evidence without any new retrieval.

**How to apply:** For fixture-backed or replayed data, set retrieval time only when the record is first created (or when it is genuinely absent). Update ingestion timestamps on every replay. Apply the same rule to nodes, relationships, artifacts, and source records.