# Versioned insight export

Illuminate publishes findings at `/api/exports/v1` without requiring the
Illuminate frontend or its graph serializer.

| Endpoint | Purpose |
| --- | --- |
| `/schema` | JSON Schema for the canonical paged JSON response |
| `/fields` | Plain-language field dictionary |
| `/sample` | Self-contained illustrative finding |
| `/findings` | Complete, paginated traversal |
| `/findings/incremental?since=...` | Findings after a prior watermark |

`limit` is 1–1000 (default 100). Follow `meta.next_cursor` until it is null.
Illuminate fingerprints the complete safe finding projection and records an
immutable event under a strictly increasing revision whenever it changes.
All pages in a traversal use the same upper revision, so later changes move to
the next incremental read without changing earlier pages. Store
`meta.watermark` only after consuming all pages, then pass it as `since` on the
next incremental run. Tokens are opaque and version-specific.

Incremental streams may contain `deleted: true` tombstones when a finding is
removed or its asserted subject changes. Consumers should delete their local
record with that `finding_id`. Full traversals omit tombstoned findings.

The default format is canonical JSON. `format=ndjson` emits one complete
finding per line. `format=csv` JSON-encodes every cell (including nulls and
strings), preserving types and nested data without dropping lineage. For these download formats,
watermark and continuation cursor are returned in `X-Illuminate-Watermark` and
`X-Illuminate-Next-Cursor`.

The exporter selects a fixed set of safe properties. It never exports raw
cached documents, credentials, or arbitrary node properties. Rejected claims
are included by default so incremental consumers see truth-state transitions;
set `include_rejected=false` only for a filtered view.
Simulation propagates from the claim, subject, target, and evidence artifacts.

Run the dependency-free consumer:

```bash
python api/examples/export_consumer.py http://localhost:8000
```