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

Treat Replit's platform-owned `main-repl/main` as a read-only integration ref.
Task completion may rebase workspace `main` onto it and replay local merge content.

**Why:** Local changes to the integration ref can be replaced by forced platform
refreshes, while task-completion rebases can change the candidate commit history.

**How to apply:** Wait for active integrations to settle, use the platform conflict
flow during completion, then rerun validation and GitHub synchronization against
the rebased candidate. Never try to make the integration ref authoritative locally.

Treat any credential-delivery channel as readable by the whole Git process tree,
not just the intended credential prompt.

**Why:** Repository-controlled hooks inherit Git's environment and open file
descriptors. A secret absent from command arguments can still leak if a hook runs
while its delivery channel is available.

**How to apply:** Remove workspace secrets from the environment before the first
Git subprocess. During secret-backed network operations, disable repository hooks
through a private, empty, command-scoped hooks directory; do not persist that
setting or alter normal local credential-helper behavior.
