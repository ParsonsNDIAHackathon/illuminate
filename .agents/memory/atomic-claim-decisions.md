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