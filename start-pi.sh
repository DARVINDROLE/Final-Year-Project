#!/usr/bin/env bash
# Start the visitor frontend on the Raspberry Pi, pointed at the laptop's
# backend over the LAN. The Pi never runs the heavy models — it only renders
# the doorbell page and uploads frames/audio to the laptop.
#
# Usage:
#   LAPTOP_IP=192.168.1.42 ./start-pi.sh
#
# Open http://<pi-ip>:8080/doorbell on the Pi's display once Vite is up.
set -euo pipefail

cd "$(dirname "$0")"

: "${LAPTOP_IP:?Set LAPTOP_IP to the laptop's LAN IPv4 address (e.g. LAPTOP_IP=192.168.1.42)}"

export VITE_API_URL="http://${LAPTOP_IP}:8000"

echo "Visitor frontend will talk to backend at $VITE_API_URL"
echo "Open the doorbell at http://<this-pi-ip>:8080/doorbell"

exec npm run dev -- --host 0.0.0.0
