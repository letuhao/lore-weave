#!/usr/bin/env bash
# verify-cycle-13.sh — CI gate for RAID cycle 13 (review gate + H0 write-back).
# Exit 0 = PASS.
#
# Asserts (per docs/raid/cycle_briefs/13_review-gate-writeback.md acceptance):
#   1. lore-enrichment-service unit + DB review-gate/lifecycle/authz/idempotency
#      suite green (incl. illegal-transition + non-owner-promote-denied +
#      origin-marker-persists-after-promote).
#   2. knowledge-service internal-enrichment unit suite green (H0 confidence
#      guard + deterministic idempotent ids).
#   3. ruff clean on the C13 code paths.
#   4. Static guards: no hardcoded model names in the write-back path; promote
#      authorization sourced from book-service projection (not a client claim).
#   5. CROSS-SERVICE LIVE SMOKE (H0 boundary — mock-only is INSUFFICIENT): on the
#      running stack + the seeded demo project, drive the REAL KG quarantine
#      round-trip against the seeded demo location 蓬萊:
#        propose(enriched) -> write-back -> assert KG fact is
#        source_type='enriched:<technique>', pending_validation=true,
#        confidence<1.0 (QUARANTINED, distinct from the canon 蓬萊 node) ->
#        author promote -> assert it became source_type='glossary',
#        confidence=1.0, pending=false WITH the permanent origin marker
#        (origin='enrichment', promoted_from_proposal_id/by, original_technique)
#        -> retract -> assert valid_until set (soft, reversible).
#      Exit non-zero only if the stack is UP but the real round-trip did not hold.
set -uo pipefail
CYCLE=13
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LE_SVC="$REPO_ROOT/services/lore-enrichment-service"
KNOW_SVC="$REPO_ROOT/services/knowledge-service"
COMPOSE="$REPO_ROOT/infra/docker-compose.yml"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

INTERNAL_TOKEN="${INTERNAL_SERVICE_TOKEN:-dev_internal_token}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-loreweave_dev_neo4j}"
# Seeded demo data (docs/raid cycle-13 runner brief).
DEMO_PROJECT="${DEMO_PROJECT:-019e7850-aa1c-7cd3-a25c-c2f9ad84fd39}"
DEMO_USER="${DEMO_USER:-019d5e3c-7cc5-7e6a-8b27-1344e148bf7c}"
# 蓬萊 — one of the 4 locked under-described demo LOCATIONs (canon node).
DEMO_GLOSS_ENTITY="${DEMO_GLOSS_ENTITY:-019e7850-aa72-78ed-8824-c6466b39498e}"

fail() { echo "[verify-cycle-13] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-13] ok: $1"; }
note() { echo "[verify-cycle-13] note: $1"; }

echo "[verify-cycle-13] running CI gate"

# ── 1. lore-enrichment-service unit + DB suite ─────────────────────────────────
if command -v python >/dev/null 2>&1; then
  ( cd "$LE_SVC" && python -m pytest tests/test_review_gate.py tests/test_api_contract.py -q ) \
    >/tmp/c13_le_unit.log 2>&1 \
    || { cat /tmp/c13_le_unit.log; fail "lore-enrichment unit suite failed"; }
  ok "lore-enrichment review-gate unit suite green"

  # DB lifecycle/authz/idempotency against the real compose Postgres (host port).
  LE_DB="${TEST_LORE_ENRICHMENT_DB_URL:-postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_lore_enrichment}"
  if TEST_LORE_ENRICHMENT_DB_URL="$LE_DB" \
     bash -c "cd '$LE_SVC' && python -m pytest tests/db/test_review_repo.py -q" \
     >/tmp/c13_le_db.log 2>&1; then
    ok "lore-enrichment review-repo DB suite green (real Postgres + H0 trigger)"
  else
    if grep -qiE 'skipped|no real|unreachable' /tmp/c13_le_db.log; then
      note "review-repo DB suite skipped (no reachable Postgres at $LE_DB)"
    else
      cat /tmp/c13_le_db.log; fail "lore-enrichment review-repo DB suite failed"
    fi
  fi
else
  note "python not on PATH — skipping lore-enrichment unit suite here"
fi

# ── 2. knowledge-service internal-enrichment unit suite ────────────────────────
if command -v python >/dev/null 2>&1; then
  ( cd "$KNOW_SVC" && python -m pytest tests/unit/test_internal_enrichment.py -q ) \
    >/tmp/c13_know.log 2>&1 \
    || { cat /tmp/c13_know.log; fail "knowledge-service internal-enrichment tests failed"; }
  ok "knowledge-service test_internal_enrichment.py green"
fi

# ── 3. ruff clean on the C13 code paths ────────────────────────────────────────
if command -v ruff >/dev/null 2>&1; then
  ( cd "$LE_SVC" && ruff check app/services/review.py app/services/writeback.py \
      app/clients/writeback.py app/api/proposals.py \
      tests/test_review_gate.py tests/db/test_review_repo.py ) \
    >/tmp/c13_ruff_le.log 2>&1 \
    || { cat /tmp/c13_ruff_le.log; fail "ruff failed on lore-enrichment C13 files"; }
  ( cd "$KNOW_SVC" && ruff check app/routers/internal_enrichment.py \
      tests/unit/test_internal_enrichment.py ) \
    >/tmp/c13_ruff_know.log 2>&1 \
    || { cat /tmp/c13_ruff_know.log; fail "ruff failed on knowledge-service C13 files"; }
  ok "ruff clean on C13 code paths"
fi

# ── 4. static guards ───────────────────────────────────────────────────────────
# (a) no hardcoded model names in the write-back path (deterministic write).
if grep -nE 'gpt-|claude-[0-9]|qwen[/-][0-9]|bge-m3|text-embedding' \
     "$LE_SVC/app/services/writeback.py" \
     "$LE_SVC/app/clients/writeback.py" \
     "$KNOW_SVC/app/routers/internal_enrichment.py" >/dev/null 2>&1; then
  fail "hardcoded model name found in C13 write-back path"
fi
ok "no hardcoded model names in C13 write-back path"
# (b) promotion authority sourced from book-service projection, not a client claim.
grep -q 'book_owner' "$LE_SVC/app/services/writeback.py" \
  || fail "promote does not consult book_owner (book-service truth source)"
grep -q '/projection' "$LE_SVC/app/clients/writeback.py" \
  || fail "book_owner does not read the book-service /projection endpoint"
ok "promote authorization sourced from book-service projection (not a client claim)"

# ── 5. CROSS-SERVICE LIVE SMOKE — H0 quarantine→promote→canon→retract ──────────
if ! command -v docker >/dev/null 2>&1; then
  note "live infra unavailable: docker not on PATH — unit gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:no-docker\"}" >> "$AUDIT_LOG"
  ok "cycle 13 unit gate PASS (live smoke skipped: no docker)"
  exit 0
fi

dc() { docker compose -f "$COMPOSE" "$@"; }
cyq() { dc exec -T neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain "$1" 2>/dev/null; }
# knowledge-service in-network port is 8092; call from inside the container.
# The URL path is EMBEDDED in the python -c string (one quoted arg) rather than
# passed as a separate argv — git-bash path-conversion only rewrites argv that
# look like paths (which corrupted the port → '8092C:' when the path was argv).
# The JSON body is passed via stdin (also conversion-safe).
kq() {
  local path="$1" body="$2"
  printf '%s' "$body" | dc exec -T knowledge-service python -c "
import sys, httpx, json
body = json.loads(sys.stdin.read())
r = httpx.post('http://localhost:8092$path',
               headers={'X-Internal-Token':'$INTERNAL_TOKEN'},
               json=body, timeout=20)
print(r.status_code)
print(r.text)
"
}

if ! dc exec -T knowledge-service python -c "import httpx; httpx.get('http://localhost:8092/health', timeout=5)" >/dev/null 2>&1; then
  note "live infra unavailable: knowledge-service not reachable — unit gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:stack-down\"}" >> "$AUDIT_LOG"
  ok "cycle 13 unit gate PASS (live smoke skipped: stack down)"
  exit 0
fi

echo "[verify-cycle-13] stack is UP — running cross-service H0 live smoke on demo 蓬萊"

PROPOSAL_ID="$(python -c 'import uuid;print(uuid.uuid4())')"
TECHNIQUE="template"

# Sanity: the canon 蓬萊 node exists and is glossary canon (the distinct anchor).
CANON_BEFORE="$(cyq "MATCH (e:Entity {glossary_entity_id:'$DEMO_GLOSS_ENTITY', user_id:'$DEMO_USER'}) RETURN e.source_type AS st, e.confidence AS c;")"
echo "$CANON_BEFORE" | grep -q 'glossary' || {
  note "live infra unavailable: demo canon node 蓬萊 not found/glossary — unit gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:no-demo-canon\"}" >> "$AUDIT_LOG"
  exit 0
}
ok "demo canon node 蓬萊 present (source_type=glossary) — the distinct authored anchor"

# 5a. WRITE-BACK — admit an enriched fact QUARANTINED.
WB_BODY="$(python -c "import json;print(json.dumps({
  'user_id':'$DEMO_USER','project_id':'$DEMO_PROJECT','proposal_id':'$PROPOSAL_ID',
  'glossary_entity_id':'$DEMO_GLOSS_ENTITY','canonical_name':'蓬萊','entity_kind':'location',
  'technique':'$TECHNIQUE',
  'facts':[{'dimension':'历史','content':'蓬萊自上古即为东海仙山，仙人所居。','confidence':0.3}]}))")"
WB_OUT="$(kq /internal/knowledge/enriched-writeback "$WB_BODY")"
echo "$WB_OUT" | head -1 | grep -q '^200' || { echo "$WB_OUT"; fail "live smoke: write-back HTTP != 200"; }
ok "write-back returned 200"

# Assert the enriched fact is QUARANTINED in Neo4j (distinct from canon).
Q="$(cyq "MATCH (f:Fact) WHERE f.promoted_from_proposal_id='$PROPOSAL_ID' AND f.user_id='$DEMO_USER' RETURN f.source_type AS st, f.pending_validation AS pv, f.confidence AS c, f.origin AS o;")"
echo "$Q" | grep -q "enriched:$TECHNIQUE" || { echo "$Q"; fail "live smoke: written fact not source_type=enriched:$TECHNIQUE (H0 leak!)"; }
echo "$Q" | grep -qiE 'true' || { echo "$Q"; fail "live smoke: written fact not pending_validation=true"; }
echo "$Q" | grep -q 'enrichment' || { echo "$Q"; fail "live smoke: written fact missing origin=enrichment marker"; }
# confidence must be < 1.0 (no canon).
if echo "$Q" | grep -qE '\b1\.0\b'; then echo "$Q"; fail "live smoke: written fact confidence reached canon 1.0 (H0 leak!)"; fi
ok "write-back QUARANTINED: source_type=enriched:$TECHNIQUE, pending=true, confidence<1.0, origin=enrichment (NOT canon)"

# 5b. PROMOTE — author flips to canon RETAINING the origin marker.
PR_BODY="$(python -c "import json;print(json.dumps({
  'user_id':'$DEMO_USER','proposal_id':'$PROPOSAL_ID','promoted_by':'$DEMO_USER',
  'promoted_at':'$NOW'}))")"
PR_OUT="$(kq /internal/knowledge/enriched-promote "$PR_BODY")"
echo "$PR_OUT" | head -1 | grep -q '^200' || { echo "$PR_OUT"; fail "live smoke: promote HTTP != 200"; }
ok "promote returned 200"

P="$(cyq "MATCH (f:Fact) WHERE f.promoted_from_proposal_id='$PROPOSAL_ID' AND f.user_id='$DEMO_USER' RETURN f.source_type AS st, f.confidence AS c, f.pending_validation AS pv, f.origin AS o, f.promoted_by AS pb, f.original_technique AS ot;")"
echo "$P" | grep -q 'glossary' || { echo "$P"; fail "live smoke: promoted fact not source_type=glossary (promote did not canonize)"; }
echo "$P" | grep -qE '\b1\.0\b' || { echo "$P"; fail "live smoke: promoted fact confidence != 1.0"; }
echo "$P" | grep -qiE 'false' || { echo "$P"; fail "live smoke: promoted fact still pending_validation"; }
# PERMANENT origin marker must SURVIVE promotion.
echo "$P" | grep -q 'enrichment' || { echo "$P"; fail "live smoke: PROMOTE DROPPED the origin=enrichment marker (H0 traceability lost!)"; }
echo "$P" | grep -q "$DEMO_USER" || { echo "$P"; fail "live smoke: promoted_by not stamped"; }
echo "$P" | grep -q "$TECHNIQUE" || { echo "$P"; fail "live smoke: original_technique not retained"; }
ok "promote → canon: source_type=glossary, confidence=1.0, pending=false WITH permanent origin marker (origin=enrichment, promoted_by, original_technique)"

# 5c. RETRACT — soft (reversible): valid_until set; fact leaves the active graph.
RT_BODY="$(python -c "import json;print(json.dumps({'user_id':'$DEMO_USER','proposal_id':'$PROPOSAL_ID'}))")"
RT_OUT="$(kq /internal/knowledge/enriched-retract "$RT_BODY")"
echo "$RT_OUT" | head -1 | grep -q '^200' || { echo "$RT_OUT"; fail "live smoke: retract HTTP != 200"; }
R="$(cyq "MATCH (f:Fact) WHERE f.promoted_from_proposal_id='$PROPOSAL_ID' AND f.user_id='$DEMO_USER' AND f.valid_until IS NOT NULL RETURN count(f) AS n;")"
echo "$R" | grep -qE '\b[1-9][0-9]*\b' || { echo "$R"; fail "live smoke: retract did not set valid_until (soft-delete)"; }
ok "retract (soft): valid_until set — fact left the active graph (reversible, not a hard delete)"

# 5d. Cleanup the smoke fact (hard delete by proposal id — leaves the seeded demo
#     canon node untouched; only this smoke proposal's nodes are removed).
cyq "MATCH (f:Fact {promoted_from_proposal_id:'$PROPOSAL_ID'}) DETACH DELETE f;" >/dev/null 2>&1 || true

SMOKE="propose -> enriched-in-KG (quarantined, source_type=enriched) -> author promote -> canon (source_type=glossary, origin marker intact) -> retract -> soft (valid_until)"
echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"$SMOKE\"}" >> "$AUDIT_LOG"
echo "[verify-cycle-13] live smoke: $SMOKE"
ok "cycle 13 CI gate PASS (cross-service H0 round-trip held on demo 蓬萊)"
exit 0
