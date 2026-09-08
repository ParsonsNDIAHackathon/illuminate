---
name: NDIA catalog contract
description: Public versus organizer-provided contracts for event-3 dataset publication.
---

The NDIA portal publicly exposes the event-3 dataset discovery shape, but its
participant write, lookup, and status routes are not part of the public API
documentation. Never infer write paths from the public read route.

**Why:** The public dataset list is a read-only endpoint even though the portal
UI includes authenticated dataset-submission pages. Guessing a write route can
turn a safe integration into a misleading or destructive one.

**How to apply:** Keep write routes explicitly configured from organizer
instructions. Validate dry runs against the public dataset field shape, and do
not describe a contribution as published until a remote dataset identity is
returned and recorded.