#!/usr/bin/env bash
# scripts/perf/w4-t0t1-micro.sh
#
# W4.2 — T0/T1 micro-bench, LIVE (closes D-S12-T0T1-MICRO).
#
# Times the two inner write ticks of the event-sourcing path where they live
# adjacently in one TX (tests/workload-gen/internal/emit.MicroBench, reusing the
# PRODUCTION SQL): T0 = INSERT INTO events (full row + jsonb + content_sha256
# hash), T1 = INSERT INTO events_outbox (2-col pointer). S7 discipline: ship the
# METHOD + a RELATIVE gate (T1.p50 < T0.p50 — a pointer INSERT must be cheaper
# than a full event append), no absolute µs threshold.
#
#   smoke   -micro-bench → gate PASS (T1.p50 < T0.p50). BITE: -micro-bite runs an
#           artificially-expensive REAL outbox INSERT (200k generate_series rows)
#           so T1 > T0 → gate FAILS. Proves the gate measures real per-call
#           latency (a constant-returning harness would not move).
#
# Verdict: NOTRUN(2) setup; FAIL(1) clean gate fails / the bite does NOT fail;
# PASS(0). Reuses the S12 scale rig shard-0 (no pgvector needed).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
SHARD_C="scale-pg-shard-0"
DB="w4_micro"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/${DB}?sslmode=disable"
SEED="${W4_SEED:-5}"; PROFILE="${W4_PROFILE:-multi-user-session}"

log()    { printf '[w4-t0t1] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
require() { docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true || notrun "$SHARD_C not running"; }
psql_adm() { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }
psql_db()  { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" "$@"; }

setup() {
  psql_adm -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${DB}" >/dev/null
  local m
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256; do
    docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" \
      < "contracts/migrations/per_reality/${m}.up.sql" || notrun "migration ${m} failed"
  done
  psql_db -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null || notrun "default partition"
  log "w4_micro ready (events + outbox + content_sha256)"
}

build_bin() {
  go -C tests/workload-gen build -o wg.exe ./cmd/workload-gen || notrun "build wg failed"
  WG="tests/workload-gen/wg.exe"
}

main() {
  require; setup; build_bin

  # Clean: the relative gate must PASS (outbox INSERT cheaper than event append).
  log "micro-bench (clean) seed=${SEED} profile=${PROFILE}"
  out="$("$WG" -seed "$SEED" -profile "$PROFILE" -micro-bench -dsn "$DSN" 2>&1)" \
    || fail "clean micro-bench gate FAILED (T1.p50 >= T0.p50): ${out}"
  printf '%s' "$out" | grep -q 'gate PASS' || fail "clean run did not report a PASS gate: ${out}"
  log "PASS(clean): ${out##*PASS: }"

  # BITE: the expensive outbox INSERT must make T1 > T0 → gate FAILS.
  # (Need a FRESH DB — the clean run already inserted these aggregates; re-emitting
  # the same seed would collide on the unique (aggregate,version) index.)
  setup
  log "micro-bench (bite: expensive outbox) seed=${SEED} profile=${PROFILE}"
  if "$WG" -seed "$SEED" -profile "$PROFILE" -micro-bench -micro-bite -dsn "$DSN" >/dev/null 2>&1; then
    fail "bite VACUOUS: the gate PASSED even with an artificially-expensive outbox INSERT — it is not measuring real per-call latency"
  fi
  log "PASS(bite): the expensive outbox INSERT made T1 >= T0 → the relative gate FIRED (non-vacuous)"
}
main "$@"
