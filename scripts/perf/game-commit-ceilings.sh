#!/usr/bin/env bash
# scripts/perf/game-commit-ceilings.sh
#
# Architecture-ceiling gate for the game tier — drives
# `services/commit-service/src/bin/ceilings.rs` against live Postgres + Redis.
#
# ── What this gates, and why the assertions look the way they do ─────────────
#
# The three ceilings (C1 per-channel commit, C2 contention curve, C3 fan-out)
# are WALL-CLOCK measurements, so their absolute values are properties of the
# machine, not of the code. A gate that asserted "C1 >= 167 commits/sec" would
# be a hardware test that goes red on a slower laptop and stays green through a
# real regression on a faster one.
#
# So the gate is built from RATIOS, which are machine-independent:
#
#   * the bites must FIRE — each by a required factor. This is the non-vacuity
#     proof: it shows the harness measures the thing it names.
#   * C2 must SCALE — aggregate throughput at K=16 must be a multiple of K=1.
#     A change that serialises the write path (a global lock, a shared writer,
#     an accidental single connection) collapses this ratio while every unit
#     test stays green.
#   * durability must be ON — a commit figure taken with fsync or
#     synchronous_commit relaxed is not a durable-commit ceiling at all, and
#     silently publishing one is the failure mode this check exists to stop.
#
# Absolute floors appear only as ABSURDITY checks (orders of magnitude below
# any plausible machine), to catch "the harness ran but did nothing".
#
# MODES
#   (default)  measure C1/C2/C3 clean + assert scaling, durability, absurdity
#   --bite     assert all three bites fire (the non-vacuity gate)
#   --sweep    print the full C2 curve K=1..64 (reporting only, no assertions)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PG_URL="${LOREWEAVE_TEST_PG_URL:-postgresql://foundation:foundation@127.0.0.1:55432/foundation}"
REDIS_URL="${LOREWEAVE_TEST_REDIS_URL:-redis://127.0.0.1:56379}"
export LOREWEAVE_TEST_PG_URL="$PG_URL" LOREWEAVE_TEST_REDIS_URL="$REDIS_URL"

BIN="target/release-commit/ceilings"

log()    { printf '[ceilings] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }

command -v cargo >/dev/null 2>&1 || notrun "cargo not found"

# SHIP RULE (Cargo.toml): commit-service builds under --profile release-commit
# (panic="unwind"). Plain --release sets panic="abort" and kills SC-A8
# containment — measuring the wrong binary shape.
cargo build -q -p commit-service --profile release-commit --bin ceilings 2>/dev/null \
  || notrun "harness failed to build"
[ -x "$BIN" ] || notrun "harness binary missing at $BIN"

# field <output> <KEY> -> the numeric value of KEY=<value>
field() { printf '%s\n' "$1" | tr ' ' '\n' | sed -n "s/^$2=\([0-9.]*\)$/\1/p" | head -1; }

# gte <a> <b> — float compare without bc (awk is in every CI image we use)
gte() { awk -v a="$1" -v b="$2" 'BEGIN{exit !(a>=b)}'; }

run() {
  local out
  # shellcheck disable=SC2068
  out="$("$BIN" $@ 2>&1)" || notrun "harness run failed ($*) — PG=$PG_URL REDIS=$REDIS_URL"
  printf '%s\n' "$out"
}

MODE="${1:-default}"
case "$MODE" in
  --sweep)
    log "C2 curve (reporting only)"
    for k in 1 2 4 8 16 32 64; do
      run c2 "$k" 60 | grep '^c2' || true
    done
    ;;

  --bite)
    log "non-vacuity gate — every bite must move its number"

    # C1: relaxing synchronous_commit must raise throughput. If it does not,
    # the commit path is not fsync-bound and C1 is not a durability ceiling.
    c1_clean="$(run c1 300)"; c1_bite="$(run c1 300 --bite-sync-off)"
    a="$(field "$c1_clean" COMMITS_PER_SEC)"; b="$(field "$c1_bite" COMMITS_PER_SEC)"
    log "c1 clean=$a  bite(sync-off)=$b"
    gte "$b" "$(awk -v a="$a" 'BEGIN{print a*1.4}')" \
      || fail "c1 bite did not fire: sync-off ($b) is not >=1.4x clean ($a) — C1 is not fsync-bound, so it is NOT a durable-commit ceiling"

    # C2: capping the pool at ONE connection must destroy the scaling. If K=16
    # still scales on one connection, the curve is not measuring DB concurrency.
    c2_clean="$(run c2 16 60)"; c2_bite="$(run c2 16 60 --bite-pool1)"
    a="$(field "$c2_clean" AGGREGATE_COMMITS_PER_SEC)"
    b="$(field "$c2_bite" AGGREGATE_COMMITS_PER_SEC)"
    log "c2 k=16 clean=$a  bite(pool1)=$b"
    gte "$(awk -v a="$a" 'BEGIN{print a*0.5}')" "$b" \
      || fail "c2 bite did not fire: pool=1 ($b) kept up with the full pool ($a) — the C2 curve is VACUOUS"

    # C3: a 100x payload must cost throughput, proving Redis work is measured
    # rather than client loop overhead.
    c3_clean="$(run c3 20000)"; c3_bite="$(run c3 20000 --bite-fat)"
    a="$(field "$c3_clean" XADD_PIPELINED_PER_SEC)"
    b="$(field "$c3_bite" XADD_PIPELINED_PER_SEC)"
    log "c3 pipelined clean=$a  bite(fat payload)=$b"
    gte "$(awk -v a="$a" 'BEGIN{print a*0.7}')" "$b" \
      || fail "c3 bite did not fire: a 100x payload ($b) cost nothing vs clean ($a) — c3 measures loop overhead, not Redis"

    log "PASS: all three bites fire — the ceilings are non-vacuous measurements"
    ;;

  default|"")
    log "measuring C1 / C2 / C3 against PG=$PG_URL REDIS=$REDIS_URL"

    c1_out="$(run c1 500)"; printf '%s\n' "$c1_out"
    # Durability must be ON or the headline number is a lie.
    printf '%s\n' "$c1_out" | grep -q 'fsync=on' \
      || fail "fsync is NOT on — this run cannot be quoted as a durable-commit ceiling"
    printf '%s\n' "$c1_out" | grep -q 'synchronous_commit=on' \
      || fail "synchronous_commit is NOT on — this run cannot be quoted as a durable-commit ceiling"
    c1_tps="$(field "$c1_out" COMMITS_PER_SEC)"
    gte "$c1_tps" 10 || fail "c1=$c1_tps commits/sec is below the absurdity floor (10) — did the harness actually commit?"

    c2_1="$(run c2 1 60)";  printf '%s\n' "$c2_1"  | grep '^c2'
    c2_16="$(run c2 16 60)"; printf '%s\n' "$c2_16" | grep '^c2'
    a="$(field "$c2_1" AGGREGATE_COMMITS_PER_SEC)"
    b="$(field "$c2_16" AGGREGATE_COMMITS_PER_SEC)"
    log "c2 scaling K=1 -> K=16: $a -> $b"
    # 4x on 16 channels is a deliberately loose bar (measured ~11x): it passes
    # on a modest box while still catching a write path that got serialised.
    gte "$b" "$(awk -v a="$a" 'BEGIN{print a*4}')" \
      || fail "c2 did not scale: K=16 ($b) is under 4x K=1 ($a) — the commit path may have been serialised"

    c3_out="$(run c3 20000)"; printf '%s\n' "$c3_out"
    c3_pipe="$(field "$c3_out" XADD_PIPELINED_PER_SEC)"
    gte "$c3_pipe" 1000 || fail "c3 pipelined=$c3_pipe/sec is below the absurdity floor (1000)"

    log "PASS: durability on, C2 scales, no absurdity floor breached"
    log "NOTE: these are CEILINGS measured with no validator stages and a toy"
    log "      domain — the real system can only sit BELOW them. See"
    log "      docs/03_planning/LLM_MMO_RPG/21_architecture_ceilings.md"
    ;;

  *)
    fail "unknown mode '$MODE' (use default | --bite | --sweep)"
    ;;
esac
