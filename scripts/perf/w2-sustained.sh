#!/usr/bin/env bash
# scripts/perf/w2-sustained.sh
#
# W2.1 — sustained-workload generator mode, LIVE against real Postgres.
#
# The workload generator gained a steady-rate loop (-duration + -rate) so a
# soak/fault has a workload that keeps running while the fault is injected
# (prerequisite for W2.2-under-load and W2.3 service RSS soak). Closes
# D-S6-SUSTAINED-WORKLOAD.
#
#   smoke   sustained: emit at ~RATE for DURATION → assert it ACTUALLY sustained
#           (emitted ≈ rate×duration, elapsed ≈ duration). Bite: the one-shot
#           burst path emits a single batch ≪ target → the same sustained
#           assertion REJECTS it → the assertion is non-vacuous.
#
# Verdict: NOTRUN(2) setup; FAIL(1) sustained under/over target, or the one-shot
# bite would PASS the sustained assertion; PASS(0). Reuses the S12 scale rig.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
SHARD_C="scale-pg-shard-0"
DB="w2_sustain"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/${DB}?sslmode=disable"
DURATION="${W2_DURATION:-5s}"
RATE="${W2_RATE:-200}"

log()    { printf '[w2-sustained] %s\n' "$*"; }
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
  # Per-reality skeleton → partitioned events → events_outbox (emit writes both).
  local m
  for m in 0001_initial 0002_events_table 0005_events_outbox_table; do
    docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" \
      < "contracts/migrations/per_reality/${m}.up.sql" || notrun "migration ${m} failed"
  done
  # The generator stamps recorded_at from a FIXED baseEpoch (2026-01); 0002 only
  # creates the migrate-month partition, so add the 2026-01 partition explicitly.
  psql_db -c "CREATE TABLE IF NOT EXISTS events_p_2026_01 PARTITION OF events FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')" >/dev/null \
    || notrun "create 2026-01 partition failed"
  log "w2_sustain ready (events + events_outbox + 2026-01 partition)"
}

build_bin() {
  log "building workload-gen ..."
  go -C tests/workload-gen build -o wg.exe ./cmd/workload-gen || notrun "build failed"
  WG="tests/workload-gen/wg.exe"
}

# extract a numeric JSON field from the sustained summary line.
jnum() { sed -n 's/.*"'"$1"'":\([0-9.]*\).*/\1/p'; }

main() {
  require
  setup
  build_bin

  local dur_s; dur_s="${DURATION%s}"
  local target; target=$(awk "BEGIN{print int($RATE*$dur_s)}")
  local floor;  floor=$(awk "BEGIN{print int($target*0.7)}")
  local ceil;   ceil=$(awk "BEGIN{print int($target*1.5)}")

  log "sustained: -duration ${DURATION} -rate ${RATE} (target ~${target} events)"
  local out; out="$("$WG" -profile single-reality -duration "$DURATION" -rate "$RATE" -emit -dsn "$DSN" 2>/dev/null)"
  echo "$out"
  local emitted elapsed
  emitted="$(printf '%s' "$out" | jnum emitted)"
  elapsed="$(printf '%s' "$out" | jnum elapsed_s)"
  [ -n "$emitted" ] || notrun "no sustained summary emitted"

  # Assertions: sustained for ~duration at ~rate.
  awk "BEGIN{exit !($emitted >= $floor && $emitted <= $ceil)}" \
    || fail "sustained emitted=${emitted} outside [${floor},${ceil}] (target ${target}) — not a real steady-rate run"
  awk "BEGIN{exit !($elapsed >= $dur_s*0.9 && $elapsed <= $dur_s*2.0)}" \
    || fail "sustained elapsed=${elapsed}s not ≈ ${dur_s}s — loop did not run for the duration"
  log "PASS(sustained): ${emitted} events over ${elapsed}s (≈ target ${target})"

  # Bite: the one-shot burst path emits a single batch. The SAME sustained
  # assertion (emitted ≥ floor) must REJECT it — else the assertion is vacuous.
  psql_db -c "TRUNCATE events, events_outbox" >/dev/null 2>&1 || true
  local biteN
  biteN="$("$WG" -profile single-reality -emit -dsn "$DSN" 2>&1 | sed -n 's/.*emitted \([0-9]*\) events.*/\1/p')"
  [ -n "$biteN" ] || notrun "one-shot bite produced no count"
  log "bite: one-shot burst emitted ${biteN} events (sustained floor is ${floor})"
  awk "BEGIN{exit !($biteN < $floor)}" \
    || fail "bite VACUOUS: the one-shot burst (${biteN}) also clears the sustained floor (${floor}) — the assertion can't tell sustained from one-shot"
  log "PASS(bite): one-shot burst (${biteN}) is correctly rejected by the sustained floor (${floor}) — assertion non-vacuous"
}
main "$@"
