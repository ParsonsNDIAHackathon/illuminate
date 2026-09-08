---
name: Evidence lineage safety
description: Durable trust rules for connector errors, shared artifacts, and claim-specific provenance.
---

Persist only allowlisted connector diagnostics such as error type and HTTP status. Never persist or emit arbitrary exception messages because they can contain credential-bearing URLs or response bodies.

**Why:** Connector libraries commonly include full request URLs and response text in exceptions, so truncation is not redaction.

**How to apply:** Any durable or user-visible connector error path must use a credential-free structured summary.

Treat a URL-deduplicated artifact's original provenance as immutable. Put each claim's source metadata, retrieval status, and simulation state on the claim and its evidence link rather than rewriting the shared artifact.

**Why:** Multiple connectors and simulated/real claims can reference the same URL; last-writer-wins metadata corrupts historical lineage.

**How to apply:** Artifact merges set provenance only on creation, while every claim-to-artifact evidence relationship records its own lineage.

Public finding exports must preserve claim, artifact, and evidence-link provenance as distinct scopes, and the complete normalized provenance must participate in ledger fingerprints.

**Why:** Flattening provenance drops claim-specific retrieval and simulation state, while excluding it from fingerprints leaves downstream consumers unaware of lineage corrections.

**How to apply:** Any new machine-consumer contract must serialize all three scopes and derive revisions from the full exported payload.