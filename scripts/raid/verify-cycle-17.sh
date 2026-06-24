#!/usr/bin/env bash
# verify-cycle-17 — C17 Writer flow polish (FE) acceptance gate. ▶ M3.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only: guided first-run (auto first
# scene + auto-pick the SOLE chat model + a contextual cue → ≤2 clicks to a first
# draft) + "Continue from cursor" first-class (caret-anchored streaming continue,
# WG-4/WG-5, LOCKED writer-not-hard-blocked). Targeted vitest + eslint/tsc on touched.
set -euo pipefail
CYCLE=17
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-17] FAIL: $1" >&2; audit "verify_cycle_17_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-17] running CI gate"

HOOK="$FE/src/features/composition/hooks/useGuidedFirstRun.ts"
PANEL="$FE/src/features/composition/components/CompositionPanel.tsx"
INLINE="$FE/src/features/composition/components/InlineAiLayer.tsx"
EDITOR="$FE/src/pages/ChapterEditorPage.tsx"

# ── 1. guided first-run: auto first scene + auto-pick the SOLE model in a HOOK ──
have "$HOOK" "useGuidedFirstRun" "missing guided first-run hook"
have "$HOOK" "soleModelId" "hook must expose the sole-model auto-pick"
have "$HOOK" "runGuided" "hook must expose an explicit runGuided() action"
# Auto-pick ONLY when exactly one model — never 0/≥2 (the misfire guard).
grep -Fq "models.length === 1" "$HOOK" || fail "auto-pick is not gated to EXACTLY one model"
# Logic lives in the hook, not the component (FE MVC).
have "$PANEL" "useGuidedFirstRun" "CompositionPanel must consume the guided hook"

# ── 2. first-run cue renders + a primed Start action creates the first scene ──
have "$PANEL" "composition-guided-cue" "missing first-run cue"
have "$PANEL" "composition-guided-start" "missing primed Start-writing action"
have "$PANEL" "guided.runGuided" "Start action must call the hook's explicit runGuided handler"

# ── 3. "Continue from cursor" is FIRST-CLASS (not buried behind the AI-mode toggle) ──
have "$INLINE" "inline-continue" "missing continue-from-cursor affordance"
have "$INLINE" "continueFromCursor" "continue-from-cursor must use the first-class i18n label"
have "$INLINE" "g.continueDraft" "continue-from-cursor must be wired to the streaming continue"
# The continue button must NOT be gated by `mode === 'ai'` (the C17 un-burying).
if grep -n "data-testid=\"inline-continue\"" "$INLINE" | grep -q "mode === 'ai'"; then
  fail "continue-from-cursor still gated behind the AI-mode toggle (not first-class)"
fi
# No useEffect-for-events in the inline layer's continue path (direct handler).
have "$INLINE" "onClick={g.continueDraft}" "continue-from-cursor must fire from a direct onClick handler"

# ── 4. editor falls back to the SOLE chat model so Continue works without a default ──
have "$EDITOR" "soleChatModel" "editor must fall back to the sole registered chat model for inline continue"
grep -Fq "chatModels.data?.length === 1" "$EDITOR" || fail "editor sole-model fallback not gated to EXACTLY one model"

# ── 5. writer NOT hard-blocked: Generate still gates only on scene+model+busy ──
CV="$FE/src/features/composition/components/ComposeView.tsx"
if grep -nE 'canGenerate' "$CV" | grep -iqE 'knowledge|grounding|embedding|rerank'; then
  fail "Generate gated on knowledge/grounding (violates LOCKED writer-not-hard-blocked)"
fi

# ── 6. no hardcoded chat-model name in the auto-pick (provider invariant) ──
# Auto-pick resolves from the registered model list (listUserModels capability:'chat').
have "$PANEL" "listUserModels" "auto-pick must resolve the chat model via the registry"
have "$EDITOR" "listUserModels" "editor sole-model fallback must resolve via the registry"

# ── 7. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-17] vitest (guided first-run + continue-from-cursor)"
npx vitest run \
  src/features/composition/hooks/__tests__/useGuidedFirstRun.test.ts \
  src/features/composition/components/__tests__/CompositionPanelGuided.test.tsx \
  src/features/composition/components/__tests__/CompositionPanelReadiness.test.tsx \
  src/features/composition/components/__tests__/CompositionPanel.test.tsx \
  src/features/composition/components/__tests__/InlineAiLayer.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -12

# ── 8. eslint + tsc on touched files ──
echo "[verify-cycle-17] eslint (touched files)"
npx eslint "$HOOK" "$PANEL" "$INLINE" "$EDITOR" --max-warnings=0 2>&1 | tail -10
echo "[verify-cycle-17] tsc --noEmit"
npx tsc --noEmit 2>&1 | tail -10

audit "verify_cycle_17_passed"
echo "[verify-cycle-17] PASS"
exit 0
