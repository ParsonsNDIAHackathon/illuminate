---
name: Live observation identity
description: Durable identity and timestamp rules for idempotent source refreshes.
---

The stable identity of an imported observation must prefer the upstream record identifier, including an as-of date when the source publishes dated snapshots. A shared URL is not always an observation identity. Keep claim review state separate from retrieval state, preserve canonical source provenance and the first upstream observation time, and update latest retrieval/cache/fallback and ingestion fields independently. When one fact aggregates multiple responses, use the oldest backing retrieval time and the most conservative cache/fallback state.

**Why:** Retries otherwise duplicate facts, while changing snapshots can collapse into one record or overwrite immutable provenance. Treating ingestion time, review status, or a cache read as a new live retrieval also makes coverage reporting falsely current.

**How to apply:** Use this rule for every new connector, bootstrap aggregate, and materialized fact path. Resume/retry should upsert the same upstream observation and preserve decisions; genuinely new dated source records should remain distinct even when their URL and value are unchanged.