---
name: Server-side URL fetch boundaries
description: Security rule for any feature that retrieves, probes, frames, redirects, or caches user-influenced URLs.
---

Every server-side path that can contact a URL must use the same public-network
destination policy. This includes document retrieval, embeddability probes,
error fallbacks, every redirect hop, and the final URL stored in a cache
sidecar. A security-policy rejection must fail closed rather than retrying
through a less-restricted helper.

**Why:** A hardened primary document fetch still permitted SSRF through an
older frameability fallback, and legacy cache metadata could retain a private
redirect destination even after the live redirect path was fixed.

**How to apply:** Route new URL probes through the shared bounded fetch
boundary. Validate both the requested and final cached URL before returning a
cached body, and add regressions for private literals, private DNS results,
public-to-private redirects, and unsafe legacy cache metadata.