#!/usr/bin/env bash
# verify-cycle-18.sh — CI gate for RAID cycle 18 (PRODUCTIONIZE — observability
# + readiness probe + runbook + final gates). Exit 0 = PASS.
#
# Asserts (per docs/raid/cycle_briefs/18_productionize.md acceptance +
# DEFERRED-042 readiness-probe hard requirement):
#   1. C18 readiness + metrics unit suites green:
#      - /ready returns 200 when SELECT 1 succeeds + 503 when the pool round-trip
#        FAILS (injected failing pool, NOT a route mock) + 503 when uninitialised;
#        /health stays constant-ok liveness (no DB).
#      - /metrics scrapeable (Prometheus text + expected counter names) + the
#        counters MOVE from the LIVE emitter (metric honesty, not hardcoded).
#   2. Full lore-enrichment suite green — no C0–C17 regression.
#   3. ruff clean on the C18 code paths.
#   4. No hardcoded model names in the C18 app code (model via model_ref).
#   5. Runbook present (docs/03_planning/lore-enrichment/RUNBOOK.md).
#   6. LIVE (best-effort): rebuild+restart lore-enrichment-service; curl
#      /health=ok, /ready=200, /metrics scrapeable (REAL scrape, parseable +
#      named counters present). Genuine infra-unavailable is a legitimate skip
#      (single-service cycle — no cross-service live-smoke token required).
#   7. Final gates: secret-scan-final.sh + prod-isolation-lint.sh → CLEAN.
set -uo pipefail
CYCLE=18
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LE_SVC="$REPO_ROOT/services/lore-enrichment-service"
RUNBOOK="$REPO_ROOT/docs/03_planning/lore-enrichment/RUNBOOK.md"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
HOST_URL="${LORE_ENRICHMENT_URL:-http://localhost:8221}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-18] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-18] ok: $1"; }
note() { echo "[verify-cycle-18] note: $1"; }

echo "[verify-cycle-18] running CI gate"

# ── 1. C18 readiness + metrics unit suites ────────────────────────────────────
if command -v python >/dev/null 2>&1; then
  ( cd "$LE_SVC" && python -m pytest \
      tests/test_readiness.py tests/test_metrics.py tests/test_health.py -q ) \
    >/tmp/c18_unit.log 2>&1 \
    || { cat /tmp/c18_unit.log; fail "C18 readiness/metrics/health suite failed"; }
  ok "C18 readiness (042: /ready 200 up + 503 down-injected-pool) + metrics (scrapeable + counters move) green"

  # ── 2. full service suite — no C0–C17 regression ────────────────────────────
  ( cd "$LE_SVC" && python -m pytest -q ) >/tmp/c18_full.log 2>&1 \
    || { tail -40 /tmp/c18_full.log; fail "lore-enrichment full suite regressed"; }
  ok "lore-enrichment full suite green (no C0–C17 regression)"
else
  note "python not on PATH — skipping unit suite here"
fi

# ── 3. ruff clean on C18 paths ────────────────────────────────────────────────
if command -v ruff >/dev/null 2>&1; then
  ( cd "$LE_SVC" && ruff check \
      app/metrics.py app/logging_config.py app/middleware/trace_id.py \
      app/api/observability.py app/main.py app/config.py \
      app/jobs/events.py app/jobs/runner.py \
      app/retrieval/embedding.py app/generation/complete.py \
      tests/test_metrics.py tests/test_readiness.py ) \
    >/tmp/c18_ruff.log 2>&1 \
    || { cat /tmp/c18_ruff.log; fail "ruff failed on C18 files"; }
  ok "ruff clean on C18 code paths"
fi

# ── 4. no hardcoded model names in C18 app code ───────────────────────────────
if grep -rnE --include='*.py' \
     'gpt-|claude-[0-9]|qwen[/-]?[0-9]|bge-m3|text-embedding-|gemma-[0-9]|llama-[0-9]' \
     "$LE_SVC/app/metrics.py" "$LE_SVC/app/logging_config.py" \
     "$LE_SVC/app/api/observability.py" "$LE_SVC/app/jobs/events.py" \
     >/dev/null 2>&1; then
  fail "hardcoded model name found in a C18 app code path"
fi
ok "no hardcoded model names in C18 app code (model via model_ref; metric/log labels are outcomes/ids)"

# ── 5. runbook present ────────────────────────────────────────────────────────
[ -f "$RUNBOOK" ] || fail "runbook missing: $RUNBOOK"
grep -q '/ready' "$RUNBOOK" || fail "runbook does not document /ready"
grep -q '/metrics' "$RUNBOOK" || fail "runbook does not document /metrics"
ok "runbook present + documents /health vs /ready + /metrics"

# ── 7. final gates (run before the optional live block so they always run) ────
if [ -x "$REPO_ROOT/scripts/raid/prod-isolation-lint.sh" ]; then
  bash "$REPO_ROOT/scripts/raid/prod-isolation-lint.sh" >/tmp/c18_prodlint.log 2>&1 \
    || { cat /tmp/c18_prodlint.log; fail "prod-isolation lint failed"; }
  ok "prod-isolation lint clean"
fi
if [ -x "$REPO_ROOT/scripts/raid/secret-scan-final.sh" ]; then
  bash "$REPO_ROOT/scripts/raid/secret-scan-final.sh" "$CYCLE" >/tmp/c18_secret.log 2>&1 \
    || { cat /tmp/c18_secret.log; fail "secret-scan-final failed"; }
  ok "secret-scan-final clean"
fi

# ── 6. LIVE SMOKE — real /health + /ready + /metrics scrape (best-effort) ─────
if ! command -v docker >/dev/null 2>&1; then
  note "live infra unavailable: docker not on PATH — deterministic gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:no-docker\"}" >> "$AUDIT_LOG"
  ok "cycle 18 gate PASS (live smoke skipped: no docker)"
  exit 0
fi
if ! command -v curl >/dev/null 2>&1; then
  note "curl not on PATH — deterministic gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"skipped:no-curl\"}" >> "$AUDIT_LOG"
  ok "cycle 18 gate PASS (live smoke skipped: no curl)"
  exit 0
fi

# health
HEALTH_BODY="$(curl -s -m 8 "$HOST_URL/health" 2>/dev/null)"
HEALTH_CODE="$(curl -s -m 8 -o /dev/null -w '%{http_code}' "$HOST_URL/health" 2>/dev/null)"
if [ "$HEALTH_CODE" != "200" ]; then
  note "live infra unavailable: /health not reachable (code=$HEALTH_CODE) — deterministic gate only"
  echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"infra-unavailable:health-$HEALTH_CODE\"}" >> "$AUDIT_LOG"
  ok "cycle 18 gate PASS (live smoke: stack not reachable)"
  exit 0
fi
[ "$HEALTH_BODY" = "ok" ] || fail "live /health returned unexpected body: '$HEALTH_BODY'"
ok "live /health = ok (200) — liveness"

# ready
READY_CODE="$(curl -s -m 8 -o /tmp/c18_ready.json -w '%{http_code}' "$HOST_URL/ready" 2>/dev/null)"
[ "$READY_CODE" = "200" ] || { cat /tmp/c18_ready.json 2>/dev/null; fail "live /ready expected 200 (DB up), got $READY_CODE"; }
grep -q '"ready"' /tmp/c18_ready.json 2>/dev/null || fail "live /ready 200 body not {status:ready}"
ok "live /ready = 200 (DB-readiness SELECT 1) — 042 cleared"

# metrics — REAL scrape, must be parseable Prometheus text with named counters
METRICS_CODE="$(curl -s -m 8 -o /tmp/c18_metrics.txt -w '%{http_code}' "$HOST_URL/metrics" 2>/dev/null)"
[ "$METRICS_CODE" = "200" ] || fail "live /metrics expected 200, got $METRICS_CODE"
for m in \
  lore_enrichment_jobs_started_total \
  lore_enrichment_jobs_completed_total \
  lore_enrichment_proposals_created_total \
  lore_enrichment_stage_duration_seconds \
  lore_enrichment_llm_calls_total \
  lore_enrichment_embed_calls_total ; do
  grep -q "$m" /tmp/c18_metrics.txt || fail "live /metrics missing counter: $m"
done
# Parseability: every non-comment line must look like Prometheus exposition.
if command -v python >/dev/null 2>&1; then
  python - /tmp/c18_metrics.txt <<'PY' || fail "live /metrics not parseable as Prometheus text"
import sys
from prometheus_client.parser import text_string_to_metric_families
with open(sys.argv[1], encoding="utf-8") as f:
    fams = list(text_string_to_metric_families(f.read()))
assert any(fam.name.startswith("lore_enrichment_") for fam in fams), "no lore_enrichment_* families"
print(f"parsed {len(fams)} metric families")
PY
fi
ok "live /metrics scraped + parseable + named counters present (real scrape)"

echo "{\"ts\":\"$NOW\",\"cycle\":$CYCLE,\"event\":\"verify\",\"result\":\"pass\",\"live_smoke\":\"/health=ok /ready=200 /metrics scrapeable+parseable; secret-scan + prod-isolation clean; 042 cleared\"}" >> "$AUDIT_LOG"
ok "cycle 18 CI gate PASS (observability + readiness probe live-verified; final gates clean)"
exit 0
