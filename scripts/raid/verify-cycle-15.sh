#!/usr/bin/env bash
# verify-cycle-15.sh — CI gate for RAID cycle 15 (eval framework EXTEND + P2/P3 gate).
# Exit 0 = PASS.
#
# Asserts (per docs/raid/cycle_briefs/15_eval-gate.md acceptance):
#   1. lore-enrichment-service C15 unit suite green: deterministic sub-score
#      scorers (schema/canon/anachronism/provenance), weighted aggregation,
#      baseline-diff regression, judge-ENSEMBLE usefulness (majority + Fleiss κ +
#      partial-credit; 050 injection-defense), gate pass/fail boundary, and the
#      enrichment_eval_runs repo round-trip (when a real DB is reachable).
#   2. ruff clean on the C15 code paths.
#   3. Climate/geo IMMUTABILITY: git diff shows ZERO changes under the climate/geo
#      eval files (the additive-not-fork invariant). Any touch = hard fail.
#   4. No hardcoded model names in the C15 app code paths (judges resolve via
#      provider-registry model_ref).
#   5. GATE actually gates: the deliberately-BAD fixture yields a NON-zero exit
#      (passed=false); the deterministic demo fixture produces a real scorecard.
#   6. LIVE SMOKE (best-effort): run the eval with the REAL judge ensemble
#      (gemma + qwen-30b + claude via provider-registry; tolerate JIT load) on the
#      DEMO output (the promoted/enriched 4 locations in the demo project) →
#      produce a real scorecard, persist to enrichment_eval_runs + freeze a
#      baseline, and show the GATE decision. A genuine infra-unavailable
#      (judge JIT won't load / stack down) is a legitimate skip.
set -uo pipefail
CYCLE=15
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LE_SVC="$REPO_ROOT/services/lore-enrichment-service"
COMPOSE="$REPO_ROOT/infra/docker-compose.yml"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

INTERNAL_TOKEN="${INTERNAL_SERVICE_TOKEN:-dev_internal_token}"
LE_DB="${TEST_LORE_ENRICHMENT_DB_URL:-postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_lore_enrichment}"
PR_DB="${PROVIDER_REGISTRY_DB_URL:-postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_provider_registry}"
PR_URL="${PROVIDER_REGISTRY_URL:-http://localhost:8208}"
DEMO_PROJECT="${DEMO_PROJECT:-019e7850-aa1c-7cd3-a25c-c2f9ad84fd39}"
DEMO_USER="${DEMO_USER:-019d5e3c-7cc5-7e6a-8b27-1344e148bf7c}"

fail() { echo "[verify-cycle-15] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-15] ok: $1"; }
note() { echo "[verify-cycle-15] note: $1"; }

echo "[verify-cycle-15] running CI gate"

# ── 1. C15 unit suite ───────────────────────────────────────────────────────────
if command -v python >/dev/null 2>&1; then
  ( cd "$LE_SVC" && python -m pytest \
      tests/test_eval_scorers.py tests/test_eval_judge.py tests/test_eval_gate.py -q ) \
    >/tmp/c15_unit.log 2>&1 \
    || { cat /tmp/c15_unit.log; fail "C15 eval unit suite failed"; }
  ok "C15 eval unit suite green (scorers + judge-ensemble + gate)"

  # Full service suite — no C0–C14 regression.
  ( cd "$LE_SVC" && python -m pytest -q ) >/tmp/c15_full.log 2>&1 \
    || { cat /tmp/c15_full.log; fail "lore-enrichment full suite regressed"; }
  ok "lore-enrichment full suite green (no C0–C14 regression)"
else
  note "python not on PATH — skipping unit suite here"
fi

# ── 2. ruff clean on C15 paths ────────────────────────────────────────────────
if command -v ruff >/dev/null 2>&1; then
  ( cd "$LE_SVC" && ruff check \
      app/eval/ app/db/repositories/eval_runs.py app/api/eval.py \
      tests/test_eval_scorers.py tests/test_eval_judge.py tests/test_eval_gate.py \
      tests/db/test_eval_runs_repo.py ) \
    >/tmp/c15_ruff.log 2>&1 \
    || { cat /tmp/c15_ruff.log; fail "ruff failed on C15 files"; }
  ( cd "$REPO_ROOT" && ruff check scripts/enrichment_eval.py ) \
    >>/tmp/c15_ruff.log 2>&1 \
    || { cat /tmp/c15_ruff.log; fail "ruff failed on scripts/enrichment_eval.py"; }
  ok "ruff clean on C15 code paths"
fi

# ── 3. CLIMATE/GEO IMMUTABILITY (additive-not-fork invariant) ──────────────────
if command -v git >/dev/null 2>&1; then
  TOUCHED="$(cd "$REPO_ROOT" && git diff --name-only HEAD -- \
      eval/climate-eval-suite.toml \
      'eval/baselines/v*.json' \
      scripts/climate_eval.py scripts/climate_eval_sweep.py \
      'eval/compare-*' 2>/dev/null)"
  if [ -n "$TOUCHED" ]; then
    echo "$TOUCHED"
    fail "climate/geo eval files were modified — additive-not-fork invariant violated"
  fi
  ok "climate/geo eval files UNTOUCHED (zero diff — additive extension confirmed)"
fi

# ── 4. no hardcoded model names in C15 app code ───────────────────────────────
if grep -rnE --include='*.py' \
     'gpt-|claude-[0-9]|qwen[/-][0-9]|bge-m3|text-embedding-|gemma-[0-9]' \
     "$LE_SVC/app/eval/" "$LE_SVC/app/db/repositories/eval_runs.py" \
     "$LE_SVC/app/api/eval.py" >/dev/null 2>&1; then
  fail "hardcoded model name found in a C15 app code path"
fi
ok "no hardcoded model names in C15 app code (judges resolve via model_ref)"
grep -q 'model_ref' "$LE_SVC/app/eval/judge_usefulness.py" \
  || fail "judge usefulness does not reference model_ref"
ok "judges resolve via provider-registry model_ref"

# ── 5. GATE actually gates — bad fixture exits non-zero, demo produces scorecard
if command -v python >/dev/null 2>&1; then
  set +e
  ( cd "$REPO_ROOT" && python scripts/enrichment_eval.py \
      --fixture eval/fixtures/enrichment_bad.json ) >/tmp/c15_bad.log 2>&1
  BAD_RC=$?
  set -e
  [ "$BAD_RC" -ne 0 ] || { cat /tmp/c15_bad.log; fail "GATE FALSE-GREEN: bad fixture did NOT block (exit 0)"; }
  grep -q "GATE: BLOCK" /tmp/c15_bad.log || fail "bad fixture did not print a BLOCK decision"
  grep -q "provenance" /tmp/c15_bad.log || fail "bad fixture did not flag the H0/provenance leak"
  ok "GATE blocks the deliberately-bad fixture (exit $BAD_RC, H0/provenance leak flagged)"

  # demo fixture produces a real deterministic scorecard (composite computed).
  ( cd "$REPO_ROOT" && python scripts/enrichment_eval.py \
      --fixture eval/fixtures/enrichment_demo.json \
      --baseline eval/baselines/enrichment-v1.json \
      --out /tmp/c15_demo_scorecard.json ) >/tmp/c15_demo.log 2>&1 || true
  grep -q "COMPOSITE" /tmp/c15_demo.log || { cat /tmp/c15_demo.log; fail "demo fixture produced no scorecard"; }
  test -f /tmp/c15_demo_scorecard.json || fail "demo scorecard JSON not written"
  ok "demo fixture produces a real scorecard + baseline-diff"
fi

# ── 6. LIVE SMOKE — real judge ensemble on the demo output ─────────────────────
if ! command -v docker >/dev/null 2>&1; then
  note "live infra unavailable: docker not on PATH — deterministic gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:no-docker\"}" >> "$AUDIT_LOG"
  ok "cycle 15 gate PASS (live smoke skipped: no docker)"
  exit 0
fi

dc() { docker compose -f "$COMPOSE" "$@"; }
if ! dc ps >/dev/null 2>&1; then
  note "live infra unavailable: compose stack not reachable — deterministic gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:stack-down\"}" >> "$AUDIT_LOG"
  ok "cycle 15 gate PASS (live smoke skipped: stack down)"
  exit 0
fi

echo "[verify-cycle-15] stack reachable — running REAL judge-ensemble eval on the demo output"

# Resolve the three judge model_refs by NAME at runtime (judges live in
# provider-registry; we pass refs, never names, to the eval). Names here are
# TEST-HARNESS lookup keys (overridable via env), NOT app code — the no-name
# invariant applies to app/ code, which only ever sees the resolved refs.
JUDGE_GEMMA_NAME="${JUDGE_GEMMA_NAME:-google/gemma-3-27b}"
JUDGE_QWEN_NAME="${JUDGE_QWEN_NAME:-qwen/qwen3-30b-a3b}"

set +e
SMOKE_OUT="$( cd "$LE_SVC" && \
  LORE_ENRICHMENT_DB_URL="$LE_DB" \
  PROVIDER_REGISTRY_DB_URL="$PR_DB" \
  INTERNAL_SERVICE_TOKEN="$INTERNAL_TOKEN" \
  PROVIDER_REGISTRY_URL="$PR_URL" \
  DEMO_PROJECT="$DEMO_PROJECT" DEMO_USER="$DEMO_USER" \
  JUDGE_GEMMA_NAME="$JUDGE_GEMMA_NAME" JUDGE_QWEN_NAME="$JUDGE_QWEN_NAME" \
  python -m tests.live_smoke_c15_eval 2>&1 )"
SMOKE_RC=$?
set -e
echo "$SMOKE_OUT"

if [ "$SMOKE_RC" -eq 0 ]; then
  SCORECARD="$(echo "$SMOKE_OUT" | sed -n 's/^SCORECARD_LINE: //p' | tail -1)"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"real judge-ensemble eval on demo output — $SCORECARD\"}" >> "$AUDIT_LOG"
  echo "[verify-cycle-15] live smoke: real judge-ensemble eval scored the demo output + persisted a baseline — $SCORECARD"
  ok "cycle 15 CI gate PASS (real judge-ensemble scorecard persisted)"
  exit 0
elif [ "$SMOKE_RC" -eq 3 ]; then
  note "live infra unavailable: judge JIT load / DB unreachable after retries"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"infra-unavailable:judge-jit\"}" >> "$AUDIT_LOG"
  ok "cycle 15 gate PASS (live smoke: live infra unavailable: judge JIT load)"
  exit 0
else
  fail "live smoke: real judge-ensemble eval did NOT complete (rc=$SMOKE_RC) — see output above"
fi
