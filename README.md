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

## Recent news on the map

Open the map to load recent GDELT coverage. Search a topic and choose the past 24 hours,
3 days, or 7 days. Coral diamonds select source articles mentioning that country in their
headline. These are approximate country mentions, not verified incident locations; articles
without a recognized country remain available under **Unplaced**. Matching currently uses
English country names and selected aliases, so other languages often remain unplaced.
The News checkbox hides the overlay without changing entity locations.

The read-only `/api/news?query=flood&timespan=24h` endpoint uses GDELT DOC 2.0, requests
up to 250 recent articles, and caches responses for five minutes. No API key is required.
The API retries a rate-limited request once after six seconds; persistent outages and rate
limits appear as retryable errors. After code changes, rebuild the running containers with
`docker compose up -d --build --no-deps api web`. See the
[GDELT DOC API documentation](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/).

Map controls use the same Vuetify components as the Explorer. News queries, results,
location filters, and selection persist while navigating between views during a session.
Selecting a headline opens the Explorer inspector; **View article details** reuses the
artifact viewer for metadata and raw GDELT data, and **Open source** uses the shared
source viewer. News search results are previews and are not automatically saved as
graph artifacts. Failed searches retain the previous labelled results.

## Shipping routes on the map

In **Map**, enable **Shipping**. Select a square port marker to filter route records
using that port, or select a route line / **Inspect route** to review goods, linked
supplier and customer, segment itinerary, evidence source, record date and notes.
**Route evidence** filters confirmed (solid teal), inferred (dashed amber) and
illustrative (dotted violet) records. Counts are records and unique linked suppliers /
destinations, not shipment volumes. Routes follow the loaded graph scope and search;
both entities and their exact directional `SUPPLIES` relationship must be loaded.

The bundled catalog contains **two hypothetical alternatives** from Nagoya to Los
Angeles or Oakland, linked to the demo SUBARU → V-22 relationship for demonstration.
Neither route nor its example cargo is a claim about actual supplier logistics.
Port positions and ocean waypoints are approximate. Inland legs, live AIS positions,
schedules, travel times and automated disruption scoring are not included. News
country mentions do not establish route disruptions, and the overlay does not change
vendor risk scores or create graph assertions.

`GET /api/shipping` serves the validated catalog. To use your own records, copy
`api/illuminate/shipping_demo.json` to `api/data/shipping.json` (or `shipping.json`
inside `ILLUMINATE_DATA_DIR`), replace its contents, and click **Refresh**. The override
replaces the entire demo catalog; an explicit empty catalog disables the examples.
A malformed override reports an error instead of silently falling back to demo data.
The data directory is included in the existing backup workflow.

Catalog format:

- `ports`: unique `id`, `name`, two-letter `country`, `latitude`, `longitude`.
- `routes`: unique `id`, `name`, `supplier_id`, `customer_id`, `relationship_id`,
  `goods`, `status`, `source: {title, reference}`, `updated_at` (ISO date), `notes`,
  and an ordered, nonempty `segments` list.
- Each segment has `from_port`, `to_port`, optional `waypoints` (latitude/longitude)
  and optional `passages` (names). Adjacent segments must share a connecting port.
  Pacific crossings are split at the date line when drawn.

Use **confirmed** only when a source documents that supplier's route and cargo;
**inferred** requires an explanation of the inference in `notes`; **illustrative**
is for scenarios without shipment evidence. `source.reference` can be an HTTP(S)
evidence URL or a document reference. Status is supplied by the catalog author, not
independently certified by the app. `updated_at` is the record's review date, not a
vessel position or departure time. There is no catalog editing UI in this first version.
