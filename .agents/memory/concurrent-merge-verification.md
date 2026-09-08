---
name: Concurrent merge verification
description: Final verification needed when parallel project tasks modify shared integration files.
---

Parallel task merges can change shared application entry points after a feature
has already passed live verification. Re-check the current integration wiring
immediately before completion, not only after the feature's initial restart.
Also treat a conflict-free rebase as structurally complete, not semantically
validated: an automatic content merge can still produce invalid source.

**Why:** A concurrent task merge preserved an import but dropped a router from
the application registration tuple after its endpoints had already passed live
checks. Internal tests did not detect the integration loss.

**How to apply:** For work that registers routes, workers, or schemas in shared
files, include an HTTP-level test against the real application object and
confirm the current shared file plus live endpoint immediately before marking
the task complete. After any rebase or conflict-resolution sequence, run at
least a parser/type check plus the affected test suite even when Git reports a
clean result.

Completion review evaluates the integrated base-to-head result, not only the
files changed by the current task.

**Why:** A task-local feature passed its own review, but completion was blocked
by reproducible regressions already present elsewhere in the integration range.
Commit provenance did not make a broken combined result acceptable.

**How to apply:** When final validation identifies an integrated regression,
coordinate with its active owner when possible; otherwise make the narrow repair
and validate that behavior before retrying completion.

Immutable evidence records should include the evaluated Git tree object as well
as the commit ID when concurrent task integration may rebase a branch.

**Why:** Automatic integration can legitimately rewrite commit IDs while
preserving a product tree, making a commit-only scorecard look unrelated even
when the evaluated files are byte-identical.

**How to apply:** Record both identities, then immediately before completion
verify that current product/config/test files match the recorded tree. If a
concurrent merge changes that tree, rerun the affected checks and full gate
instead of relying on ancestry or an older scorecard.
