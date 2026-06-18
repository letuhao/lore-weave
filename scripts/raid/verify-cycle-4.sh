#!/usr/bin/env bash
# verify-cycle-4 — C4 Book picker (FE) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only: reusable BookPicker emits
# book_id (empty valid) + both raw call-sites swapped (ProjectFormModal +
# campaign step). Targeted vitest.
set -euo pipefail
CYCLE=4
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-4] FAIL: $1" >&2; audit "verify_cycle_4_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-4] running CI gate"

# ── 1. BookPicker exists + emits book_id (uses booksApi.listBooks, reused as-is) ──
BP="$FE/src/components/shared/BookPicker.tsx"
[ -f "$BP" ] || fail "BookPicker.tsx missing"
have "$BP" "booksApi.listBooks" "BookPicker must search via booksApi.listBooks"
have "$BP" "onChange(b.book_id)" "BookPicker must emit book_id"

# ── 2. both call sites swapped (the campaign step is the easy miss) ──
PFM="$FE/src/features/knowledge/components/ProjectFormModal.tsx"
have "$PFM" "<BookPicker" "ProjectFormModal not swapped to BookPicker"
grep -Eq 'type="text"[^>]*value=\{bookId\}' "$PFM" && fail "raw-UUID book_id input still present in ProjectFormModal" || true
BPS="$FE/src/features/campaigns/components/steps/BookProjectStep.tsx"
have "$BPS" "<BookPicker" "campaign BookProjectStep not swapped to BookPicker"

# ── 3. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-4] vitest (BookPicker)"
npx vitest run src/components/shared/__tests__/BookPicker.test.tsx --reporter=dot 2>&1 | tail -12

audit "verify_cycle_4_passed"
echo "[verify-cycle-4] PASS"
exit 0
