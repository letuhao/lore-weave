#!/usr/bin/env bash
# verify-cycle-1 — C1 rerank registration (FE) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only cycle: static asserts that
# the register form offers `rerank` via the canonical token + i18n labels in all
# locales + the empty-state register CTA, then targeted vitest.
set -euo pipefail
CYCLE=1
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() {
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
}
fail() { echo "[verify-cycle-1] FAIL: $1" >&2; audit "verify_cycle_1_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-1] running CI gate"

# ── 1. rerank is a registerable capability via the canonical token (not a literal) ──
CF="$FE/src/features/settings/CapabilityFlags.tsx"
have "$CF" "RERANK_CAPABILITY" "CapabilityFlags does not register rerank via the canonical RERANK_CAPABILITY token"

# ── 2. i18n label capability.flag.rerank present in ALL locales ──
for loc in en ja vi zh-TW; do
  grep -Fq '"rerank"' "$FE/src/i18n/locales/$loc/settings.json" \
    || fail "settings locale $loc missing the capability.flag.rerank label"
done

# ── 3. empty-state register CTA wired into the rerank picker (BL-1, in-flow register) ──
have "$FE/src/features/knowledge/components/RerankModelPicker.tsx" "AddModelCta" \
  "RerankModelPicker empty-state does not offer the in-flow register CTA"

# ── 4. targeted vitest green (register-form + picker wiring + C0 reconcile guard) ──
cd "$FE"
echo "[verify-cycle-1] vitest (CapabilityFlags + RerankModelPicker)"
npx vitest run \
  src/features/settings/__tests__/CapabilityFlags.test.tsx \
  src/features/knowledge/components/__tests__/RerankModelPicker.test.tsx \
  --reporter=dot 2>&1 | tail -20

audit "verify_cycle_1_passed"
echo "[verify-cycle-1] PASS"
exit 0
