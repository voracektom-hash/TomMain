#!/usr/bin/env bash
# Run watcher + web app together for local development. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
# Stop both processes however this script ends (Ctrl+C, terminal closed, kill).
trap 'trap - TERM; kill 0' INT TERM EXIT
.venv/bin/python -m hlidac.watcher &
echo "Appka: http://localhost:${WEB_PORT:-8000}  (z telefonu ve stejné Wi-Fi: http://<IP počítače>:${WEB_PORT:-8000})"
.venv/bin/python -m hlidac.web.app &
wait
