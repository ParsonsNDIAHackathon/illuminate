---
name: Optional fetch-once cache
description: Why deployment must not require the shared retrieval cache or managed PostgreSQL.
---

The fetch-once cache may remain available as an opt-in capability, but production
startup must not require cache authority, cache credentials, or managed
PostgreSQL. When no authority is configured, connectors use their ordinary live
HTTP path and offline fixtures remain available.

**Why:** Making the cache mandatory introduced a deployment bootstrap dependency
on a production database and stopped otherwise healthy builds from starting. The
user chose restoring deployability by removing the offending mandatory
functionality rather than retaining that coordination guarantee.

**How to apply:** Keep cache authority and required-mode defaults disabled in
deployment configuration. Do not gate launcher readiness on cache schema state
or require `DATABASE_URL` solely for retrieval caching.