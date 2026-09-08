# Illuminate

Supplier-network intelligence: one graph, any consumer. Built for the NDIA Global Defense
Hackathon, Washington DC, 8–10 Sep 2026 (UC-7 supply chain illumination, UC-11 vendor risk).

**What it is, what is in the graph, and how it is built: open [`details.html`](details.html).**
For a concise judge-facing source-to-decision view, trust boundaries, deployment paths, and
presenter answers, see the [architecture and lineage brief](docs/architecture-lineage-brief.md).
For the timed six-minute script, failure drills, clean-session harness, recording plan, and
release gates, use the [judge demo rehearsal packet](docs/DEMO_REHEARSAL.md).
For the harsh evidence-only rubric result, evaluated revision, deductions, and unresolved
blockers, see the [versioned rubric scorecards](docs/rubric-scorecards/README.md).
For role-specific goals, safety expectations, and executable review scenarios, see the
[NDIA user personas](docs/NDIA_USER_PERSONAS.md).

Release and deployment decisions must also consult the maintained
[Product Data and Software BOM](docs/BOM.md). Run `make validate-bom` to detect
unrecorded sources, fixtures, packages, images, plugins, or incomplete metadata.

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
In Replit these guarded commands consume the existing `GITHUB_KEY` secret
automatically. Agents and contributors must never print, copy, or embed that
secret in commands, remote URLs, files, or Git configuration.

Requires Docker and `make`. For the host-side dev loop (hot reload) you also need
Python ≥ 3.12 and Node ≥ 20.

### Validate data sources

The connector contract suite is deterministic and does not require network
access, Neo4j, or connector credentials:

```bash
cd api
uv run pytest tests/test_connector_output_contracts.py \
  tests/test_live_source_validation.py tests/test_connector_diagnostics.py \
  tests/test_source_coverage_contract.py tests/test_source_lineage.py
```

Live source checks are separate, bounded, read-only diagnostics. They do not run
enrichment or write to the graph. Explicitly enable them after configuring any
credential-gated connectors through the application:

```bash
cd api
ILLUMINATE_LIVE_SOURCE_TESTS=1 uv run pytest -m live_sources -vv
```

To print the same checks as a JSON summary:

```bash
cd api
uv run illuminate-validate-sources
```

Each source reports `passed`, `skipped`, `authentication_failed`, `unavailable`,
or `contract_failed`. A skip names the missing credential; authentication and
provider failures are normalized so credentials and raw upstream responses are
never printed.

## Start

```bash
cp .env.example .env    # then set NEO4J_PASSWORD and SESSION_SECRET in it
make up                 # neo4j + api + web in containers
```

`.env` sits next to `docker-compose.yml`, so compose picks it up automatically; it also
configures the host-side API under `make dev`. Both secrets are required and have no
defaults — `make up` stops with a named variable rather than booting insecurely. `.env`
is gitignored.

Open http://localhost:8080. Then **Settings › Connectors** → paste an OpenAI key to enable
chat and Cypher generation. Without a key the app still browses the graph and answers
template questions.

If the graph is empty (first run), seed the demo program from committed fixtures:

```bash
make seed        # V-22 Osprey (PMA-275) from cached public data, ~1 min
```

Seeding runs inside the api container when the stack is up, so it needs no host Python;
under `make dev` it uses the host venv instead.

The seed reads only committed fixtures. When a connector learns to ask for more (LittleSis
now follows officers' other seats, ownership, memberships, lobbying and transactions),
record the new responses once and commit them:

```bash
cd api && .venv/bin/python -m illuminate.seed.record littlesis   # adds fixtures, touches no graph
```

Other addresses: API and docs at http://localhost:8000/docs, Neo4j browser at
http://localhost:7474. The Neo4j username is `neo4j`; its password is whatever you set
for `NEO4J_PASSWORD`. `make down` stops everything and keeps the data. `make dev` runs
Neo4j in Docker with the API and web on the host with hot reload (web on
http://localhost:5173).

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
