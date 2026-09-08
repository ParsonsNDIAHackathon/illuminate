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

Unauthenticated finding exports must require an explicit public classification; missing or malformed classification fails closed. When a previously public finding leaves that boundary, emit only a redacted stable-ID tombstone.

**Why:** Merely preserving a restrictive label after disclosure is not access control, and a full-payload tombstone can disclose the record it is meant to withdraw.

**How to apply:** Enforce eligibility both in the source query and before ledger writes; preserve only the deletion key and lifecycle flags in withdrawal events. Bind tokens and ledger namespaces to the public-policy generation so retained pre-policy events cannot be replayed.

Presentation must never infer verified claim status, retrieval method, scoring rule, or freshness from a related aggregate. Show unavailable unless that exact evidence or factor provides the value.

**Why:** Evaluation eligibility is not claim verification, and category freshness can differ from an individual factor's timestamp; inferred labels overstate provenance.

**How to apply:** Keep derived status separate from nullable claim status, compute freshness per factor, and resolve supply lineage by exact relationship/evidence ID—never by a non-unique contract reference.