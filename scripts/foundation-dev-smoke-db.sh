#!/usr/bin/env bash
# scripts/foundation-dev-smoke-db.sh
#
# Phase 0 (Enablement) — DB live-smoke bootstrap for the foundation-dev stack.
#
# Brings up the foundation-dev compose stack, waits for Postgres to be healthy,
# creates the `dp_kernel_test` database if absent, applies the per-reality
# migrations the PgEventStore integration suite depends on (0002 events +
# 0004 aggregate_snapshots), and prints the DSN line:
#
#   LOREWEAVE_TEST_PG_URL=postgres://foundation:foundation@localhost:<port>/dp_kernel_test
#
# The PgEventStore live-smoke is then:
#   LOREWEAVE_TEST_PG_URL=$(...) cargo test -p dp-kernel --test integration_event_store
#
# Idempotent + re-runnable: CREATE DATABASE is guarded, the migrations
# themselves are CREATE ... IF NOT EXISTS where it matters, and re-applying is
# a no-op against an already-migrated DB.
#
# Env overrides (mirror the compose defaults):
#   FOUNDATION_PG_PORT   host port for Postgres (default 55432)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASSWORD="foundation"
TEST_DB="dp_kernel_test"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"

MIGRATIONS=(
  "contracts/migrations/per_reality/0002_events_table.up.sql"
  "contracts/migrations/per_reality/0004_aggregate_snapshots_table.up.sql"
)

log() { printf '[smoke-db] %s\n' "$*"; }

# 1) Bring up the stack (idempotent — `up -d` is a no-op for running services).
log "bringing up foundation-dev stack ($COMPOSE_FILE) ..."
docker compose -f "$COMPOSE_FILE" up -d

# 2) Wait for Postgres healthy (pg_isready inside the container).
log "waiting for Postgres ($PG_CONTAINER) to accept connections ..."
deadline=$(( $(date +%s) + 120 ))
until docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" -d "$PG_USER" >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    log "ERROR: Postgres did not become ready within 120s"
    docker compose -f "$COMPOSE_FILE" ps
    exit 1
  fi
  sleep 2
done
log "Postgres is ready."

# psql helper bound to the container (no host psql client required).
psql_db() {
  local db="$1"; shift
  docker exec -e PGPASSWORD="$PG_PASSWORD" -i "$PG_CONTAINER" \
    psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$db" "$@"
}

# 3) Create the test DB if absent (idempotent — guarded by a catalog probe).
exists=$(docker exec -e PGPASSWORD="$PG_PASSWORD" -i "$PG_CONTAINER" \
  psql -tAc "SELECT 1 FROM pg_database WHERE datname='${TEST_DB}'" -U "$PG_USER" -d "$PG_USER" 2>/dev/null || true)
if [ "$exists" = "1" ]; then
  log "database '$TEST_DB' already exists — skipping create."
else
  log "creating database '$TEST_DB' ..."
  docker exec -e PGPASSWORD="$PG_PASSWORD" -i "$PG_CONTAINER" \
    psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_USER" -c "CREATE DATABASE ${TEST_DB};"
fi

# 4) Apply per-reality migrations (re-runnable — IF NOT EXISTS semantics).
for m in "${MIGRATIONS[@]}"; do
  if [ ! -f "$m" ]; then
    log "ERROR: migration not found: $m"
    exit 1
  fi
  log "applying migration: $m"
  psql_db "$TEST_DB" < "$m"
done

# 5) Confirm the expected tables exist.
log "verifying tables ..."
for tbl in events aggregate_snapshots; do
  present=$(psql_db "$TEST_DB" -tAc \
    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='${tbl}')" \
    | tr -d '[:space:]')
  if [ "$present" = "t" ]; then
    log "  table '$tbl' ... OK"
  else
    log "ERROR: expected table '$tbl' is missing after migration."
    exit 1
  fi
done

# 6) Print the DSN line for downstream use.
DSN="postgres://${PG_USER}:${PG_PASSWORD}@localhost:${PG_PORT}/${TEST_DB}"
log "tables confirmed. Run the live-smoke with:"
echo "LOREWEAVE_TEST_PG_URL=${DSN}"
