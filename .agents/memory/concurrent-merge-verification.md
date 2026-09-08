---
name: Concurrent merge verification
description: Final verification needed when parallel project tasks modify shared integration files.
---

Parallel task merges can change shared application entry points after a feature
has already passed live verification. Re-check the current integration wiring
immediately before completion, not only after the feature's initial restart.

**Why:** A concurrent task merge preserved an import but dropped a router from
the application registration tuple after its endpoints had already passed live
checks. Internal tests did not detect the integration loss.

**How to apply:** For work that registers routes, workers, or schemas in shared
files, include an HTTP-level test against the real application object and
confirm the current shared file plus live endpoint immediately before marking
the task complete.

Completion review evaluates the integrated base-to-head result, not only the
files changed by the current task.

**Why:** A task-local feature passed its own review, but completion was blocked
by reproducible regressions already present elsewhere in the integration range.
Commit provenance did not make a broken combined result acceptable.

**How to apply:** When final validation identifies an integrated regression,
coordinate with its active owner when possible; otherwise make the narrow repair
and validate that behavior before retrying completion.