---
name: Fetch-once cache scope
description: Why immutable retrieval caching is deployment-scoped rather than exposed across project environments.
---

Each operational deployment owns its fetch-once authority and durable cache.
Production workers coordinate over loopback through managed PostgreSQL. Task and
development environments must fail closed for live retrievals unless explicitly
configured with their own authority; offline fixtures remain available.

**Why:** The main deployment must remain password-protected, and the project
account does not provide external-access tokens for machine callers. Exposing the
whole app publicly just to share the cache was rejected in favor of per-instance
durability across process restarts and redeployments.

**How to apply:** Keep production cache traffic local to the deployment and
persist immutable records in its managed database. Do not point task branches at
the protected production URL or silently bypass an unavailable local authority.