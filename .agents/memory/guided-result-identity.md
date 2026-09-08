---
name: Guided result identity
description: How guided analysis UI distinguishes matched subjects from contextual graph elements.
---

For named graph templates, treat result-row identities as the authoritative matched subjects. A returned subgraph is the complete visual context and may include roots, intermediate suppliers, owners, locations, evidence, and other entities that did not themselves match the template.

**Why:** Inferring affected vendors from all entities in a subgraph can confidently misattribute a risk or gap to an intermediate node. This is especially easy for multi-hop supply and ownership paths.

**How to apply:** Build finding summaries and affected-subject labels from deduplicated result rows, then use the subgraph only for path display, inspection, and truth/simulation context.

When a user expands an item from a guided finding list, extend that list with the returned one-hop neighborhood, including matching nodes and relationships that were already resident in the broader graph.

**Why:** A global before/after store difference misses useful neighbors already loaded by the initial program view, so a successful expansion can appear to do nothing.

**How to apply:** Scope expansion to the selected item and the neighborhood returned or represented after its request; do not substitute every globally loaded contextual element.