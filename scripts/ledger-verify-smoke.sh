#!/usr/bin/env bash
# scripts/ledger-verify-smoke.sh
#
# S2b/C3 live-smoke — the event-store integrity ledger end to end:
#
#   workload-gen -emit    →  events + events_outbox (real outbox write path)
#   workload-gen -verify  →  C3 ledger check (self-consistency + against-ledger)
#   assert  →  0 violations (the seeded log is internally consistent AND matches
#              the deterministic baseline, incl payload hashes)
#
# Unlike the pipeline smoke this needs NO projection rebuild — C3 verifies the
# event LOG, not projections — so it applies only the events + outbox migrations.
# Re-runnable (drops + recreates the smoke DB).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
SMOKE_DB="ledger_verify_smoke"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${SMOKE_DB}?sslmode=disable"
SEED="${SEED:-1}"
PROFILE="${PROFILE:-single-reality}"

log() { printf '[ledger-smoke] %s\n' "$*"; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }

log "bringing up foundation-dev postgres ..."
docker compose -f "$COMPOSE" up -d postgres-foundation >/dev/null

log "waiting for postgres ..."
for _ in $(seq 1 30); do
  if docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1; then break; fi
  sleep 2
done

log "(re)creating smoke DB $SMOKE_DB ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${SMOKE_DB}" >/dev/null
psql_db foundation -c "CREATE DATABASE ${SMOKE_DB}" >/dev/null

log "applying events + outbox migrations ..."
for m in 0001_initial 0002_events_table 0005_events_outbox_table; do
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$SMOKE_DB" < "contracts/migrations/per_reality/${m}.up.sql"
done
log "ensuring events DEFAULT partition ..."
psql_db "$SMOKE_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null

# Prefer a prebuilt binary (some shells lack `go` on PATH; -emit/-verify take the
# DSN as a flag, so no env propagation is needed).
WG="${WG_BIN:-}"
[ -n "$WG" ] || { [ -x tests/workload-gen/wg.exe ] && WG="tests/workload-gen/wg.exe"; }
[ -n "$WG" ] || { [ -x tests/workload-gen/wg ] && WG="tests/workload-gen/wg"; }
run_wg() {
  if [ -n "$WG" ]; then "$WG" "$@"; else ( cd tests/workload-gen && "${GO_BIN:-go}" run ./cmd/workload-gen "$@" ); fi
}

log "emitting workload (seed=$SEED profile=$PROFILE) ..."
run_wg -seed "$SEED" -profile "$PROFILE" -emit -dsn "$DSN"

log "running C3 ledger verify ..."
run_wg -seed "$SEED" -profile "$PROFILE" -verify -dsn "$DSN"

log "PASS: ledger verified clean (seed=$SEED profile=$PROFILE)"
