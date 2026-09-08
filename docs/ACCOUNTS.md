# Accounts, keys and credentials

Status as of 2026-09-07. **No accounts are created on an operator's behalf** — keyed
sources may require an email-verified signup. Use an approved organization account and
paste the key into **Settings › Connectors** in the app; keys are
encrypted at rest (`api/data/vault.json`, key in `api/data/vault.key`) and never enter a
prompt. Record passwords in your own password manager, not here.

## Works today with no key (verified reachable 2026-09-07)

| Connector | Source | Notes |
|---|---|---|
| USAspending | api.usaspending.gov | primes, subawards, recipients (UEI), NAICS/PSC, competition |
| GLEIF | api.gleif.org | LEI, legal jurisdiction, level-2 direct/ultimate parents |
| OFAC SDN | treasury.gov sdn.csv | sanctions screen (fuzzy name match, list cached daily); organisation and individual designations screened separately |
| **UN Security Council Consolidated List** | scsanctions.un.org consolidated.xml | multilateral sanctions screen; 275 entity and 736 individual designations with committee regime and listing date. The published URL 302s to a short-lived signed blob, so the fetch follows redirects and the diagnostic reads a 3xx as healthy |
| LittleSis | littlesis.org/api | officers, directors, tenures (CC BY-SA 4.0) |
| SEC EDGAR | sec.gov / data.sec.gov | tickers, submissions; needs the descriptive User-Agent we send |
| GDELT | api.gdeltproject.org | news; rate-limited (~1 req / 5 s, 429 otherwise) — treated as best-effort |
| **SAM.gov Exclusions (public extract)** | sam.gov Data Services daily ZIP | debarment/suspension screen done locally against ~34k firm + special-entity records; no key, no quota; slim index committed in fixtures for offline use |

## Needs a key — please register

| Connector | Register at | Free? | Why we want it |
|---|---|---|---|
| SAM.gov Entity Management | https://sam.gov → login.gov → Individual account → Workspace › Profile › **API Key** | yes, ~10 req/day | registration status, CAGE, incorporation, NAICS per vendor. **Key received and stored 2026-09-07.** Exclusions no longer need this key (see public extract above) |
| **OpenAI** | https://platform.openai.com/api-keys | pay-as-you-go | chat, Cypher generation, extraction, summaries, web-search enrichment. Without it the app runs in template-only mode |
| OpenCorporates | https://opencorporates.com/api_accounts/new | free tier on approval | registry + officer records across jurisdictions |
| Market data (Finnhub) | https://finnhub.io/register | yes | quotes for the few listed parents; low priority |

Optional / noted but not wired: ITA Consolidated Screening List (api.trade.gov) — its TLS
certificate had expired on 2026-09-05 and 2026-09-07; data.trade.gov requires a key.

## Already in the vault

| Credential | Vault slot | Status |
|---|---|---|
| SAM.gov API key | `sam` | stored encrypted when configured; personal tiers may be heavily throttled. The connector backs off on 429 and stops its SAM seed pass at the first quota response |
| api.data.gov key | `api_data_gov` | stored encrypted when configured; not used by a connector yet |

## Local infrastructure

| Thing | Value |
|---|---|
| Neo4j (docker compose) | bolt://localhost:7687 · user `neo4j` · operator-supplied password · browser http://localhost:7474 |
| API | http://localhost:8000 (OpenAPI at /docs) · MCP streamable HTTP at /mcp |
| Web (vite dev) | http://localhost:5173 |
| Web (compose, nginx) | http://localhost:8080 |

Set unique `NEO4J_PASSWORD` and `SESSION_SECRET` environment values before starting
Docker Compose. Do not expose the database or API directly beyond localhost.
