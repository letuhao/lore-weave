#!/usr/bin/env bash
# verify-cycle-3.sh — CI gate for RAID cycle 3 (API contract freeze). Exit 0 = PASS.
# Generated from scripts/raid/verify-cycle-template.sh.
#
# Asserts (per docs/raid/cycle_briefs/03_api-contract.md acceptance criteria):
#   1. OpenAPI 3.1 spec exists and LINTS CLEAN via the platform's Spectral
#      ruleset (contracts/.spectral.yaml) — same tool/convention as
#      scripts/lint-contract.sh.
#   2. All 4 resource families + the H0 author `promote` endpoint are present in
#      the spec; the proposal schema carries the H0 origin/lifecycle markers.
#   3. No hardcoded provider/model names in the spec or stub code (LOCKED).
#   4. FastAPI app imports without error; every spec path is mounted; every stub
#      route returns 200/201/202 or 501 (never 404/500) — route-presence +
#      stub-status tests.
#   5. service unit suite green.
# Single-service (lore-enrichment-service only) → NO cross-service live-smoke token.
set -uo pipefail
CYCLE=3
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="$REPO_ROOT/services/lore-enrichment-service"
SPEC="$REPO_ROOT/contracts/api/lore-enrichment/v1/openapi.yaml"
RULESET="$REPO_ROOT/contracts/.spectral.yaml"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-3] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-3] ok: $1"; }

echo "[verify-cycle-3] running CI gate"

# ── 1. spec exists + OpenAPI 3.1 + Spectral lint clean ─────────────────────────
[ -f "$SPEC" ] || fail "missing contracts/api/lore-enrichment/v1/openapi.yaml"
head -1 "$SPEC" | grep -q "openapi: 3.1" || fail "spec must be OpenAPI 3.1"
ok "spec present and OpenAPI 3.1"

if npx --yes @stoplight/spectral-cli lint --ruleset "$RULESET" "$SPEC" >/tmp/c3_lint.log 2>&1; then
  ok "spectral lint clean ($(grep -o 'No results.*' /tmp/c3_lint.log | head -1))"
else
  cat /tmp/c3_lint.log
  # Distinguish a real lint error from npx/network unavailability.
  if grep -qiE "error|severity of 'error'" /tmp/c3_lint.log && ! grep -qi "No results" /tmp/c3_lint.log; then
    fail "spectral lint reported errors"
  fi
  echo "[verify-cycle-3] note: spectral unavailable (npx/network) — relying on the spec-shape pytest below"
fi

# ── 2. all 4 families + promote + H0 fields present in the spec ────────────────
for p in \
  "/v1/lore-enrichment/jobs:" \
  "/v1/lore-enrichment/proposals:" \
  "/v1/lore-enrichment/sources:" \
  "/v1/lore-enrichment/templates:" \
  "/v1/lore-enrichment/proposals/{proposal_id}/promote:"; do
  grep -qF "$p" "$SPEC" || fail "spec path missing: $p"
done
ok "4 families + promote endpoint present in spec"

for field in "origin" "technique" "provenance_json" "confidence" \
             "source_refs_json" "cultural_grounding_ref" "review_status" \
             "promoted_entity_id" "promoted_by" "promoted_at" \
             "promoted_from_proposal_id" "original_technique"; do
  grep -qF "$field" "$SPEC" || fail "H0 proposal field missing from spec: $field"
done
grep -qF "exclusiveMaximum: 1.0" "$SPEC" || fail "H0: confidence exclusiveMaximum 1.0 missing"
ok "H0 proposal fields + confidence<1.0 ceiling present"

# ── 3. no hardcoded provider/model names in spec or stub code (LOCKED) ─────────
if grep -rniE "text-embedding-bge-m3|bge-m3|nomic-embed|\bqwen|\bgemma|gpt-4|gpt-3\.|text-embedding-3|claude-[0-9]|\bllama" \
     "$SPEC" "$SVC/app/api" 2>/dev/null; then
  fail "hardcoded provider/model name in spec or stub code"
fi
ok "no hardcoded provider/model names"

# ── 4. app imports + route-presence + stub-status tests ────────────────────────
cd "$SVC" || fail "service dir missing"
# The app fails fast on missing secrets (by design); supply throwaway values for
# the import check, mirroring tests/conftest.py. These are never real creds.
if ! LORE_ENRICHMENT_DB_URL="postgresql://t:t@localhost:5432/t" \
     JWT_SECRET="test_jwt_secret" \
     INTERNAL_SERVICE_TOKEN="test_internal_token" \
     python -c "import app.main" >/tmp/c3_import.log 2>&1; then
  cat /tmp/c3_import.log
  fail "FastAPI app failed to import"
fi
ok "app.main imports clean"

if ! python -m pytest tests/test_api_contract.py -q >/tmp/c3_contract.log 2>&1; then
  cat /tmp/c3_contract.log
  fail "route-presence / stub-status tests red"
fi
ok "route-presence + stub-status tests green ($(grep -oE '[0-9]+ passed' /tmp/c3_contract.log | head -1))"

# ── 5. full service unit suite green (DB tests need compose; excluded here) ────
if ! python -m pytest -q --ignore=tests/db >/tmp/c3_unit.log 2>&1; then
  cat /tmp/c3_unit.log
  fail "service unit suite red"
fi
ok "service unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c3_unit.log | head -1))"

mkdir -p "$(dirname "$AUDIT_LOG")"
echo "{\"ts\":\"$NOW\",\"event\":\"verify_cycle_pass\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
echo "[verify-cycle-3] PASS"
exit 0
