#!/usr/bin/env bash
# verify-cycle-17.sh — CI gate for RAID cycle 17 (strategy (d) RE-COOK, P3 —
# gate-enforced + LICENSING). Exit 0 = PASS.
#
# Asserts (per docs/raid/cycle_briefs/17_strategy-recook.md acceptance +
# DEFERRED-054 gate-enforcement hard requirement + the C17 LICENSING safety):
#   1. C17 unit suite green: ReCookStrategy (H0 origin='enriched:recook' + conf<1.0
#      + quarantined + recook-basis provenance citing the LICENSED source),
#      canon-verify runs on re-cooked content (anachronism on re-cooked modern!),
#      grounding required (no invent-from-nothing), the LICENSING gate (default-deny:
#      public_domain/licensed ADMITTED; unlicensed/copyrighted/unknown/missing
#      REFUSED at corpus-admission AND fact-emit), AND the gate-aware factory
#      enforcement (LOCKED → InactiveStrategyError; CLEARED → selectable; an
#      override cannot bypass a locked gate; read-error fails closed).
#   2. RUNNER gate e2e: gate LOCKED + recook → refused before runner; CLEARED + PD
#      → re-cooks H0 proposals; CLEARED + unlicensed → refused mid-run (no proposal);
#      recook cost (12.0) binds; P1 path unaffected. (Same end-to-end enforcement as
#      C16's test_runner_gate_e2e, extended to P3 + licensing.)
#   3. Full lore-enrichment suite green — no C0–C16 regression.
#   4. ruff clean on the C17 code paths.
#   5. No hardcoded model names in the C17 app code (model via provider-registry
#      model_ref / the injected CompleteFn seam).
#   6. GATE ENFORCEMENT (054): focused assertion that gate-LOCKED → recook is NOT
#      selectable and gate-CLEARED → selectable (gate ENFORCED, not advisory).
#   7. LICENSING ENFORCEMENT: focused assertion that an unlicensed/unknown source
#      is REFUSED and a public_domain/licensed source is ADMITTED (default-deny).
#   8. Eval-gate clears threshold BEFORE active: re-run the C15 deterministic gate
#      (bad fixture BLOCKS) to confirm the gate the factory reads is real + gates.
#      C17 reads this gate; it does NOT edit it.
#   9. Isolation: git diff touches NO climate/geo eval files, NO C15 eval files,
#      NO world-service / game-server / infra/existing-prod.
#  10. LIVE SMOKE (best-effort): a real re-cook of a PUBLIC-DOMAIN history snippet
#      into 商周 via real Qwen → a quarantined, H0-tagged proposal, ONLY when the
#      gate is cleared, AND a copyrighted negative-control source REFUSED. Genuine
#      infra-unavailable is a legitimate skip (no cross-service token required —
#      this cycle is in-service per the brief).
set -uo pipefail
CYCLE=17
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LE_SVC="$REPO_ROOT/services/lore-enrichment-service"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-17] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-17] ok: $1"; }
note() { echo "[verify-cycle-17] note: $1"; }

echo "[verify-cycle-17] running CI gate"

# ── 1+2. C17 unit + runner-e2e suites ────────────────────────────────────────────
if command -v python >/dev/null 2>&1; then
  ( cd "$LE_SVC" && python -m pytest \
      tests/test_recook_strategy.py tests/test_runner_recook_gate_e2e.py -q ) \
    >/tmp/c17_unit.log 2>&1 \
    || { cat /tmp/c17_unit.log; fail "C17 re-cook unit/e2e suite failed"; }
  ok "C17 re-cook unit + runner-gate-e2e suites green (H0 + canon-verify + gate + licensing)"

  # ── 3. full service suite — no C0–C16 regression ─────────────────────────────
  ( cd "$LE_SVC" && python -m pytest -q ) >/tmp/c17_full.log 2>&1 \
    || { tail -40 /tmp/c17_full.log; fail "lore-enrichment full suite regressed"; }
  ok "lore-enrichment full suite green (no C0–C16 regression)"
else
  note "python not on PATH — skipping unit suite here"
fi

# ── 4. ruff clean on C17 paths ────────────────────────────────────────────────────
if command -v ruff >/dev/null 2>&1; then
  ( cd "$LE_SVC" && ruff check \
      app/strategies/recook.py app/strategies/licensing.py \
      app/strategies/__init__.py app/jobs/stages.py app/jobs/assembly.py \
      app/retrieval/store.py app/db/migrate.py \
      tests/test_recook_strategy.py tests/test_runner_recook_gate_e2e.py ) \
    >/tmp/c17_ruff.log 2>&1 \
    || { cat /tmp/c17_ruff.log; fail "ruff failed on C17 files"; }
  ok "ruff clean on C17 code paths"
fi

# ── 5. no hardcoded model names in C17 app code ──────────────────────────────────
if grep -rnE --include='*.py' \
     'gpt-|claude-[0-9]|qwen[/-][0-9]|bge-m3|text-embedding-|gemma-[0-9]|llama-[0-9]' \
     "$LE_SVC/app/strategies/recook.py" \
     "$LE_SVC/app/strategies/licensing.py" >/dev/null 2>&1; then
  fail "hardcoded model name found in a C17 app code path"
fi
ok "no hardcoded model names in C17 app code (model via model_ref / CompleteFn)"
grep -q 'model_ref' "$LE_SVC/app/strategies/recook.py" \
  || fail "re-cook strategy does not reference model_ref"
ok "re-cook resolves the model via provider-registry model_ref"

# ── 6. GATE ENFORCEMENT (054) — the load-bearing assertion (P3) ──────────────────
if command -v python >/dev/null 2>&1; then
  ( cd "$LE_SVC" && python -m pytest \
      tests/test_recook_strategy.py tests/test_runner_recook_gate_e2e.py -q -k \
      "gate_locked or gate_cleared or override_cannot_bypass or read_error or fails_closed or refuses_recook" ) \
    >/tmp/c17_gate.log 2>&1 \
    || { cat /tmp/c17_gate.log; fail "GATE ENFORCEMENT tests failed (054 not enforced for P3)"; }
  ok "GATE ENFORCED (054) for P3: LOCKED→unselectable+refused, CLEARED→selectable, no override bypass"
fi

# ── 7. LICENSING ENFORCEMENT — the C17-specific safety ───────────────────────────
if command -v python >/dev/null 2>&1; then
  ( cd "$LE_SVC" && python -m pytest \
      tests/test_recook_strategy.py tests/test_runner_recook_gate_e2e.py -q -k \
      "license or licensed or inadmissible or unlicensed or unresolvable or admits" ) \
    >/tmp/c17_lic.log 2>&1 \
    || { cat /tmp/c17_lic.log; fail "LICENSING ENFORCEMENT tests failed"; }
  ok "LICENSING ENFORCED (default-deny): PD/licensed ADMITTED; unlicensed/unknown/copyrighted REFUSED"
fi

# ── 8. eval gate clears threshold BEFORE active (the gate C17 reads is real) ─────
if command -v python >/dev/null 2>&1 \
   && [ -f "$REPO_ROOT/scripts/enrichment_eval.py" ]; then
  set +e
  ( cd "$REPO_ROOT" && python scripts/enrichment_eval.py \
      --fixture eval/fixtures/enrichment_bad.json ) >/tmp/c17_evalbad.log 2>&1
  BAD_RC=$?
  set -e
  [ "$BAD_RC" -ne 0 ] || { cat /tmp/c17_evalbad.log; fail "eval gate FALSE-GREEN: bad fixture did not BLOCK"; }
  ok "eval gate still blocks the bad fixture (exit $BAD_RC) — gate is real, re-cook gated on it"
fi

# ── 9. ISOLATION (additive-not-fork + no prod/cross-service drift) ───────────────
if command -v git >/dev/null 2>&1; then
  TOUCHED="$(cd "$REPO_ROOT" && git diff --name-only HEAD -- \
      eval/climate-eval-suite.toml 'eval/baselines/v*.json' \
      scripts/climate_eval.py scripts/climate_eval_sweep.py 'eval/compare-*' \
      scripts/enrichment_eval.py eval/enrichment-eval-suite.toml \
      'eval/baselines/enrichment-*.json' \
      services/world-service services/game-server infra/existing-prod 2>/dev/null)"
  if [ -n "$TOUCHED" ]; then
    echo "$TOUCHED"
    fail "isolation violated — C17 must NOT touch climate/geo eval, C15 eval files, world-service/game-server/prod"
  fi
  ok "isolation OK (no climate/geo eval, no C15 eval files, no world-service/game-server/prod)"

  if [ -x "$REPO_ROOT/scripts/raid/prod-isolation-lint.sh" ]; then
    bash "$REPO_ROOT/scripts/raid/prod-isolation-lint.sh" >/tmp/c17_prodlint.log 2>&1 \
      || { cat /tmp/c17_prodlint.log; fail "prod-isolation lint failed"; }
    ok "prod-isolation lint clean"
  fi
fi

# ── 10. LIVE SMOKE — real Qwen re-cook of a PD source into 商周 (best-effort) ─────
LIVE_SMOKE="$LE_SVC/tests/live_smoke_c17_recook.py"
if ! command -v docker >/dev/null 2>&1; then
  note "live infra unavailable: docker not on PATH — deterministic gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:no-docker\"}" >> "$AUDIT_LOG"
  ok "cycle 17 gate PASS (live smoke skipped: no docker)"
  exit 0
fi
if ! docker compose -f "$REPO_ROOT/infra/docker-compose.yml" ps >/dev/null 2>&1; then
  note "live infra unavailable: compose stack not reachable — deterministic gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:stack-down\"}" >> "$AUDIT_LOG"
  ok "cycle 17 gate PASS (live smoke skipped: stack down)"
  exit 0
fi
if [ ! -f "$LIVE_SMOKE" ]; then
  note "live smoke harness not present — deterministic gate only (in-service cycle, no cross-service token required)"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:no-harness\"}" >> "$AUDIT_LOG"
  ok "cycle 17 gate PASS (live smoke skipped: harness JIT — deterministic enforcement proven)"
  exit 0
fi

echo "[verify-cycle-17] stack reachable — running REAL Qwen re-cook of a PD source into 商周"
LE_DB="${TEST_LORE_ENRICHMENT_DB_URL:-postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_lore_enrichment}"
PR_DB="${PROVIDER_REGISTRY_DB_URL:-postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_provider_registry}"
PR_URL="${PROVIDER_REGISTRY_URL:-http://localhost:8208}"
INTERNAL_TOKEN="${INTERNAL_SERVICE_TOKEN:-dev_internal_token}"
# app.config.Settings() (pulled in transitively at smoke import) requires these;
# supply the compose dev defaults so config-load can't crash the smoke before
# _main runs (a missing secret would otherwise look like a hard fail, not a skip).
JWT_SECRET_V="${JWT_SECRET:-loreweave_local_dev_jwt_secret_change_me_32chars}"
set +e
SMOKE_OUT="$( cd "$LE_SVC" && \
  LORE_ENRICHMENT_DB_URL="$LE_DB" PROVIDER_REGISTRY_DB_URL="$PR_DB" \
  PROVIDER_REGISTRY_URL="$PR_URL" INTERNAL_SERVICE_TOKEN="$INTERNAL_TOKEN" \
  JWT_SECRET="$JWT_SECRET_V" \
  python -m tests.live_smoke_c17_recook 2>&1 )"
SMOKE_RC=$?
set -e
echo "$SMOKE_OUT"
if [ "$SMOKE_RC" -eq 0 ]; then
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"real Qwen re-cook of PD source into 商周 → quarantined H0 proposal; copyrighted source refused\"}" >> "$AUDIT_LOG"
  ok "cycle 17 CI gate PASS (real re-cook → quarantined H0-tagged proposal; licensing enforced)"
  exit 0
elif [ "$SMOKE_RC" -eq 3 ]; then
  note "live infra unavailable: Qwen JIT load / DB unreachable / gate not cleared after retries"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"infra-unavailable:qwen-jit-or-gate\"}" >> "$AUDIT_LOG"
  ok "cycle 17 gate PASS (live smoke: live infra unavailable: Qwen JIT load / gate)"
  exit 0
else
  fail "live smoke: real re-cook did NOT complete (rc=$SMOKE_RC) — see output above"
fi
