#!/usr/bin/env bash
# scripts/perf/w5-usl-exponent-band.sh
#
# G2 (structural perf-shape gate) — the complexity-exponent band, the per-op-TIME
# complement to the USL throughput fit. usl.FitComplexityExponent fits the
# LOG-LOG SLOPE (power-law exponent p in time≈c·N^p) by OLS over ALL sweep points
# (NOT a 2-point secant); the gate asserts p ≤ CEILING — catching an O(1)→O(n)
# regression a higher layer can introduce. Gates the SLOPE, NOT the USL γ.
# NOT a wall-clock threshold — the exponent is a machine-independent SHAPE.
#
# ── CALIBRATION (D-G2-USL-BAND-CALIBRATE, cleared 2026-06-15) ──────────────────
# Per F7 the band must be set from observed rig behaviour, not guessed. A pgbench
# append-latency-vs-concurrency sweep (N∈{1,2,4,8,16,32}, --calibrate) on
# foundation-dev (i9-13900K, pgvector/pg16) over 3 reps fitted exponents
# 0.136 / 0.147 / 0.153 → baseline ≈ 0.145, run-to-run stdev ≈ 0.007 (healthy
# per-op latency is ~flat past the 1→2 connection step — strongly sub-linear).
# The run-to-run noise is negligible; the dominant uncertainty is CROSS-RIG
# baseline drift (a slower CI runner saturates earlier → a higher healthy
# exponent). So the LIVE CEILING is set to **0.50** — ~3.4× the measured baseline
# and ~50× the run-to-run stdev, yet well BELOW linear (1.0): it fires on an
# O(1)→O(n) creep (exponent→~1.0) while absorbing cross-rig baseline drift. If a
# nightly runner ever shows a healthy exponent near 0.50, re-run --calibrate there
# and raise the ceiling (it is a nightly, non-PR-blocking gate).
CEILING="${G2_EXPONENT_CEILING:-0.50}"
#
# ── MODES ────────────────────────────────────────────────────────────────────
#   (default)    Go unit proof — band check recovers a clean exponent in-band and
#                a realistic super-linear bite out-of-band. Per-PR non-vacuity.
#   --calibrate  run R pgbench latency-vs-concurrency sweeps, print each fitted
#                exponent + mean/stdev (how the CEILING above was derived).
#   --live       run ONE sweep, fit the exponent, assert p ≤ CEILING. LW_G2_BITE=1
#                feeds a synthetic super-linear series through the SAME fit+ceiling
#                pipeline and asserts it FAILS (live-pipeline non-vacuity).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG="${FOUNDATION_PG_CONTAINER:-foundation-dev-postgres}"
REPS="${G2_CALIBRATE_REPS:-3}"
RUNGS="${G2_RUNGS:-1 2 4 8 16 32}"
SECS="${G2_SECS:-3}"

log()    { printf '[w5-usl-band] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

command -v go >/dev/null 2>&1 || notrun "go not found"

# fit_exponent reads "N,time" CSV on stdin, prints the fitted exponent (float).
USLFIT=""
build_uslfit() {
  USLFIT="$(mktemp)"
  go -C tests/perf build -o "$USLFIT" ./usl/cmd/usl-fit 2>/dev/null || notrun "usl-fit failed to build"
}
fit_exponent() { # stdin: header+CSV → echoes the exponent
  "$USLFIT" -exponent | sed -n 's/.*"exponent": \([0-9.eE+-]*\).*/\1/p'
}

# --- live sweep plumbing (pgbench against the foundation PG container) ---------
SCHEMA="g2band"
PGBENCH_SQL='\set rid random(1, 100000000)
INSERT INTO '"$SCHEMA"'.events VALUES (gen_random_uuid(), '"'"'00000000-0000-0000-0000-000000000001'"'"', '"'"'npc'"'"', '"'"'agg-'"'"' || :rid, :rid, '"'"'npc.said'"'"', 1, '"'"'{"text":"hi"}'"'"', '"'"'{"s":"1"}'"'"', now(), now(), '"'"'deadbeef'"'"');'

pg_exec() { docker exec -i "$PG" psql -q -v ON_ERROR_STOP=1 -U foundation -d foundation "$@"; }

ensure_rig() {
  command -v docker >/dev/null 2>&1 || notrun "docker not available for the live sweep"
  docker exec "$PG" pg_isready -U foundation >/dev/null 2>&1 || notrun "foundation PG ($PG) not reachable"
  docker exec "$PG" which pgbench >/dev/null 2>&1 || notrun "pgbench not in the PG image"
  pg_exec <<SQL 2>/dev/null || notrun "could not (re)create the throwaway schema"
DROP SCHEMA IF EXISTS $SCHEMA CASCADE;
CREATE SCHEMA $SCHEMA;
CREATE TABLE $SCHEMA.events (
  event_id uuid PRIMARY KEY, reality_id uuid NOT NULL, aggregate_type text NOT NULL,
  aggregate_id text NOT NULL, aggregate_version bigint NOT NULL, event_type text NOT NULL,
  event_version int NOT NULL, payload jsonb NOT NULL, metadata jsonb,
  occurred_at timestamptz NOT NULL, recorded_at timestamptz NOT NULL, content_sha256 text NOT NULL);
SQL
}

run_sweep() { # echoes "N,latency_ms" lines across the rungs
  for N in $RUNGS; do
    local J=$(( N < 8 ? N : 8 ))
    local lat
    lat=$(printf '%s\n' "$PGBENCH_SQL" | docker exec -i "$PG" pgbench -n -c "$N" -j "$J" -T "$SECS" -f - -U foundation -d foundation 2>/dev/null \
      | sed -n 's/^latency average = \([0-9.]*\) ms/\1/p')
    [ -n "$lat" ] || return 1
    echo "$N,$lat"
  done
}

cleanup_rig() { pg_exec -c "DROP SCHEMA IF EXISTS $SCHEMA CASCADE" >/dev/null 2>&1 || true; }

MODE="${1:-default}"
case "$MODE" in
  default|"")
    log "running the band unit proof (clean recovers ~0.80 in-band; bite ~1.30 exits the 1.20 ceiling)"
    if go -C tests/perf test ./usl/... -run "TestComplexityExponent"; then
      log "PASS: log-log slope band check is non-vacuous (bites a realistic super-linearity)"
    else
      fail "band unit proof failed"
    fi
    ;;

  --calibrate)
    build_uslfit; ensure_rig; trap cleanup_rig EXIT
    log "calibration: $REPS reps × rungs [$RUNGS], ${SECS}s each — fitting the exponent per rep"
    sum=0; sumsq=0; n=0
    for r in $(seq 1 "$REPS"); do
      csv="$(run_sweep)" || notrun "pgbench sweep failed (rep $r)"
      exp="$(printf 'n,time\n%s\n' "$csv" | fit_exponent)"
      [ -n "$exp" ] || fail "could not fit exponent (rep $r): $csv"
      log "rep $r: exponent=$exp"
      sum=$(awk -v a="$sum" -v b="$exp" 'BEGIN{printf "%.9f", a+b}')
      sumsq=$(awk -v a="$sumsq" -v b="$exp" 'BEGIN{printf "%.9f", a+b*b}')
      n=$((n+1))
    done
    awk -v s="$sum" -v sq="$sumsq" -v n="$n" -v ceil="$CEILING" 'BEGIN{
      m=s/n; var=(sq/n)-(m*m); if(var<0)var=0; sd=sqrt(var);
      printf "[w5-usl-band] baseline exponent: mean=%.4f stdev=%.4f over %d reps; committed CEILING=%.2f (headroom %.2f above mean)\n", m, sd, n, ceil, ceil-m;
    }'
    log "PASS (calibration report; CEILING is the committed gate value above)"
    ;;

  --live)
    build_uslfit
    if [ "${LW_G2_BITE:-0}" = "1" ]; then
      log "live BITE: a synthetic super-linear (p≈1.5) series through the REAL fit+ceiling pipeline must FAIL"
      bite="$(printf 'n,time\n1,1\n2,2.83\n4,8\n8,22.6\n16,64\n32,181\n' | fit_exponent)"
      log "bite exponent=$bite (ceiling=$CEILING)"
      over=$(awk -v e="$bite" -v c="$CEILING" 'BEGIN{print (e>c)?"yes":"no"}')
      [ "$over" = "yes" ] || fail "live-pipeline bite did NOT exceed the ceiling — gate VACUOUS"
      log "PASS: live-pipeline bite exceeds the ceiling (gate is non-vacuous)"
      exit 0
    fi
    ensure_rig; trap cleanup_rig EXIT
    log "live: one latency-vs-concurrency sweep [$RUNGS], ${SECS}s each — assert exponent ≤ $CEILING"
    csv="$(run_sweep)" || notrun "pgbench sweep failed"
    exp="$(printf 'n,time\n%s\n' "$csv" | fit_exponent)"
    [ -n "$exp" ] || fail "could not fit exponent: $csv"
    log "fitted exponent=$exp (points: $(echo "$csv" | tr '\n' ' '))"
    over=$(awk -v e="$exp" -v c="$CEILING" 'BEGIN{print (e>c)?"yes":"no"}')
    [ "$over" = "no" ] || fail "per-op latency exponent $exp exceeds ceiling $CEILING — a super-linear (O(1)→O(n)) regression"
    log "PASS: per-op latency exponent $exp ≤ $CEILING (sub-linear; no structural regression)"
    ;;

  *)
    fail "unknown mode '$MODE' (use default | --calibrate | --live [LW_G2_BITE=1])"
    ;;
esac
