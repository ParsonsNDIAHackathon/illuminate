---
name: Main branch synchronization
description: Durable safety rules for reconciling Replit and GitHub main histories without rewriting or racing shared work.
---

Fetch the remote branch into the exact tracking ref used for comparison; do not
assume a successful fetch refreshed that ref through ambient fetch mappings.
Capture the local candidate before ancestry evaluation and publish only that
immutable commit, never a mutable branch name resolved later.

**Why:** Custom refspecs can leave a stale tracking ref while fetch succeeds, and
concurrent local work can advance a branch between validation and push. Either
case can make synchronization falsely report success or publish unevaluated work.

**How to apply:** Fetch before work and again after concurrent merges. Fast-forward
only when remote history is an ancestor-safe continuation; refuse dirty or
diverged states. Push without force, then fetch and compare exact commit IDs again.
Task-workspace SSH remotes may be platform-refreshed even when direct fetch cannot
authenticate, so do not delete those remotes merely because a manual fetch prompts.

On an actively changing shared `main`, use a bounded fetch–merge–push loop. A
non-fast-forward rejection is evidence that the remote moved after evaluation,
not permission to force-push.

**Why:** Parallel task merges can advance the remote several times during one
reconciliation. Incorporating each observed remote tip preserves every history
while a bounded loop avoids silently chasing a branch that never settles.

**How to apply:** After each conflict-resolved merge, fetch immediately before
pushing. If the fetched tip is not an ancestor, merge it and revalidate; retry only
a small fixed number of times, and stop for review if the remote keeps advancing.

Replit's concurrent-task integration may rebuild workspace `main` by rebasing it
onto the platform-owned `main-repl/main` base. A merge made only on workspace
`main` can disappear while its file changes survive as patch-equivalent commits.
Locally changing that base is not durable because the platform force-refreshes it
from its authoritative remote.

**Why:** Repeated history-preserving merges were replaced during completion review
because active task integration rebased `main`; a later attempt to update the local
base was itself replaced by a forced fetch.

**How to apply:** Confirm the reflog before repeating a vanished merge. If it shows
automatic rebases and forced base refreshes, do not modify the local integration
base or keep racing it. Coordinate with the integration owner or wait until active
task merges settle, then reconcile workspace `main` and recheck ancestry immediately.

Treat any credential-delivery channel as readable by the whole Git process tree,
not just the intended credential prompt.

**Why:** Repository-controlled hooks inherit Git's environment and open file
descriptors. A secret absent from command arguments can still leak if a hook runs
while its delivery channel is available.

**How to apply:** Remove workspace secrets from the environment before the first
Git subprocess. During secret-backed network operations, disable repository hooks
through a private, empty, command-scoped hooks directory; do not persist that
setting or alter normal local credential-helper behavior.