#!/usr/bin/env bash
# verify-cycle-0 — C0 bootstrap (shared FE foundation) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only cycle: static asserts on the
# three deliverables + targeted vitest. Playwright screenshot is filed separately
# (G4 UI smoke) — this gate does not drive a browser.
set -euo pipefail
CYCLE=0
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() {
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
}

fail() { echo "[verify-cycle-0] FAIL: $1" >&2; audit "verify_cycle_0_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }
absent() { grep -Fq "$2" "$1" && fail "$3" || true; }

echo "[verify-cycle-0] running CI gate"

# ── 1. FormDialog: max-height + internal scroll body + pinned (shrink-0) footer ──
FD="$FE/src/components/shared/FormDialog.tsx"
have "$FD" "max-h-[85vh]"     "FormDialog missing max-h cap"
have "$FD" "overflow-y-auto"  "FormDialog body not scrollable"
have "$FD" "flex-shrink-0"    "FormDialog footer/header not pinned (flex-shrink-0)"

# ── 2. Reusable AddModelCta (deep-link + return path) ──
CTA="$FE/src/components/shared/AddModelCta.tsx"
[ -f "$CTA" ] || fail "AddModelCta.tsx missing"
have "$CTA" "/settings/providers" "AddModelCta does not deep-link to the registration surface"
have "$CTA" "return="             "AddModelCta drops the return path"

# ── 3. rerank/reranker reconcile: ONE canonical token = 'rerank' ──
API="$FE/src/features/settings/api.ts"
have "$API" "RERANK_CAPABILITY = 'rerank'" "settings/api missing canonical RERANK_CAPABILITY"
absent "$API" "'reranker'" "settings/api CapabilityType still references divergent 'reranker'"
absent "$FE/src/features/settings/AddModelModal.tsx" "reranker:" "AddModelModal CAP_STYLES still keyed 'reranker'"
have "$FE/src/features/knowledge/components/RerankModelPicker.tsx" "RERANK_CAPABILITY" \
  "RerankModelPicker not wired to the canonical token"
# ProvidersTab honors the round-trip
have "$FE/src/features/settings/ProvidersTab.tsx" "searchParams.get('return')" \
  "ProvidersTab does not honor the AddModelCta return path"

# ── 4. Wiring + component tests green (the spy-injection guard) ──
cd "$FE"
echo "[verify-cycle-0] vitest (RerankModelPicker wiring + AddModelCta)"
npx vitest run \
  src/features/knowledge/components/__tests__/RerankModelPicker.test.tsx \
  src/components/shared/__tests__/AddModelCta.test.tsx \
  --reporter=dot 2>&1 | tail -20

audit "verify_cycle_0_passed"
echo "[verify-cycle-0] PASS"
exit 0
