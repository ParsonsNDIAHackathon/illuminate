# Repository agent guidance

GitHub `origin/main` is the canonical shared history. The Replit workspace's
`main` branch must track it.

- Before beginning task work, switch to a clean `main`, run `make sync-pre`, and
  create or refresh an isolated task branch from that commit.
- Never run the main synchronization command from an unfinished task branch.
- After concurrent task merges, re-run `make sync-pre` before final integration.
- Commit only intended files and validate the complete task before publishing.
- After a reviewed task reaches Replit `main`, run `make sync-publish` and verify
  that it reports `main` and `origin/main` at the same commit before declaring
  completion.
- Never rebase, reset, or force-push shared `main`. If histories diverge or a
  push is protected, follow the command's recovery guidance and preserve both
  sides for review.