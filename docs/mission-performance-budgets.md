# Mission performance budgets

The judged path uses the committed offline seed fixtures and a five-second warm-request target. This is a smoke budget, not production capacity testing.

| Action | Baseline class | Target |
| --- | --- | ---: |
| API/database readiness | startup-ready | 5,000 ms diagnostic target |
| Initial program graph | warm path | 5,000 ms |
| Each named graph preset | warm path | 5,000 ms |
| Vendor report | warm path | 5,000 ms |
| Comparison data | warm path | 5,000 ms |
| Export graph data | warm path | 5,000 ms |

Exact requests and machine-readable targets live in `config/mission-performance-budgets.json`. Comparison currently measures the bounded two-vendor data request; export measures the bounded graph payload that the client exports. This keeps the harness independent of presentation formats.

The 2026-09-08 Replit deterministic-fixture baseline used three samples per operation. Startup reached Neo4j in 18 seconds and the API in 24 seconds. Warm-path maxima were: readiness 4 ms, initial program graph 37 ms, presets 44 ms, vendor report 22 ms, comparison data 8 ms, and export data 37 ms. All judged requests met the five-second target. The Docker baseline is recorded in `.performance/docker.json`; generate a fresh local record after material runtime or fixture changes. Because the Replit Docker daemon used for that record blocks bridge forwarding, the runtime check used an uncommitted host-network override. The committed bridge topology, DNS names, and published-port configuration were validated statically but must be exercised on a normal Docker host.

## Repeatable measurement

Start either supported stack, seed it without network calls, and run:

```sh
./scripts/seed.sh --offline
python3 scripts/measure-mission-performance.py --environment replit --reset-fixture --output .performance/replit.json
# or, against docker compose:
python3 scripts/measure-mission-performance.py --environment docker --reset-fixture --output .performance/docker.json
```

`--reset-fixture` is destructive: it replaces the local graph with the committed offline demo fixture. The command uses only Python's standard library. It verifies the expected fixture identity and useful response content, prints median/max latency and maximum payload bytes for every action, and exits non-zero for request errors or a warm sample over budget. Failures include the method and path; slow results tell the operator to inspect query plan, cardinality, and payload size. The JSON output is the per-environment baseline record.

To include stack launch time in a baseline, start from a stopped stack and pass its launch command:

```sh
python3 scripts/measure-mission-performance.py --environment replit --start-command scripts/replit-dev.sh --reset-fixture
python3 scripts/measure-mission-performance.py --environment docker --start-command "docker compose up" --reset-fixture
```

Timing gates deliberately apply to warm deterministic requests. Startup readiness is recorded separately because first startup includes Neo4j and schema initialization and varies with allocated host resources.

## Enforced bounds

- Search returns 1–50 results.
- Entity, people, and artifact pages return 1–1,000 results; entity offsets are 0–100,000.
- Graph traversal depth is 1–6 and neighbourhood size is 1–1,000 nodes.
- Validated free-form Cypher defaults to 500 rows and clamps at 2,000.
- Database reads use the configured transaction timeout and fetch at most the global maximum plus one row.