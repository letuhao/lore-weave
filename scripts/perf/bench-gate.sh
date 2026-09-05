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
#   --self-test         drive the CSV parser over fixtures — fast, needs neither
#                       go nor benchstat, and runs in the sweep. `--bite` is the
#                       live end-to-end proof; this is the one that runs anywhere.
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

# Resolve benchstat from PATH or GOPATH/bin — LAZILY, and without dying.
#
# TWO DEFECTS, both at the top of the file and both silent. This block ran
# unconditionally at load, so `--self-test` (which needs neither go nor
# benchstat) could not run without them. Worse, `$(go env GOPATH)` under
# `set -euo pipefail` KILLS the script when `go` is absent: the gate exited
# **127 with no output at all**, instead of the `NOTRUN(setup)` + exit 2 it was
# written to produce three lines below. An adjacent decision — a shell option
# set at the top of the file — defeating the guard written for exactly that
# case, which is `GTD-5` a second time.
BENCHSTAT=""
require_benchstat() {
  BENCHSTAT="$(command -v benchstat || true)"
  if [ -z "$BENCHSTAT" ]; then
    local gopath=""
    if command -v go >/dev/null 2>&1; then
      gopath="$(go env GOPATH 2>/dev/null || true)"
    fi
    [ -n "$gopath" ] && [ -x "$gopath/bin/benchstat" ] && BENCHSTAT="$gopath/bin/benchstat"
  fi
  [ -n "$BENCHSTAT" ] || notrun "benchstat not found (go install golang.org/x/perf/cmd/benchstat@latest)"
}

run_bench() { # $1=outfile  [env LW_PERF_BITE inherited]
  ( cd "$PERF_DIR" && go test -run='^$' -bench=. -count="$COUNT" "$BENCH_PKG" ) >"$1" 2>/dev/null
}

# regressions OLD NEW -> prints any significant sec/op regression rows; rc=1 if any.
regressions() {
  "$BENCHSTAT" -format csv "$1" "$2" 2>/dev/null | parse_csv
}

# The CSV parser, split out so a case can drive it without go or benchstat. It
# reads benchstat's `-format csv` on stdin; rc 1 = a significant sec/op
# regression, rc 0 = none, rc 2 = the CSV had no sec/op rows to judge.
#
# THAT LAST CODE IS THE FIX. The header warns that benchstat's output format
# "drifts across versions" — and if it drifts far enough that no `,sec/op,`
# section is recognised, the awk saw zero rows, set nothing, and exited 0, which
# every caller reads as "no regression". A parser that understood nothing and a
# clean benchmark run were the same exit code, in the gate whose entire purpose
# is catching a silent regression.
parse_csv() {
  awk -F, '
    /^,sec\/op,/        { insec=1; next }
    /^,(B\/op|allocs\/op),/ { insec=0; next }
    insec && $1!="geomean" && $1!="" {
      seen=1
      vs=$6
      if (vs ~ /^\+/) { printf "  REGRESSION %s  %s  (%s)\n", $1, vs, $7; bad=1 }
    }
    END {
      if (!seen) {
        print "  NO sec/op ROWS PARSED — benchstat output not understood" > "/dev/stderr"
        exit 2
      }
      exit bad
    }
  '
}

selftest() {
  local failures=0

  # p <name> <want-rc> <csv>
  p() {
    local name="$1" want="$2" csv="$3"
    local got
    set +e
    printf '%s' "$csv" | parse_csv >/dev/null 2>&1
    got=$?
    set -e
    if [ "$got" = "$want" ]; then
      echo "  ok   $name: rc=$got"
    else
      echo "  FAIL $name: rc=$got (want $want)"
      failures=$((failures + 1))
    fi
  }

  local HDR=',old,CI,new,CI,vs base,P'
  echo "bench-gate --self-test"

  p "a significant sec/op REGRESSION is flagged" 1 \
"
,sec/op,
${HDR}
BenchFoo-8,1.00n,±1%,2.00n,±1%,+100.00%,p=0.001 n=6
"
  p "an insignificant change (~) is not" 0 \
"
,sec/op,
${HDR}
BenchFoo-8,1.00n,±1%,1.01n,±1%,~,p=0.400 n=6
"
  p "an IMPROVEMENT is not a regression" 0 \
"
,sec/op,
${HDR}
BenchFoo-8,2.00n,±1%,1.00n,±1%,-50.00%,p=0.001 n=6
"
  p "a regression in the B/op section does NOT gate" 0 \
"
,sec/op,
${HDR}
BenchFoo-8,1.00n,±1%,1.01n,±1%,~,p=0.400 n=6
,B/op,
${HDR}
BenchFoo-8,10,±1%,20,±1%,+100.00%,p=0.001 n=6
"
  p "the geomean row is ignored" 0 \
"
,sec/op,
${HDR}
BenchFoo-8,1.00n,±1%,1.01n,±1%,~,p=0.400 n=6
geomean,1.00n,,1.01n,,+100.00%,
"
  p "...but a real row alongside geomean still gates" 1 \
"
,sec/op,
${HDR}
BenchFoo-8,1.00n,±1%,2.00n,±1%,+100.00%,p=0.001 n=6
geomean,1.00n,,2.00n,,+100.00%,
"
  # THE FLOOR: a drifted/empty benchstat output must not read as "no regression".
  p "EMPTY output is CANNOT-JUDGE, not a pass" 2 ""
  p "output with no sec/op section is CANNOT-JUDGE" 2 \
"
,B/op,
${HDR}
BenchFoo-8,10,±1%,20,±1%,+100.00%,p=0.001 n=6
"
  p "a sec/op header with no rows is CANNOT-JUDGE" 2 \
"
,sec/op,
${HDR}
"

  if [ "$failures" -gt 0 ]; then
    echo "bench-gate --self-test: $failures rule(s) did not behave"
    return 2
  fi
  echo "bench-gate --self-test: every rule bites, and none cries wolf"
  return 0
}

MODE="${1:-local}"
case "$MODE" in
  --self-test|--selftest)
    selftest
    exit $?
    ;;

  --bite)
    require_benchstat
    log "bite: clean vs LW_PERF_BITE=1 (same runner) — gate MUST fire"
    OLD="$(mktemp)"; NEW="$(mktemp)"; trap 'rm -f "$OLD" "$NEW"' EXIT
    ( unset LW_PERF_BITE; run_bench "$OLD" )
    LW_PERF_BITE=1 run_bench "$NEW"
    set +e; out="$(regressions "$OLD" "$NEW")"; rc=$?; set -e
    if [ "$rc" -eq 2 ]; then
      notrun "benchstat produced no parseable sec/op rows — cannot judge the bite"
    elif [ "$rc" -eq 0 ]; then
      # rc=0 means NO regression detected → the gate failed to bite.
      fail "bite did NOT fire — benchstat saw no regression in the bitten benchmark; gate is VACUOUS"
    else
      log "bite fired — benchstat flagged the injected regression:"
      printf '%s\n' "$out"
      log "PASS: gate is non-vacuous"
    fi
    ;;

  --ci-ab)
    require_benchstat
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
    set +e; out="$(regressions "$OLD" "$NEW")"; rc=$?; set -e
    if [ "$rc" -eq 2 ]; then
      notrun "benchstat produced no parseable sec/op rows — refusing to report a pass"
    elif [ "$rc" -eq 0 ]; then
      log "no significant sec/op regression vs $BASE_REF"
      log "PASS"
    else
      log "$out"
      fail "significant sec/op regression vs $BASE_REF (Mann-Whitney p<0.05)"
    fi
    ;;

  local|"")
    selftest || exit 2
    echo
    require_benchstat
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
