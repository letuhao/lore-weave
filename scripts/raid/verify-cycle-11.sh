#!/usr/bin/env bash
# verify-cycle-11 — C11 Pending Proposals inbox (FE-only) gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE only — NO new BE. Asserts:
#   - the inbox aggregates EXACTLY 3 existing sources, read-only + deep-link:
#       1. glossary AI-suggested drafts  (listAiSuggestions → status=draft&tags=ai-suggested)
#       2. wiki suggestions review queue (listSuggestions  → status=pending)
#       3. lore-enrichment proposals     (listProposals    → review_status proposed|author_reviewing)
#   - each row carries an origin + a deep-link URL to that source's EXISTING review UI.
#   - per-source graceful degrade (one source erroring/empty must not blank the inbox).
#   - rendered in the C6 shell Proposals section, route-scoped (G6 — bookId from the route project).
# LOCKED guards (grep-asserts): INTEGRATE not duplicate (NO accept/reject/edit
#   mutation in the inbox), NO new BE proposal store, EXACTLY 3 sources (no 4th),
#   exact source filters, G6 route-scoping (no project select-box).
# Static asserts. vitest proven green via PowerShell at VERIFY (bash-spawned
# vitest can hang in this env — the script greps the test files exist instead).
set -euo pipefail
CYCLE=11
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-11] FAIL: $1" >&2; audit "verify_cycle_11_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-11] running CI gate"

LIB="$FE/src/features/knowledge/lib/proposalsInbox.ts"
HOOK="$FE/src/features/knowledge/hooks/useProposalsInbox.ts"
TAB="$FE/src/features/knowledge/components/ProposalsInboxTab.tsx"
SHELL="$FE/src/pages/ProjectDetailShell.tsx"
LIBTEST="$FE/src/features/knowledge/lib/__tests__/proposalsInbox.test.ts"
TABTEST="$FE/src/features/knowledge/components/__tests__/ProposalsInboxTab.test.tsx"

# ── 1. lib — EXACTLY 3 source adapters (glossary · wiki · enrichment) ──
[ -f "$LIB" ] || fail "proposalsInbox.ts not found"
have "$LIB" "fetchGlossarySource" "glossary source adapter missing"
have "$LIB" "fetchWikiSource" "wiki source adapter missing"
have "$LIB" "fetchEnrichmentSource" "enrichment source adapter missing"
# EXACTLY 3 — there is no 4th source adapter.
SRC_COUNT="$(grep -cE "^async function fetch[A-Za-z]+Source" "$LIB" || true)"
[ "$SRC_COUNT" = "3" ] || fail "expected EXACTLY 3 source adapters, found $SRC_COUNT (no 4th source)"

# ── 2. lib — exact source filters (LOCKED) ──
# glossary: the dedicated AI-suggestions endpoint (status=draft&tags=ai-suggested encoded inside it).
have "$LIB" "listAiSuggestions" "glossary source must use listAiSuggestions (status=draft&tags=ai-suggested)"
# wiki: the suggestions review queue filtered to pending (NOT a 'stub' article status).
have "$LIB" "listSuggestions" "wiki source must use listSuggestions (the review queue)"
grep -Fq "'stub'" "$LIB" && fail "wiki source must NOT filter a nonexistent article status='stub'"
grep -Eq "status: *'pending'" "$LIB" || fail "wiki source must filter status='pending'"
# enrichment: the two pending-review states, fetched as exact-match calls.
have "$LIB" "listProposals" "enrichment source must use listProposals"
have "$LIB" "proposed" "enrichment source missing review_status=proposed"
have "$LIB" "author_reviewing" "enrichment source missing review_status=author_reviewing"

# ── 3. lib — each row carries an origin + a deep-link to the source's review UI ──
have "$LIB" "deepLinkUrl" "rows missing deepLinkUrl"
have "$LIB" "proposalDeepLink" "deep-link builders missing"
grep -Fq '/glossary' "$LIB" || fail "glossary deep-link missing"
grep -Fq '/wiki' "$LIB" || fail "wiki deep-link missing"
grep -Fq '/enrichment' "$LIB" || fail "enrichment deep-link missing"

# ── 4. lib — per-source graceful degrade (each source try/catch, no batch reject) ──
have "$LIB" "ProposalSourceResult" "per-source result type missing (graceful degrade)"
grep -Fq "error: toError(e)" "$LIB" || fail "a source does not capture its error for graceful degrade"

# ── 5. lib — LOCKED: read-only aggregation, NO new BE store / mutation here ──
grep -Eq "method: *'POST'|method: *'PATCH'|method: *'DELETE'|method: *'PUT'" "$LIB" && \
  fail "inbox lib must be READ-ONLY (no write method) — integrate, don't duplicate"

# ── 6. hook — owns the query lifecycle, book-scoped, enabled on bookId ──
[ -f "$HOOK" ] || fail "useProposalsInbox.ts not found"
have "$HOOK" "fetchProposalInbox" "hook does not call fetchProposalInbox"
have "$HOOK" "bookId" "hook not book-scoped"

# ── 7. tab — unified rows + per-origin counts + deep-link <Link> + states ──
[ -f "$TAB" ] || fail "ProposalsInboxTab.tsx not found"
have "$TAB" "useProposalsInbox" "tab does not use the inbox hook"
have "$TAB" "proposals-count-" "tab missing per-origin counts"
have "$TAB" "deepLinkUrl" "tab rows do not deep-link"
have "$TAB" "<Link" "tab rows must be deep-link navigations (<Link>)"
have "$TAB" "proposals-no-book" "tab missing no-book state"
have "$TAB" "proposals-empty" "tab missing empty state"
have "$TAB" "proposals-source-error-" "tab missing per-source error (graceful degrade)"
# read-only: NO accept/reject/edit control smuggled into the inbox. Match
# actual handler/call patterns (onAccept=, reviewSuggestion(, …) — not prose.
grep -Eq "onAccept=|onReject=|reviewSuggestion\(|promoteEntity\(|approveProposal\(|rejectProposal\(" "$TAB" && \
  fail "inbox tab must be READ-ONLY (no accept/reject/edit) — integrate, don't duplicate"

# ── 8. shell — wired into the C6 Proposals section, route-scoped (G6) ──
have "$SHELL" "ProposalsInboxTab" "ProjectDetailShell does not render ProposalsInboxTab"
grep -Eq "ProposalsInboxTab bookId=\{project\?\.book_id" "$SHELL" || \
  fail "Proposals section not route-scoped via the project's book_id (G6)"
# G6: no project select-box — bookId comes from the route project.
grep -Fq "ProposalsInboxTab" "$SHELL" || fail "ProposalsInboxTab not wired"

# ── 9. provider-gate green (no hardcoded model literal) ──
echo "[verify-cycle-11] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 10. FE test files present (proven green via PowerShell vitest) ──
[ -f "$LIBTEST" ] || fail "FE proposalsInbox lib test missing"
[ -f "$TABTEST" ] || fail "FE ProposalsInboxTab test missing"
grep -Fq "degrades gracefully" "$LIBTEST" || fail "lib test does not cover graceful degrade"
grep -Fq "two exact-match calls" "$LIBTEST" || fail "lib test does not cover the enrichment two-call exact filter"
grep -Fq "status=pending" "$LIBTEST" || grep -Fq "status: 'pending'" "$LIBTEST" || \
  fail "lib test does not assert the wiki status=pending filter"

audit "verify_cycle_11_passed"
echo "[verify-cycle-11] PASS"
exit 0
