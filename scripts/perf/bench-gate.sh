#!/usr/bin/env bash
# scripts/perf/bench-gate.sh
#
# S7 deliverable F2 — the statistical micro-benchmark regression gate.
#
# benchstat (Mann-Whitney U @ α=0.05) over the tests/perf/bench micro-benchmarks.
# benchstat prints a numeric "vs base" delta ONLY when the change is significant
# (else "~"), so a significant regression ⟺ the sec/op "vs base" column starts
# with '+'. We parse `benchstat -format csv` (machine-readable; the human table
# format + -col semantics drift across versions — S7 review MED-3), focusing on
# the sec/op metric (time regression is the gate signal; B/op + allocs/op are
# informational).
#
# Validated against: golang.org/x/perf/cmd/benchstat (perf v0.0.0-20260610, the
# version `go install golang.org/x/perf/cmd/benchstat@latest` resolved 2026-06-13).
# CSV layout this parser depends on:
#   ,<old>,CI,<new>,CI,vs base,P    <- header per metric section (sec/op,B/op,…)
#   <BenchName>,<old>,<ci>,<new>,<ci>,<vs base>,<P>
#
# ── MODES ────────────────────────────────────────────────────────────────────
#   --bite              run old=clean / new=LW_PERF_BITE=1 on the SAME process;
#                       assert benchstat FLAGS the injected regression (else the
#                       gate is vacuous → exit 1). The non-vacuity proof.
#   --ci-ab <base-ref>  SAME-RUNNER A/B (S7 review HIGH-2): bench <base-ref> and
#                       the current HEAD on the SAME machine, fail on a
#                       significant sec/op regression. This is the real CI gate.
#   (default)           local-dev: bench HEAD, print drift vs the committed
#                       INFORMATIONAL baseline, NEVER exit 1 (cross-machine — not
#                       a gate). Writes the baseline on first run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PERF_DIR="tests/perf"
BENCH_PKG="./bench/"
COUNT="${BENCH_COUNT:-10}"          # >=6 (benchstat needs >=6 for a CI @0.95)
BASELINE_DIR="scripts/perf/baselines"
BASELINE="$BASELINE_DIR/bench-baseline.txt"

log()    { printf '[bench-gate] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

# Resolve benchstat from PATH or GOPATH/bin.
BENCHSTAT="$(command -v benchstat || true)"
if [ -z "$BENCHSTAT" ]; then
  GB="$(go env GOPATH 2>/dev/null)/bin/benchstat"
  [ -x "$GB" ] && BENCHSTAT="$GB"
fi
[ -n "$BENCHSTAT" ] || notrun "benchstat not found (go install golang.org/x/perf/cmd/benchstat@latest)"

run_bench() { # $1=outfile  [env LW_PERF_BITE inherited]
  ( cd "$PERF_DIR" && go test -run='^$' -bench=. -count="$COUNT" "$BENCH_PKG" ) >"$1" 2>/dev/null
}

# regressions OLD NEW -> prints any significant sec/op regression rows; rc=1 if any.
regressions() {
  "$BENCHSTAT" -format csv "$1" "$2" 2>/dev/null | awk -F, '
    /^,sec\/op,/        { insec=1; next }
    /^,(B\/op|allocs\/op),/ { insec=0; next }
    insec && $1!="geomean" && $1!="" {
      vs=$6
      if (vs ~ /^\+/) { printf "  REGRESSION %s  %s  (%s)\n", $1, vs, $7; bad=1 }
    }
    END { exit bad }
  '
}

MODE="${1:-local}"
case "$MODE" in
  --bite)
    log "bite: clean vs LW_PERF_BITE=1 (same runner) — gate MUST fire"
    OLD="$(mktemp)"; NEW="$(mktemp)"; trap 'rm -f "$OLD" "$NEW"' EXIT
    ( unset LW_PERF_BITE; run_bench "$OLD" )
    LW_PERF_BITE=1 run_bench "$NEW"
    if out="$(regressions "$OLD" "$NEW")"; then
      # rc=0 from awk means NO regression detected → the gate failed to bite.
      fail "bite did NOT fire — benchstat saw no regression in the bitten benchmark; gate is VACUOUS"
    else
      log "bite fired — benchstat flagged the injected regression:"
      printf '%s\n' "$out"
      log "PASS: gate is non-vacuous"
    fi
    ;;

  --ci-ab)
    BASE_REF="${2:-}"
    [ -n "$BASE_REF" ] || notrun "--ci-ab needs a <base-ref> (e.g. origin/main or the merge-base)"
    [ -z "$(git status --porcelain)" ] || notrun "working tree dirty — --ci-ab needs a clean tree (no stash, by design)"
    git rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null || notrun "base ref '$BASE_REF' not found"
    ORIG="$(git symbolic-ref -q --short HEAD || git rev-parse HEAD)"
    OLD="$(mktemp)"; NEW="$(mktemp)"
    # -f so a go.sum touched by `go test` on the base ref can't block the restore
    # (review LOW-3). The discarded change is only a transient module-sum bump.
    restore() { git checkout -f --quiet "$ORIG" 2>/dev/null || true; rm -f "$OLD" "$NEW"; }
    trap restore EXIT
    log "A/B same-runner: base=$BASE_REF head=$ORIG count=$COUNT"
    git checkout --quiet "$BASE_REF"
    run_bench "$OLD" || notrun "bench failed on base ref (the benchmarks may not exist there yet — first-baseline case)"
    git checkout --quiet "$ORIG"
    run_bench "$NEW"
    if out="$(regressions "$OLD" "$NEW")"; then
      log "no significant sec/op regression vs $BASE_REF"
      log "PASS"
    else
      log "$out"
      fail "significant sec/op regression vs $BASE_REF (Mann-Whitney p<0.05)"
    fi
    ;;

  local|"")
    NEW="$(mktemp)"; trap 'rm -f "$NEW"' EXIT
    run_bench "$NEW"
    if [ ! -f "$BASELINE" ]; then
      mkdir -p "$BASELINE_DIR"
      cp "$NEW" "$BASELINE"
      log "wrote first INFORMATIONAL baseline → $BASELINE (NOT a CI gate input)"
      log "PASS (baseline-first; gate disarmed until a baseline exists)"
    else
      log "drift vs committed informational baseline (cross-machine — informational only):"
      "$BENCHSTAT" "$BASELINE" "$NEW" 2>/dev/null || true
      log "PASS (local-dev never gates; the CI gate is --ci-ab, same-runner)"
    fi
    ;;

  *)
    fail "unknown mode '$MODE' (use --bite | --ci-ab <ref> | local)"
    ;;
esac
