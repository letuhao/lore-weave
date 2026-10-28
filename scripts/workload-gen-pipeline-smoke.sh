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
# db-safety-gate: file-ok — every database this script DROPs is named by a
# NON-OVERRIDABLE LITERAL (workload_gen_smoke and the per-shard names derived from it), so no
# environment variable can retarget it at a real database. That is a stronger
# guarantee than a runtime marker check on an overridable name, which is what the
# gate would otherwise ask for. Brought into scope 2026-07-29 when the gate's
# shell-file selector was widened from "test" to test|smoke|drill.
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
# ALL per-reality migrations, not a hand-picked subset: the 0017/0018
# retirements dropped the pc/npc/region/session/world_kv projections, so the
# old 7-file list both missed 0016's ruleset_digest (the wg's INSERT
# dependencies) and rebuilt into tables that no longer exist. Applying the
# whole directory IS the real current schema — same pattern schema-conf uses.
for f in contracts/migrations/per_reality/*.up.sql; do
  log "  $(basename "$f")"
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

# Tables the current schema populates. 0017/0018 dropped every projection
# except canon_projection ("canon is the only projection with a producer" —
# world-service rebuild::all_projections, whose test pins len==1), so the old
# 8-table list rebuilt into tables that no longer exist.
TABLES="canon_projection"
export REALITY_DB_URL="$REALITY_DSN" # export (Linux); on Windows Git Bash a .exe may not inherit — run on Linux CI
TOTAL=0
for t in $TABLES; do
  log "rebuilding $t ..."
  rc=0
  out=$("$REBUILDER" --reality-id "$REALITY_ID" --projection "$t") || rc=$?
  failed=$(printf '%s' "$out" | grep -o '"aggregates_failed":[0-9]*' | grep -o '[0-9]*' || true)

  # No stats JSON = a crash / invocation error (NOT a clean rebuild).
  if [ -z "$failed" ]; then
    log "FAIL: $t rebuild produced no stats (rc=$rc): ${out:-<no output>}"
    exit 1
  fi

  n=$(psql_db "$SMOKE_DB" -tA -c "SELECT count(*) FROM ${t}")
  log "  $t rows=$n failed=$failed"
  if [ "$failed" -gt 0 ]; then
    log "FAIL: $t had ${failed} failed aggregate(s) on rebuild"
    exit 1
  fi
  TOTAL=$((TOTAL + n))
done

log "total projection rows = $TOTAL (from $EVENTS events)"
[ "$TOTAL" -gt 0 ] || { log "FAIL: projections empty after rebuild"; exit 1; }
log "PASS: emit → rebuild populated $TOTAL projection rows from $EVENTS events"

# C structural (S2) — no-orphan sweep over the freshly-rebuilt projections:
# every projection row's event_id must resolve to a real event. A latent guard
# (tautological on a rebuilt DB today; fires the day a non-rebuild writer lands)
# — run here so it stays green in the same pipeline the rows came from.
log "C structural: no-orphan projection sweep ..."
if [ -n "$WG" ]; then
  "$WG" -check-projections -dsn "$REALITY_DSN"
else
  ( cd tests/workload-gen && "${GO_BIN:-go}" run ./cmd/workload-gen -check-projections -dsn "$REALITY_DSN" )
fi
log "PASS: emit → rebuild → no-orphan clean (B→derived spine + C structural)"
