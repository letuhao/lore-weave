#!/usr/bin/env bash
# test-infra-up-dps — B2 per-DPS isolated test stack (Postgres + Redis + MinIO)
# Per RAID_WORKFLOW.md §13.2 with deterministic port allocation.
#
# Port formula (deterministic; cycle 999 + dps 9 caps below 20000):
#   Postgres = 10000 + cycle * 10 + dps_id
#   Redis    = 12000 + cycle * 10 + dps_id
#   MinIO    = 14000 + cycle * 10 + dps_id
#   MinIO console = 16000 + cycle * 10 + dps_id
#
# Usage: test-infra-up-dps.sh <cycle> <dps_id>
set -euo pipefail
CYCLE_RAW="${1:-}"
DPS="${2:-}"
if [ -z "$CYCLE_RAW" ] || [ -z "$DPS" ]; then
  echo "usage: test-infra-up-dps.sh <cycle> <dps_id>" >&2
  exit 1
fi

# Normalize cycle: 00X smoke uses cycle=999 sentinel
if [ "$CYCLE_RAW" = "00X" ] || [ "$CYCLE_RAW" = "0" ]; then
  CYCLE=999
else
  CYCLE="$CYCLE_RAW"
fi
PG_PORT=$((10000 + CYCLE * 10 + DPS))
REDIS_PORT=$((12000 + CYCLE * 10 + DPS))
MINIO_PORT=$((14000 + CYCLE * 10 + DPS))
MINIO_CONSOLE=$((16000 + CYCLE * 10 + DPS))

# Range guard
if [ "$PG_PORT" -gt 19999 ] || [ "$REDIS_PORT" -gt 19999 ] || [ "$MINIO_PORT" -gt 19999 ] || [ "$MINIO_CONSOLE" -gt 19999 ]; then
  echo "[test-infra-up] port out of range 10000-20000 — cycle=$CYCLE dps=$DPS" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$REPO_ROOT/scripts/raid/test-infra-template.docker-compose.yml"
PROJECT="raid-c${CYCLE_RAW}-dps${DPS}"

echo "[test-infra-up] project=$PROJECT pg=$PG_PORT redis=$REDIS_PORT minio=$MINIO_PORT/$MINIO_CONSOLE"

export RAID_PG_PORT="$PG_PORT"
export RAID_REDIS_PORT="$REDIS_PORT"
export RAID_MINIO_PORT="$MINIO_PORT"
export RAID_MINIO_CONSOLE="$MINIO_CONSOLE"

docker compose -p "$PROJECT" -f "$TEMPLATE" up -d

echo "[test-infra-up] ready"
echo "POSTGRES_URL=postgres://test:test@localhost:${PG_PORT}/test"
echo "REDIS_URL=redis://localhost:${REDIS_PORT}/0"
echo "MINIO_ENDPOINT=http://localhost:${MINIO_PORT}"
