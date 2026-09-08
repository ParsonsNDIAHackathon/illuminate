#!/usr/bin/env bash
# Prove the documented fixture-mode stack parses without a cache authority while
# retaining the fail-closed live-retrieval contract.
set -euo pipefail
cd "$(dirname "$0")/.."

config="$(
  env \
    -u ILLUMINATE_FETCH_CACHE_URL \
    -u ILLUMINATE_FETCH_CACHE_REQUIRED \
    -u ILLUMINATE_FETCH_CACHE_AUTHORITY_ENABLED \
    NEO4J_PASSWORD=compose-test-password \
    SESSION_SECRET=compose-test-session-secret \
    docker compose --env-file /dev/null -f docker-compose.yml config --format json
)"

printf '%s' "$config" | python -c '
import json
import sys

document = json.load(sys.stdin)
environment = document["services"]["api"]["environment"]
assert environment["ILLUMINATE_FETCH_CACHE_URL"] == ""
assert environment["ILLUMINATE_FETCH_CACHE_REQUIRED"] == "true"
assert environment["ILLUMINATE_FETCH_CACHE_AUTHORITY_ENABLED"] == "false"
'

echo "ok - fixture-mode compose config keeps live retrieval fail-closed"