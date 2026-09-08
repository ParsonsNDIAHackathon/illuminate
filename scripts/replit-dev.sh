#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STARTED_AT=$SECONDS
STARTUP_TIMEOUT="${ILLUMINATE_STARTUP_TIMEOUT_SECONDS:-180}"
SHUTDOWN_TIMEOUT="${ILLUMINATE_SHUTDOWN_TIMEOUT_SECONDS:-10}"
DEADLINE=$((SECONDS + STARTUP_TIMEOUT))
WEB_PORT="${PORT:-8080}"
NEO4J_ROOT="${ILLUMINATE_NEO4J_ROOT:-$ROOT/.neo4j}"

export NEO4J_server_directories_data="$NEO4J_ROOT/data"
export NEO4J_server_directories_logs="$NEO4J_ROOT/logs"
export NEO4J_server_directories_run="$NEO4J_ROOT/run"
export NEO4J_server_directories_transaction_logs_root="$NEO4J_ROOT/transactions"
export NEO4J_server_directories_plugins="$NEO4J_ROOT/plugins"
export NEO4J_CONF="$NEO4J_ROOT/conf"
mkdir -p "$NEO4J_server_directories_data" "$NEO4J_server_directories_logs" \
  "$NEO4J_server_directories_run" "$NEO4J_server_directories_transaction_logs_root" \
  "$NEO4J_server_directories_plugins" "$NEO4J_CONF"

PASSWORD_FILE="$NEO4J_ROOT/dev-password"
PASSWORD_MARKER="$NEO4J_ROOT/.password-set"
CONFIGURED_PASSWORD="${NEO4J_PASSWORD:-${SESSION_SECRET:-}}"
STORED_PASSWORD=""
[ ! -f "$PASSWORD_FILE" ] || STORED_PASSWORD="$(cat "$PASSWORD_FILE")"
NEEDS_CREDENTIAL_MIGRATION=0

if [ -n "$CONFIGURED_PASSWORD" ]; then
  export NEO4J_PASSWORD="$CONFIGURED_PASSWORD"
  if [ -f "$PASSWORD_MARKER" ] && [ "$STORED_PASSWORD" != "$CONFIGURED_PASSWORD" ]; then
    NEEDS_CREDENTIAL_MIGRATION=1
  fi
elif [ -n "$STORED_PASSWORD" ]; then
  export NEO4J_PASSWORD="$STORED_PASSWORD"
elif [ -f "$PASSWORD_MARKER" ]; then
  echo "Existing Neo4j data needs NEO4J_PASSWORD or SESSION_SECRET for bounded credential recovery." >&2
  exit 1
else
  export NEO4J_PASSWORD="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
fi

NEO4J_BIN="$(readlink -f "$(command -v neo4j)")"
NEO4J_SHARE="$(cd "$(dirname "$NEO4J_BIN")/../share/neo4j" && pwd)"
APOC_JAR="$(find "$NEO4J_SHARE/labs" -maxdepth 1 -name 'apoc-*-core.jar' -print -quit)"
[ -n "$APOC_JAR" ] || { echo "Required Neo4j APOC core plugin was not found." >&2; exit 1; }
ln -sf "$APOC_JAR" "$NEO4J_server_directories_plugins/$(basename "$APOC_JAR")"

write_neo4j_config() {
  local auth_enabled="${1:-true}"
  cat > "$NEO4J_CONF/neo4j.conf" <<EOF
server.default_listen_address=127.0.0.1
server.directories.data=$NEO4J_server_directories_data
server.directories.logs=$NEO4J_server_directories_logs
server.directories.run=$NEO4J_server_directories_run
server.directories.transaction.logs.root=$NEO4J_server_directories_transaction_logs_root
server.directories.plugins=$NEO4J_server_directories_plugins
dbms.security.procedures.allowlist=apoc.*
dbms.security.procedures.unrestricted=apoc.*
dbms.security.auth_enabled=$auth_enabled
EOF
}

wait_for_neo4j_http() {
  local pid="$1"
  local label="$2"
  local deadline=$((SECONDS + STARTUP_TIMEOUT))
  until curl --max-time 2 -sf http://127.0.0.1:7474/ >/dev/null; do
    kill -0 "$pid" 2>/dev/null || {
      echo "Neo4j exited during $label." >&2
      return 1
    }
    [ "$SECONDS" -lt "$deadline" ] || {
      echo "Neo4j $label timed out after ${STARTUP_TIMEOUT}s." >&2
      return 1
    }
    sleep 1
  done
}

stop_process() {
  local pid="${1:-}"
  local label="${2:-process}"
  [ -n "$pid" ] || return 0
  kill "$pid" 2>/dev/null || true
  local deadline=$((SECONDS + SHUTDOWN_TIMEOUT))
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "$label did not stop after ${SHUTDOWN_TIMEOUT}s; forcing shutdown." >&2
      kill -KILL "$pid" 2>/dev/null || true
      break
    fi
    sleep 1
  done
  wait "$pid" 2>/dev/null || true
}

if [ "$NEEDS_CREDENTIAL_MIGRATION" -eq 1 ]; then
  echo "Recovering the retained Neo4j credential without replacing graph data..."
  write_neo4j_config false
  neo4j console &
  RECOVERY_PID=$!
  cleanup_recovery() {
    stop_process "$RECOVERY_PID" "Neo4j credential-recovery process"
    write_neo4j_config true
  }
  trap cleanup_recovery EXIT INT TERM
  wait_for_neo4j_http "$RECOVERY_PID" "credential recovery"
  if ! timeout --foreground --signal=TERM --kill-after=5 "${STARTUP_TIMEOUT}s" python3 - <<'PY'
import os
from neo4j import GraphDatabase
from neo4j.exceptions import ClientError

with GraphDatabase.driver(os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"), auth=None) as driver:
    driver.verify_connectivity()
    with driver.session(database="system") as session:
        try:
            session.run(
                "ALTER USER neo4j SET PLAINTEXT PASSWORD $password CHANGE NOT REQUIRED",
                password=os.environ["NEO4J_PASSWORD"],
            ).consume()
        except ClientError as error:
            # A stale local hint can request recovery even when the retained
            # store already uses the desired secret. That state is healthy.
            same_password = (
                error.code == "Neo.ClientError.Statement.ArgumentError"
                and "Old password and new password cannot be the same" in str(error)
            )
            if not same_password:
                raise
PY
  then
    echo "Neo4j credential recovery failed or timed out; graph data was not replaced." >&2
    exit 1
  fi
  cleanup_recovery
  trap - EXIT INT TERM
fi

write_neo4j_config true
INITIALIZED_NOW=0
if [ ! -f "$PASSWORD_MARKER" ]; then
  neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD" --require-password-change=false
  INITIALIZED_NOW=1
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
    os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
    auth=(os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]),
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
PY
then
  echo "Neo4j Bolt authentication/APOC verification failed; the credential file was not changed." >&2
  exit 1
fi

umask 077
PASSWORD_TMP="$PASSWORD_FILE.tmp.$$"
printf '%s\n' "$NEO4J_PASSWORD" > "$PASSWORD_TMP"
chmod 600 "$PASSWORD_TMP"
mv "$PASSWORD_TMP" "$PASSWORD_FILE"
[ "$INITIALIZED_NOW" -eq 0 ] || touch "$PASSWORD_MARKER"

setsid bash -c 'cd api && exec python3 -m uvicorn illuminate.main:app --host 0.0.0.0 --port 8000' &
API_PID=$!

echo "Waiting for Illuminate API..."
until curl --max-time 2 -sf http://127.0.0.1:8000/api/health | grep -q '"ok":true'; do
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