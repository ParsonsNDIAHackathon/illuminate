---
name: Locked Python subprojects on Replit
description: Replit-specific uv environment behavior for independently locked Python subprojects.
---

When a nested Python project has its own lockfile, set `UV_PROJECT_ENVIRONMENT` to
an absolute environment path inside that subproject before running `uv sync
--project ... --frozen`.

**Why:** Replit exports `UV_PROJECT_ENVIRONMENT` to a shared workspace environment.
A relative override is interpreted from the discovered project root, which can
silently create an unintended doubly nested path.

**How to apply:** Deployment build commands for nested Python services should use
the workspace’s absolute path (for example, derived from `$PWD`) and launch with
that environment’s interpreter.