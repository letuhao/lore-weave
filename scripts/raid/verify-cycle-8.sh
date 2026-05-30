#!/usr/bin/env bash
# verify-cycle-8.sh — CI gate for RAID cycle 8 (Strategy core). Exit 0 = PASS.
# Modeled on scripts/raid/verify-cycle-7.sh.
#
# Asserts (per docs/raid/cycle_briefs/08_strategy-core.md acceptance criteria):
#   1. Strategy core modules exist: app/strategies/{base,registry,feature_flags}.py
#      (EnrichmentStrategy ABC, StrategyRegistry, feature-flags) and
#      app/jobs/{state_machine,cost_guardrail}.py.
#   2. Q-R2 invariant in CODE: P1 (template/retrieval) active by default; P2/P3
#      (fabrication/recook) registered but INACTIVE until the C15 gate.
#   3. The three unit suites green: registry (active/inactive/unknown select),
#      state machine (legal + illegal-raise), cost guardrail (cap breach → paused).
#   4. Live demonstrations (in-process, no cross-service call):
#        a. an INACTIVE technique is NOT selectable (raises) and NOT in list_active;
#        b. a cost batch that overruns the cap pauses the job (status -> paused,
#           reason cost_cap) BEFORE the overrun.
#   5. ruff clean on the new app/ + test files.
#   6. NO hardcoded provider/model names anywhere in the new modules.
#   7. Scope: NO migrations, NO LLM/embed client imports, NO real strategy body.
#   8. Full service unit suite green (no regression).
# Single-service cycle (in-process state machine + registry) → NO cross-service
# live-smoke token required.
set -uo pipefail
CYCLE=8
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="$REPO_ROOT/services/lore-enrichment-service"
STRAT_DIR="$SVC/app/strategies"
JOBS_DIR="$SVC/app/jobs"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-8] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-8] ok: $1"; }

echo "[verify-cycle-8] running CI gate"

# ── 1. core modules exist with the required symbols ───────────────────────────
for f in "$STRAT_DIR/base.py" "$STRAT_DIR/registry.py" "$STRAT_DIR/feature_flags.py" \
         "$JOBS_DIR/state_machine.py" "$JOBS_DIR/cost_guardrail.py"; do
  [ -f "$f" ] || fail "missing module: $f"
done
grep -q "class EnrichmentStrategy" "$STRAT_DIR/base.py" || fail "base.py missing EnrichmentStrategy ABC"
grep -q "class CostEstimate" "$STRAT_DIR/base.py" || fail "base.py missing CostEstimate"
grep -q "class Tier" "$STRAT_DIR/base.py" || fail "base.py missing Tier"
grep -q "class StrategyRegistry" "$STRAT_DIR/registry.py" || fail "registry.py missing StrategyRegistry"
for sym in "def select" "def list_active" "def register"; do
  grep -q "$sym" "$STRAT_DIR/registry.py" || fail "registry.py missing: $sym"
done
grep -q "InactiveStrategyError" "$STRAT_DIR/registry.py" || fail "registry.py missing InactiveStrategyError"
grep -q "class FeatureFlags" "$STRAT_DIR/feature_flags.py" || fail "feature_flags.py missing FeatureFlags"
grep -q "class JobStateMachine" "$JOBS_DIR/state_machine.py" || fail "state_machine.py missing JobStateMachine"
grep -q "IllegalTransitionError" "$JOBS_DIR/state_machine.py" || fail "state_machine.py missing IllegalTransitionError"
grep -q "class CostGuardrail" "$JOBS_DIR/cost_guardrail.py" || fail "cost_guardrail.py missing CostGuardrail"
ok "strategy core modules present (interface + registry + flags + state machine + cost guardrail)"

# ── 2. Q-R2 default-active set is exactly P1 (derived from tier table) ─────────
grep -q "DEFAULT_ACTIVE_TECHNIQUES" "$STRAT_DIR/feature_flags.py" || fail "feature_flags.py missing DEFAULT_ACTIVE_TECHNIQUES"
ok "feature-flag default-active set is declared (P1-derived)"

# ── 3+4. unit suites green + live in-process demonstrations ───────────────────
cd "$SVC" || fail "service dir missing"

if ! python -m pytest tests/test_strategy_registry.py tests/test_job_state_machine.py \
       tests/test_cost_guardrail.py -q >/tmp/c8_units.log 2>&1; then
  cat /tmp/c8_units.log
  fail "C8 unit suites red"
fi
ok "C8 unit suites green ($(grep -oE '[0-9]+ passed' /tmp/c8_units.log | head -1))"

# In-process demonstration: (a) inactive technique not selectable / not listed;
# (b) cost-cap overrun pauses the job (status -> paused, reason cost_cap) BEFORE
# the overrun. No cross-service call — this is the cycle's acceptance smoke.
python - <<'PY' || fail "C8 in-process demonstration failed (see error above)"
import asyncio

from app.strategies.base import CostEstimate, EnrichmentStrategy, Technique, Tier
from app.strategies.feature_flags import load_feature_flags
from app.strategies.registry import (
    InactiveStrategyError,
    StrategyRegistry,
    UnknownStrategyError,
)
from app.jobs.cost_guardrail import CostCapExceeded, CostGuardrail
from app.jobs.state_machine import (
    IllegalTransitionError,
    JobRecord,
    JobState,
    JobStateMachine,
    PauseReason,
)


class _Stub(EnrichmentStrategy):
    def __init__(self, technique):
        self.technique = technique

    def estimate_cost(self, gap_batch):
        return CostEstimate(technique=self.technique, gap_count=len(gap_batch),
                            units=float(len(gap_batch)), cost=float(len(gap_batch)))

    async def run(self, gap_batch, context):
        return None


# (a) registry: P1 selectable, P2/P3 dark, unknown raises distinctly
reg = StrategyRegistry()
for t in Technique:
    reg.register(_Stub(t))

assert reg.select(Technique.TEMPLATE).tier is Tier.P1
assert reg.select(Technique.RETRIEVAL).tier is Tier.P1
active_keys = {s.technique for s in reg.list_active()}
assert active_keys == {Technique.TEMPLATE, Technique.RETRIEVAL}, active_keys

for dark in (Technique.FABRICATION, Technique.RECOOK):
    try:
        reg.select(dark)
        raise SystemExit(f"BUG: inactive {dark} was selectable")
    except InactiveStrategyError:
        pass
    assert dark not in active_keys

try:
    reg.select("does-not-exist")
    raise SystemExit("BUG: unknown key did not raise")
except UnknownStrategyError:
    pass

# the C15 gate can flip P2 on — and ONLY then is it selectable
gated = StrategyRegistry(flags=load_feature_flags(overrides={Technique.FABRICATION: True}))
for t in Technique:
    gated.register(_Stub(t))
assert gated.select(Technique.FABRICATION).technique is Technique.FABRICATION
try:
    gated.select(Technique.RECOOK)  # P3 still dark
    raise SystemExit("BUG: P3 leaked when only P2 was gated on")
except InactiveStrategyError:
    pass
print("registry-demo-ok: P1 selectable, P2/P3 dark until gate, unknown raises")

# (b) cost-cap overrun pauses the job BEFORE the overrun
async def cost_demo():
    rec = JobRecord(job_id="demo-job", state=JobState.RUNNING)
    persisted = []

    async def sink(r):
        persisted.append(r.state)

    sm = JobStateMachine(rec, persist=sink)
    g = CostGuardrail(cap=5.0)
    await g.charge_or_pause(3.0, sm)          # fits
    assert rec.state is JobState.RUNNING
    try:
        await g.charge_or_pause(3.0, sm)      # 3+3=6 > 5 → pause before overrun
        raise SystemExit("BUG: cap overrun did not pause")
    except CostCapExceeded:
        pass
    assert rec.state is JobState.PAUSED, rec.state
    assert rec.pause_reason is PauseReason.COST_CAP
    assert g.spent == 3.0, g.spent           # spend NOT pushed past the cap
    assert persisted == [JobState.PAUSED], persisted  # persisted status == paused
    # illegal transition raises (no silent no-op)
    term = JobStateMachine(JobRecord(job_id="t", state=JobState.COMPLETED))
    try:
        await term.resume()
        raise SystemExit("BUG: resume-from-completed did not raise")
    except IllegalTransitionError:
        pass

asyncio.run(cost_demo())
print("cost-cap-demo-ok: job paused(cost_cap) before overrun; illegal transition raised")
PY
ok "in-process demo: inactive technique not selectable + cost-cap pause(before overrun) + illegal transition raises"

# ── 5. ruff clean ─────────────────────────────────────────────────────────────
if ! python -m ruff check "$STRAT_DIR" "$JOBS_DIR" \
       tests/test_strategy_registry.py tests/test_job_state_machine.py \
       tests/test_cost_guardrail.py >/tmp/c8_ruff.log 2>&1; then
  cat /tmp/c8_ruff.log
  fail "ruff check failed on app/strategies + app/jobs + C8 tests"
fi
ok "ruff clean on app/strategies + app/jobs + C8 tests"

# ── 6. no hardcoded provider/model names in the new modules ───────────────────
if grep -rniE --include="*.py" \
   "text-embedding-bge-m3|bge-m3|nomic-embed|\bqwen|\bgemma|gpt-4|gpt-3\.|text-embedding-3|claude-[0-9]|\bllama" \
   "$STRAT_DIR" "$JOBS_DIR"; then
  fail "hardcoded provider/model name in strategy core"
fi
ok "no hardcoded provider/model names in strategy core"

# ── 7. scope: no migrations, no LLM/embed client imports, no real strategy body ─
if grep -rnE "import (httpx|openai|litellm|requests|neo4j)|from (httpx|openai|litellm|requests|neo4j)" \
   "$STRAT_DIR" "$JOBS_DIR"; then
  fail "strategy core imports an LLM/HTTP client — C8 is interface-only (generation is C9/C10)"
fi
# the OUT-of-scope DB migration: no DDL/migrate edits in this cycle's modules
if grep -rnE "CREATE TABLE|ALTER TABLE|run_migrations" "$STRAT_DIR" "$JOBS_DIR"; then
  fail "strategy core touches migrations — C8 reuses the C2 schema, no new DDL"
fi
ok "scope clean: no migrations, no LLM/embed client, no generation body"

# ── 8. full service unit suite green (no regression) ──────────────────────────
if ! python -m pytest -q >/tmp/c8_unit.log 2>&1; then
  cat /tmp/c8_unit.log
  fail "service unit suite red"
fi
ok "service unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c8_unit.log | head -1))"

mkdir -p "$(dirname "$AUDIT_LOG")"
echo "{\"ts\":\"$NOW\",\"event\":\"verify_cycle_pass\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
echo "[verify-cycle-8] PASS"
exit 0
