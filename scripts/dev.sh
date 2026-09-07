#!/usr/bin/env bash
# Local development: Neo4j in Docker, API and web on the host.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d neo4j
if [ ! -d api/.venv ]; then python3 -m venv api/.venv && api/.venv/bin/pip install -q -e "api[dev]"; fi
[ -d web/node_modules ] || (cd web && npm install --no-audit --no-fund)
echo "waiting for neo4j…"; until curl -sf localhost:7474 >/dev/null; do sleep 1; done
(cd api && .venv/bin/uvicorn illuminate.main:app --reload --port 8000) &
(cd web && npm run dev) &
wait
