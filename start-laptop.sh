#!/usr/bin/env bash
# Start the Smart Doorbell backend on the laptop, bound to all interfaces so
# devices on the same WiFi (e.g. a Raspberry Pi running the visitor frontend)
# can reach it.
#
# Usage:
#   ./start-laptop.sh
#
# Stop with Ctrl-C. Auto-reload is on; remove --reload for production.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -d fyp-api ]]; then
  echo "error: virtualenv 'fyp-api' not found. Run setup steps from the README first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source fyp-api/bin/activate

echo "Backend starting on http://0.0.0.0:8000 — accessible from this LAN."
echo "Find your LAN IP with: ipconfig getifaddr en0   (macOS)"
exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
