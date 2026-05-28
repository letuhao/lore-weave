#!/usr/bin/env bash
# test-infra-down-dps — tears down per-DPS test stack
# Per RAID_WORKFLOW.md §13.2 (volumes wiped — no state between DPS runs).
set -euo pipefail
CYCLE_RAW="${1:-}"
DPS="${2:-}"
if [ -z "$CYCLE_RAW" ] || [ -z "$DPS" ]; then
  echo "usage: test-infra-down-dps.sh <cycle> <dps_id>" >&2
  exit 1
fi
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$REPO_ROOT/scripts/raid/test-infra-template.docker-compose.yml"
PROJECT="raid-c${CYCLE_RAW}-dps${DPS}"

echo "[test-infra-down] project=$PROJECT"
# Need port env vars to match the up call (compose interpolates them but
# down ignores port mappings — set to dummy values)
export RAID_PG_PORT=0 RAID_REDIS_PORT=0 RAID_MINIO_PORT=0 RAID_MINIO_CONSOLE=0
docker compose -p "$PROJECT" -f "$TEMPLATE" down -v 2>&1 | sed 's/^/  /' || true
echo "[test-infra-down] done"
