#!/usr/bin/env bash
# scripts/perf/w5-usl-exponent-band.sh
#
# G2 (structural perf-shape gate) — assert the per-operation TIME does not creep
# super-linear as load N grows (an O(1)→O(n) regression). Gates the fitted
# LOG-LOG SLOPE (power-law exponent p in time≈c·N^p), fitted by OLS over ALL
# sweep points (NOT a 2-point secant), p ≤ 1+ε. NOT a wall-clock threshold —
# the exponent is a machine-independent SHAPE.
#
# ── MODES ────────────────────────────────────────────────────────────────────
#   (default)   run the Go unit proof: the band check recovers a known clean
#               exponent AND a realistic super-linear bite (p≈1.30 vs a 1.20
#               ceiling) EXITS the band. This is the per-PR non-vacuity gate.
#   --live      run the band over a REAL rig sweep. DEFERRED: ε is not yet
#               calibrated from observed slope variance (D-G2-USL-BAND-CALIBRATE),
#               so this NOTRUNs rather than ship a wide vacuous band as green (F7).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

log()    { printf '[w5-usl-band] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

command -v go >/dev/null 2>&1 || notrun "go not found"

MODE="${1:-default}"
case "$MODE" in
  --live)
    notrun "live exponent-band gate is DEFERRED pending ε calibration \
(D-G2-USL-BAND-CALIBRATE): ε must be set from the observed run-to-run slope \
variance on the scale rig before this can gate without false-firing. The unit \
proof (default mode) ships the mechanism + bite green now."
    ;;
  default|"")
    log "running the band unit proof (clean recovers ~0.80 in-band; bite ~1.30 exits the 1.20 ceiling)"
    if go -C tests/perf test ./usl/... -run "TestComplexityExponent"; then
      log "PASS: log-log slope band check is non-vacuous (bites a realistic super-linearity)"
    else
      fail "band unit proof failed"
    fi
    ;;
  *)
    fail "unknown mode '$MODE' (use default | --live)"
    ;;
esac
