#!/usr/bin/env bash
# scripts/workload-gen-pipeline-smoke.sh
#
# S3 live-smoke — the base→derived pipeline end to end:
#
#   workload-gen -emit  →  events + events_outbox (real outbox write path)
#   world-service rebuilder  →  replays those events into the LIVE projections
#   assert  →  projections are populated, every rebuild clean (failed=0)
#
# This proves the seeded generator's events actually flow through to the
# projection tables (the spine's base→derived path). The rebuilder-vs-
# replay-aggregate differential (the integrity-checker daemon) is the oracle
# layer — tracked as D-WORKLOAD-GEN-INTEGRITY-DIFF.
#
# Live test: requires the foundation-dev docker stack + the prebuilt rebuilder
# binary. Re-runnable (drops + recreates the smoke DB).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
SMOKE_DB="workload_gen_smoke"
REALITY_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${SMOKE_DB}?sslmode=disable"
SEED="${SEED:-1}"
PROFILE="${PROFILE:-single-reality}"

log() { printf '[wg-smoke] %s\n' "$*"; }
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

log "applying per-reality migrations ..."
for m in 0001_initial 0002_events_table 0005_events_outbox_table 0006_projections 0008_pgvector_setup 0009_canon_projection; do
  f="contracts/migrations/per_reality/${m}.up.sql"
  log "  $m"
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$SMOKE_DB" < "$f"
done

# The events table is RANGE-partitioned by recorded_at (monthly); production
# provisions partitions per month. For the smoke, a DEFAULT partition catches
# the generator's logical-clock timestamps without coupling to a month.
log "ensuring events DEFAULT partition ..."
psql_db "$SMOKE_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null

log "emitting workload (seed=$SEED profile=$PROFILE) ..."
# Prefer a prebuilt binary (WG_BIN or tests/workload-gen/wg[.exe]) — some shells
# (Git Bash) don't carry `go` on PATH; fall back to `go run` when available.
WG="${WG_BIN:-}"
[ -n "$WG" ] || { [ -x tests/workload-gen/wg.exe ] && WG="tests/workload-gen/wg.exe"; }
[ -n "$WG" ] || { [ -x tests/workload-gen/wg ] && WG="tests/workload-gen/wg"; }
if [ -n "$WG" ]; then
  "$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$REALITY_DSN"
else
  ( cd tests/workload-gen && "${GO_BIN:-go}" run ./cmd/workload-gen -seed "$SEED" -profile "$PROFILE" -emit -dsn "$REALITY_DSN" )
fi

EVENTS=$(psql_db "$SMOKE_DB" -tA -c "SELECT count(*) FROM events")
OUTBOX=$(psql_db "$SMOKE_DB" -tA -c "SELECT count(*) FROM events_outbox")
log "events=$EVENTS  outbox=$OUTBOX"
[ "$EVENTS" -gt 0 ] || { log "FAIL: no events written"; exit 1; }
[ "$EVENTS" = "$OUTBOX" ] || { log "FAIL: events ($EVENTS) != outbox ($OUTBOX)"; exit 1; }

REALITY_ID=$(psql_db "$SMOKE_DB" -tA -c "SELECT DISTINCT reality_id FROM events LIMIT 1")
log "reality=$REALITY_ID"

REBUILDER="target/debug/rebuilder.exe"
[ -x "$REBUILDER" ] || REBUILDER="target/debug/rebuilder"
[ -x "$REBUILDER" ] || { log "FAIL: rebuilder binary not found (cargo build -p world-service --bin rebuilder)"; exit 2; }

# Tables the single-reality / multi-* profiles populate (skip embedding +
# relationship tables — no events emitted for those yet).
TABLES="region_projection npc_projection npc_session_memory_projection pc_projection pc_inventory_projection session_participants world_kv_projection canon_projection"
# All tables now rebuild clean. npc_session_memory_projection was a MULTI-AGGREGATE
# table that failed under the per-aggregate rebuilder (the npc.said increment
# couldn't find the session-created row); D-REBUILDER-MULTI-AGG fixed it via the
# global-order replay path (rebuild::global), so no table is soft-failed anymore.
SOFT_FAIL_TABLES=""
export REALITY_DB_URL="$REALITY_DSN" # export (Linux); on Windows Git Bash a .exe may not inherit — run on Linux CI
TOTAL=0
for t in $TABLES; do
  log "rebuilding $t ..."
  rc=0
  out=$("$REBUILDER" --reality-id "$REALITY_ID" --projection "$t") || rc=$?
  is_soft=false
  printf '%s' "$SOFT_FAIL_TABLES" | grep -qw "$t" && is_soft=true
  failed=$(printf '%s' "$out" | grep -o '"aggregates_failed":[0-9]*' | grep -o '[0-9]*' || true)

  # No stats JSON = a crash / invocation error (NOT a clean rebuild). Don't let
  # it pass silently just because other tables populate.
  if [ -z "$failed" ]; then
    if [ "$is_soft" = true ]; then
      log "  $t: no stats (rc=$rc) — soft table, tolerated"
      continue
    fi
    log "FAIL: $t rebuild produced no stats (rc=$rc): ${out:-<no output>}"
    exit 1
  fi

  n=$(psql_db "$SMOKE_DB" -tA -c "SELECT count(*) FROM ${t}")
  log "  $t rows=$n failed=$failed"
  if [ "$failed" -gt 0 ] && [ "$is_soft" != true ]; then
    log "FAIL: $t had ${failed} failed aggregate(s) on rebuild"
    exit 1
  fi
  TOTAL=$((TOTAL + n))
done

log "total projection rows = $TOTAL (from $EVENTS events)"
[ "$TOTAL" -gt 0 ] || { log "FAIL: projections empty after rebuild"; exit 1; }
log "PASS: emit → rebuild populated $TOTAL projection rows from $EVENTS events"
