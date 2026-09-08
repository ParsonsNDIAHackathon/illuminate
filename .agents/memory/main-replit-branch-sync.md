---
name: Main Replit branch sync
description: How to verify the main Replit project's branch from a task workspace when its SSH remote cannot fetch non-interactively.
---

In a task workspace, treat `main-repl/main` as a platform-refreshed tracking ref and
re-check it immediately before completion. A direct `git fetch main-repl main` may
prompt for an SSH password that the task workspace cannot provide.

**Why:** Replit's post-merge/task plumbing refreshed `main-repl/main` several times
while parallel tasks completed, even though a manual fetch through the configured
SSH proxy could not authenticate non-interactively.

**How to apply:** Verify the tracking ref's commit and divergence before and after
long conflict-resolution work. Merge any newly arrived commits, then confirm
`main-repl/main` is an ancestor and has zero remote-only commits. Do not replace or
delete the Replit remote merely because a manual fetch prompts for credentials.