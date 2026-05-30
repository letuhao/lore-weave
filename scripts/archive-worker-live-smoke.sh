#!/usr/bin/env bash
# scripts/archive-worker-live-smoke.sh
#
# P1 (DEFERRED 056+057) — archive-worker live-smoke. Stands up the foundation-dev
# stack (Postgres + MinIO) + a per-reality DB, and runs the cold-storage pipeline
# + restore end-to-end against REAL Postgres + REAL MinIO:
#
#   old events partition → Parquet+ZSTD → MinIO → verify → archive_state → DROP
#   → restore: MinIO Get → decode → re-INSERT events_restore_<m>
#
# Idempotent + re-runnable. The Go test applies its own migrations + seeds.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASSWORD="foundation"
SMOKE_DB="archive_smoke"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
MINIO_PORT="${FOUNDATION_MINIO_PORT:-59000}"

log() { printf '[arch-smoke] %s\n' "$*"; }

log "bringing up foundation-dev (postgres + minio) ..."
docker compose -f "$COMPOSE_FILE" up -d postgres-foundation minio-foundation

log "waiting for Postgres ..."
deadline=$(( $(date +%s) + 120 ))
until docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" -d "$PG_USER" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then log "ERROR: Postgres not ready"; exit 1; fi
  sleep 2
done
log "Postgres ready."

exists=$(docker exec -e PGPASSWORD="$PG_PASSWORD" -i "$PG_CONTAINER" \
  psql -tAc "SELECT 1 FROM pg_database WHERE datname='${SMOKE_DB}'" -U "$PG_USER" -d "$PG_USER" 2>/dev/null || true)
if [ "$exists" = "1" ]; then
  log "database '$SMOKE_DB' exists — reusing."
else
  log "creating database '$SMOKE_DB' ..."
  docker exec -e PGPASSWORD="$PG_PASSWORD" -i "$PG_CONTAINER" \
    psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_USER" -c "CREATE DATABASE ${SMOKE_DB};"
fi

export LW_INTEGRATION_DB="postgres://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${SMOKE_DB}?sslmode=disable"
export LW_INTEGRATION_MINIO_ENDPOINT="localhost:${MINIO_PORT}"
export LW_INTEGRATION_MINIO_ACCESS="foundation"
export LW_INTEGRATION_MINIO_SECRET="foundation-secret-dev-only"

log "LW_INTEGRATION_DB=${LW_INTEGRATION_DB}"
log "LW_INTEGRATION_MINIO_ENDPOINT=${LW_INTEGRATION_MINIO_ENDPOINT}"
log "running archive-worker live-smoke ..."

go -C tests/integration test -tags=integration -run TestArchiveWorkerLiveSmoke -count=1 -v ./...
log "PASS — archive-worker archive+restore live-smoke green."
