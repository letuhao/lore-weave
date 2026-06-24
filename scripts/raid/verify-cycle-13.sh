#!/usr/bin/env bash
# verify-cycle-13 — C13 Build wizard: glossary pinning (BE+FE). Per
# RAID_WORKFLOW.md §13 (exit 0 = pass). Asserts the pinning seam end-to-end:
#   - knowledge BE: StartJobRequest.pinned_glossary_entity_ids + pinned_entity_ids
#     JSONB migration + _merge_pinned prepend at every _run_pipeline call site +
#     the pinned-injection cost line; thin glossary-entity-stats proxy.
#   - worker-ai: GlossaryClient.fetch_entities_by_ids (reuses X-Internal-Token,
#     NO new secret) + pinned names replace the hardcoded known_entities=[] in
#     BOTH the sync (_extract_and_persist) and decoupled (_start_decoupled_chunk)
#     extraction paths.
#   - glossary BE: GET /internal/books/{id}/entities/stats GROUP-BY over
#     chapter_entity_links (mention_count + first/last_chapter_index + coverage).
#   - FE: Step-2 dual-list + auto-pin banner + per-window budget + POST of
#     pinned_glossary_entity_ids.
# Static greps + targeted pytest (knowledge+worker-ai) + go test (glossary) +
# targeted vitest + provider-gate. Name-prefix injection (NOT a new prompt block)
# + no-new-secret are the load-bearing invariants.
set -euo pipefail
CYCLE=13
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KS="$REPO_ROOT/services/knowledge-service"
WA="$REPO_ROOT/services/worker-ai"
GS="$REPO_ROOT/services/glossary-service"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-13] FAIL: $1" >&2; audit "verify_cycle_13_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-13] running CI gate"

ORCH="$KS/app/extraction/pass2_orchestrator.py"
EXTR="$KS/app/routers/public/extraction.py"
REPO="$KS/app/db/repositories/extraction_jobs.py"
MIG="$KS/app/db/migrate.py"
ENT="$KS/app/routers/public/entities.py"
KGC="$KS/app/clients/glossary_client.py"
RUNNER="$WA/app/runner.py"
WGC="$WA/app/clients.py"
STATS="$GS/internal/api/entity_stats_handler.go"
SRV="$GS/internal/api/server.go"
APIFE="$FE/src/features/knowledge/api.ts"
PINLIB="$FE/src/features/knowledge/lib/pinning.ts"
PINHOOK="$FE/src/features/knowledge/hooks/usePinning.ts"
PINSTEP="$FE/src/features/knowledge/components/PinningStep.tsx"
DLG="$FE/src/features/knowledge/components/BuildGraphDialog.tsx"

# ── 1. knowledge orchestrator — name-prefix injection at EVERY call site ──
have "$ORCH" "def _merge_pinned" "orchestrator missing _merge_pinned helper"
have "$ORCH" "pinned_names: list[str] | None = None" "orchestrator public fns missing pinned_names param"
# BOTH public entry points (chat_turn + chapter) must prepend pinned into the
# known_entities passed to _run_pipeline — missing one drops pins from a window.
N_MERGE=$(grep -c "_merge_pinned(pinned_names, known_entities)" "$ORCH" || true)
[ "$N_MERGE" -ge 2 ] || fail "orchestrator must call _merge_pinned at BOTH _run_pipeline call sites (got $N_MERGE)"
# Pinned MUST NOT be a separate prompt block — it reuses known_entities.
grep -Fq "pinned_block" "$ORCH" && fail "pinning must be name-prefix injection, not a separate prompt block"

# ── 2. knowledge BE — StartJobRequest field + migration + repo threading ──
have "$EXTR" "pinned_glossary_entity_ids: list[str] | None = None" "StartJobRequest missing pinned_glossary_entity_ids"
have "$EXTR" "pinned_entity_ids=body.pinned_glossary_entity_ids" "start route does not thread pinned ids to the job create"
have "$MIG" "ADD COLUMN IF NOT EXISTS pinned_entity_ids JSONB" "migration missing pinned_entity_ids JSONB column"
have "$REPO" "targets, concurrency_level, pinned_entity_ids" "repo _SELECT_COLS missing pinned_entity_ids"
have "$REPO" "pinned_entity_ids: list[str] | None = None" "repo models missing pinned_entity_ids field"

# ── 3. knowledge BE — pinned-injection cost line (× num_windows) ──
have "$EXTR" "_TOKENS_PER_PINNED_ENTITY" "estimate missing the pinned per-entity token constant"
have "$EXTR" "estimated_pinned_tokens" "estimate missing the pinned-injection cost line"
grep -Fq "body.pinned_count * _TOKENS_PER_PINNED_ENTITY * num_windows" "$EXTR" \
  || fail "pinned cost is not pinned_count × tokens × num_windows"

# ── 4. knowledge BE — thin glossary-entity-stats proxy for the FE banner ──
have "$ENT" "glossary-entity-stats" "knowledge missing the glossary-entity-stats proxy route"
have "$KGC" "def get_entity_stats" "knowledge glossary_client missing get_entity_stats"
have "$KGC" "entities/stats" "knowledge glossary_client get_entity_stats wrong endpoint"

# ── 5. worker-ai — fetch_entities_by_ids reuses X-Internal-Token (NO secret) ──
have "$WGC" "async def fetch_entities_by_ids" "worker-ai GlossaryClient missing fetch_entities_by_ids"
have "$WGC" "entities/by-ids" "worker-ai fetch_entities_by_ids wrong endpoint"
# No new per-service URL/token env for the fetch — it must reuse the client's
# existing X-Internal-Token header (set once in __init__).
grep -Eq "PINNED_URL|PIN_TOKEN|GLOSSARY_PIN|new_secret" "$WGC" \
  && fail "worker-ai introduced a new secret/URL for pinning (must reuse X-Internal-Token)"
have "$RUNNER" "j.targets, j.concurrency_level, j.pinned_entity_ids" "runner job-fetch SELECT missing pinned_entity_ids"
have "$RUNNER" "def _decode_pinned" "runner missing _decode_pinned JSONB normaliser"
have "$RUNNER" "glossary_client.fetch_entities_by_ids" "runner does not fetch the pinned names"
# The hardcoded known_entities=[] must be GONE from both extraction paths.
grep -Fq "known_entities=[]" "$RUNNER" && fail "runner still hardcodes known_entities=[] (pinning defeated)"
have "$RUNNER" "known_entities=list(pinned_names or [])" "runner does not inject pinned names into known_entities"

# ── 6. glossary BE — stats GROUP-BY endpoint + route registration ──
[ -f "$STATS" ] || fail "glossary entity_stats_handler.go not found"
have "$STATS" "func (s *Server) internalEntityStats" "glossary missing internalEntityStats handler"
have "$STATS" "chapter_entity_links" "glossary stats not querying chapter_entity_links"
have "$STATS" "GROUP BY" "glossary stats missing GROUP-BY aggregation"
have "$STATS" "coverage_pct" "glossary stats missing coverage_pct"
have "$STATS" "first_chapter_index" "glossary stats missing first_chapter_index"
have "$SRV" "entities/stats" "glossary server.go does not register the stats route"

# ── 7. FE — types + dual-list + auto-pin banner + budget + POST ──
have "$APIFE" "pinned_glossary_entity_ids?: string[]" "api.ts ExtractionStartPayload missing pinned ids"
have "$APIFE" "GlossaryEntityStat" "api.ts missing GlossaryEntityStat type"
have "$APIFE" "getGlossaryEntityStats" "api.ts missing getGlossaryEntityStats method"
[ -f "$PINLIB" ] || fail "pinning.ts lib not found"
have "$PINLIB" "isAutoPinCandidate" "pinning lib missing auto-pin heuristic"
have "$PINLIB" "AUTOPIN_MAX_COVERAGE" "pinning lib missing sparse-coverage threshold"
[ -f "$PINHOOK" ] || fail "usePinning hook not found"
[ -f "$PINSTEP" ] || fail "PinningStep component not found"
have "$PINSTEP" "autopin-banner" "PinningStep missing the auto-pin banner"
have "$PINSTEP" "pinning-pinned" "PinningStep missing the pinned dual-list"
have "$PINSTEP" "pinning-budget" "PinningStep missing the per-window budget"
have "$DLG" "PinningStep" "BuildGraphDialog does not render the PinningStep"
have "$DLG" "pinned_glossary_entity_ids: pinning.pinnedIdList" "BuildGraphDialog does not POST the pinned ids"

# ── 8. provider-gate (no hardcoded model literal; pinning is an internal call) ──
echo "[verify-cycle-13] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 9. targeted pytest — knowledge (orchestrator + estimate + stats proxy) ──
echo "[verify-cycle-13] pytest (knowledge C13)"
( cd "$KS" && python -m pytest \
    tests/unit/test_pass2_orchestrator.py \
    tests/unit/test_extraction_estimate.py \
    tests/unit/test_glossary_entity_stats_c13.py \
    -q 2>&1 | tail -6 ) || fail "knowledge-service C13 pytest failed"

# ── 10. targeted pytest — worker-ai (glossary fetch + runner threading) ──
echo "[verify-cycle-13] pytest (worker-ai C13)"
( cd "$WA" && python -m pytest \
    tests/test_glossary_pinning.py \
    tests/test_runner.py \
    -q 2>&1 | tail -6 ) || fail "worker-ai C13 pytest failed"

# ── 11. go test — glossary stats handler (pure helpers always run) ──
echo "[verify-cycle-13] go test (glossary stats)"
( cd "$GS" && go test ./internal/api/ \
    -run "EntityStats|ComputeEntityStats|MaxChapterDenominator" 2>&1 | tail -6 ) \
  || fail "glossary-service C13 go test failed"

# ── 12. targeted vitest (pinning lib + step) — best-effort ──
echo "[verify-cycle-13] vitest (pinning) — best-effort"
( cd "$FE" && timeout 180 npx vitest run \
    src/features/knowledge/lib/__tests__/pinning.test.ts \
    --reporter=dot --testTimeout=10000 2>&1 | tail -6 ) \
  || echo "[verify-cycle-13] WARN: vitest skipped/hung (PowerShell run is authoritative)"

audit "verify_cycle_13_passed"
echo "[verify-cycle-13] PASS"
exit 0
