#!/usr/bin/env bash
# scripts/perf/l1-migration.sh
#
# S13 (Inc-3) — L1 migration canary-gated rollout, LIVE. Drives the REAL
# canary.Orchestrator + runner.Runner with a REAL Applier that runs migration SQL
# against REAL per-reality DBs on the scale rig (via docker exec psql). The
# VerificationGate is injected (no production verification suite yet —
# D-MIGRATE-CLI-LIVE-WIRING), so "live" = real runner + real SQL + real per-reality
# isolation, gate injected.
#
# The two abort paths are DISTINCT (canary.go:206 Phase-1 apply, :217 Phase-2 gate)
# and each gets its own bite. Headline invariant: a broken/unverified migration is
# NEVER fanned out to the rest of the fleet.
#
#   apply-abort   broken migration everywhere → canary apply fails → abort
#                 canary_apply_failed → rest NEVER attempted. Bite: ignore the canary
#                 result → fanout runs.
#   verify-abort  migration applies but verification FAILS (gate.Fail) → abort
#                 canary_verification_* → rest NEVER attempted. Bite: gate.Pass when
#                 it should fail → fanout runs.
#   isolation     one poison fanout reality dead-letters (retries exhausted) while
#                 the rest succeed; runner concurrency cap respected (peak <= cap).
#   smoke         all three.
#
# Verdict: NOTRUN(2) setup; FAIL(1) a guard not holding or a vacuous bite; PASS(0)
# clean. Reuses the S12 scale rig's shard-0. Re-runnable (harness resets per-reality DBs).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
SHARD_C="scale-pg-shard-0"
MO="services/migration-orchestrator"

log()    { printf '[l1-migration] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }

bin() { local c; for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
ensure_bin() {
  CD="$(bin ${MO}/cdrill.exe ${MO}/cdrill)" && return 0
  log "building canary-drill ..."
  go -C "$MO" build -o cdrill.exe ./cmd/canary-drill || notrun "build failed"
  CD="${MO}/cdrill.exe"
}

require() {
  docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true || notrun "$SHARD_C not running (scale-rig.sh up)"
}

cmd() { ensure_bin; require; "$CD" -mode "$1"; }

cmd_smoke() {
  ensure_bin; require
  log "Phase-1 abort (apply-fail) ..."
  cmd apply-abort
  log "Phase-2 abort (verification gate) ..."
  cmd verify-abort
  log "per-reality isolation (dead-letter + concurrency cap) ..."
  cmd isolation
  log "PASS(smoke): both abort paths block fanout (each with a non-vacuous bite); isolation dead-letters one while the rest migrate"
}

main() {
  local sub="${1:-smoke}"; shift || true
  case "$sub" in
    apply-abort|verify-abort|isolation) cmd "$sub" ;;
    smoke) cmd_smoke ;;
    *) echo "usage: $0 {apply-abort|verify-abort|isolation|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
