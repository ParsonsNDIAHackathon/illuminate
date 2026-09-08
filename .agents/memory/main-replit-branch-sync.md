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