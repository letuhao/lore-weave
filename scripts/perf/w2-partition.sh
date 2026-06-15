#!/usr/bin/env bash
# scripts/perf/w2-partition.sh
#
# W2.4b — partition-boundary rollover, LIVE against real Postgres.
#
# The per-reality `events` table is monthly RANGE-partitioned on recorded_at
# (0002), with NO default partition. This drill proves events written ACROSS a
# month boundary are all stored + replayable when the next-month partition
# exists, and that a MISSING partition fails LOUDLY (never silent loss). Closes
# D-S6-PARTITION-ROLLOVER.
#
#   smoke   create month M + M+1 partitions; write an aggregate's v1 in M and v2
#           in M+1 (spanning the boundary); assert both stored (1 per partition)
#           and the parent table replays them in monotonic order (-check-history).
#           Bite: INSERT a v3 in M+2 with NO M+2 partition → Postgres REJECTS it
#           ("no partition ... found for row") → the next-month partition is
#           load-bearing; absence is a loud failure, not silent loss.
#
# Verdict: NOTRUN(2) setup; FAIL(1) loss across the boundary, or the missing-
# partition INSERT did NOT fail; PASS(0). Reuses the S12 scale rig (shard-0).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
SHARD_C="scale-pg-shard-0"
DB="w2_partition"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/${DB}?sslmode=disable"
RID="00000000-0000-0000-0000-0000000000b2"

log()    { printf '[w2-partition] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

require() {
  docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true || notrun "$SHARD_C not running (scale-rig.sh up)"
}
psql_adm() { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }
psql_db()  { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" "$@"; }
psql_raw() { docker exec -i "$SHARD_C" psql -tA -U "$PG_USER" -d "$DB" "$@"; } # no ON_ERROR_STOP → capture errors

setup() {
  psql_adm -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${DB}" >/dev/null
  local m
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256; do
    docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" \
      < "contracts/migrations/per_reality/${m}.up.sql" || notrun "migration ${m} failed"
  done
  # Month M = 2026-03, M+1 = 2026-04. Deliberately NO M+2 (2026-05) partition.
  psql_db -c "CREATE TABLE events_p_2026_03 PARTITION OF events FOR VALUES FROM ('2026-03-01') TO ('2026-04-01')" >/dev/null || notrun "M partition failed"
  psql_db -c "CREATE TABLE events_p_2026_04 PARTITION OF events FOR VALUES FROM ('2026-04-01') TO ('2026-05-01')" >/dev/null || notrun "M+1 partition failed"
  log "w2_partition ready (2026-03 + 2026-04 partitions; NO 2026-05)"
}

ins() { # version recorded_at
  psql_db -c "INSERT INTO events
    (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version, event_type, event_version, payload, occurred_at, recorded_at)
    VALUES (gen_random_uuid(), '${RID}', 'npc', 'n1', $1, 'npc.said', 1, '{}'::jsonb, '$2', '$2')"
}

build_bin() {
  go -C tests/workload-gen build -o wg.exe ./cmd/workload-gen || notrun "build wg failed"
  WG="tests/workload-gen/wg.exe"
}

main() {
  require
  setup
  build_bin

  # v1 in M, v2 in M+1 — spans the boundary.
  ins 1 "2026-03-31 23:00:00+00" >/dev/null || notrun "insert v1 (M) failed"
  ins 2 "2026-04-01 01:00:00+00" >/dev/null || notrun "insert v2 (M+1) failed"

  local total m_cnt m1_cnt
  total="$(psql_raw -c "SELECT count(*) FROM events")"
  m_cnt="$(psql_raw -c "SELECT count(*) FROM events_p_2026_03")"
  m1_cnt="$(psql_raw -c "SELECT count(*) FROM events_p_2026_04")"
  log "stored: total=${total} (M=${m_cnt}, M+1=${m1_cnt})"
  [ "$total" = "2" ] && [ "$m_cnt" = "1" ] && [ "$m1_cnt" = "1" ] \
    || fail "events not split across the boundary as expected (total=${total} M=${m_cnt} M+1=${m1_cnt})"

  # Replay across the boundary: the parent table reads both partitions in order.
  "$WG" -check-history -dsn "$DSN" >/dev/null 2>&1 \
    || fail "cross-boundary replay not monotonic — loss/reorder across the partition boundary"
  log "PASS(rollover): v1(M) + v2(M+1) both stored, parent table replays monotonically across the boundary"

  # Bite: a v3 in M+2 (2026-05) with NO 2026-05 partition MUST be rejected.
  local out
  out="$(ins 3 "2026-05-01 00:00:00+00" 2>&1)" && {
    fail "bite VACUOUS: a 2026-05 INSERT SUCCEEDED with no 2026-05 partition — a default/overflow partition exists, so missing-partition is NOT a loud failure"
  }
  # Match ONLY the specific missing-partition error (no broad "partition" catch-all
  # that an unrelated partition-mentioning error could satisfy). PG14+ phrasing:
  #   no partition of relation "events" found for row
  case "$out" in
    *"no partition of relation"*"found for row"*)
      log "PASS(bite): the M+2 INSERT was REJECTED (no 2026-05 partition) — rollover is load-bearing, no silent loss" ;;
    *)
      fail "bite: M+2 INSERT failed but NOT on a missing-partition error — got: ${out}" ;;
  esac
}
main "$@"
