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