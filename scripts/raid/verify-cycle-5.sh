#!/usr/bin/env bash
# verify-cycle-5 — C5 build-graph gates unblock (FE) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only: empty-model AddModelCta +
# visible benchmark gate (no enable-too-early) + disabled-reason. Targeted vitest.
set -euo pipefail
CYCLE=5
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-5] FAIL: $1" >&2; audit "verify_cycle_5_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-5] running CI gate"

BGD="$FE/src/features/knowledge/components/BuildGraphDialog.tsx"
EMP="$FE/src/features/knowledge/components/EmbeddingModelPicker.tsx"

# ── 1. in-flow AddModelCta on empty LLM + empty embedding (no dead-ends) ──
have "$BGD" "AddModelCta" "BuildGraphDialog missing in-flow AddModelCta for empty LLM"
have "$EMP" "AddModelCta" "EmbeddingModelPicker empty-state missing in-flow AddModelCta"

# ── 2. benchmark is a visible gate — no enable-too-early during load ──
have "$BGD" "benchmarkLoading" "BuildGraphDialog missing benchmark-loading guard (enable-too-early)"
have "$BGD" "disabledReason" "BuildGraphDialog missing disabled-reason messaging"
grep -Fq "build-graph-disabled-reason" "$BGD" || fail "disabled-reason not rendered"

# ── 3. rerank is NOT a build precondition (LOCKED diagnosis) ──
# canConfirm must not reference rerank as a gate.
if grep -nE 'canConfirm' "$BGD" | grep -iq 'rerank'; then
  fail "rerank used as a build-graph precondition (violates LOCKED diagnosis)"
fi

# ── 4. targeted vitest green (gate logic) ──
cd "$FE"
echo "[verify-cycle-5] vitest (BuildGraphDialog gates)"
npx vitest run \
  src/features/knowledge/components/__tests__/BuildGraphDialog.test.tsx \
  src/features/knowledge/components/__tests__/EmbeddingModelPicker.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -10

audit "verify_cycle_5_passed"
echo "[verify-cycle-5] PASS"
exit 0
