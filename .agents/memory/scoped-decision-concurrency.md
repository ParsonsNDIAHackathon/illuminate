---
name: Scoped decision concurrency
description: Concurrency rule for append-only decisions whose current state is projected within a program scope.
---

Use a scope-local version as the optimistic concurrency token, and a separate
entity-wide sequence for unified chronology and latest-event projections.

**Why:** If a program-scoped screen submits the version it can see but the
write compares it with an entity-global version, an unrelated program's event
can permanently block both updates and first decisions in that scope.

**How to apply:** Any new scoped analyst event stream should lock the shared
entity, compare the expected token only within the active scope, and increment
the global sequence in the same transaction. Test interleaved scopes as well
as competing writes within one scope.