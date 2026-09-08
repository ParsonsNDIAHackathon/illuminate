---
name: Neo4j on Replit
description: Replit-specific Neo4j configuration constraints for running Illuminate without Docker.
---

Use an explicit writable Neo4j configuration directory in the workspace, including data, logs, run, transactions, and plugins directories. Wire the matching bundled APOC core JAR into that plugin directory and allow `apoc.*` procedures.

**Why:** The Nix-packaged Neo4j home is read-only, so password initialization fails if the admin tool uses its default config. Illuminate’s explorer also depends on `apoc.path.subgraphAll`, which is unavailable unless the bundled APOC JAR is explicitly loaded.

**How to apply:** Any Replit launcher for Illuminate should configure Neo4j’s writable directories before setting the initial password, enable bundled APOC, wait for Neo4j, then wait for API health before exposing Vite.

For bounded multi-hop analytics, use internally limited path expansion with a sentinel, materialize graph values into scalar/map data before aggregation boundaries, and propagate truncation to downstream completeness claims.