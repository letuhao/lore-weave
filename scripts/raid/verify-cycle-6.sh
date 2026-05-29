#!/usr/bin/env bash
# verify-cycle-6.sh — L1.D Migration Orchestrator + L1.I Per-DB Metrics
# Per RAID_WORKFLOW.md §13 (CI gate exit 0 = pass).
#
# Cycle 6 ships:
#   DPS 1 — L1.D migration-orchestrator Go service:
#     services/migration-orchestrator/{go.mod,README.md,cmd/migrate/,
#       pkg/{manifest,runner,canary}}/
#     contracts/migrations/manifest.yaml (references cycle-5 0001_initial)
#     contracts/service_acl/matrix.yaml (L1.D.6 entry, no over-grant)
#     scripts/migration-idempotency-validator.sh
#     tests/integration/migration_run_test.go
#     runbooks/migration/persistent_failure.md
#
#   DPS 2 — L1.I per-db metrics:
#     infra/prometheus/scrape-config.yaml (dynamic file_sd_configs)
#     infra/prometheus/recording-rules.yaml
#     infra/prometheus/alerts/{per-reality,meta}.yaml
#     infra/prometheus/targets/per-reality/README.md (integration hook)
#     infra/postgres-exporter/postgres-exporter.yaml (cardinality controls)
#     contracts/observability/inventory.yaml (cycles 1-6 enumerated)
#     dashboards/{per-reality-health,shard-health}.json
#     tests/integration/metrics_cardinality_test.go
#
# Locked Q-IDs:
#   Q-L1D-1: V1 doc-only manual rollback (no auto-rollback code path).
#   Q-L1I-1: HA pair via federation (external_labels.prom_replica).
#   Q-L1I-2: 30d native Prometheus retention; NO Thanos sidecar.

set -euo pipefail

CYCLE=6
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FAILED=0

audit() {
  mkdir -p "$(dirname "$AUDIT_LOG")"
  echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE${2:+,$2}}" >> "$AUDIT_LOG"
}

step() { echo "[verify-cycle-$CYCLE] === $* ==="; }
fail() { echo "[verify-cycle-$CYCLE] FAIL: $*" >&2; FAILED=1; }
ok()   { echo "[verify-cycle-$CYCLE] ok:   $*"; }

cd "$REPO_ROOT"

# ────────────────────────────────────────────────────────────────────────────────
step "1/12 — required artifacts present (DPS 1 + DPS 2)"
required=(
  # DPS 1 — migration-orchestrator
  "services/migration-orchestrator/go.mod"
  "services/migration-orchestrator/go.sum"
  "services/migration-orchestrator/README.md"
  "services/migration-orchestrator/cmd/migrate/main.go"
  "services/migration-orchestrator/cmd/migrate/main_test.go"
  "services/migration-orchestrator/pkg/manifest/manifest.go"
  "services/migration-orchestrator/pkg/manifest/manifest_test.go"
  "services/migration-orchestrator/pkg/runner/runner.go"
  "services/migration-orchestrator/pkg/runner/runner_test.go"
  "services/migration-orchestrator/pkg/canary/canary.go"
  "services/migration-orchestrator/pkg/canary/canary_test.go"
  "contracts/migrations/manifest.yaml"
  "contracts/service_acl/matrix.yaml"
  "scripts/migration-idempotency-validator.sh"
  "tests/integration/migration_run_test.go"
  "runbooks/migration/persistent_failure.md"

  # DPS 2 — per-db metrics
  "infra/prometheus/scrape-config.yaml"
  "infra/prometheus/recording-rules.yaml"
  "infra/prometheus/alerts/per-reality.yaml"
  "infra/prometheus/alerts/meta.yaml"
  "infra/prometheus/targets/per-reality/README.md"
  "infra/postgres-exporter/postgres-exporter.yaml"
  "contracts/observability/inventory.yaml"
  "dashboards/per-reality-health.json"
  "dashboards/shard-health.json"
  "tests/integration/metrics_cardinality_test.go"
)
for f in "${required[@]}"; do
  if [ -f "$f" ]; then ok "  $f"; else fail "missing: $f"; fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "2/12 — Q-L1D-1 honored (V1 = doc-only manual rollback; NO auto-rollback code)"
# Forbidden patterns in the migration-orchestrator code: any rollback/revert API
forbidden_terms='Rollback|AutoRollback|revert_migration|rollback_migration|MarkRolledBack'
if grep -rEn "$forbidden_terms" services/migration-orchestrator/pkg/ services/migration-orchestrator/cmd/ 2>/dev/null | grep -v _test.go | grep -v 'migration_rolled_back' | grep -v 'rollback' | grep -v '//.*rollback' >/dev/null; then
  matches=$(grep -rEn "$forbidden_terms" services/migration-orchestrator/pkg/ services/migration-orchestrator/cmd/ 2>/dev/null | grep -v _test.go | grep -v 'migration_rolled_back')
  fail "Q-L1D-1 violation — rollback code path found:\n$matches"
else
  ok "no rollback code paths in migration-orchestrator (Q-L1D-1 V1 doc-only)"
fi
# Runbook MUST cite Q-L1D-1
if grep -qE 'Q-L1D-1' runbooks/migration/persistent_failure.md; then
  ok "persistent_failure runbook cites Q-L1D-1"
else
  fail "persistent_failure runbook missing Q-L1D-1 reference"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "3/12 — Q-L1I-1 honored (HA pair via federation — external_labels.prom_replica)"
if grep -qE 'prom_replica:' infra/prometheus/scrape-config.yaml; then
  ok "scrape-config has external_labels.prom_replica (HA federation marker)"
else
  fail "scrape-config missing external_labels.prom_replica (Q-L1I-1)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "4/12 — Q-L1I-2 honored (V1 = 30d native retention; NO Thanos sidecar)"
# Forbidden file paths
for f in infra/thanos/thanos.yaml infra/thanos/sidecar.yaml infra/prometheus/thanos-sidecar.yaml; do
  if [ -f "$f" ]; then
    fail "Q-L1I-2 V1 violation: $f present (V1 = 30d native only; no Thanos)"
  fi
done
# Forbidden config keywords in scrape-config — strip comment lines first
# (comments naming the deferred-to-V1+30d Thanos sidecar are fine; what we
# forbid is an ACTIVE config that references those backends).
active_refs=$(grep -hvE '^\s*#' infra/prometheus/scrape-config.yaml infra/prometheus/recording-rules.yaml infra/prometheus/alerts/*.yaml 2>/dev/null | grep -iE 'thanos|cortex|m3db|mimir' || true)
if [ -n "$active_refs" ]; then
  fail "Q-L1I-2 violation — long-term storage backend in ACTIVE prom config:\n$active_refs"
else
  ok "no active Thanos/Cortex/Mimir refs in prometheus configs"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "5/12 — manifest references cycle-5 per-reality 0001_initial"
if grep -qE 'id:\s+"0001_initial"' contracts/migrations/manifest.yaml; then
  ok "manifest first entry = 0001_initial (cycle 5 skeleton honored)"
else
  fail "manifest first entry NOT 0001_initial"
fi
# Cross-check: 0001 SQL skeleton file exists (cycle 5 carry)
if [ -f contracts/migrations/per_reality/0001_initial.up.sql ]; then
  ok "per_reality/0001_initial.up.sql present (cycle 5 carry verified)"
else
  fail "per_reality/0001_initial.up.sql missing — cycle-5 invariant broken"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "6/12 — service_acl matrix is MINIMUM-needed (no DELETE anywhere)"
if grep -qE 'migration-orchestrator' contracts/service_acl/matrix.yaml; then
  ok "matrix.yaml has migration-orchestrator entry"
else
  fail "matrix.yaml missing migration-orchestrator"
fi
# CRITICAL: no DELETE op on any table (audit append-only + Q-L1D-1 no rollback)
if grep -qE '^\s*-\s*DELETE' contracts/service_acl/matrix.yaml; then
  fail "matrix.yaml has DELETE op — violates Q-L1D-1 V1 (no auto-rollback) + S04 §12T.4 (audit append-only)"
else
  ok "matrix.yaml has no DELETE ops (minimum-needed write set)"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "7/12 — idempotency validator detects non-idempotent SQL"
# Positive: shipped 0001 must pass
if bash scripts/migration-idempotency-validator.sh >/dev/null 2>&1; then
  ok "idempotency-validator passes on shipped 0001_initial"
else
  fail "idempotency-validator FAILED on shipped 0001_initial — should pass"
fi
# Negative: inject a non-idempotent file into a temp dir, validator must reject
tmp_bad=$(mktemp --suffix=.sql)
cat > "$tmp_bad" <<'EOF'
CREATE TABLE foo (id int);
CREATE INDEX foo_idx ON foo (id);
EOF
if bash scripts/migration-idempotency-validator.sh "$tmp_bad" >/dev/null 2>&1; then
  fail "idempotency-validator should REJECT non-idempotent SQL but passed"
else
  ok "idempotency-validator correctly rejects non-idempotent SQL"
fi
rm -f "$tmp_bad"

# ────────────────────────────────────────────────────────────────────────────────
step "8/12 — concurrency-cap + canary + no-rollback tests (Go unit)"
if command -v go >/dev/null 2>&1; then
  (
    cd services/migration-orchestrator
    if go build ./... 2>&1; then ok "go build migration-orchestrator"; else fail "go build migration-orchestrator"; exit 1; fi
    if go vet ./... 2>&1; then ok "go vet migration-orchestrator"; else fail "go vet migration-orchestrator"; exit 1; fi
    if go test ./... 2>&1; then ok "go test migration-orchestrator"; else fail "go test migration-orchestrator"; exit 1; fi
  ) || FAILED=1
else
  echo "[verify-cycle-$CYCLE] note: go CLI absent — skipping Go checks"
fi

# Pin the load-bearing test names exist (defense in depth — regression guard)
for tn in TestConcurrencyCapHoldsAt10 TestRetryExhaustedThenPersistentFailure TestNoAutoRollbackInV1; do
  if grep -qE "func $tn" services/migration-orchestrator/pkg/runner/runner_test.go; then
    ok "runner test present: $tn"
  else
    fail "runner test missing: $tn"
  fi
done
for tn in TestCanary_AppliesToExactlyOneRealityFirst TestCanary_HardWaitNotAsync TestCanary_CanaryFailureAbortsFanout; do
  if grep -qE "func $tn" services/migration-orchestrator/pkg/canary/canary_test.go; then
    ok "canary test present: $tn"
  else
    fail "canary test missing: $tn"
  fi
done

# ────────────────────────────────────────────────────────────────────────────────
step "9/12 — cardinality controls in postgres-exporter (only reality_id + shard_host)"
# Per-reality queries MUST use reality_id as the LABEL and NOT introduce
# query_id / pid / database labels that explode cardinality. Strip comments
# first — the file's own intro comment ENUMERATES forbidden labels for
# documentation purposes.
forbidden_labels='query_id|usage:\s*LABEL.*pid|usage:\s*LABEL.*datname'
active_violations=$(grep -nvE '^\s*#' infra/postgres-exporter/postgres-exporter.yaml | grep -E "$forbidden_labels" || true)
if [ -n "$active_violations" ]; then
  fail "postgres-exporter has high-cardinality label in active config:\n$active_violations"
else
  ok "postgres-exporter has no high-cardinality labels (only reality_id + shard_host per-reality)"
fi
# Must have the audit-table restriction (relname only allowed via IN-list)
if grep -qE 'WHERE relname IN' infra/postgres-exporter/postgres-exporter.yaml; then
  ok "postgres-exporter restricts relname via WHERE IN (cardinality bound)"
else
  fail "postgres-exporter exposes pg_stat_user_tables without restriction"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "10/12 — observability inventory ENUMERATES cycles 1-6 metrics"
inv=contracts/observability/inventory.yaml
# Spot-check: at least one metric from each shipping cycle (1,2,5,6).
# Cycles 3+4 didn't ship Prom-scraped metrics (PII / audit-table writers only).
for cyc in 1 2 5 6; do
  if grep -qE "shipped_cycle:\s*$cyc" "$inv"; then
    ok "inventory has metric(s) from cycle $cyc"
  else
    fail "inventory missing cycle $cyc entries"
  fi
done
# Must declare cardinality budget
if grep -qE '^cardinality_budget:' "$inv"; then
  ok "inventory declares cardinality_budget"
else
  fail "inventory missing cardinality_budget block"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "11/12 — Go integration build (cycle 5 regress + cycle 6 migration/metrics)"
if command -v go >/dev/null 2>&1; then
  (
    cd tests/integration
    if go build -tags=integration ./... 2>&1; then
      ok "go build -tags=integration tests/integration"
    else
      fail "go build -tags=integration tests/integration"; exit 1
    fi
    # Run the new cycle-6 integration tests (mock-only, no infra needed)
    if go test -tags=integration -run "TestMigration|TestCanary|TestInventory|TestCardinality|TestPostgresExp|TestNoThanos" ./... 2>&1; then
      ok "go test -tags=integration (cycle 6 tests)"
    else
      fail "go test -tags=integration (cycle 6 tests)"; exit 1
    fi
  ) || FAILED=1
else
  echo "[verify-cycle-$CYCLE] note: go CLI absent — skipping integration build"
fi

# ────────────────────────────────────────────────────────────────────────────────
step "12/12 — promtool config syntax check (best-effort) + secret-scan"
if command -v promtool >/dev/null 2>&1; then
  if promtool check rules infra/prometheus/recording-rules.yaml infra/prometheus/alerts/per-reality.yaml infra/prometheus/alerts/meta.yaml >/dev/null 2>&1; then
    ok "promtool check rules — recording + alerts"
  else
    fail "promtool check rules failed"
  fi
else
  echo "[verify-cycle-$CYCLE] note: promtool absent — skipping config syntax check (CI must have promtool)"
fi
# B5 prod-isolation-lint
if [ -x scripts/raid/prod-isolation-lint.sh ]; then
  if bash scripts/raid/prod-isolation-lint.sh 2>&1 | tail -5; then
    ok "B5 prod-isolation-lint passed"
  else
    fail "B5 prod-isolation-lint failed"
  fi
fi
# B6 secret-scan
if [ -x scripts/raid/secret-scan-cycle.sh ]; then
  if bash scripts/raid/secret-scan-cycle.sh "$CYCLE" 2>&1 | tail -5; then
    ok "B6 secret-scan passed"
  else
    fail "B6 secret-scan failed (or gitleaks absent on dev — CI gate will run)"
  fi
fi

# ────────────────────────────────────────────────────────────────────────────────
audit "verify_cycle_complete" "\"failed\":$FAILED"

if [ "$FAILED" -ne 0 ]; then
  echo "[verify-cycle-$CYCLE] FAIL: one or more checks failed"
  exit 1
fi
echo "[verify-cycle-$CYCLE] PASS"
exit 0
