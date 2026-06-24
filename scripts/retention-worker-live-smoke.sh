#!/usr/bin/env bash
# scripts/retention-worker-live-smoke.sh
#
# P1 (DEFERRED 058) — retention-worker live-smoke. Runs both retention paths
# end-to-end against REAL Postgres (foundation-dev):
#   1. outbox prune (pgx Deleter) — published+old events_outbox rows.
#   2. audit retention (os/exec → event-audit-retention-cron.sh → psql).
#
# Requires host `bash` + `psql`. Idempotent + re-runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASSWORD="foundation"
SMOKE_DB="retention_smoke"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"

log() { printf '[ret-smoke] %s\n' "$*"; }

log "bringing up foundation-dev (postgres) ..."
docker compose -f "$COMPOSE_FILE" up -d postgres-foundation

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

log "LW_INTEGRATION_DB=${LW_INTEGRATION_DB}"
log "running retention-worker live-smoke ..."

go -C tests/integration test -tags=integration -run TestRetentionWorkerLiveSmoke -count=1 -v ./...
log "PASS — retention-worker outbox+audit prune live-smoke green."
