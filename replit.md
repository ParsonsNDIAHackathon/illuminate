# Repository agent guidance

GitHub `origin/main` is the canonical shared history. The Replit workspace's
`main` branch must track it.

- Before beginning task work, switch to a clean `main`, run `make sync-pre`, and
  create an isolated task branch from that commit.
- Never run the main synchronization command from an unfinished task branch.
- Preserve branch history for every task integration: merge upstream changes
  into task branches, and merge completed task branches into the integration
  branch. Never rebase a task branch or use rebase to synchronize or resolve
  conflicts.
- After concurrent task merges, re-run `make sync-pre` before final integration.
- Commit only intended files and validate the complete task before publishing.
- After a reviewed task reaches Replit `main`, run `make sync-publish` and verify
  that it reports `main` and `origin/main` at the same commit before declaring
  completion.
- Never rebase or reset task branches or shared `main`, and never force-push
  either. If histories diverge or a push is protected, follow the command's
  recovery guidance and preserve both sides for review through a merge.