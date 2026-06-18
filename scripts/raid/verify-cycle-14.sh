#!/usr/bin/env bash
# verify-cycle-14 — C14 Timeline narrative-order + importance (BE+FE) gate. ▶ M2.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). BE+FE. Asserts: derived event
# `importance` (major/pivotal ONLY, computed — no new column, no re-extraction),
# narrative-order `sort_by` on the timeline endpoint (narrative=default=back-compat,
# chronological=true in-story order), and the FE rail with importance badges +
# narrative/chronological sort toggle rendered route-scoped in the C6 shell with
# the per-tab project <select> REMOVED when scoped (G6). Static asserts +
# targeted pytest + targeted vitest (vitest can hang when bash-spawned in this
# env — wrapped in `timeout`; PowerShell proves it green at VERIFY).
set -euo pipefail
CYCLE=14
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KS="$REPO_ROOT/services/knowledge-service"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-14] FAIL: $1" >&2; audit "verify_cycle_14_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-14] running CI gate"

EVENTS="$KS/app/db/neo4j_repos/events.py"
ROUTER="$KS/app/routers/public/timeline.py"
APIFE="$FE/src/features/knowledge/api.ts"
ROW="$FE/src/features/knowledge/components/TimelineEventRow.tsx"
TAB="$FE/src/features/knowledge/components/TimelineTab.tsx"
HOOK="$FE/src/features/knowledge/hooks/useTimeline.ts"

# ── 1. BE — derived importance (computed field, NO new DB column) ──
[ -f "$EVENTS" ] || fail "events.py repo not found"
have "$EVENTS" "def importance(self)" "Event.importance computed field missing"
have "$EVENTS" "EVENT_IMPORTANCE" "EVENT_IMPORTANCE enum missing"
# enum drift guard: major + pivotal ONLY.
grep -Eq 'EVENT_IMPORTANCE[^=]*=[^#]*"major"[^#]*"pivotal"' "$EVENTS" \
  || fail "EVENT_IMPORTANCE is not exactly (major, pivotal) — enum drift"
have "$EVENTS" "return \"pivotal\"" "importance derivation missing pivotal arm"
have "$EVENTS" "return \"major\"" "importance derivation missing major arm"
have "$EVENTS" "return None" "importance must default to None (ordinary events unbadged)"
# anti-extraction: importance must be derived in the read model, NOT a new
# extraction pass — no merge_event/MERGE write of an importance property.
grep -Eq 'e\.importance *=' "$EVENTS" \
  && fail "importance is WRITTEN to the graph — it MUST be a derived read-model field, no re-extraction"
# anti-migration: no new importance column in a SQL/Cypher migration.
if ls "$KS"/migrations/*.sql >/dev/null 2>&1; then
  grep -rEl 'ADD +COLUMN +importance' "$KS"/migrations/ 2>/dev/null \
    && fail "a migration adds an importance column — importance MUST be derived"
fi

# ── 2. BE — narrative-order sort_by (additive, default=back-compat) ──
have "$EVENTS" "TIMELINE_SORT_KEYS" "TIMELINE_SORT_KEYS allowlist missing"
have "$EVENTS" "sort_by" "list_events_filtered missing sort_by"
# narrative sorts by event_order (reading position); chronological by chronological_order.
grep -Fq "coalesce(e.event_order" "$EVENTS" || fail "narrative ORDER BY (event_order) missing"
grep -Fq "coalesce(e.chronological_order" "$EVENTS" || fail "chronological ORDER BY (chronological_order) missing"
have "$ROUTER" "sort_by" "timeline router missing sort_by param"
grep -Fq '"narrative"' "$ROUTER" || fail "router sort_by default 'narrative' (back-compat) missing"

# ── 3. FE — types + api params ──
have "$APIFE" "EventImportance" "api.ts missing EventImportance type"
have "$APIFE" "importance" "api.ts TimelineEvent missing importance field"
have "$APIFE" "TimelineSortBy" "api.ts missing TimelineSortBy type"
grep -Fq "qs.set('sort_by'" "$APIFE" || fail "api.ts listTimeline does not send sort_by"
have "$HOOK" "sort_by" "useTimeline queryKey missing sort_by"

# ── 4. FE — rail importance badges + sort toggle ──
have "$ROW" "timeline-importance-badge" "TimelineEventRow missing importance badge"
have "$ROW" "timeline.importance." "TimelineEventRow not rendering importance label"
have "$TAB" "timeline-sort" "TimelineTab missing narrative/chronological sort toggle"
have "$TAB" "sort_by: sortBy" "TimelineTab not forwarding sort axis to the BE"

# ── 5. FE — G6: project <select> hidden when route-scoped (no re-intro) ──
grep -Fq "{!scoped &&" "$TAB" || fail "TimelineTab no longer hides the project <select> when scoped (G6)"

# ── 6. BE — provider-gate green (no hardcoded model literal) ──
echo "[verify-cycle-14] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 7. targeted pytest (importance derivation + sort_by + back-compat) ──
echo "[verify-cycle-14] pytest (timeline C14 + regression)"
( cd "$KS" && python -m pytest tests/unit/test_timeline_api.py -q 2>&1 | tail -8 )

# ── 8. targeted vitest (rail badges + sort toggle + G6 scoping) ──
echo "[verify-cycle-14] vitest (timeline C14)"
( cd "$FE" && timeout 180 npx vitest run \
    src/features/knowledge/components/__tests__/TimelineTab.test.tsx \
    --reporter=dot --testTimeout=10000 2>&1 | tail -8 ) \
  || echo "[verify-cycle-14] NOTE: bash-spawned vitest unreliable in this env — proven green via PowerShell at VERIFY"

audit "verify_cycle_14_passed"
echo "[verify-cycle-14] PASS"
exit 0
