#!/usr/bin/env bash
# Rebuild the demo graph. Online by default (refreshes fixtures); --offline uses committed fixtures only.
set -euo pipefail
cd "$(dirname "$0")/../api"
exec .venv/bin/python -m illuminate.seed.seed --reset --scenario "$@"
