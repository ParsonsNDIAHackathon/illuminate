---
name: Atomic claim decisions
description: Concurrency rule for claim review transitions and materialized graph facts.
---

Claim commit/reject decisions must acquire a database write lock before reading
the current review state, and all materialized graph effects must remain inside
that same transaction. A losing decision may report the winner but must not
mutate status or graph facts.

**Why:** A read-check followed by separate writes lets commit and reject both
appear successful, then leaves a terminal status inconsistent with the direct
graph relationship or property written by the competing decision.

**How to apply:** Any new terminal claim action or additional commit side effect
must join the existing claim-scoped transaction. Verify both possible winners
under real database contention, including final review status and materialized
fact consistency.

Repeating a terminal analyst/API commit must be a no-op. Connector-driven
projection refresh is a separate, explicit operation and may update a fact only
while that projection still identifies the same backing claim.

**Why:** Replaying accepted claim A after a newer conflicting claim B can
otherwise restore A without a review event, silently reversing the authoritative
decision history.

**How to apply:** Keep public commit retries idempotent. For ingestion refreshes,
guard relationship and attribute writes by current claim ownership, and test the
sequence A commit → B commit → A retry for both normal and refresh paths.