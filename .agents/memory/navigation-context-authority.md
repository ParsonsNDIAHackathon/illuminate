---
name: Navigation context authority
description: Why decision-workflow scope and mode must be reproducible from route state.
---

Mission scope, report traces, and comparison mode are URL-owned state. In-memory graph or view state may fill a missing route value, but must never override an explicit route value.

**Why:** Decision surfaces are entered through direct links and browser Back/Forward as well as in-app controls. If retained store state wins, the visible report or graph can silently use a different program or vendor than the URL promises.

**How to apply:** Preserve program, vendor, finding, focused elements, and evidence identifiers across contextual transitions. Make query-only route changes rehydrate reused views, and keep explicit calibration/example modes distinct from live selections. Treat every graph-scope route transition as a cancellation boundary, even when the destination appears cached: route the selector first, invalidate pending replacements, and let only the current generation commit canvas, focus, style, or loading state.

Route-scoped async success and progress indicators must be keyed to the full route scope, and only successful, usable results may suppress a repeat run.

**Why:** A completion banner from one mission can otherwise survive navigation into another, while caching failed or empty attempts can make an explicit retry silently skip the analysis.

**How to apply:** Clear mismatched presentation state synchronously at route entry, reject stale completions, and leave failed or empty runs eligible for retry.