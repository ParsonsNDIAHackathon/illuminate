---
name: Raw retrieval cache isolation
description: Why shared upstream payloads require a database boundary separate from the analytical graph.
---

Store raw shared-cache payloads behind a dedicated database connection and a
bearer-protected cache authority. Never place them in the analytical Neo4j
database, even under labels omitted from the public schema.

**Why:** The analytical Cypher surface permits useful scalar projections and
unlabelled traversals. A label allowlist cannot reliably prevent payload
exfiltration through aliases, path syntax, zero-length traversals, or future
query features.

**How to apply:** Any service that persists raw upstream responses, lease
ownership, or credential-scope fingerprints must use storage credentials and a
database inaccessible to user-supplied analytical queries. Fail authority
startup and requests closed when that isolation is missing.