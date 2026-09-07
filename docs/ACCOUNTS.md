# Accounts, keys and credentials

Status as of 2026-09-07. **No accounts were created on your behalf** — every keyed
source below needs an email-verified signup, which I could not complete. Register with
berge472@gmail.com and paste the key into **Settings › Connectors** in the app; keys are
encrypted at rest (`api/data/vault.json`, key in `api/data/vault.key`) and never enter a
prompt. Record passwords in your own password manager, not here.

## Works today with no key (verified reachable 2026-09-07)

| Connector | Source | Notes |
|---|---|---|
| USAspending | api.usaspending.gov | primes, subawards, recipients (UEI), NAICS/PSC, competition |
| GLEIF | api.gleif.org | LEI, legal jurisdiction, level-2 direct/ultimate parents |
| OFAC SDN | treasury.gov sdn.csv | sanctions screen (fuzzy name match, list cached daily) |
| LittleSis | littlesis.org/api | officers, directors, tenures (CC BY-SA 4.0) |
| SEC EDGAR | sec.gov / data.sec.gov | tickers, submissions; needs the descriptive User-Agent we send |
| GDELT | api.gdeltproject.org | news; rate-limited (~1 req / 5 s, 429 otherwise) — treated as best-effort |

## Needs a key — please register

| Connector | Register at | Free? | Why we want it |
|---|---|---|---|
| **SAM.gov Entity & Exclusions** | https://api.data.gov/signup/ | yes (email verification) | registration status, CAGE, incorporation, **debarment/exclusion screen** — the authoritative negative of "approved" |
| **OpenAI** | https://platform.openai.com/api-keys | pay-as-you-go | chat, Cypher generation, extraction, summaries, web-search enrichment. Without it the app runs in template-only mode |
| OpenCorporates | https://opencorporates.com/api_accounts/new | free tier on approval | registry + officer records across jurisdictions |
| Market data (Finnhub) | https://finnhub.io/register | yes | quotes for the few listed parents; low priority |

Optional / noted but not wired: ITA Consolidated Screening List (api.trade.gov) — its TLS
certificate had expired on 2026-09-05 and 2026-09-07; data.trade.gov requires a key.

## Local infrastructure

| Thing | Value |
|---|---|
| Neo4j (docker compose) | bolt://localhost:7687 · user `neo4j` · password `illuminate-dev` · browser http://localhost:7474 |
| API | http://localhost:8000 (OpenAPI at /docs) · MCP streamable HTTP at /mcp |
| Web (vite dev) | http://localhost:5173 |
| Web (compose, nginx) | http://localhost:8080 |

Change `NEO4J_AUTH` in `docker-compose.yml` and `NEO4J_PASSWORD` in the API env together
before exposing anything beyond localhost.
