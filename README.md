# Illuminate — one graph, any consumer

A supplier-network intelligence platform that does not know it is about defense. Model any
consumer's dependency graph, attach evidence to every edge, and ask it questions in plain
language. Point it at a DoD program and it is **UC-7 Defense Supply Chain Illumination**;
point it at the government as a buying organisation and it is **UC-11 Automated Vendor Risk
Assessment**. NDIA Global Defense Hackathon, Washington DC, 8–10 Sep 2026.

Built from `challenges/ndia-solution-proposal.html`; the design decisions D1–D8 in that
document map onto the code as noted below.

| Layer | Stack | Where |
|---|---|---|
| Store | Neo4j 5 + APOC | `docker-compose.yml` |
| Backend | FastAPI, neo4j async driver, OpenAI SDK, MCP SDK | `api/illuminate/` |
| Frontend | Vue 3 · Vuetify 3 · Cytoscape.js (fcose) · Pinia | `web/src/` |
| Model access | user-supplied OpenAI key, encrypted at rest | Settings › Connectors |
| Agent surface | in-app tool calling **and** MCP (stdio + streamable HTTP) over one handler module | `api/illuminate/tools/`, `mcp_server.py` |

## Quick start

```bash
# 1. Neo4j
docker compose up -d neo4j

# 2. API (Python ≥ 3.12)
cd api && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m illuminate.seed.seed --reset --scenario --offline   # demo graph from committed fixtures (~1 min)
.venv/bin/uvicorn illuminate.main:app --reload --port 8000              # http://localhost:8000/docs

# 3. Web
cd ../web && npm install && npm run dev                                  # http://localhost:5173
```

Or everything in containers: `docker compose up --build` → web on http://localhost:8080,
API on :8000, Neo4j browser on :7474 (`neo4j` / `illuminate-dev`). `scripts/dev.sh` runs
the host-side variant; `scripts/seed.sh [--offline]` rebuilds the graph.

Then open **Settings › Connectors** and paste an OpenAI key to enable chat, Cypher
generation, summaries and web-search enrichment. Without one the app degrades to graph
browsing and template queries (typed questions are matched to templates by intent) — it
does not fail. Keys that need registering are listed in [`docs/ACCOUNTS.md`](docs/ACCOUNTS.md).

## What is in the demo graph

`illuminate.seed.seed` builds **V-22 Osprey Program (PMA-275)** from live sources and caches
every response under `api/illuminate/seed/fixtures/` so the graph rebuilds offline:

- **USAspending** — top-20 prime recipients by obligated amount since FY2020 (UEI, business
  types, address, place of performance, PSC/NAICS, competition → `sole_source`), plus all
  reported sub-awardees (tier 2). Awards are `Artifact {kind:'award'}` nodes.
- **GLEIF** — LEI, legal jurisdiction (`INCORPORATED_IN`), level-2 direct and ultimate
  parents (`OWNS`, `ULTIMATE_PARENT_OF`, `PARENT_SEATED_IN`). Real finding: eight tier-1
  suppliers resolve to a foreign ultimate parent (e.g. Subaru → JP, Canadian Commercial
  Corporation → CA).
- **OFAC SDN** and **SAM.gov exclusions** (public daily extract, ~34k firm/special-entity
  records) — sanctions and debarment screens on every entity, matched locally by UEI, CAGE
  and strict name, recorded as `Claim`s with the matched rows as detail. No API quota spent.
- **LittleSis + SEC EDGAR** — officers and directors as `Person` nodes with one tenured
  `HELD_ROLE` edge per term; tickers, CIKs and filings for listed firms.
- **`--scenario`** adds a clearly-labelled *simulated* adversarial tie (the brief allows
  "simulated or historical"): *Ningbo Precision Castings Ltd (simulated)*, a Delaware shell
  that manufactures in CN, 100 % owned via a HK intermediary by a CN state group, attached
  sole-source at tier 3, with a former director of its tier-2 customer on its board. Every
  synthetic node and edge carries `simulated: true` and is badged in the UI.

Try in the chat rail:

- *for all of the program's vendors, highlight goods in purple and services in yellow*
- *highlight all entities that rely on manufacturing in CN, include tier 2 and below*
- *which suppliers have a foreign ultimate parent?* · *show sole-source suppliers* · *shared directors*
- *add Acme Castings as a tier-3 supplier to AVIAN, LLC* → permission dialog with a real impact count

## How the proposal's decisions show up in code

| Decision | Implementation |
|---|---|
| **D1** one contract, two transports | `tools/contract.py` defines nine tools once; `llm/chat.py` hands them to the model, `mcp_server.py` publishes the identical list. Both call `tools/handlers.dispatch`, so the permission gate applies to external agents too. |
| **D2** graph-first retrieval | Templates and generated Cypher return real subgraphs (`graphio.py`); the canvas draws what the query returned. Vector index over filings is a stated post-hackathon cut. |
| **D3** validated Cypher | `cypher/validator.py` classifies every statement READ / WRITE / DESTRUCTIVE / SCHEMA, enforces the label/relationship/APOC allowlist, caps variable-length hops at 6, appends or clamps `LIMIT`, and rejects `CALL db.*`, `LOAD CSV`, admin commands and multi-statements. Reads run under a read session with a timeout. Executed Cypher is always shown in the UI. `cypher/templates.py` serves the named intents. |
| **D4** ask before writing | `tools/permissions.py`: a WRITE/DESTRUCTIVE statement is executed inside a transaction that is **rolled back** to get real counters, then held for the user (approve once / approve shape for session / edit / refuse). Destructive statements require the affected count to be acknowledged and never auto-approve. Three modes in Settings. Refusals return to the model as tool results. |
| **D5** enrichment proposes, trust commits | `connectors/` propose `Fact`s; `enrichment/claims.py` stages each as a `Claim` (+ `Artifact`), then the trust rule commits authoritative-connector facts, holds open-source facts until a human or a second independent source agrees, and writes the direct relationship with `claim_id` for fast traversal. |
| **D6** encoding is data | `styles.py` / `web/src/styles/styleOps.ts`: `style_ops` reference element ids; `fill`/`stroke` are palette **names** resolved to theme-tested tokens; unknown names fall back to neutral with a warning; the legend is derived from the ops. |
| **D7** credentials server-side | `vault.py` (Fernet, per user). The model receives tool results, never keys. |
| **D8** two tiers, cached prefix | `llm/client.py` picks `model_strong` / `model_fast`; `llm/prompts.py` keeps the schema+tools+taxonomy prefix constant (~1.9k tokens, above OpenAI's cache threshold) and appends per-turn context separately. |

Two modelling decisions from the proposal are visible in `schema.py`: **country is not one
field** (`INCORPORATED_IN`, `OPERATES_IN`, `MANUFACTURES_IN`, `PARENT_SEATED_IN` to `Location`
nodes) and **evidence attaches to assertions** (reified `Claim` nodes with `ASSERTS`/`TARGETS`,
`Artifact -[:EVIDENCES]-> Claim`).

## API surface

REST under `/api` (OpenAPI at `/docs`): graph/search/subgraph, entities + `/report`
(the UC-11 profile: identity, geography, control, people, six risk families with citations
and honest *no-data* rows), people, artifacts, claims (+commit/reject), query
(cypher/template/validate/styles), permissions (+approve/refuse), connectors (+credential),
enrich/jobs, workspace. Chat over `ws://…/ws/chat`; permission requests and job updates
are broadcast on the same socket. MCP at `POST /mcp/` (streamable HTTP, stateless) and
`illuminate-mcp` (stdio) — e.g. for Claude Desktop / Claude Code:

```json
{ "mcpServers": { "illuminate": { "command": "/path/to/api/.venv/bin/illuminate-mcp" } } }
```

## Tests

```bash
cd api && .venv/bin/python -m pytest -q       # validator + templates (pure) and gate + WS (live Neo4j, skipped if down)
cd web && npm run build
```

## Honest limits (unchanged from the proposal)

Entity resolution is the whole game — UEI/CAGE/LEI carry it; the residue is name matching
with a matcher tuned to refuse the subset trap (`ids.name_match_score`), and every fuzzy
merge records its method and confidence. Sub-award coverage is uneven, so tier depth varies
by program. Text-to-Cypher fails in ways that look like answers, which is why templates are
the default and the query is always shown. People are harder to resolve than companies and
coverage is skewed to large listed firms. An interlock is a lead, not a finding. **The tool
flags; it does not accuse.**

SAM.gov's personal-key tier allows ~10 Entity API calls a day, so per-vendor registration
details fill in slowly unless a federal or system-account key is used; the exclusion screen
does not depend on it because it runs against the public daily extract.

Cut on purpose for the three days: vector index over filings, multi-tenant auth, adverse
media / financial-health scoring (shown as no-data instead), market data (wired, keyed off).
