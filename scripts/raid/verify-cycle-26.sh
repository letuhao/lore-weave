#!/usr/bin/env bash
# verify-cycle-26 — C26 Critic override enforcement (BE composition). Per
# RAID_WORKFLOW.md §13 (exit 0 = pass). dị bản M3: a DERIVATIVE critic dimension
# that activates ONLY for derivative Works (source_work_id), LOADS the active
# entity_override[] via C25's resolution path (reuse — NO re-merge), flags an
# OVERRIDE SLIP (overridden field reverted to canon/base → finding with
# entity+field+expected-vs-found), checks DELTA INTERNAL CONSISTENCY, and is WIRED
# into the critique call site (a wiring test proves it FIRES — anti-no-op). AI-free
# (composition has no AI imports). Static greps + targeted pytest + py_compile +
# provider-gate.
set -euo pipefail
CYCLE=26
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CS="$REPO_ROOT/services/composition-service"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-26] FAIL: $1" >&2; audit "verify_cycle_26_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-26] running CI gate"

CRITIC_OV="$CS/app/engine/critic_override.py"
ENGINE="$CS/app/routers/engine.py"
TEST_OV="$CS/tests/unit/test_critic_override.py"
TEST_ENG="$CS/tests/unit/test_engine_router.py"

for f in "$CRITIC_OV" "$ENGINE" "$TEST_OV" "$TEST_ENG"; do
  [ -f "$f" ] || fail "missing source file: $f"
done

# ── 1. the derivative critic dimension — detector + orchestrator ──
have "$CRITIC_OV" "def detect_override_findings" "critic_override missing the pure slip detector"
have "$CRITIC_OV" "def critique_overrides" "critic_override missing the wired orchestrator"
have "$CRITIC_OV" "override_slip" "detector does not emit a structured override-slip finding"
have "$CRITIC_OV" "delta_inconsistency" "detector does not check delta internal consistency"
# expected-vs-found structured finding fields.
have "$CRITIC_OV" '"expected"' "override-slip finding missing the expected (override) value"
have "$CRITIC_OV" '"found"' "override-slip finding missing the found (reverted base) value"

# ── 2. REUSE C25's resolution path — NO re-merge / NO re-implemented override read ──
have "$CRITIC_OV" "build_derivative_context" "dimension does not reuse C25's build_derivative_context (override resolution)"
have "$CRITIC_OV" "_resolve_override_anchors" "dimension does not reuse C25's anchor reconcile"
# Must NOT re-implement the override merge (apply_entity_overrides is C25's; the
# critic READS overrides, it does not re-merge present base+delta).
grep -Fq "def apply_entity_overrides" "$CRITIC_OV" && fail "critic re-implements the override merge (must reuse C25)" || true
grep -Fq "def merge_present" "$CRITIC_OV" && fail "critic re-implements base+delta merge (must reuse C25)" || true

# ── 3. ACTIVATES ONLY for a derivative Work (source_work_id) ──
have "$CRITIC_OV" "source_project_id is None" "dimension does not gate activation on a derivative (source project)"

# ── 4. SCOPE — entity-field + canon-rule only (no relationship/event overrides) ──
have "$CRITIC_OV" "OVERRIDE_CANON_FIELD" "dimension does not enforce the added canon-rule scope"
grep -Eiq "relationship_override|event_override" "$CRITIC_OV" \
  && fail "dimension enforces relationship/event overrides (out of M0 scope)" || true

# ── 5. WIRED at the critique call site (anti-no-op) ──
have "$ENGINE" "from app.engine.critic_override import critique_overrides" "engine router does not import the dimension"
have "$ENGINE" "critique_overrides(" "engine router does not invoke the dimension at the critique call site"
have "$ENGINE" "derivative_findings" "engine router does not surface the derivative findings"
# the WIRING test exists + asserts the dimension fires for a derivative.
have "$TEST_ENG" "test_critique_derivative_dimension_FIRES_at_call_site" "missing the router-level wiring test (anti-no-op)"
have "$TEST_OV" "test_wiring_dimension_fires_for_derivative" "missing the unit wiring (spy-injection) test"
have "$TEST_OV" "test_no_activation_on_canon_work" "missing the canon-Work no-activation test"
have "$TEST_OV" "test_inherited_entity_not_flagged" "missing the inherited-entity false-positive guard test"

# ── 6. AI-free — composition has NO AI imports (the dimension is deterministic) ──
grep -Eq "import (openai|anthropic|cohere|google\\.generativeai|litellm)" "$CRITIC_OV" \
  && fail "critic_override imports a provider SDK (composition must stay AI-free)" || true

# ── 7. py_compile syntax gate (touched files) ──
echo "[verify-cycle-26] py_compile"
python -m py_compile "$CRITIC_OV" "$ENGINE" || fail "py_compile failed on a touched file"

# ── 8. provider-gate (composition has NO AI imports — keep it) ──
echo "[verify-cycle-26] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 9. targeted pytest — derivative critic + engine router (wiring) ──
echo "[verify-cycle-26] pytest (derivative critic + engine router wiring)"
( cd "$CS" && python -m pytest \
    tests/unit/test_critic_override.py \
    tests/unit/test_engine_router.py \
    tests/unit/test_critic.py \
    -q 2>&1 | tail -6 ) || fail "composition-service C26 pytest failed"

audit "verify_cycle_26_passed"
echo "[verify-cycle-26] PASS"
exit 0
