#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Synchronizing locked Python dependencies..."
uv sync --frozen

echo "Installing locked web dependencies..."
npm ci --prefix web --no-audit --no-fund

echo "Building the web application..."
npm run build --prefix web

echo "Post-merge setup complete."
echo "After reviewing and validating canonical main, publish it explicitly with: make sync-publish"