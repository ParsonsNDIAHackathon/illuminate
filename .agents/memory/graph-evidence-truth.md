---
name: Graph evidence truth
description: How deterministic consumers should decide whether graph facts are approved evidence.
---

Do not treat relationship metadata alone as the current truth status when a graph fact references a backing claim. Resolve the backing claim and its artifacts at evaluation time, and require the claim to remain committed with no simulated claim, artifact, relationship, or endpoint.

**Why:** A claim can be rejected after it has materialized a relationship. The relationship remains useful for provenance and review, but its copied metadata no longer proves that the fact is approved.

**How to apply:** Any deterministic score, export, or operational decision based on graph relationships must validate current claim/artifact truth. Claimless trusted facts require explicit provenance, retrieval time, and confidence; unknown provenance is missing evidence, not a clear result.