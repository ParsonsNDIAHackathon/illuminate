#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Synchronizing locked Python dependencies..."
API_ENV="$ROOT/api/.venv"
UV_PROJECT_ENVIRONMENT="$API_ENV" uv sync --project api --frozen

echo "Applying development fetch-cache schema..."
[ -n "${DATABASE_URL:-}" ] || {
  echo "DATABASE_URL is required to apply the development database schema." >&2
  exit 1
}
(cd api && "$API_ENV/bin/python" - <<'PY'
import asyncio
import os
from pathlib import Path

import asyncpg


async def main() -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await connection.execute(
            Path("migrations/001_fetch_cache.sql").read_text(encoding="utf-8")
        )
    finally:
        await connection.close()


asyncio.run(main())
PY
)

echo "Installing locked web dependencies..."
npm ci --prefix web --no-audit --no-fund

echo "Building the web application..."
npm run build --prefix web

echo "Post-merge setup complete."
echo "After reviewing and validating canonical main, publish it explicitly with: make sync-publish"