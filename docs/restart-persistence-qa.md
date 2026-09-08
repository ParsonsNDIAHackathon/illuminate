# Restart Persistence and Idempotency QA

This runbook separates product behavior from host configuration failures. It is
safe for development data only. The seed command resets the development graph;
never run it against production.

## Lifecycle matrix

| Scenario | Command / action | Expected persisted state |
|---|---|---|
| Clean Replit start | Start `UC7 Illuminate` with `scripts/replit-dev.sh` | Neo4j data lives under `.neo4j`; API health becomes `ok`; web becomes reachable. A new empty graph is usable but not judged-workflow ready until seeded. |
| Warm/repeated Replit start | Stop and start the workflow twice | The protected local Neo4j credential and graph remain; child process groups are terminated before restart, so ports are not orphaned. |
| Clean Docker-compatible start | `NEO4J_PASSWORD=... SESSION_SECRET=... docker compose up --build --wait -d` | Named volume `neo4j-data` and bind-mounted `api/data` persist. Missing required variables fail during Compose interpolation, before product startup. |
| Repeated seed | `scripts/seed.sh --offline`, record counts, then repeat and record counts | Stable fixture-backed claim, entity, artifact, source-record, and keyed relationship identities keep facts singular. Counts and export finding identifiers remain unchanged; ingestion timestamps may advance. |
| Interrupted seed | Start `scripts/seed.sh --offline`, interrupt it, then query health | Seed metadata is `running`, never stale `complete`; primary workflow readiness is false. Rerun the same seed command to recover. |
| API restart | Restart only API process/container | Graph and `api/data` state remain. Export ledger, catalog state, and remote dataset identity are reused. |
| Frontend restart | Restart only web process/container | No graph or API state changes. Relative API routes reconnect after the web is ready. |
| Neo4j restart | Restart only Neo4j and wait for health, then refresh `/api/health?refresh=true` | Graph volume/directory remains. The already-running API reconnects through the driver and reports healthy without reseeding. |
| Complete-stack restart | Stop/start workflow or `docker compose down && docker compose up --wait -d` | Counts, seed completion, export identifiers, and publication state remain stable. Do not use `docker compose down -v`. |
| Partial restore | Restore graph and `api/data` from the same backup | Publication bookkeeping and graph export ledger stay consistent. Restoring only one side is an operator configuration error and requires restoring the matching pair. |

## Evidence capture

Before and after each boundary, capture:

```bash
curl -fsS 'http://127.0.0.1:8000/api/health?refresh=true'
docker compose ps                         # Docker-compatible run
docker compose logs --tail=100 SERVICE    # Docker-compatible run
```

Capture graph counts with:

```cypher
MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY label;
MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY type;
MATCH (m:SeedMetadata {id:'primary'}) RETURN m;
```

For replay comparison, also record ordered `finding_id` values and the catalog
preview's `export_id`, `export_version`, and `export_watermark`. Confirmation
tokens can change because they expire; that is expected. A dry run must not
create `api/data/ndia-catalog.json`.

## Publication recovery safeguards

- Export identity is the versioned pair
  `illuminate-insight-findings:<export version>` and is stable across restarts.
- Live submission requires an exact, current preview token plus explicit
  operator authorization.
- The local catalog state file is atomically replaced and persisted in
  `api/data`.
- A recorded remote dataset ID makes retries idempotent.
- A timeout or interrupted submission records `submitting`/`unknown`; another
  POST is blocked until configured remote lookup reconciles the outcome.
- Dry-run validation sends nothing and persists no publication record.

## Failure classification and recovery

| Observation | Classification | Exact recovery |
|---|---|---|
| Compose says `Set NEO4J_PASSWORD` or `Set SESSION_SECRET` | Environment configuration | Set the required variables through the environment's secret mechanism, then rerun Compose. |
| Replit says existing data needs its current password once | Environment configuration | Restore the matching credential once; the launcher writes the protected local credential file. |
| APOC jar/procedure missing | Environment packaging | Restore the declared Neo4j/APOC package; do not reseed. |
| Port already occupied after abnormal termination | Environment/process cleanup | Stop the old workflow/container, verify the owning PID, then start once. Do not delete data. |
| Seed status remains `running` after interruption | Expected safe product state | Rerun `scripts/seed.sh --offline`; successful completion replaces it with `complete`. |
| Repeated seed changes persisted fact counts or finding IDs | Product defect | Preserve before/after commands, service status, logs, count queries, and the exact seed arguments; rerun once from the same persisted state to confirm. |
| API stays unavailable after Neo4j is healthy and refreshed | Product defect | Capture Neo4j and API logs plus health JSON; restart API without reseeding and retest. |
| Publication retry sends a second POST while state is uncertain | Product defect | Stop retries, preserve `api/data/ndia-catalog.json` and sanitized logs, reconcile through lookup, then retest. |

Automated regression assertions live in `api/tests/test_seed_orchestration.py`,
`api/tests/test_exports.py`, and `api/tests/test_catalog.py`.

## Verified development execution — 2026-09-08

The QA run used the managed `UC7 Illuminate` workflow and development data.
No production service or data was touched.

- `docker compose config --quiet` accepted the checked-in configuration.
  Repeating it with empty required variables failed before startup with the
  explicit `NEO4J_PASSWORD is missing a value` configuration error.
- The managed Replit workflow reached Neo4j, Bolt/APOC, API, and web readiness.
  The first warm restart retained the prior complete seed and reported ready.
- Two consecutive `scripts/seed.sh --offline` resets produced identical seed
  terminal counts: 1,303 domain nodes and 2,123 relationships. Both public
  export snapshots contained the same ordered set of 451 finding identifiers.
- A simulated interruption stamp made refreshed health report `degraded`,
  `primary_workflow_ready=false`, and the database seed status `running`.
  A non-reset `python -m illuminate.seed.seed --offline --scenario` replay
  restored ready state without changing relationship counts or finding IDs.
- Terminating the API caused the Replit launcher to shut down the whole process
  group. The API completed application shutdown and Neo4j logged its stop six
  seconds later. Restarting the workflow restored exactly 2,272 total nodes
  (including export-ledger state), 2,123 relationships, and all 451 finding IDs.
  The UI rendered the same V-22 mission as ready after restart; evidence is in
  `docs/qa-evidence/task-34-restart-ready.jpg`.
- Optional SAM connector reads produced sanitized `RuntimeError` diagnostics
  during the offline replay but did not block deterministic seed completion.
  This is an optional connector/environment condition, not a startup defect.

### Defects found and retested

1. **Stale completion after interrupted reset.** Previously, a prior `complete`
   seed stamp survived until the end of a replay, even after reset had deleted
   graph data. The seed now records `running` before reset or writes. The forced
   interruption regression confirms no new completion stamp is written, and the
   live health/replay drill confirms the exact recovery sequence above.
2. **Export identity drift after seed reset.** Before correction, identical
   graph counts still yielded only 2 shared IDs across two 466-finding exports.
   Fixture-backed claims now use content-derived claim identities and replaying
   a committed claim does not append another review. The retest produced 451 of
   451 shared IDs and also collapsed duplicate fixture facts.