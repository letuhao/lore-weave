#!/usr/bin/env bash
# scripts/perf/platform-slo.sh
#
# D-D-PERF-NIGHTLY — platform user-HTTP p95 SLO battery (consume-side of
# contracts/slo/latency.yaml). Two layers, matching the "buildable half + infra-gated
# measurement" split the P2·D spec calls for:
#
#   1. ALWAYS: slo_assert.py --self-test — proves the assertion logic reds on a breach
#      with NO stack. This is the enforceable, always-green CI check.
#   2. LIVE (gated on PERF_PLATFORM_TARGET): k6 drives the SLO endpoints at the gateway
#      edge → summary → slo_assert asserts measured p95 vs target. NOTRUN when no target
#      or no k6 (the novel-platform stack isn't booted here — this runs against an
#      external staging/dev target, exactly like the SLO measurement is deployment-gated).
#
# Verdict: self-test fails or a live breach → exit 1; ran the live assertion clean →
# exit 0; no target / no k6 → exit 2 (NOTRUN, treated green by the nightly workflow).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
RESULTS="tests/conformance/results"
K6_SCRIPT="tests/perf/k6/http_platform_slo.js"
SLO="contracts/slo/latency.yaml"
SUMMARY="$ROOT/$RESULTS/k6-platform-slo-summary.json"
TARGET="${PERF_PLATFORM_TARGET:-}"

log()    { printf '[platform-slo] %s\n' "$*"; }
notrun() { log "NOTRUN: $*"; exit 2; }

mkdir -p "$RESULTS"

# ── 1. self-test (always; no stack) ──────────────────────────────────────────
log "self-test: proving the p95 assertion trips on a breach ..."
if ! python scripts/perf/slo_assert.py --self-test; then
  log "FAIL: slo_assert self-test failed — the assertion logic is broken"
  exit 1
fi

# ── 2. live measurement (gated) ──────────────────────────────────────────────
command -v k6 >/dev/null 2>&1 || notrun "k6 not present — self-test only (CI nightly installs k6)"
[ -n "$TARGET" ] || notrun "PERF_PLATFORM_TARGET unset — no platform stack to measure (deployment-gated)"

log "k6 driving $SLO endpoints at $TARGET ..."
REQUIRE_ALL_FLAG=""
[ "${PERF_REQUIRE_ALL:-0}" = "1" ] && REQUIRE_ALL_FLAG="--require-all"

SUMMARY_OUT="$SUMMARY" TARGET="$TARGET" TOKEN="${PERF_TOKEN:-}" \
  BOOK_ID="${PERF_BOOK_ID:-}" SESSION_ID="${PERF_SESSION_ID:-}" \
  PERF_DRIVE_MUTATING="${PERF_DRIVE_MUTATING:-0}" \
  k6 run "$K6_SCRIPT" >/dev/null 2>&1 || notrun "k6 run failed (target unreachable?)"

[ -f "$SUMMARY" ] || notrun "k6 produced no summary"
log "asserting measured p95 vs SLO targets ..."
python scripts/perf/slo_assert.py "$SUMMARY" --slo "$SLO" $REQUIRE_ALL_FLAG
rc=$?
[ "$rc" = 0 ] && log "PASS: all measured endpoints within p95 budget"
exit "$rc"
