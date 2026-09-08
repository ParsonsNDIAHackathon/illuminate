#!/usr/bin/env bash
# Rebuild the demo graph. Online by default (refreshes fixtures); --offline uses committed fixtures only.
# Works either way the stack runs: inside the api container after `make up`, or in the host venv from `make dev`.
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=${COMPOSE:-docker compose}
args=(-m illuminate.seed.seed --reset --scenario "$@")

if [ -n "$($COMPOSE ps -q --status running api 2>/dev/null)" ]; then
  exec $COMPOSE exec -T api python "${args[@]}"
elif [ -x api/.venv/bin/python ]; then
  cd api && exec .venv/bin/python "${args[@]}"
elif command -v docker >/dev/null 2>&1; then
  # Nothing up yet: a one-off api container, which starts neo4j first via depends_on.
  exec $COMPOSE run --rm api python "${args[@]}"
else
  echo "seed needs the stack: run 'make up' (containers) or 'make dev' (host venv) first" >&2
  exit 1
fi
