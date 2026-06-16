#!/usr/bin/env bash
# scripts/perf/l1-capacity.sh
#
# S13 (Inc-2) — L1 capacity / provisioning enforcement, LIVE against real Postgres.
#
# LOCATE-FIRST result (plan R1). The capacity enforcement surface is three distinct
# points; this slice tests each where it actually lives, and records the one gap
# honestly rather than faking a pass:
#
#   1. shard_utilization snapshot-validity CHECKs (DB, meta-pg) — REAL. Reject
#      malformed snapshots (capacity<=0, negative counters, cpu out of range, bad
#      host). Tested here + a drop-constraint bite proves non-vacuity.
#      GAP: there is NO `current_db_count <= capacity_max_dbs` CHECK — the DB does
#      NOT block over-subscription. We demonstrate that (a row with used>cap inserts
#      fine) so the gap is on the record, not hidden.
#   2. CapacityPlanner::pick_shard (Rust, world-service) — REAL app-level
#      over-subscription rejection (refuses when every shard >= full). Run via
#      `l1-capacity.sh planner` (cargo). NOTE the planner is correct but NOT yet
#      wired to read the live shard_utilization table into its snapshot — recorded as
#      D-S13-CAPACITY-ROUTING-GLUE.
#   3. capacity-override → scaling_events via MetaWrite (Go) — REAL I8 audit (one
#      meta_write_audit row in the same TX) + the 24h window enforced by the
#      scaling_events_override_expiry_within_24h CHECK. Driven by the capacity-override
#      harness; the bite proves the I8 audit is produced BY MetaWrite (a raw INSERT
#      bypassing MetaWrite leaves no audit).
#
# Subcommands:
#   check    shard_utilization CHECK enforcement (valid OK + 4 invalid rejected) +
#            the over-subscription gap demonstration.
#   override capacity-override harness: valid 24h override → I8 audit; 48h rejected.
#   planner  cargo test world-service capacity_planner + provisioner (app-level).
#   bite     drop-constraint bite (shard_utilization) + MetaWrite-bypass bite (I8).
#   smoke    check + override + bite (DB-focused; run `planner` separately for Rust).
#
# Verdict: NOTRUN(2) setup; FAIL(1) an enforcement point not enforcing or a vacuous
# bite; PASS(0) clean. Reuses the S12 scale rig's meta-pg. Re-runnable (fresh DB).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
META_C="scale-meta-pg"
META_DB="l1_capacity"
META_HOSTPORT="127.0.0.1:55510"
DSN="postgres://${PG_USER}:${PG_PASS}@${META_HOSTPORT}/${META_DB}?sslmode=disable"

log()    { printf '[l1-capacity] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

bin() { local c; for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
ensure_bin() {
  CO="$(bin services/meta-worker/capovr.exe services/meta-worker/capovr)" && return 0
  log "building capacity-override ..."
  go -C services/meta-worker build -o capovr.exe ./cmd/capacity-override || notrun "build failed"
  CO="services/meta-worker/capovr.exe"
}

require() {
  docker inspect -f '{{.State.Running}}' "$META_C" 2>/dev/null | grep -q true || notrun "$META_C not running (scale-rig.sh up)"
}

psql_db()  { docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" "$@"; }
psql_adm() { docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }

# Fresh l1_capacity with exactly the tables the capacity surface touches:
# reality_registry (001), meta_write_audit (013) + scrub_version (027),
# shard_utilization (024), scaling_events (025).
migrate_meta() {
  psql_adm -c "DROP DATABASE IF EXISTS ${META_DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${META_DB}" >/dev/null
  local m
  for m in 001_reality_registry 013_meta_write_audit 027_meta_write_audit_scrub_version \
           024_shard_utilization 025_scaling_events; do
    docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql" \
      || notrun "meta migration ${m} failed"
  done
  log "l1_capacity migrated (reality_registry + meta_write_audit + shard_utilization + scaling_events)"
}

# A valid shard_utilization row template (override fields via psql -v).
insert_shard() {
  # args: host count cpu cap  (storage/conn/maxbytes fixed-valid)
  local host="$1" count="$2" cpu="$3" cap="$4"
  psql_db -c "INSERT INTO shard_utilization
    (snapshot_id, shard_host, current_db_count, total_storage_bytes, cpu_load_pct,
     connection_count, capacity_max_dbs, capacity_max_bytes)
    VALUES (gen_random_uuid(), '${host}', ${count}, 1000, ${cpu}, 10, ${cap}, 1000000)"
}

# expect_reject CMD... — the insert MUST fail SPECIFICALLY on a CHECK constraint
# (not an infra/connection error, which would false-pass the negative assertion).
expect_reject() {
  local what="$1"; shift
  local out rc
  out="$("$@" 2>&1)" && rc=0 || rc=$?
  if [ "$rc" -eq 0 ]; then
    fail "${what}: insert SUCCEEDED but a CHECK should have rejected it (enforcement missing/vacuous)"
  fi
  case "$out" in
    *"violates check constraint"*) log "  rejected as expected (check constraint): ${what}" ;;
    *) fail "${what}: insert failed but NOT on a check constraint (infra error?) — got: ${out}" ;;
  esac
}

cmd_check() {
  require; migrate_meta
  log "shard_utilization CHECK enforcement:"
  # Valid snapshot lands.
  insert_shard "pg-shard-0.internal" 50 42.5 100 >/dev/null || fail "valid snapshot was rejected"
  log "  valid snapshot accepted"
  # Four malformed snapshots each rejected by their CHECK.
  expect_reject "capacity_max_dbs=0 (capacity_positive)"  insert_shard "pg-shard-1.internal" 5 10 0
  expect_reject "current_db_count=-1 (counters_nonneg)"   insert_shard "pg-shard-1.internal" -1 10 100
  expect_reject "cpu_load_pct=150 (cpu_range)"            insert_shard "pg-shard-1.internal" 5 150 100
  expect_reject "shard_host='bad-host' (host_format)"      insert_shard "bad-host" 5 10 100
  # GAP (on the record): over-subscription is NOT a DB CHECK — used>cap inserts fine.
  if insert_shard "pg-shard-2.internal" 999 10 100 >/dev/null 2>&1; then
    log "  GAP CONFIRMED: used(999) > capacity_max_dbs(100) inserted OK — the DB does NOT"
    log "  enforce over-subscription; that guard is app-level only (CapacityPlanner). See"
    log "  D-S13-CAPACITY-ROUTING-GLUE."
  else
    fail "over-subscription was rejected by the DB — a current_db_count<=capacity CHECK now exists; update this slice + remove the gap row"
  fi
  log "PASS(check): snapshot-validity CHECKs enforce; over-subscription gap documented"
}

cmd_override() { ensure_bin; require; "$CO" -meta-dsn "$DSN" -mode override; }

cmd_planner() {
  require >/dev/null 2>&1 || true  # planner is pure-Rust; no DB needed
  command -v cargo >/dev/null 2>&1 || notrun "cargo not on PATH (app-level planner evidence)"
  log "app-level over-subscription rejection (CapacityPlanner::pick_shard, world-service):"
  # cargo test takes ONE positional filter — run the two modules separately.
  local mod
  for mod in capacity_planner provisioner; do
    cargo test --manifest-path services/world-service/Cargo.toml --lib "${mod}::" \
      || fail "world-service ${mod} tests failed (app-level enforcement broken)"
  done
  log "PASS(planner): pick_shard refuses when every shard >= full; provisioner rejects a full cluster"
}

cmd_bite() {
  ensure_bin; require; migrate_meta
  # Bite A — shard_utilization CHECK is the enforcer (drop it → the rejected row lands).
  log "bite A: drop shard_utilization_capacity_positive → the capacity=0 row should now land"
  psql_db -c "ALTER TABLE shard_utilization DROP CONSTRAINT shard_utilization_capacity_positive" >/dev/null
  if insert_shard "pg-shard-9.internal" 5 10 0 >/dev/null 2>&1; then
    log "  PASS(bite A): capacity_max_dbs=0 inserted once the CHECK was dropped — the CHECK was the enforcer (non-vacuous)"
  else
    fail "bite A vacuous: capacity=0 still rejected after dropping the CHECK — something else blocks it"
  fi
  # Bite B — the I8 audit is produced by MetaWrite (raw INSERT bypassing it → no audit).
  log "bite B: a scaling_events write bypassing MetaWrite should leave 0 meta_write_audit rows"
  "$CO" -meta-dsn "$DSN" -mode bite
}

cmd_smoke() {
  ensure_bin; require
  cmd_check
  log "capacity-override I8 + 24h CHECK ..."
  migrate_meta; cmd_override
  cmd_bite
  log "PASS(smoke): CHECK enforcement + I8 override audit + both bites (planner: run separately)"
}

main() {
  local sub="${1:-smoke}"; shift || true
  case "$sub" in
    check)    cmd_check ;;
    override) migrate_meta; cmd_override ;;
    planner)  cmd_planner ;;
    bite)     cmd_bite ;;
    smoke)    cmd_smoke ;;
    *) echo "usage: $0 {check|override|planner|bite|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
