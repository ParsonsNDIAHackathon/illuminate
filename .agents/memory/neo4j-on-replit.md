---
name: Neo4j on Replit
description: Replit-specific Neo4j configuration constraints for running Illuminate without Docker.
---

Use an explicit writable Neo4j configuration directory in the workspace, including data, logs, run, transactions, and plugins directories. Wire the matching bundled APOC core JAR into that plugin directory and allow `apoc.*` procedures.

**Why:** The Nix-packaged Neo4j home is read-only, so password initialization fails if the admin tool uses its default config. Illuminate’s explorer also depends on `apoc.path.subgraphAll`, which is unavailable unless the bundled APOC JAR is explicitly loaded.

**How to apply:** Any Replit launcher for Illuminate should configure Neo4j’s writable directories before setting the initial password, enable bundled APOC, wait for Neo4j, then wait for API health before exposing Vite.

Keep the generated development credential and the existing graph store on the same lifecycle; never silently replace one without updating the other.

**Why:** An existing Neo4j store retains its admin credential. Generating a different credential after the local credential state disappears prevents the workflow from restarting even though the graph data is still healthy.

**How to apply:** Treat the retained graph store and its credential metadata as one lifecycle. If they diverge, restore consistency without deleting or reseeding graph data, and require authenticated access before declaring startup ready.

Never externally forward Neo4j HTTP or Bolt listeners, including in development.
Credential recovery temporarily disables authentication, so loopback binding is
safe only when the platform is not forwarding those listeners.

**Why:** An external port mapping can make a loopback-only recovery instance
reachable while authentication is disabled, exposing unrestricted graph access.

**How to apply:** Expose only application ports. Keep Neo4j on unforwarded
loopback listeners throughout normal startup and credential recovery.

Run any destructive reset-based QA against isolated temporary Neo4j directories, never the persisted workspace store.

**Why:** Deterministic seed tests replace graph contents; using the normal workspace directories can erase analyst data while investigating an unrelated startup or journey defect.

**How to apply:** Configure temporary data, log, run, transaction, plugin, and config directories, seed that disposable instance, and remove it after testing. Retest the real workflow without reset once its credential path is healthy.

Use a persistent, single-instance VM deployment while Illuminate embeds Neo4j and stores its graph and worker checkpoints on the instance filesystem.

**Why:** Autoscaled instances have independent ephemeral filesystems, so instance replacement can lose graph state and concurrent instances can diverge.

**How to apply:** Keep the deployment target on an always-on VM unless graph state, analyst decisions, and checkpoints have first moved to an external durable database shared by every instance.

For bounded multi-hop analytics, use internally limited path expansion with a sentinel, materialize graph values into scalar/map data before aggregation boundaries, and propagate truncation to downstream completeness claims.