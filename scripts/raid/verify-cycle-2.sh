#!/usr/bin/env bash
# verify-cycle-2 — C2 rerank discovery (BE+FE) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). Cross-service: provider-registry Go
# inventory parser (Cohere/OpenAI/LM Studio rerank detection, canonical token) +
# FE setup guidance. Live-smoke recorded separately (local-rerank backend down).
set -euo pipefail
CYCLE=2
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PR="$REPO_ROOT/services/provider-registry-service"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-2] FAIL: $1" >&2; audit "verify_cycle_2_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-2] running CI gate"

ADP="$PR/internal/provider/adapters.go"
# ── 1. rerank discovery present, canonical token (no divergent 'reranker') ──
have "$ADP" 'parseCohereModels'           "adapters.go missing Cohere-shape parser"
grep -Eq 'strings\.Contains\(id, "rerank"\)' "$ADP" || fail "classifyOpenAIModel missing rerank case"
# the LM Studio parser must no longer tag the divergent 'reranker'
grep -Fq 'cap = "reranker"' "$ADP" && fail "divergent 'reranker' capability still tagged in adapters.go" || true

# ── 2. FE setup guidance (discovery path) ──
have "$FE/src/features/knowledge/components/RerankModelPicker.tsx" "rerankDiscoveryHint" \
  "FE rerank setup-guidance (discovery hint) missing"

# ── 3. NO per-service rerank URL/token env regression (D-RERANK-NOT-BYOK) ──
# Flag only ACTUAL env reads of a rerank backend (Getenv("RERANK_URL"/MODEL/SERVICE_TOKEN))
# in CONSUMING services. provider-registry-service is the gateway (its `RERANK_MODEL_*`
# strings are API error codes, not env) so it's excluded.
if grep -rEn 'Getenv\("RERANK_(URL|MODEL|SERVICE_TOKEN)"' "$REPO_ROOT/services" --include='*.go' \
   | grep -v '_test.go' | grep -v 'provider-registry-service' >/dev/null 2>&1; then
  fail "per-service RERANK_URL/MODEL/TOKEN env read detected (must be a provider-registry BYOK credential)"
fi

# ── 4. Go inventory-parser tests green ──
echo "[verify-cycle-2] go test (rerank discovery)"
go test -C "$PR" ./internal/provider/ -run 'Rerank|Cohere|Classify|LMStudioNative' -count=1 2>&1 | tail -8

audit "verify_cycle_2_passed"
echo "[verify-cycle-2] PASS"
exit 0
