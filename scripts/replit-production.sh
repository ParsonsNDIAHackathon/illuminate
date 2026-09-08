#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8080}"
STARTUP_TIMEOUT="${ILLUMINATE_STARTUP_TIMEOUT_SECONDS:-180}"
STATE_ROOT="${ILLUMINATE_STATE_ROOT:-$ROOT/.replit-production}"
NEO4J_ROOT="$STATE_ROOT/neo4j"
PYTHON="${ILLUMINATE_PYTHON:-$ROOT/api/.venv/bin/python}"

export NEO4J_URI="${NEO4J_URI:-bolt://127.0.0.1:7687}"
export NEO4J_USER="${NEO4J_USER:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-${SESSION_SECRET:-}}"
export ILLUMINATE_DATA_DIR="${ILLUMINATE_DATA_DIR:-$STATE_ROOT/illuminate}"
export ILLUMINATE_CORS_ORIGINS="${ILLUMINATE_CORS_ORIGINS:-}"

[ -x "$PYTHON" ] || {
  echo "Locked Python environment is missing; run the configured deployment build command." >&2
  exit 1
}
[ -n "$NEO4J_PASSWORD" ] || {
  echo "NEO4J_PASSWORD or SESSION_SECRET must be configured as a Replit secret." >&2
  exit 1
}

export NEO4J_server_directories_data="$NEO4J_ROOT/data"
export NEO4J_server_directories_logs="$NEO4J_ROOT/logs"
export NEO4J_server_directories_run="$NEO4J_ROOT/run"
export NEO4J_server_directories_transaction_logs_root="$NEO4J_ROOT/transactions"
export NEO4J_server_directories_plugins="$NEO4J_ROOT/plugins"
export NEO4J_CONF="$NEO4J_ROOT/conf"

mkdir -p "$NEO4J_server_directories_data" "$NEO4J_server_directories_logs" \
  "$NEO4J_server_directories_run" "$NEO4J_server_directories_transaction_logs_root" \
  "$NEO4J_server_directories_plugins" "$NEO4J_CONF" "$ILLUMINATE_DATA_DIR"

NEO4J_BIN="$(readlink -f "$(command -v neo4j)")"
NEO4J_SHARE="$(cd "$(dirname "$NEO4J_BIN")/../share/neo4j" && pwd)"
APOC_JAR="$(find "$NEO4J_SHARE/labs" -maxdepth 1 -name 'apoc-*-core.jar' -print -quit)"
[ -n "$APOC_JAR" ] || { echo "Required Neo4j APOC core plugin was not found." >&2; exit 1; }
ln -sf "$APOC_JAR" "$NEO4J_server_directories_plugins/$(basename "$APOC_JAR")"

cat > "$NEO4J_CONF/neo4j.conf" <<EOF
server.default_listen_address=127.0.0.1
server.directories.data=$NEO4J_server_directories_data
server.directories.logs=$NEO4J_server_directories_logs
server.directories.run=$NEO4J_server_directories_run
server.directories.transaction.logs.root=$NEO4J_server_directories_transaction_logs_root
server.directories.plugins=$NEO4J_server_directories_plugins
dbms.security.procedures.allowlist=apoc.*
dbms.security.procedures.unrestricted=apoc.*
EOF

if [ ! -f "$NEO4J_ROOT/.password-set" ]; then
  neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD" --require-password-change=false
  touch "$NEO4J_ROOT/.password-set"
fi

NEO4J_PID=""
API_PID=""
cleanup() {
  trap - EXIT INT TERM
  [ -z "$API_PID" ] || kill "$API_PID" 2>/dev/null || true
  [ -z "$NEO4J_PID" ] || kill "$NEO4J_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

neo4j console &
NEO4J_PID=$!

deadline=$((SECONDS + STARTUP_TIMEOUT))
remaining_seconds() {
  local remaining=$((deadline - SECONDS))
  [ "$remaining" -gt 0 ] || {
    echo "Production startup timed out after ${STARTUP_TIMEOUT}s." >&2
    return 1
  }
  printf '%s\n' "$remaining"
}

echo "Waiting for Neo4j..."
until curl --max-time 2 -fsS http://127.0.0.1:7474/ >/dev/null; do
  kill -0 "$NEO4J_PID" 2>/dev/null || { echo "Neo4j exited before becoming ready." >&2; exit 1; }
  [ "$SECONDS" -lt "$deadline" ] || { echo "Neo4j readiness timed out after ${STARTUP_TIMEOUT}s." >&2; exit 1; }
  sleep 1
done

echo "Verifying Neo4j Bolt authentication and APOC..."
remaining="$(remaining_seconds)"
if ! timeout --foreground --signal=TERM --kill-after=5 "${remaining}s" "$PYTHON" - <<'PY'
import os
from neo4j import GraphDatabase

with GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
) as driver:
    driver.verify_connectivity()
    with driver.session(database=os.environ.get("NEO4J_DATABASE", "neo4j")) as session:
        version = session.run("RETURN apoc.version() AS version").single()["version"]
        available = session.run(
            "CALL apoc.help('apoc.path.subgraphAll') "
            "YIELD name RETURN count(name) > 0 AS available"
        ).single()["available"]
        if not version or not available:
            raise RuntimeError("required APOC procedure apoc.path.subgraphAll is unavailable")
print("Neo4j Bolt authentication and APOC are ready.")
PY
then
  echo "Neo4j Bolt/APOC verification failed or exceeded the startup deadline." >&2
  exit 1
fi

echo "Preparing deterministic mission dataset..."
remaining="$(remaining_seconds)"
if ! (cd api && timeout --foreground --signal=TERM --kill-after=5 "${remaining}s" \
  "$PYTHON" -m illuminate.seed.seed --offline --scenario --skip-enrich); then
  echo "Mission dataset preparation failed or exceeded the startup deadline." >&2
  exit 1
fi

[ -f "$ROOT/web/dist/index.html" ] || {
  echo "Production frontend build is missing; run the configured deployment build command." >&2
  exit 1
}

echo "Starting Illuminate on port $PORT..."
(cd api && exec "$PYTHON" -m uvicorn illuminate.main:app --host 0.0.0.0 --port "$PORT") &
API_PID=$!

while true; do
  health_json="$(curl --max-time 5 -fsS "http://127.0.0.1:$PORT/api/health?refresh=true" 2>/dev/null || true)"
  if [ -n "$health_json" ] && "$PYTHON" -c \
    'import json,sys; h=json.load(sys.stdin); raise SystemExit(0 if h.get("ok") and h.get("primary_workflow_ready") else 1)' \
    <<<"$health_json"; then
    break
  fi
  kill -0 "$API_PID" 2>/dev/null || { echo "Illuminate API exited before becoming ready." >&2; exit 1; }
  [ "$SECONDS" -lt "$deadline" ] || { echo "Illuminate readiness timed out after ${STARTUP_TIMEOUT}s." >&2; exit 1; }
  sleep 1
done

remaining="$(remaining_seconds)"
probe_timeout=$((remaining < 5 ? remaining : 5))
if ! curl --max-time "$probe_timeout" -fsS "http://127.0.0.1:$PORT/" | grep -q '<div id="app"></div>'; then
  echo "Production SPA failed its startup probe." >&2
  exit 1
fi
if [ "$(curl --max-time "$probe_timeout" -sS -o /dev/null -w '%{http_code}' \
  -X POST "http://127.0.0.1:$PORT/mcp" -H 'content-type: application/json' --data '{}')" != "307" ]; then
  echo "Production MCP redirect failed its startup probe." >&2
  exit 1
fi
if [ -n "${ILLUMINATE_MCP_HTTP_TOKEN:-}" ]; then
  mcp_json="$(curl --max-time "$probe_timeout" -fsS -X POST "http://127.0.0.1:$PORT/mcp/" \
    -H "authorization: Bearer $ILLUMINATE_MCP_HTTP_TOKEN" \
    -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"startup-probe","version":"1"}}}')"
  if ! "$PYTHON" -c \
    'import json,sys; r=json.load(sys.stdin); raise SystemExit(0 if r.get("result") else 1)' \
    <<<"$mcp_json"; then
    echo "Authenticated production MCP transport failed its startup probe." >&2
    exit 1
  fi
else
  if [ "$(curl --max-time "$probe_timeout" -sS -o /dev/null -w '%{http_code}' \
    "http://127.0.0.1:$PORT/mcp/")" != "503" ]; then
    echo "Disabled production MCP transport did not fail closed." >&2
    exit 1
  fi
fi
echo "Illuminate production runtime is ready (API, SPA, and protected MCP boundary)."

wait -n "$NEO4J_PID" "$API_PID"
echo "A required production process exited; shutting down." >&2
exit 1