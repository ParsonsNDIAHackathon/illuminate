---
name: Readiness truth rules
description: Aggregate readiness semantics for deterministic mission workflows and optional services.
---

Rehearsal workflow readiness requires both a completed, versioned seed stamp and a live check that the mission root still has prime and subcontractor paths. Production operational readiness is a separate signal based on fresh live procurement coverage, not seed metadata. Only database reachability gates process startup. Stale data degrades aggregate status without making optional connectors or models startup dependencies.

**Why:** Historical counters, taxonomy nodes, and complete offline/scenario seeds can all exist without current operational evidence. Conversely, a valid live graph may not have rehearsal seed metadata. Conflating those states either skips needed live recovery or rebuilds an unnecessary default demo.

**How to apply:** Keep health endpoints, production scripts, seed changes, and operator surfaces consistent with these signals. Trigger production recovery from operational coverage/freshness, retain seed readiness as rehearsal diagnostics, and report optional failures separately. Decision-facing UI must name the active mode; “rehearsal ready” must not read as “live operational evidence ready.”