---
name: Seed replay identity
description: Safety and identity rules for interrupted and repeated development seed rebuilds.
---

Mark a seed as in progress before any reset or graph write, and do not retain a
prior completion stamp while a rebuild is underway. Fixture-backed observations
must have deterministic identities across destructive replay; terminal claims
must be no-op decisions when encountered again.

**Why:** A reset interrupted after deletion could otherwise advertise an old
successful seed, and random claim identities can preserve identical graph counts
while changing every public finding identifier.

**How to apply:** For seed and restore lifecycle changes, test the interruption
window before deletion, compare semantic graph counts across two identical
replays, and compare the complete exported identifier set—not only readiness or
row counts.