#!/usr/bin/env bash
# scripts/metaworker-live-smoke.sh
#
# P1 (DEFERRED 069) — meta-worker canon fan-out live-smoke. Stands up two DBs on
# the foundation-dev stack (a meta DB + a per-reality DB) and runs the full
# spine end-to-end against REAL Postgres + REAL Redis:
#
#   canon.entry.created outbox row
#     → publisher drain → XADD xreality.book.canon.updated
#     → meta-worker XREADGROUP → canon_writer → canon_projection
#
# Idempotent + re-runnable. The Go test applies its own migrations.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASSWORD="foundation"
META_DB="metaworker_meta"
REALITY_DB="metaworker_smoke"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
REDIS_PORT="${FOUNDATION_REDIS_PORT:-56379}"

log() { printf '[mw-smoke] %s\n' "$*"; }

log "bringing up foundation-dev (postgres + redis) ..."
docker compose -f "$COMPOSE_FILE" up -d postgres-foundation redis-foundation

log "waiting for Postgres ..."
deadline=$(( $(date +%s) + 120 ))
until docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" -d "$PG_USER" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "ERROR: Postgres not ready within 120s"; exit 1
  fi
  sleep 2
done
log "Postgres ready."

create_db() {
  local db="$1"
  local exists
  exists=$(docker exec -e PGPASSWORD="$PG_PASSWORD" -i "$PG_CONTAINER" \
    psql -tAc "SELECT 1 FROM pg_database WHERE datname='${db}'" -U "$PG_USER" -d "$PG_USER" 2>/dev/null || true)
  if [ "$exists" = "1" ]; then
    log "database '$db' exists — reusing."
  else
    log "creating database '$db' ..."
    docker exec -e PGPASSWORD="$PG_PASSWORD" -i "$PG_CONTAINER" \
      psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_USER" -c "CREATE DATABASE ${db};"
  fi
}
create_db "$META_DB"
create_db "$REALITY_DB"

export LW_INTEGRATION_DB="postgres://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${REALITY_DB}?sslmode=disable"
export LW_INTEGRATION_META_DB="postgres://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${META_DB}?sslmode=disable"
export LW_INTEGRATION_REDIS="redis://localhost:${REDIS_PORT}/0"

log "LW_INTEGRATION_DB=${LW_INTEGRATION_DB}"
log "LW_INTEGRATION_META_DB=${LW_INTEGRATION_META_DB}"
log "LW_INTEGRATION_REDIS=${LW_INTEGRATION_REDIS}"
log "running meta-worker live-smoke ..."

go -C tests/integration test -tags=integration -run TestMetaWorkerLiveSmoke -count=1 -v ./...
log "PASS — meta-worker canon fan-out live-smoke green."
