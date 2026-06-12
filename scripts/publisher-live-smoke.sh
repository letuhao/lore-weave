#!/usr/bin/env bash
# scripts/publisher-live-smoke.sh
#
# P1 (Event-sourcing spine) — DEFERRED 054 D-PUBLISHER-LIVE-WIRING live-smoke.
#
# Brings up the foundation-dev stack, creates a dedicated per-reality DB
# (`publisher_smoke`), and runs the publisher end-to-end smoke against REAL
# Postgres + REAL Redis:
#
#   outbox row -> pgsource (FOR UPDATE SKIP LOCKED) -> redis XADD
#     -> events_outbox.published=TRUE  +  lw.events.<reality>  +  xreality.<type>
#
# The Go test applies the per-reality migrations itself; this script only
# provisions the DB + exports the two DSNs + invokes the test.
#
# Idempotent + re-runnable. Env overrides mirror the compose defaults:
#   FOUNDATION_PG_PORT     host port for Postgres (default 55432)
#   FOUNDATION_REDIS_PORT  host port for Redis    (default 56379)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASSWORD="foundation"
SMOKE_DB="publisher_smoke"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
REDIS_PORT="${FOUNDATION_REDIS_PORT:-56379}"

log() { printf '[pub-smoke] %s\n' "$*"; }

log "bringing up foundation-dev stack ..."
docker compose -f "$COMPOSE_FILE" up -d postgres-foundation redis-foundation

log "waiting for Postgres ($PG_CONTAINER) ..."
deadline=$(( $(date +%s) + 120 ))
until docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" -d "$PG_USER" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "ERROR: Postgres not ready within 120s"; docker compose -f "$COMPOSE_FILE" ps; exit 1
  fi
  sleep 2
done
log "Postgres ready."

# Create the smoke DB if absent (idempotent).
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
export LW_INTEGRATION_REDIS="redis://localhost:${REDIS_PORT}/0"

log "LW_INTEGRATION_DB=${LW_INTEGRATION_DB}"
log "LW_INTEGRATION_REDIS=${LW_INTEGRATION_REDIS}"
log "running publisher live-smoke ..."

go -C tests/integration test -tags=integration -run TestPublisherLiveSmoke -count=1 -v ./...
log "PASS — publisher live-smoke green."
