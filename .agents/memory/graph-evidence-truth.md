---
name: Graph evidence truth
description: How deterministic consumers should decide whether graph facts are approved evidence.
---

Do not treat relationship metadata alone as the current truth status when a graph fact references a backing claim. Resolve the backing claim and its artifacts at evaluation time, and require the claim to remain committed with no simulated claim, artifact, relationship, or endpoint.

**Why:** A claim can be rejected after it has materialized a relationship. The relationship remains useful for provenance and review, but its copied metadata no longer proves that the fact is approved.

**How to apply:** Any deterministic score, export, or operational decision based on graph relationships must validate current claim/artifact truth. Claimless trusted facts require explicit provenance, retrieval time, and confidence; unknown provenance is missing evidence, not a clear result.

In risk explanations, label the scoring rule or factor as **derived** and its eligible committed backing evidence as **verified**. A frozen calibration preset remains **simulated** even when it demonstrates verified-evidence semantics.

**Why:** Collapsing rule output, claim approval, and fixture status into one badge can make a derived score look like a directly observed fact or make simulated demo data look operational.

**How to apply:** Show these states independently in comparisons and exports; staged and rejected evidence must remain visible as excluded evidence, never silently disappear or score.