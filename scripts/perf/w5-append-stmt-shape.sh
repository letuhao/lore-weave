#!/usr/bin/env bash
# scripts/perf/w5-append-stmt-shape.sh
#
# G1 (structural perf-shape gate) — assert the REAL event-append path issues the
# high-water `SELECT MAX(aggregate_version)` exactly ONCE per append, independent
# of batch size K (the N+1 a higher layer could introduce by moving the read into
# the per-event loop). Live, via `pg_stat_statements` over the Rust harness
# `crates/dp-kernel/examples/g1_append_stmt.rs` which drives the REAL
# `PgEventStore::append_events` (clean) / a real per-event-SELECT append (bite).
#
# This is NOT a wall-clock gate — it counts STATEMENT CALLS (machine-independent).
#
# ── MODES ────────────────────────────────────────────────────────────────────
#   (default)   clean K=1 and K=64; PASS iff the SELECT-MAX call count is
#               constant in K (==1) while INSERT count == K. The structural gate.
#   --bite      run the per-event-SELECT append; assert SELECT-MAX calls SCALE
#               with K (==K) — proving the default assertion CAN fail (non-vacuity).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_URL="${LOREWEAVE_TEST_PG_URL:-postgresql://foundation:foundation@127.0.0.1:55432/foundation}"
export LOREWEAVE_TEST_PG_URL="$PG_URL"

log()    { printf '[w5-stmt-shape] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

command -v cargo >/dev/null 2>&1 || notrun "cargo not found"

# Build the harness once.
cargo build -q -p dp-kernel --example g1_append_stmt 2>/dev/null \
  || notrun "harness failed to build"

# run_harness <mode> <k> -> echoes "<select_calls> <insert_calls>"; NOTRUN if the
# harness can't reach PG / pg_stat_statements.
run_harness() {
  local mode="$1" k="$2" out
  if ! out="$(cargo run -q -p dp-kernel --example g1_append_stmt -- "$mode" "$k" 2>/dev/null)"; then
    notrun "harness run failed (mode=$mode k=$k) — is PG up + pg_stat_statements preloaded? URL=$PG_URL"
  fi
  local sel ins
  sel="$(printf '%s\n' "$out" | sed -n 's/.*SELECT_MAX_CALLS=\([0-9-]*\).*/\1/p')"
  ins="$(printf '%s\n' "$out" | sed -n 's/.*INSERT_CALLS=\([0-9-]*\).*/\1/p')"
  [ -n "$sel" ] && [ -n "$ins" ] || notrun "could not parse harness output: $out"
  echo "$sel $ins"
}

MODE="${1:-default}"
case "$MODE" in
  --bite)
    log "bite: per-event-SELECT append (the injected N+1) — SELECT-MAX must SCALE with K"
    read -r sel ins < <(run_harness bite 64)
    log "bite K=64 -> SELECT_MAX_CALLS=$sel INSERT_CALLS=$ins"
    if [ "$sel" -le 1 ]; then
      fail "bite did NOT fire — SELECT-MAX calls=$sel did not scale with K=64; the gate would be VACUOUS"
    fi
    if [ "$sel" -ne 64 ]; then
      log "WARN: expected SELECT-MAX calls==64, got $sel (still >1, so the invariant still fires)"
    fi
    log "PASS: bite fires — a per-event high-water SELECT makes the count scale (gate is non-vacuous)"
    ;;

  default|"")
    log "clean: REAL append_events — SELECT-MAX must be CONSTANT (==1) across K"
    read -r s1 i1 < <(run_harness clean 1)
    log "clean K=1  -> SELECT_MAX_CALLS=$s1 INSERT_CALLS=$i1"
    read -r s64 i64 < <(run_harness clean 64)
    log "clean K=64 -> SELECT_MAX_CALLS=$s64 INSERT_CALLS=$i64"
    [ "$s1" = "1" ]   || fail "clean K=1 expected 1 high-water SELECT, got $s1"
    [ "$s64" = "1" ]  || fail "clean K=64 high-water SELECT scaled to $s64 — an N+1 regression in append_events"
    [ "$i1" = "1" ]   || fail "clean K=1 expected 1 event INSERT, got $i1"
    [ "$i64" = "64" ] || fail "clean K=64 expected 64 event INSERTs, got $i64"
    log "PASS: high-water SELECT is constant (1) in K; INSERTs scale (1, 64) as designed"
    ;;

  *)
    fail "unknown mode '$MODE' (use default | --bite)"
    ;;
esac
