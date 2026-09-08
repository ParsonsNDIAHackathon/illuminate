# Illuminate

Supplier-network intelligence: one graph, any consumer. Built for the NDIA Global Defense
Hackathon, Washington DC, 8–10 Sep 2026 (UC-7 supply chain illumination, UC-11 vendor risk).

**What it is, what is in the graph, and how it is built: open [`details.html`](details.html).**
For a concise judge-facing source-to-decision view, trust boundaries, deployment paths, and
presenter answers, see the [architecture and lineage brief](docs/architecture-lineage-brief.md).
For role-specific goals, safety expectations, and executable review scenarios, see the
[NDIA user personas](docs/NDIA_USER_PERSONAS.md).

**Building a partner consumer:** see the
[`Interoperability consumer guide`](docs/INTEROPERABILITY.md) for versioned
findings, incremental retrieval, provenance, simulation handling, and the
planned NDIA catalog contribution.

**New contributor? Follow the [contributor onboarding guide](docs/ONBOARDING.md)**
to create a task, work in a branch, open a pull request, and run Illuminate
locally.

GitHub `origin/main` is the canonical shared history. Before starting work on a
clean Replit `main`, run `make sync-pre`. After reviewed, validated work reaches
Replit `main`, run `make sync-publish`; see the
[main-branch synchronization policy](docs/ONBOARDING.md#keep-replit-main-and-github-main-synchronized).

Requires Docker and `make`. For the host-side dev loop (hot reload) you also need
Python ≥ 3.12 and Node ≥ 20.

## Start

```bash
export NEO4J_PASSWORD='choose-a-unique-password'
export SESSION_SECRET='choose-a-different-long-random-value'
make up          # neo4j + api + web in containers
```

Open http://localhost:8080. Then **Settings › Connectors** → paste an OpenAI key to enable
chat and Cypher generation. Without a key the app still browses the graph and answers
template questions.

If the graph is empty (first run), seed the demo program from committed fixtures:

```bash
make seed        # V-22 Osprey (PMA-275) from cached public data, ~1 min
```

Seeding runs inside the api container when the stack is up, so it needs no host Python;
under `make dev` it uses the host venv instead.

`make up` waits for Neo4j, database-aware API health, and the web server. API health and
mission readiness are intentionally separate: before the first seed,
`/api/health?refresh=true` returns HTTP 200 with `primary_workflow_ready: false` and an
operator action. After `make seed`, it must report `ok: true` and
`primary_workflow_ready: true`.

Other addresses: API and docs at http://localhost:8000/docs, Neo4j browser at
http://localhost:7474. Set unique `NEO4J_PASSWORD` and `SESSION_SECRET` environment
values before `make up`; the username is `neo4j`. `make down` stops everything and keeps
the data. `make dev` runs Neo4j in Docker with the API and web on the host with hot reload
(web on http://localhost:5173).


### Docker operations

- **Configuration:** Compose injects the same `NEO4J_*`, `SESSION_SECRET`,
  `ILLUMINATE_DATA_DIR`, and CORS settings used by the host launchers. Keep secrets in
  the environment or an uncommitted `.env`; never add them to an image or the repository.
- **Persistence:** the graph lives in the `neo4j-data` volume. Workspace settings,
  encrypted connector keys, and caches live in `api/data/`. Both survive `make down`.
  `docker compose down -v` deliberately deletes the graph volume and is not a routine
  shutdown command.
- **Seed and schema:** the API applies idempotent schema setup on startup. `make seed`
  resets and stamps the deterministic offline mission fixture; it is destructive to the
  current graph.
- **Shutdown:** `make down` asks all containers to stop and preserves state. Use
  `docker compose logs api neo4j web` when a service fails or becomes unhealthy.
- **Recovery:** if a retained graph rejects the configured password, restore the original
  password or restore a known backup; changing only the environment cannot change an
  existing Neo4j store password. See **Restart from a backup** below.

## Back up

```bash
make backup      # → backups/illuminate-YYYYmmdd-HHMMSS.tgz
make backups     # list them
```

The archive holds the Neo4j volume (the graph) and `api/data/` (your encrypted keys and
workspace settings). Neo4j is stopped for a few seconds while the copy is taken, then
restarted. Chat history is in memory only and is not backed up.

## Restart from a backup

Put the archive in `backups/`, then either:

```bash
make restore BACKUP=latest                 # or BACKUP=illuminate-20260908-130123.tgz
```

or boot compose straight from it (the `restore` step runs before Neo4j and does nothing
when `BACKUP` is unset):

```bash
make down
BACKUP=illuminate-20260908-130123.tgz make up
```

Either way the graph and `api/data/` are replaced with the archive's contents. Don't put
`BACKUP` in `.env` or it will restore on every start.

`make help` lists all targets.

## Replit production deployment

Replit production uses a reserved VM because Illuminate runs a WebSocket endpoint,
a background worker, and an embedded Neo4j process. Publishing runs:

```bash
UV_PROJECT_ENVIRONMENT=$PWD/api/.venv uv sync --project api --frozen --no-dev
npm --prefix web ci
npm --prefix web run build
bash scripts/replit-production.sh
```

The launcher prepares writable Neo4j directories, enables the bundled APOC core
plugin, waits for Neo4j, rebuilds the deterministic offline V-22 mission dataset,
then serves the API, MCP transport (`/mcp/`), WebSocket endpoint, and built Vue SPA
from one public origin. A missing plugin, failed seed, failed process, or readiness
timeout terminates startup rather than exposing a partially healthy deployment.

### Environment

- `PORT` is supplied by Replit and must not be hardcoded.
- `NEO4J_PASSWORD` must be set as a Replit secret. If omitted, the launcher uses
  the required `SESSION_SECRET`; never expose Neo4j's internal ports publicly.
- Keep the selected password secret stable for retained VM state. Changing it
  without resetting the deployment-local Neo4j store causes startup to fail
  clearly rather than running with mismatched credentials.
- `ILLUMINATE_STATE_ROOT` optionally relocates Neo4j and workspace state.
- `ILLUMINATE_STARTUP_TIMEOUT_SECONDS` optionally changes the 180-second startup
  deadline.
- Connector credentials remain optional and must be configured through Replit
  Secrets or the app's connector settings; do not commit them.

The VM filesystem should not be treated as a durable backup. A rebuild or a new
deployment can replace local Neo4j and application state, and the deterministic
fixtures are seeded again at startup. Use the existing Docker backup path for
portable archives; long-term production persistence requires a separately managed
database, which is outside this deployment.

To redeploy, merge the desired revision to `main`, open Replit Publishing, and
publish again. After publishing, verify `/api/health?refresh=true` reports
`ok: true` and `primary_workflow_ready: true`, then load the root page and start
the V-22 mission from the guided entry screen.

### Replit development operations

The configured `UC7 Illuminate` workflow runs `scripts/replit-dev.sh`: Nix Neo4j with
APOC, the host API on port 8000, and the Vite UI on port 8080. It generates a protected
local Neo4j password when none is supplied, stores Neo4j state under `.neo4j/`, and uses
the same `api/data/` workspace state as Compose. Run `make seed` to reset the deterministic
fixture, then verify `/api/health?refresh=true` as above. Stopping or restarting the
workflow terminates all three child processes; their state remains on disk.

If `.neo4j/` predates the protected local credential file, export that store's current
`NEO4J_PASSWORD` once so the launcher can adopt it. A missing or unusable APOC plugin,
Neo4j exit, API exit, web exit, or 180-second readiness timeout is printed to the workflow
log and terminates startup instead of silently serving a partial process tree. Set
`ILLUMINATE_STARTUP_TIMEOUT_SECONDS` to override that deadline.
