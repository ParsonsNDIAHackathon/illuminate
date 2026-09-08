# Illuminate

Supplier-network intelligence: one graph, any consumer. Built for the NDIA Global Defense
Hackathon, Washington DC, 8–10 Sep 2026 (UC-7 supply chain illumination, UC-11 vendor risk).

**What it is, what is in the graph, and how it is built: open [`details.html`](details.html).**

Requires Docker and `make`. For the host-side dev loop (hot reload) you also need
Python ≥ 3.12 and Node ≥ 20.

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
