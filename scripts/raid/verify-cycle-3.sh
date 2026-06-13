#!/usr/bin/env bash
# verify-cycle-3 — C3 rerank connection test (BE+FE) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). Cross-service: provider-registry
# rerank-aware verify (real /v1/rerank via provider.Rerank, BYOK credential) +
# EditModelModal Test rendering. Live-smoke recorded separately (backend down).
set -euo pipefail
CYCLE=3
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PR="$REPO_ROOT/services/provider-registry-service"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-3] FAIL: $1" >&2; audit "verify_cycle_3_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-3] running CI gate"

SRV="$PR/internal/api/server.go"
# ── 1. rerank-aware verify present, via the canonical provider.Rerank gateway ──
have "$SRV" "func (s *Server) verifyRerank" "server.go missing verifyRerank"
have "$SRV" "provider.Rerank("            "verifyRerank must call the canonical provider.Rerank gateway path"
grep -Eq 'case "rerank":' "$SRV" || fail "verify switch missing rerank case"
# detectPrimaryCapability recognizes rerank
grep -Eq '"video_gen", "rerank"' "$SRV" || fail "detectPrimaryCapability does not include rerank"

# ── 2. no per-service rerank URL/token env read (D-RERANK-NOT-BYOK), excl gateway ──
if grep -rEn 'Getenv\("RERANK_(URL|MODEL|SERVICE_TOKEN)"' "$REPO_ROOT/services" --include='*.go' \
   | grep -v '_test.go' | grep -v 'provider-registry-service' >/dev/null 2>&1; then
  fail "per-service RERANK_URL/MODEL/TOKEN env read detected (must be a BYOK credential)"
fi

# ── 3. FE EditModelModal renders the rerank Test result ──
have "$FE/src/features/settings/EditModelModal.tsx" "verify_ok_rerank" \
  "EditModelModal does not render the rerank Test result (scores)"

# ── 4. Go rerank-verify tests green ──
echo "[verify-cycle-3] go test (rerank verify)"
go test -C "$PR" ./internal/api/ -run 'Rerank|DetectPrimaryCapability' -count=1 2>&1 | tail -8

audit "verify_cycle_3_passed"
echo "[verify-cycle-3] PASS"
exit 0
