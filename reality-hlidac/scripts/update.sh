#!/usr/bin/env bash
# Reality Hlídač – update to the newest version. Data, accounts and rules stay.
#   sudo ./scripts/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
docker compose up -d --build
docker image prune -f >/dev/null
docker compose ps --format '{{.Service}}: {{.Status}}'
echo "Hotovo."
