#!/usr/bin/env bash
# scripts/perf/l1-lifecycle.sh
#
# S13 (Inc-1) — I9 lifecycle CAS, LIVE under concurrent racers (S9 model-checked
# the logic; this proves it at runtime against real Postgres). Drives the REAL
# contracts/meta.AttemptStateTransition via the lifecycle-race harness.
#
#   race   N racers attempt active→migrating on ONE reality → exactly ONE wins
#          (CAS), N-1 get concurrent_modification, audit has one success row.
#   bite   N racers do a RAW status UPDATE with no CAS guard → MANY win → proves
#          the CAS is what holds correctness.
#   smoke  race + bite.
#
# Verdict: NOTRUN(2) setup; FAIL(1) >1 winner under CAS, or the bite producing ≤1
# winner; PASS(0) clean. Reuses the S12 scale rig's meta-pg. Re-runnable.
#
# R09 safe-closure note (review MED-2/R6): AttemptStateTransition only CASes status
# + audits — it does NOT drain. An automated closure-drain orchestrator was NOT
# found in the foundation (closure is the lifecycle transition + reality_close_audit
# + an SRE runbook). So this slice proves the CAS/transition + audit; the drain is
# recorded as a gap (D-S13-CLOSURE-DRAIN) rather than asserted.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
META_C="scale-meta-pg"
META_DB="l1_meta"
META_HOSTPORT="127.0.0.1:55510"
DSN="postgres://${PG_USER}:${PG_PASS}@${META_HOSTPORT}/${META_DB}?sslmode=disable"
RACERS="${RACERS:-16}"

log()    { printf '[l1-lifecycle] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
ensure_bin() {
  LC="$(bin services/meta-worker/lcrace.exe services/meta-worker/lcrace)" && return 0
  log "building lifecycle-race ..."
  go -C services/meta-worker build -o lcrace.exe ./cmd/lifecycle-race || notrun "build failed"
  LC="services/meta-worker/lcrace.exe"
}

require() {
  docker inspect -f '{{.State.Running}}' "$META_C" 2>/dev/null | grep -q true || notrun "$META_C not running (scale-rig.sh up)"
}

# Fresh l1_meta with exactly the tables AttemptStateTransition→MetaWrite touch:
# reality_registry (001), lifecycle_transition_audit (004), meta_write_audit (013)
# + its scrub_version column (027).
migrate_meta() {
  docker exec -i "$META_C" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation -c "DROP DATABASE IF EXISTS ${META_DB} WITH (FORCE)" >/dev/null
  docker exec -i "$META_C" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
  for m in 001_reality_registry 004_lifecycle_transition_audit 013_meta_write_audit 027_meta_write_audit_scrub_version; do
    docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql" \
      || notrun "meta migration ${m} failed"
  done
  log "l1_meta migrated (reality_registry + lifecycle_transition_audit + meta_write_audit)"
}

cmd_race() { ensure_bin; require; "$LC" -meta-dsn "$DSN" -racers "$RACERS" -mode race; }
cmd_bite() { ensure_bin; require; "$LC" -meta-dsn "$DSN" -racers "$RACERS" -mode bite; }

cmd_smoke() {
  ensure_bin; require; migrate_meta
  log "I9 CAS race: ${RACERS} racers attempt active→migrating on one reality ..."
  cmd_race
  log "bite: raw no-CAS UPDATE race ..."
  cmd_bite
  log "PASS(smoke): exactly-one-wins under CAS; raw no-CAS race yields many winners (the bite)"
}

main() {
  local sub="${1:-smoke}"; shift || true
  case "$sub" in
    race)  migrate_meta; cmd_race ;;
    bite)  migrate_meta; cmd_bite ;;
    smoke) cmd_smoke ;;
    *) echo "usage: $0 {race|bite|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
