---
name: Live projection policy
description: Applying live-only data policy consistently across snapshots, deltas, and derived fields.
---

An operational data policy must be enforced on every projection channel, including initial REST snapshots, retained client caches, live graph deltas, nested evidence, and every relationship in an association path. After filtering base records, recompute every derived flag from the visible records instead of retaining pre-filtered values.

**Why:** A correct initial response can still be contaminated by a later unfiltered update or by cached records retained after the policy changes, while derived indicators can preserve the meaning of evidence that was removed or accidentally broaden their original domain rules.

**How to apply:** When adding a truth-state or simulation filter, inventory snapshots, retained caches, and streaming paths together. A policy change must cancel in-flight loads, evict cached records and styles, then reload under the new policy. Filter complete association paths before collection and limits, including relationships and backing claims—not only returned nodes. Centralize derived-field calculation and run it again after filtering; any existence query used for classification must enforce the same policy while preserving domain restrictions such as supplier-only interlocks.