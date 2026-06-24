#!/usr/bin/env bash
# scripts/perf/w2-history.sh
#
# W2.2 — per-aggregate history-ordering monotonicity, LIVE against real Postgres.
#
# The ledger checker now asserts (CheckAggregateMonotonicity) that, walking the
# events in recorded order, each aggregate's version is strictly previous+1 — no
# reorder. This is the coverage version-COMPLETENESS misses (a sorted-set check
# passes a complete-but-reordered set). Closes D-S6-HISTORY-ORDERING.
#
#   smoke   emit a workload → `wg -check-history` PASS (monotonic). Bite: reorder
#           one aggregate's v2 BEFORE its v1 (set stays complete) → -check-history
#           FAILS while -verify (completeness) still PASSES → the new check adds
#           coverage (non-vacuous).
#
# Verdict: NOTRUN(2) setup; FAIL(1) clean log flagged, or the reorder bite NOT
# caught (or completeness wrongly flags it); PASS(0). Reuses the S12 scale rig.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
SHARD_C="scale-pg-shard-0"
DB="w2_history"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/${DB}?sslmode=disable"
SEED="${W2_SEED:-7}"
PROFILE="${W2_PROFILE:-single-reality}"

log()    { printf '[w2-history] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

require() {
  docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true || notrun "$SHARD_C not running (scale-rig.sh up)"
}
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
  psql_db -c "CREATE TABLE IF NOT EXISTS events_p_2026_01 PARTITION OF events FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')" >/dev/null \
    || notrun "create 2026-01 partition failed"
  log "w2_history ready"
}

build_bin() {
  log "building workload-gen ..."
  go -C tests/workload-gen build -o wg.exe ./cmd/workload-gen || notrun "build failed"
  WG="tests/workload-gen/wg.exe"
}

main() {
  require
  setup
  build_bin

  log "emit seed=${SEED} profile=${PROFILE}"
  "$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$DSN" >/dev/null 2>&1 || notrun "emit failed"

  # Clean: monotonic.
  if ! "$WG" -check-history -dsn "$DSN" >/dev/null 2>&1; then
    fail "clean log flagged as non-monotonic"
  fi
  log "PASS(clean): emitted history is per-aggregate monotonic"

  # Bite: reorder v2 BEFORE v1 on an aggregate that has >=2 versions — keeps the
  # version SET complete but breaks the recorded ORDER.
  local moved
  moved="$(psql_db -tA -c "
    WITH agg AS (
      SELECT reality_id, aggregate_type, aggregate_id
      FROM events GROUP BY 1,2,3 HAVING count(*) >= 2 ORDER BY 1,2,3 LIMIT 1
    ),
    v1 AS (
      SELECT e.recorded_at AS r1 FROM events e JOIN agg USING (reality_id, aggregate_type, aggregate_id)
      WHERE e.aggregate_version = 1
    )
    UPDATE events e SET recorded_at = (SELECT r1 FROM v1) - interval '10 seconds'
    FROM agg
    WHERE e.reality_id=agg.reality_id AND e.aggregate_type=agg.aggregate_type
      AND e.aggregate_id=agg.aggregate_id AND e.aggregate_version=2
    RETURNING 1")"
  [ -n "$moved" ] || notrun "bite found no aggregate with >=2 versions to reorder"
  log "bite: moved an aggregate's v2 to 10s BEFORE its v1 (set still complete)"

  # -check-history MUST now fail (reorder caught).
  if "$WG" -check-history -dsn "$DSN" >/dev/null 2>&1; then
    fail "bite VACUOUS: -check-history still passed after a reorder — the monotonicity check cannot fail"
  fi
  log "  -check-history correctly FAILED on the reorder"

  # -verify (completeness) MUST still pass — proving the reorder is invisible to
  # the set-completeness check, i.e. monotonicity adds real coverage.
  if ! "$WG" -seed "$SEED" -profile "$PROFILE" -verify -dsn "$DSN" >/dev/null 2>&1; then
    fail "bite over-reaches: -verify (completeness) ALSO failed on a recorded_at-only reorder — expected it to pass (so the contrast proves new coverage)"
  fi
  log "PASS(bite): reorder caught by -check-history but PASSES -verify (completeness) — monotonicity is the check that adds coverage (non-vacuous)"
}
main "$@"
