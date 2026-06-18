#!/usr/bin/env bash
# verify-cycle-24 — C24 Divergence wizard + derivative studio (FE) ▶ dị bản M1
# acceptance gate. Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only cycle
# (features/composition/) consuming C23's POST /works/{id}/derive. Static asserts
# + targeted vitest (PowerShell proves vitest separately at VERIFY; bash-spawned
# vitest can hang in this env so the list is small).
set -euo pipefail
CYCLE=24
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-24] FAIL: $1" >&2; audit "verify_cycle_24_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-24] running CI gate"

API="$FE/src/features/composition/api.ts"
TYPES="$FE/src/features/composition/types.ts"
WIZHOOK="$FE/src/features/composition/hooks/useDivergenceWizard.ts"
CTXHOOK="$FE/src/features/composition/hooks/useDerivativeContext.ts"
WIZARD="$FE/src/features/composition/components/DivergenceWizard.tsx"
STEPS="$FE/src/features/composition/components/DivergenceWizardSteps.tsx"
LAUNCH="$FE/src/features/composition/components/DivergenceWizardButton.tsx"
BANNER="$FE/src/features/composition/components/DerivativeBanner.tsx"
BADGE="$FE/src/features/composition/components/GroundingLayerBadge.tsx"
LAYERS="$FE/src/features/composition/components/DerivativeGroundingLayers.tsx"
PANEL="$FE/src/features/composition/components/CompositionPanel.tsx"

# ── 1. api.deriveWork → POST /works/{id}/derive (consumes C23, no new BE) ──
[ -f "$API" ] || fail "composition api.ts not found"
have "$API" "deriveWork" "api missing deriveWork"
have "$API" "/derive" "deriveWork does not POST to the /derive route"
have "$TYPES" "DeriveBody" "types missing DeriveBody"
have "$TYPES" "DivergenceTaxonomy" "types missing DivergenceTaxonomy"
have "$TYPES" "source_work_id" "Work type missing source_work_id (banner needs it)"

# ── 2. 4-step wizard ending in the derive submit ──
[ -f "$WIZHOOK" ] || fail "useDivergenceWizard not found"
have "$WIZHOOK" "deriveWork" "wizard controller does not submit deriveWork"
have "$WIZHOOK" "goNext" "wizard controller missing explicit goNext callback"
have "$WIZHOOK" "goBack" "wizard controller missing explicit goBack callback"
# Step transitions MUST be explicit callbacks — NO useEffect-for-events. There must
# be no useEffect at all in the wizard controller. Strip comments first so the
# explanatory "no useEffect-for-events" prose doesn't trip the gate.
WIZHOOK_CODE="$(sed -E 's#//.*$##; s#/\*.*\*/##' "$WIZHOOK")"
echo "$WIZHOOK_CODE" | grep -q "useEffect" && fail "wizard controller uses useEffect (must transition via explicit callbacks)" || true
[ -f "$STEPS" ] || fail "DivergenceWizardSteps not found"
have "$STEPS" "Step1Source" "step 1 (source/branch) missing"
have "$STEPS" "Step2Type" "step 2 (divergence type) missing"
have "$STEPS" "Step3Overrides" "step 3 (overrides preview) missing"
have "$STEPS" "Step4Name" "step 4 (name) missing"
have "$STEPS" "branchPoint" "step 1 missing the chapter-level branch point control (G3)"
have "$WIZHOOK" "branch_point" "wizard body omits branch_point (G3) from the derive submit"
have "$STEPS" "character_transform" "type selector missing character_transform (genderbend) taxonomy"
have "$STEPS" "pov_shift" "type selector missing pov_shift taxonomy"

# ── 3. wizard step state NOT conditionally unmounted (internal branching) ──
[ -f "$WIZARD" ] || fail "DivergenceWizard not found"
# All four step bodies must stay MOUNTED (CSS hidden), not ternary-unmounted.
have "$WIZARD" "Step1Source" "wizard does not mount Step1Source"
have "$WIZARD" "Step4Name" "wizard does not mount Step4Name"
have "$WIZARD" "hidden" "wizard does not use CSS-hidden internal branching for steps"
# A `{w.step === N ? <A/> : <B/>}` ternary across step bodies would unmount state.
WIZ_CODE="$(sed -E 's#//.*$##; s#/\*.*\*/##' "$WIZARD")"
echo "$WIZ_CODE" | grep -Eq '\?\s*<Step[0-9]' && fail "wizard ternary-unmounts a step body (destroys hook state)" || true

# ── 4. derivative studio banner (source + branch_point) ──
[ -f "$BANNER" ] || fail "DerivativeBanner not found"
have "$BANNER" "derivative-banner" "banner missing its testid"
have "$BANNER" "branchPoint" "banner does not surface the branch_point"
have "$PANEL" "DerivativeBanner" "studio panel does not render the derivative banner"

# ── 5. 2-layer INHERITED/OVERRIDDEN badges + legend (G2, real state) ──
[ -f "$BADGE" ] || fail "GroundingLayerBadge not found"
have "$BADGE" "GroundingLayerLegend" "badge file missing the legend"
have "$BADGE" "data-layer" "badge does not expose its layer (data-layer)"
have "$BADGE" "GroundingLayer" "badge missing the GroundingLayer type"
[ -f "$CTXHOOK" ] || fail "useDerivativeContext not found"
have "$CTXHOOK" "classifyGroundingLayer" "context missing the layer classifier"
have "$CTXHOOK" "'inherited'" "context missing the INHERITED (base) layer literal"
have "$CTXHOOK" "'overridden'" "context missing the OVERRIDDEN (delta) layer literal"
have "$CTXHOOK" "overrideIds" "context does not key the layer off the REAL override set"
[ -f "$LAYERS" ] || fail "DerivativeGroundingLayers not found"
have "$LAYERS" "GroundingLayerBadge" "grounding layers does not render the badge"
have "$LAYERS" "classify" "grounding layers does not classify entities by real override state"

# ── 6. reference spine READ-ONLY, NOT auto-inserted (LOCKED) ──
have "$LAYERS" "reference-spine" "reference spine surfacing missing"
LAYERS_CODE="$(sed -E 's#//.*$##; s#/\*.*\*/##' "$LAYERS")"
echo "$LAYERS_CODE" | grep -Eiq 'insertIntoDraft|onAccept|paste|appendToDraft|insert\(' && fail "reference spine auto-inserts source prose (LOCKED no-auto-insert)" || true

# ── 7. launch entry point in the studio ──
[ -f "$LAUNCH" ] || fail "DivergenceWizardButton not found"
have "$PANEL" "DivergenceWizardButton" "studio panel does not offer the divergence wizard launch"

# ── 8. NO BE schema/API change (C23 owns derive + tables) ──
if git -C "$REPO_ROOT" diff --name-only HEAD 2>/dev/null | grep -E 'services/composition-service/.*(migrat|schema|routers/works\.py|models\.py)' ; then
  fail "C24 must not touch composition-service derive schema/API (C23 owns BE)"
fi

# ── 9. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-24] vitest (wizard + context + banner + badges)"
npx vitest run \
  src/features/composition/hooks/__tests__/useDivergenceWizard.test.tsx \
  src/features/composition/hooks/__tests__/useDerivativeContext.test.tsx \
  src/features/composition/components/__tests__/DivergenceWizard.test.tsx \
  src/features/composition/components/__tests__/DerivativeBanner.test.tsx \
  src/features/composition/components/__tests__/DerivativeGroundingLayers.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -12

audit "verify_cycle_24_passed"
echo "[verify-cycle-24] PASS"
exit 0
