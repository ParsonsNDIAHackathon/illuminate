#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STARTED_AT=$SECONDS
STARTUP_TIMEOUT="${ILLUMINATE_STARTUP_TIMEOUT_SECONDS:-180}"
SHUTDOWN_TIMEOUT="${ILLUMINATE_SHUTDOWN_TIMEOUT_SECONDS:-10}"
DEADLINE=$((SECONDS + STARTUP_TIMEOUT))
WEB_PORT="${PORT:-8080}"

export NEO4J_server_directories_data="$ROOT/.neo4j/data"
export NEO4J_server_directories_logs="$ROOT/.neo4j/logs"
export NEO4J_server_directories_run="$ROOT/.neo4j/run"
export NEO4J_server_directories_transaction_logs_root="$ROOT/.neo4j/transactions"
export NEO4J_server_directories_plugins="$ROOT/.neo4j/plugins"
export NEO4J_CONF="$ROOT/.neo4j/conf"
mkdir -p "$NEO4J_server_directories_data" "$NEO4J_server_directories_logs" \
  "$NEO4J_server_directories_run" "$NEO4J_server_directories_transaction_logs_root" \
  "$NEO4J_server_directories_plugins" "$NEO4J_CONF"

PASSWORD_FILE="$ROOT/.neo4j/dev-password"
if [ ! -f "$PASSWORD_FILE" ]; then
  if [ -f "$ROOT/.neo4j/.password-set" ]; then
    if [ -z "${NEO4J_PASSWORD:-}" ]; then
      echo "Existing Neo4j data needs its current NEO4J_PASSWORD once to create the protected local credential file." >&2
      exit 1
    fi
  fi
  umask 077
  if [ -n "${NEO4J_PASSWORD:-}" ]; then
    printf '%s\n' "$NEO4J_PASSWORD" > "$PASSWORD_FILE"
  else
    python3 - <<'PY' > "$PASSWORD_FILE"
import secrets
print(secrets.token_urlsafe(32))
PY
  fi
fi
export NEO4J_PASSWORD="$(cat "$PASSWORD_FILE")"

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

if [ ! -f "$ROOT/.neo4j/.password-set" ]; then
  neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD" --require-password-change=false
  touch "$ROOT/.neo4j/.password-set"
fi

setsid neo4j console &
NEO4J_PID=$!

cleanup() {
  local rc=$?
  local pid
  local -a pids=()
  local -a running=()
  trap - EXIT INT TERM
  for pid in "${API_PID:-}" "${WEB_PID:-}" "${NEO4J_PID:-}"; do
    [ -z "$pid" ] || pids+=("$pid")
  done
  for pid in "${pids[@]}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  local shutdown_deadline=$((SECONDS + SHUTDOWN_TIMEOUT))
  while true; do
    running=()
    for pid in "${pids[@]}"; do
      kill -0 -- "-$pid" 2>/dev/null && running+=("$pid")
    done
    [ "${#running[@]}" -gt 0 ] || break
    if [ "$SECONDS" -ge "$shutdown_deadline" ]; then
      for pid in "${running[@]}"; do
        kill -KILL -- "-$pid" 2>/dev/null || true
      done
      break
    fi
    sleep 0.2
  done
  for pid in "${pids[@]}"; do
    kill -0 "$pid" 2>/dev/null || wait "$pid" 2>/dev/null || true
  done
  return "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Waiting for Neo4j..."
until curl --max-time 2 -sf http://127.0.0.1:7474 >/dev/null; do
  if ! kill -0 "$NEO4J_PID" 2>/dev/null; then
    echo "Neo4j exited before becoming ready." >&2
    exit 1
  fi
  if [ "$SECONDS" -ge "$DEADLINE" ]; then
    echo "Neo4j readiness timed out after ${STARTUP_TIMEOUT}s." >&2
    exit 1
  fi
  sleep 1
done
echo "Neo4j ready after $((SECONDS - STARTED_AT))s"

echo "Verifying Neo4j Bolt authentication and APOC..."
remaining=$((DEADLINE - SECONDS))
[ "$remaining" -gt 0 ] || {
  echo "Neo4j Bolt/APOC verification exceeded the ${STARTUP_TIMEOUT}s startup deadline." >&2
  exit 1
}
probe_timeout=$((remaining < 15 ? remaining : 15))
if ! timeout --foreground --signal=TERM --kill-after=2 "${probe_timeout}s" python3 - <<'PY'
import os
from neo4j import GraphDatabase

with GraphDatabase.driver(
    "bolt://127.0.0.1:7687",
    auth=("neo4j", os.environ["NEO4J_PASSWORD"]),
) as driver:
    driver.verify_connectivity()
    with driver.session() as session:
        version = session.run("RETURN apoc.version() AS version").single()["version"]
        available = session.run(
            "CALL apoc.help('apoc.path.subgraphAll') "
            "YIELD name RETURN count(name) > 0 AS available"
        ).single()["available"]
        if not version or not available:
            raise RuntimeError("required APOC procedure apoc.path.subgraphAll is unavailable")
PY
then
  echo "Neo4j Bolt authentication or APOC verification failed." >&2
  exit 1
fi

setsid bash -c 'cd api && exec python3 -m uvicorn illuminate.main:app --host 0.0.0.0 --port 8000' &
API_PID=$!

echo "Waiting for Illuminate API..."
until curl --max-time 5 -sf http://127.0.0.1:8000/api/health | grep -q '"ok":true'; do
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "Illuminate API exited before becoming ready." >&2
    exit 1
  fi
  if [ "$SECONDS" -ge "$DEADLINE" ]; then
    echo "Illuminate API readiness timed out after ${STARTUP_TIMEOUT}s." >&2
    exit 1
  fi
  sleep 1
done
echo "Illuminate API ready after $((SECONDS - STARTED_AT))s"

setsid bash -c 'cd web && exec npm run dev -- --host 0.0.0.0 --port "$1" --strictPort' _ "$WEB_PORT" &
WEB_PID=$!

echo "Waiting for Illuminate web..."
until curl --max-time 2 -sf "http://127.0.0.1:$WEB_PORT/" >/dev/null; do
  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    echo "Illuminate web exited before becoming ready." >&2
    exit 1
  fi
  if [ "$SECONDS" -ge "$DEADLINE" ]; then
    echo "Illuminate web readiness timed out after ${STARTUP_TIMEOUT}s." >&2
    exit 1
  fi
  sleep 1
done
echo "Illuminate development stack ready after $((SECONDS - STARTED_AT))s"

wait -n "$NEO4J_PID" "$API_PID" "$WEB_PID"