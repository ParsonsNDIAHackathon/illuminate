---
name: Inventory contract boundaries
description: Principles for trustworthy dependency and data-source inventory validation.
---

Inventory validation must reconcile declarations in both directions and compare
the full dependency identity, including versions, extras, markers, and runtime
conditions. Generated declaration evidence must remain separate from curated
license, terms, cost, and review conclusions.

**Why:** Name-only or one-way checks can certify stale lockfiles and removed
registrations. Treating generated unknowns as immutable curated values also
prevents reviewers from recording an authoritative conclusion later.

**How to apply:** When extending any maintained inventory, prove additions,
removals, and material declaration changes all fail independently. Preserve the
raw generated evidence beside editable reviewed assessments, and validate each
according to its own authority boundary.