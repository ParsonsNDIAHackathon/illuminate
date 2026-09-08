"""Minimal consumer using only HTTP and the Illuminate v1 public contract."""
from __future__ import annotations

import json
import sys
from urllib.parse import urlencode
from urllib.request import urlopen


def consume(base_url: str, since: str | None = None) -> str:
    cursor = None
    watermark = since or ""
    while True:
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        elif since:
            params["since"] = since
        url = f"{base_url.rstrip('/')}/api/exports/v1/findings/incremental?{urlencode(params)}"
        with urlopen(url) as response:
            page = json.load(response)
        for finding in page["findings"]:
            print(f"{finding['finding_id']}: {finding['subject_name']} — {finding['predicate']}")
        watermark = page["meta"]["watermark"]
        cursor = page["meta"]["next_cursor"]
        if not cursor:
            return watermark


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    saved_watermark = sys.argv[2] if len(sys.argv) > 2 else None
    print("watermark:", consume(base, saved_watermark))