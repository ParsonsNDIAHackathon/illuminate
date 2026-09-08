---
name: Focused graph membership
description: The boundary between supply-chain membership and contextual metadata in a program-focused graph.
---

A program-focused graph may add entities to the program membership set only through `SUPPLIES` paths. Geography, categories, people, evidence, and similar metadata are terminal context for known members, not membership edges.

**Why:** Different programs legitimately share countries, categories, people, evidence sources, and owners. Treating arbitrary graph connectivity as membership lets one program's live update or neighbourhood load pull another program's suppliers onto the focused canvas.

**How to apply:** Establish the program's bounded supply member set independently of the local display radius by following incoming `SUPPLIES` edges from the program toward suppliers. Then attach enabled context in directions that cannot cross from shared context into another entity. Apply the same direction and boundary to initial reads and incremental updates.