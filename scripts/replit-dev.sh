#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export NEO4J_server_directories_data="$ROOT/.neo4j/data"
export NEO4J_server_directories_logs="$ROOT/.neo4j/logs"
export NEO4J_server_directories_run="$ROOT/.neo4j/run"
export NEO4J_server_directories_transaction_logs_root="$ROOT/.neo4j/transactions"
export NEO4J_server_directories_plugins="$ROOT/.neo4j/plugins"
export NEO4J_CONF="$ROOT/.neo4j/conf"
mkdir -p "$NEO4J_server_directories_data" "$NEO4J_server_directories_logs" \
  "$NEO4J_server_directories_run" "$NEO4J_server_directories_transaction_logs_root" \
  "$NEO4J_server_directories_plugins" "$NEO4J_CONF"

NEO4J_BIN="$(readlink -f "$(command -v neo4j)")"
NEO4J_SHARE="$(cd "$(dirname "$NEO4J_BIN")/../share/neo4j" && pwd)"
ln -sf "$NEO4J_SHARE/labs/apoc-5.26.1-core.jar" \
  "$NEO4J_server_directories_plugins/apoc-5.26.1-core.jar"

cat > "$NEO4J_CONF/neo4j.conf" <<EOF
server.default_listen_address=0.0.0.0
server.directories.data=$NEO4J_server_directories_data
server.directories.logs=$NEO4J_server_directories_logs
server.directories.run=$NEO4J_server_directories_run
server.directories.transaction.logs.root=$NEO4J_server_directories_transaction_logs_root
server.directories.plugins=$NEO4J_server_directories_plugins
dbms.security.procedures.allowlist=apoc.*
dbms.security.procedures.unrestricted=apoc.*
EOF

if [ ! -f "$ROOT/.neo4j/.password-set" ]; then
  neo4j-admin dbms set-initial-password illuminate-dev --require-password-change=false
  touch "$ROOT/.neo4j/.password-set"
fi

neo4j console &
NEO4J_PID=$!

cleanup() {
  kill "${API_PID:-}" "${WEB_PID:-}" "$NEO4J_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Waiting for Neo4j..."
until curl -sf http://127.0.0.1:7474 >/dev/null; do
  if ! kill -0 "$NEO4J_PID" 2>/dev/null; then
    echo "Neo4j exited before becoming ready." >&2
    exit 1
  fi
  sleep 1
done

(
  cd api
  exec python3 -m uvicorn illuminate.main:app --host 0.0.0.0 --port 8000
) &
API_PID=$!

echo "Waiting for Illuminate API..."
until curl -sf http://127.0.0.1:8000/api/health >/dev/null; do
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "Illuminate API exited before becoming ready." >&2
    exit 1
  fi
  sleep 1
done

(
  cd web
  exec npm run dev -- --host 0.0.0.0 --port "${PORT:-8080}" --strictPort
) &
WEB_PID=$!

wait -n "$NEO4J_PID" "$API_PID" "$WEB_PID"