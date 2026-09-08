---
name: Credential diagnostic truth
description: Safety rule for deciding whether a credentialed source has actually accepted an operator key.
---

Credential checks must accept only a complete, recognizable provider success envelope. Known rejection envelopes map to authentication; malformed, truncated, or unknown nominal-success responses must fail closed as unavailable.

**Why:** HTTP status alone is not proof of authentication. Providers may encode a rejected credential as a 2xx empty result or an endpoint-specific 404. Loose substring checks can also mistake truncated or unrelated payloads for success.

**How to apply:** Keep diagnostics bounded, non-mutating, non-cached, and sanitized. Use stable positive lookups where empty results are ambiguous, validate typed provider fields, and normalize documented provider-specific rejection statuses.

UI status must distinguish a stored credential from a provider-verified connector. Saving a key should trigger the diagnostic before presenting success.

Changing a shared credential invalidates every connector that uses it; running a test updates only that connector and must preserve other displayed diagnostic results.