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

## Shipping, US highways and rail

In **Map**, enable **Shipping** for supplier-linked journeys. **US highways** and
**US rail** are independent reference layers, available even when no supplier route
is loaded. Use **US** to fit the contiguous United States; search **Find corridor or
city**, then select a line or **Inspect US corridor** for its stops, source and notes.
Blue lines are Interstates; dashed orange lines are freight rail corridors.

The curated reference includes selected stretches of I-5, I-10, I-15, I-20, I-35,
I-40, I-70, I-75, I-80, I-90 and I-95, plus BNSF Southern Transcon, Union Pacific
Overland and Norfolk Southern Heartland connections. Geography is a schematic
sequence of nearby cities, not surveyed road/track centerlines or a complete network.
Highway coverage is Interstate-only; local streets, port access, drayage and final-mile
roads are omitted. City/hub markers do not identify actual supplier facilities.
The reference comes from [FHWA](https://www.fhwa.dot.gov/Planning/national_highway_system/),
[BNSF](https://www.bnsf.com/ship-with-bnsf/maps-and-shipping-locations/index.page),
[Union Pacific](https://www.up.com/aboutup/reference/maps/) and
[Norfolk Southern](https://www.norfolksouthern.com/en/ship-by-rail/our-rail-network).
No current closure, capacity, operating schedule or guaranteed through service is implied.

### Supplier journeys

Select a square port or circular inland hub to filter dependent route records.
Select a journey to review its supplier/customer link, cargo, ordered ocean/truck/rail
legs, corridor names, sources and record date. **Journey transport** selects whole
journeys containing that mode, preserving connecting legs. **Route evidence** filters
confirmed, inferred and illustrative records. Counts are journey records and unique
suppliers/destinations, not shipment volumes. Both entities and their exact directional
`SUPPLIES` relationship must be present in the loaded graph scope; supplier search
also matches route modes, corridors and connection areas. Reference layers have their
own search and are not evidence of supplier use.

The demo has five **hypothetical alternatives**, all attached to the existing SUBARU
→ V-22 supplier relationship: Nagoya–Los Angeles and Nagoya–Oakland ocean examples;
a Los Angeles–Barstow–Oklahoma City–Chicago trucking continuation using I-10/I-15,
I-40 and I-35/I-80; and two rail continuations to Chicago, via Union Pacific from
Oakland and BNSF from Los Angeles. Neither cargo nor actual use of these lanes by
SUBARU is verified. Chicago is a logistics connection area, not the V-22 delivery site.
Connecting service, terminal transfers and final delivery are not modeled.

`GET /api/shipping` serves the supplier catalog. Copy `api/illuminate/shipping_demo.json`
to `api/data/shipping.json` (or `shipping.json` in `ILLUMINATE_DATA_DIR`), replace its
contents and click **Refresh** to use your own records. The override replaces the demo;
an empty catalog disables its examples. Invalid overrides report an error, retaining
previously loaded UI records with a warning. There is no catalog editor in this version.
`GET /api/shipping/network` separately serves the bundled US reference; overriding
supplier records does not replace this reference. Both JSON assets ship in the API package.

Catalog format (old ocean-only catalogs remain compatible):

- `ports`: unique `id`, `name`, two-letter `country`, `latitude`, `longitude`, and optional
  `kind` (`port`, `hub`, `intermodal`; defaults to `port`). The legacy `ports` key now
  accommodates inland connection areas as well as seaports.
- `routes`: unique `id`, `name`, `supplier_id`, `customer_id`, `relationship_id`, `goods`,
  `status`, `source: {title, reference}`, `updated_at` (ISO date), `notes`, and ordered
  nonempty `segments`.
- Segments: `from_port`, `to_port`, optional `waypoints`, `passages`, `mode` (defaults
  to `ocean`) and `source`. Domestic modes (`truck`, `rail`) require US endpoints,
  corridor names and a source; truck names must be Interstate designations. Ocean
  segments must connect ports. Adjacent legs must connect, and Pacific geometry is
  split at the date line.

Use **confirmed** only with shipment evidence, **inferred** with an explained inference,
and **illustrative** for scenarios. A corridor reference documents infrastructure,
not shipment evidence. Status is author supplied, not independently certified by the app.
Dates are record review dates. The overlays do not create graph assertions or change
vendor risk scores, and nearby news does not establish disruption of a route.
