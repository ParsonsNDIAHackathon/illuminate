#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:${PORT:-8080}}"
OUT="${REHEARSAL_OUTPUT_DIR:-rehearsal-results}"
CHROMIUM="${CHROMIUM:-$(command -v chromium || command -v chromium-browser || true)}"
BROWSER_TIMEOUT="${REHEARSAL_BROWSER_TIMEOUT_SECONDS:-45}"
VIRTUAL_TIME_BUDGET="${REHEARSAL_VIRTUAL_TIME_BUDGET_MS:-12000}"
START=$SECONDS

[ -n "$CHROMIUM" ] || { echo "Chromium is required for a clean-browser rehearsal." >&2; exit 1; }
mkdir -p "$OUT"
PROFILE="$(mktemp -d)"
trap 'rm -rf "$PROFILE"' EXIT

# Use the browser origin, not the API's private port: this proves proxy routing too.
health="$(curl --fail --silent --show-error --max-time 10 "$BASE_URL/api/health?refresh=true")"
python3 -c 'import json,sys; h=json.load(sys.stdin); assert h["ok"]; assert h["primary_workflow_ready"], h.get("message")' <<<"$health"

check_page() {
  local path="$1" marker="$2" name="$3" reject="${4:-}"
  local dom="$OUT/$name.html"
  if ! timeout "$BROWSER_TIMEOUT" "$CHROMIUM" \
    --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
    --user-data-dir="$PROFILE" --virtual-time-budget="$VIRTUAL_TIME_BUDGET" \
    --dump-dom "$BASE_URL$path" >"$dom" 2>"$OUT/$name.chromium.log"; then
    echo "Browser render failed or timed out for $path" >&2
    exit 1
  fi
  grep -Fq "$marker" "$dom" || {
    echo "Expected marker '$marker' was not rendered at $path" >&2
    exit 1
  }
  if [ -n "$reject" ] && grep -Fq "$reject" "$dom"; then
    echo "Failure marker '$reject' was rendered at $path" >&2
    exit 1
  fi
}

# One fresh profile represents one clean judge session. The order mirrors the live script.
check_page "/" "Which vendors can this program trust" "01-mission"

# Follow the actual first mission action emitted by the UI, preserving its root and lens.
MISSION_HREF="$(python3 - "$OUT/01-mission.html" <<'PY'
import sys
from html.parser import HTMLParser

class MissionLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.anchor_href = None
        self.anchor_text = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.anchor_href = dict(attrs).get("href")
            self.anchor_text = []
    def handle_data(self, data):
        if self.anchor_href is not None:
            self.anchor_text.append(data)
    def handle_endtag(self, tag):
        if tag == "a" and self.anchor_href is not None:
            if "Find supply exposure" in " ".join(self.anchor_text):
                self.href = self.anchor_href
            self.anchor_href = None

parser = MissionLinkParser()
parser.feed(open(sys.argv[1]).read())
if not parser.href:
    raise SystemExit("The enabled Find supply exposure action was not rendered")
print(parser.href)
PY
)"
if [[ "$MISSION_HREF" != /explorer\?* ||
      "$MISSION_HREF" != *root_id=* ||
      "$MISSION_HREF" != *template=* ]]; then
  echo "Mission action was not a scoped analysis: $MISSION_HREF" >&2
  exit 1
fi
ROOT_ID="$(python3 - "$MISSION_HREF" <<'PY'
import sys
from urllib.parse import parse_qs, urlsplit
print(parse_qs(urlsplit(sys.argv[1]).query)["root_id"][0])
PY
)"
TEMPLATE="$(python3 - "$MISSION_HREF" <<'PY'
import sys
from urllib.parse import parse_qs, urlsplit
print(parse_qs(urlsplit(sys.argv[1]).query)["template"][0])
PY
)"
check_page "$MISSION_HREF" "data-rehearsal-template=\"$TEMPLATE\"" "02-scoped-finding" "Running Supply exposure analysis"
grep -Fq "data-rehearsal-root=\"$ROOT_ID\"" "$OUT/02-scoped-finding.html" || {
  echo "Completed analysis did not retain mission root $ROOT_ID" >&2
  exit 1
}
grep -Eq 'data-rehearsal-elements="[1-9][0-9]*"' "$OUT/02-scoped-finding.html" || {
  echo "Completed analysis contained no usable graph results" >&2
  exit 1
}
check_page "/portfolio?root_id=$ROOT_ID" 'href="/entities/' "03-portfolio" "No vendor identities could be retrieved."
grep -Fq "uc11.vendor-risk.v1" "$OUT/03-portfolio.html" || {
  echo "Portfolio rendered no usable vendor risk assessments" >&2
  exit 1
}

elapsed=$((SECONDS - START))
[ "$elapsed" -le 360 ] || { echo "Rehearsal exceeded six minutes: ${elapsed}s" >&2; exit 1; }
printf 'PASS clean browser profile; mission action → scoped finding → assessed portfolio; %ss / 360s\n' "$elapsed" |
  tee "$OUT/result.txt"
