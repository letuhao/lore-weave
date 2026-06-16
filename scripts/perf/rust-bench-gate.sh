#!/usr/bin/env bash
# scripts/perf/rust-bench-gate.sh
#
# G3 (structural perf-shape gate) — the Rust analogue of the S7/F2 benchstat gate
# (`bench-gate.sh`), for the projection HOT PATH that the Go harness can't reach
# (`apply_one` over the full 11-projection set + the real `build_stmt` SQL
# builder, both Rust). criterion runs the bench; its same-run statistical
# comparison (`--save-baseline` / `--baseline`) is the regression signal.
#
# Like benchstat, this is a SAME-RUNNER A/B (`--ci-ab`) — NEVER an absolute-µs
# threshold (cross-machine variance → flaky/vacuous; the F2 review HIGH-2 lesson).
#
# ── MODES ────────────────────────────────────────────────────────────────────
#   --selftest          parse-only: assert the criterion regression-verdict
#                       parser fires on a known "regressed" sample and stays
#                       silent on an "improved"/"no change" sample (F11 — guards
#                       output-format drift across criterion versions). No build.
#   --bite              clean baseline vs LW_PERF_BITE=1 on the SAME runner;
#                       assert criterion FLAGS the injected regression (else the
#                       gate is vacuous → exit 1). The non-vacuity proof.
#   --ci-ab <base-ref>  bench <base-ref> then HEAD on the SAME runner; FAIL on a
#                       criterion-reported regression. The real CI gate.
#   (default/local)     bench HEAD only, print the report, never gate.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
BENCH="projection_hotpath"
PKG="world-service"
# criterion regresses verbosely; capture stdout and scan it.
CRIT_REGRESS_RE='Performance has regressed'
CRIT_IMPROVE_RE='Performance has improved'

log()    { printf '[rust-bench-gate] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

# verdict_regressed <file> -> rc 0 if criterion flagged a regression in it.
verdict_regressed() { grep -qE "$CRIT_REGRESS_RE" "$1"; }

# run_bench <outfile> [extra cargo-bench args...] ; LW_PERF_BITE inherited.
run_bench() {
  local out="$1"; shift
  cargo bench -p "$PKG" --bench "$BENCH" -- "$@" >"$out" 2>&1
}

selftest() {
  # Embedded known criterion output samples — if the format drifts so these no
  # longer match, the gate would silently stop detecting regressions; this test
  # fails first and forces a parser update (F11).
  local reg imp t
  t="$(mktemp -d)"; trap 'rm -rf "$t"' RETURN
  reg="$t/reg"; imp="$t/imp"
  cat >"$reg" <<'EOF'
apply_one/npc.said      time:   [1.20 us 1.25 us 1.31 us]
                        change: [+18.0% +21.4% +24.9%] (p = 0.00 < 0.05)
                        Performance has regressed.
EOF
  cat >"$imp" <<'EOF'
apply_one/npc.said      time:   [0.90 us 0.92 us 0.95 us]
                        change: [-12.0% -9.4% -6.1%] (p = 0.00 < 0.05)
                        Performance has improved.
EOF
  verdict_regressed "$reg" || fail "selftest: parser MISSED a regressed sample (criterion format drift?)"
  if verdict_regressed "$imp"; then
    fail "selftest: parser FALSE-fired on an improved sample"
  fi
  log "PASS: regression-verdict parser is non-vacuous (fires on regressed, silent on improved)"
}

MODE="${1:-local}"
# --selftest is pure bash (parser-only) and needs no toolchain; every other mode
# builds, so guard cargo there.
case "$MODE" in
  --selftest) ;;
  *) command -v cargo >/dev/null 2>&1 || notrun "cargo not found" ;;
esac

case "$MODE" in
  --selftest)
    selftest
    ;;

  --bite)
    selftest
    log "bite: clean baseline vs LW_PERF_BITE=1 (same runner) — gate MUST fire"
    OUT="$(mktemp)"; trap 'rm -f "$OUT"' EXIT
    log "establishing clean baseline 'gatebase' ..."
    ( unset LW_PERF_BITE; run_bench "$OUT" --save-baseline gatebase ) \
      || notrun "clean bench failed to build/run (see above)"
    log "re-running with LW_PERF_BITE=1 vs 'gatebase' ..."
    LW_PERF_BITE=1 run_bench "$OUT" --baseline gatebase \
      || notrun "bitten bench failed to build/run"
    if verdict_regressed "$OUT"; then
      log "bite fired — criterion flagged the injected regression:"
      grep -E "$CRIT_REGRESS_RE" "$OUT" | head -3
      log "PASS: gate is non-vacuous"
    else
      fail "bite did NOT fire — criterion saw no regression under LW_PERF_BITE=1; gate is VACUOUS (raise LW_PERF_BITE_ITERS)"
    fi
    ;;

  --ci-ab)
    BASE_REF="${2:-}"
    [ -n "$BASE_REF" ] || notrun "--ci-ab needs a <base-ref> (e.g. origin/main or the merge-base)"
    [ -z "$(git status --porcelain)" ] || notrun "working tree dirty — --ci-ab needs a clean tree"
    git rev-parse --verify --quiet "$BASE_REF^{commit}" >/dev/null || notrun "base ref '$BASE_REF' not found"
    selftest
    ORIG="$(git symbolic-ref -q --short HEAD || git rev-parse HEAD)"
    OUT="$(mktemp)"
    restore() { git checkout -f --quiet "$ORIG" 2>/dev/null || true; rm -f "$OUT"; }
    trap restore EXIT
    log "A/B same-runner: base=$BASE_REF head=$ORIG"
    git checkout --quiet "$BASE_REF"
    run_bench "$OUT" --save-baseline ciab_base \
      || notrun "bench failed on base ref (benches may not exist there yet — first-introduction case)"
    git checkout --quiet "$ORIG"
    run_bench "$OUT" --baseline ciab_base || fail "bench failed to run on HEAD"
    if verdict_regressed "$OUT"; then
      log "criterion flagged a regression vs $BASE_REF:"
      grep -E "$CRIT_REGRESS_RE" "$OUT" | head -10
      fail "significant projection-hotpath regression vs $BASE_REF"
    else
      log "no projection-hotpath regression vs $BASE_REF"
      log "PASS"
    fi
    ;;

  local|"")
    OUT="$(mktemp)"; trap 'rm -f "$OUT"' EXIT
    run_bench "$OUT" || notrun "bench failed to build/run"
    log "local bench run (informational — never gates):"
    grep -E 'time:|change:|Performance' "$OUT" || cat "$OUT"
    log "PASS (local-dev never gates; the CI gate is --ci-ab, same-runner)"
    ;;

  *)
    fail "unknown mode '$MODE' (use --selftest | --bite | --ci-ab <ref> | local)"
    ;;
esac
