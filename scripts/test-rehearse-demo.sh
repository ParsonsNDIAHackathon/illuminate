#!/usr/bin/env bash
set -euo pipefail

UPSTREAM="${1:-http://127.0.0.1:${PORT:-8080}}"
PORT="${REHEARSAL_STALL_PROXY_PORT:-18099}"
TMP="$(mktemp -d)"
trap 'kill "${PROXY_PID:-}" 2>/dev/null || true; rm -rf "$TMP"' EXIT

command -v chromium >/dev/null || { echo "Chromium is required." >&2; exit 1; }
curl --fail --silent --show-error --max-time 10 "$UPSTREAM/api/health?refresh=true" >/dev/null

cat >"$TMP/stall_proxy.py" <<'PY'
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = os.environ["UPSTREAM"].rstrip("/")
PORT = int(os.environ["STALL_PORT"])
INTERCEPTED = os.environ["INTERCEPTED"]

class Handler(BaseHTTPRequestHandler):
    def relay(self):
        if self.path.startswith("/api/query/template"):
            open(INTERCEPTED, "w").write(self.path)
            time.sleep(30)
            self.send_error(504, "intentional stalled template")
            return
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {
            key: value for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "content-length", "accept-encoding"}
        }
        request = urllib.request.Request(
            UPSTREAM + self.path, data=body, headers=headers, method=self.command,
        )
        try:
            response = urllib.request.urlopen(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        payload = response.read()
        self.send_response(response.status)
        for key, value in response.headers.items():
            if key.lower() not in {"connection", "content-length", "content-encoding", "transfer-encoding"}:
                self.send_header(key, value)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    do_GET = relay
    do_POST = relay
    def log_message(self, *_):
        pass

ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
PY

UPSTREAM="$UPSTREAM" STALL_PORT="$PORT" INTERCEPTED="$TMP/intercepted" python3 "$TMP/stall_proxy.py" &
PROXY_PID=$!
for _ in $(seq 1 20); do
  curl --fail --silent --max-time 2 "http://127.0.0.1:$PORT/api/health" >/dev/null && break
  sleep 0.25
done
curl --fail --silent --show-error --max-time 2 "http://127.0.0.1:$PORT/api/health" >/dev/null

set +e
if REHEARSAL_BROWSER_TIMEOUT_SECONDS=8 \
   REHEARSAL_VIRTUAL_TIME_BUDGET_MS=4000 \
   REHEARSAL_OUTPUT_DIR="$TMP/output" \
   scripts/rehearse-demo.sh "http://127.0.0.1:$PORT" >"$TMP/result.log" 2>&1; then
  rc=0
else
  rc=$?
fi
set -e
if [ "$rc" -eq 0 ]; then
  echo "Rehearsal gate incorrectly passed while the mission template was stalled." >&2
  exit 1
fi
[ -s "$TMP/intercepted" ] || {
  echo "The negative drill failed before intercepting the mission template." >&2
  cat "$TMP/result.log" >&2
  exit 1
}
grep -Fq "Browser render failed or timed out for /explorer?" "$TMP/result.log" || {
  echo "The negative drill failed at an unexpected stage." >&2
  cat "$TMP/result.log" >&2
  exit 1
}

echo "PASS rehearsal gate rejects a stalled mission template after graph loading"