---
name: Judge-journey gates
description: How automated demo rehearsals avoid passing when the visible application journey is broken.
---

Rehearsal automation must follow the action rendered by the mission entry,
preserve its scope, and assert conditional success states produced by loaded
data. Static headings, placeholders, or route availability are not sufficient.
The check must use the browser-facing origin for API traffic.

**Why:** Static page chrome can render while program selection, same-origin API
routing, graph analysis, or vendor assessment has failed, producing a false
release pass.

**How to apply:** For judge-path checks, derive the next navigation from the
rendered UI, require the analysis completion marker and usable assessed records,
reject visible failure states, and include a negative check proving unavailable
same-origin APIs fail the gate.