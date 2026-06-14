#!/usr/bin/env bash
# verify-cycle-15 — C15 Writer unblock (FE) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only: empty chat-model AddModelCta
# in Compose + "Ready to draft" optional-knowledge messaging + plain-editor→AI
# bridge (WG-1/WG-2/WG-6, LOCKED writer-not-hard-blocked). Targeted vitest +
# eslint/tsc on touched files.
set -euo pipefail
CYCLE=15
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-15] FAIL: $1" >&2; audit "verify_cycle_15_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-15] running CI gate"

PANEL="$FE/src/features/composition/components/CompositionPanel.tsx"
BRIDGE="$FE/src/features/composition/components/CowriteBridgeButton.tsx"
EDITOR="$FE/src/pages/ChapterEditorPage.tsx"

# ── 1. empty chat-model state → in-flow AddModelCta in Compose (no dead end) ──
have "$PANEL" "AddModelCta" "CompositionPanel missing in-flow AddModelCta for empty chat-model list"
have "$PANEL" "composition-add-chat-model" "AddModelCta not surfaced in Compose selector bar"

# ── 2. "Ready to draft" + optional-knowledge messaging when a chat model exists ──
have "$PANEL" "composition-ready-to-draft" "CompositionPanel missing ready-to-draft cue"
have "$PANEL" "readyToDraft" "CompositionPanel missing ready-to-draft i18n key"

# ── 3. writer NOT hard-blocked: Generate must NOT be gated on knowledge/grounding ──
# canGenerate (ComposeView) gates only on scene + model + busy — never on knowledge.
CV="$FE/src/features/composition/components/ComposeView.tsx"
if grep -nE 'canGenerate' "$CV" | grep -iqE 'knowledge|grounding|embedding|rerank'; then
  fail "Generate gated on knowledge/grounding (violates LOCKED writer-not-hard-blocked)"
fi

# ── 4. no hardcoded chat-model name in Compose (provider invariant) ──
# The model is resolved via the registry (aiModelsApi.listUserModels capability:'chat').
have "$PANEL" "listUserModels" "CompositionPanel must resolve chat model via the registry"

# ── 5. plain-editor → AI bridge: a live direct-handler button (not a dead button) ──
have "$BRIDGE" "onActivate" "CowriteBridgeButton missing direct onActivate handler"
have "$BRIDGE" "chapter-cowrite-bridge" "CowriteBridgeButton missing testid"
have "$EDITOR" "CowriteBridgeButton" "ChapterEditorPage does not wire the plain-editor→AI bridge"
have "$EDITOR" "setRightTab('compose')" "bridge does not open the Compose panel"
# the bridge must NOT use a useEffect to react to the click (MVC: direct handler).
# Match an actual call/import, not the prose comment that explains the rule.
if grep -nE "useEffect\(|[,{ ]useEffect[ ,}]" "$BRIDGE" >/dev/null 2>&1; then
  fail "CowriteBridgeButton uses useEffect (must be a direct handler, no useEffect-for-events)"
fi

# ── 6. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-15] vitest (writer-unblock readiness + bridge)"
npx vitest run \
  src/features/composition/components/__tests__/CompositionPanelReadiness.test.tsx \
  src/features/composition/components/__tests__/CowriteBridgeButton.test.tsx \
  src/features/composition/components/__tests__/CompositionPanel.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -12

# ── 7. eslint + tsc on touched files ──
echo "[verify-cycle-15] eslint (touched files)"
npx eslint "$PANEL" "$BRIDGE" "$EDITOR" --max-warnings=0 2>&1 | tail -10
echo "[verify-cycle-15] tsc --noEmit"
npx tsc --noEmit 2>&1 | tail -10

audit "verify_cycle_15_passed"
echo "[verify-cycle-15] PASS"
exit 0
