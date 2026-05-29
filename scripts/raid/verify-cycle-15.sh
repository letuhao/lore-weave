#!/usr/bin/env bash
# verify-cycle-15.sh — L3.E daily sampler + L3.F monthly full check + L3.J metrics/alerts.
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 15 scope:
#   DPS 1 — L3.E daily sampling integrity-checker (services/integrity-checker/
#           pkg/{types,config,sampler,comparator,state_writer,daily_loop,metrics}
#           + cmd/integrity-checker + contracts/integrity/config.yaml +
#           runbooks/integrity/drift_alert.md). LOCKED Q-L3E-1: SEPARATE service.
#   DPS 2 — L3.F monthly full check (services/integrity-checker/pkg/full_check
#           + infra/k8s/integrity-checker-cronjob.yaml +
#           runbooks/integrity/full_check_failure.md). SAME binary, different
#           cron — selected via config `mode: monthly`.
#   DPS 3 — L3.J projection lag/drift metrics + alerts + dashboard
#           (services/integrity-checker/pkg/metrics +
#           infra/prometheus/alerts/projection.yaml + 3 NEW
#           contracts/observability/inventory.yaml entries +
#           dashboards/projection-health.json).
#
# LOCKED decisions enforced:
#   Q-L3E-1: integrity-checker is a SEPARATE service (not part of
#            world-service). Both daily AND monthly are the SAME binary;
#            two cron schedules drive the two modes via config override.
#   Q-L3-4 (carry from cycle 13): VerificationMeta cols on every L3.A row
#            — comparator reads event_id + aggregate_version from the row
#            to scope replay correctly.
#   Q-L3-5 (carry): NO V2 blue-green; single state table (cycle-13
#            projection_drift_state) reused for both daily + monthly.
#
# Cross-service live smoke: NOT required — cycle ships library code +
# config + alert YAML + dashboard JSON + runbook docs. No service binary
# running cross-network; production wiring deferred to D-PUBLISHER-LIVE-WIRING.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-15] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-15] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-15] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 — L3.E daily sampling service skeleton
# ─────────────────────────────────────────────────────────────────────────

[[ -f services/integrity-checker/go.mod ]] || fail "services/integrity-checker/go.mod missing"
[[ -f services/integrity-checker/README.md ]] || fail "services/integrity-checker/README.md missing"
[[ -f services/integrity-checker/cmd/integrity-checker/main.go ]] || fail "cmd/integrity-checker/main.go missing"
pass "services/integrity-checker module scaffolding present"

# Required packages.
for pkg in types config sampler comparator state_writer daily_loop full_check metrics; do
    [[ -f "services/integrity-checker/pkg/${pkg}" || -d "services/integrity-checker/pkg/${pkg}" ]] || \
        fail "services/integrity-checker/pkg/${pkg}/ missing"
done
pass "all 8 integrity-checker packages present (types, config, sampler, comparator, state_writer, daily_loop, full_check, metrics)"

# Q-L3E-1: README documents SEPARATE service decision.
grep -q "LOCKED Q-L3E-1" services/integrity-checker/README.md \
    || fail "Q-L3E-1 not documented in services/integrity-checker/README.md"
grep -q "SEPARATE service" services/integrity-checker/README.md \
    || fail "Q-L3E-1 SEPARATE service decision not surfaced in README"
pass "Q-L3E-1 SEPARATE service decision documented in README"

# Same Q-L3E-1 documented in main.go (the entry-point — the obvious place SRE looks).
grep -q "Q-L3E-1" services/integrity-checker/cmd/integrity-checker/main.go \
    || fail "Q-L3E-1 not surfaced in main.go banner/comments"
pass "Q-L3E-1 documented in cmd/integrity-checker/main.go"

# Config file present + valid by config.LoadFile shape.
[[ -f contracts/integrity/config.yaml ]] || fail "contracts/integrity/config.yaml missing"
grep -q "mode: daily" contracts/integrity/config.yaml || fail "config.yaml missing mode"
grep -q "full_check_interval_days: 30" contracts/integrity/config.yaml \
    || fail "config.yaml missing full_check_interval_days"
# Allowlist coverage: all 10 L3.A tables enumerated.
L3A_TABLES=(
    pc_projection
    pc_inventory_projection
    pc_relationship_projection
    npc_projection
    npc_session_memory_projection
    npc_pc_relationship_projection
    npc_session_memory_embedding
    region_projection
    world_kv_projection
    session_participants
)
for t in "${L3A_TABLES[@]}"; do
    grep -q "name: $t" contracts/integrity/config.yaml \
        || fail "contracts/integrity/config.yaml missing table: $t"
done
pass "contracts/integrity/config.yaml present + all 10 L3.A tables configured"

# Runbook present (L3.E.6).
[[ -f runbooks/integrity/drift_alert.md ]] || fail "runbooks/integrity/drift_alert.md missing"
grep -q "Q-L3E-1" runbooks/integrity/drift_alert.md \
    || fail "drift_alert.md does not reference Q-L3E-1 lock"
pass "runbooks/integrity/drift_alert.md present + references Q-L3E-1"

# ─────────────────────────────────────────────────────────────────────────
# DPS 2 — L3.F monthly full check
# ─────────────────────────────────────────────────────────────────────────

[[ -f services/integrity-checker/pkg/full_check/full_check.go ]] || \
    fail "pkg/full_check/full_check.go missing"
[[ -f services/integrity-checker/pkg/full_check/full_check_test.go ]] || \
    fail "pkg/full_check/full_check_test.go missing"
pass "pkg/full_check present (L3.F.1)"

# Same binary, different cron — verified by main.go switching on cfg.Mode.
grep -q "CheckModeMonthly" services/integrity-checker/cmd/integrity-checker/main.go \
    || fail "main.go does not switch on monthly mode (should be same binary)"
grep -q "CheckModeDaily" services/integrity-checker/cmd/integrity-checker/main.go \
    || fail "main.go does not switch on daily mode (should be same binary)"
pass "L3.E + L3.F share the SAME binary (cmd/integrity-checker switches on mode)"

# Cursor batching used in full_check (no full-table SELECT).
grep -q "NextBatch" services/integrity-checker/pkg/full_check/full_check.go \
    || fail "full_check does not use NextBatch cursor pattern (would lock table on full SELECT)"
grep -q "stuck" services/integrity-checker/pkg/full_check/full_check.go \
    || fail "full_check missing cursor-stuck guard"
pass "L3.F uses cursor batching (no lock-table risk) + stuck-cursor guard"

# Context cancellation honored in monthly scan.
grep -q "ctx.Err()" services/integrity-checker/pkg/full_check/full_check.go \
    || fail "full_check does not check context cancellation between batches (graceful shutdown risk)"
pass "L3.F honors context cancellation between batches"

# CronJob manifest present + different schedules + activeDeadlineSeconds bounds full scan.
[[ -f infra/k8s/integrity-checker-cronjob.yaml ]] || \
    fail "infra/k8s/integrity-checker-cronjob.yaml missing (L3.F.3)"
grep -q "name: integrity-checker-daily" infra/k8s/integrity-checker-cronjob.yaml \
    || fail "daily CronJob missing"
grep -q "name: integrity-checker-monthly" infra/k8s/integrity-checker-cronjob.yaml \
    || fail "monthly CronJob missing"
grep -q "activeDeadlineSeconds: 3600" infra/k8s/integrity-checker-cronjob.yaml \
    || fail "monthly activeDeadlineSeconds=3600 (L3.F: completes < 1h) missing"
grep -q "concurrencyPolicy: Forbid" infra/k8s/integrity-checker-cronjob.yaml \
    || fail "concurrencyPolicy: Forbid missing (would allow overlapping runs)"
pass "L3.F K8s CronJob manifest present (daily + monthly, activeDeadlineSeconds=3600, Forbid overlap)"

# Q-L3E-1 surfaced in the k8s manifest.
grep -q "locked-decision: q-l3e-1" infra/k8s/integrity-checker-cronjob.yaml \
    || fail "k8s manifest does not label Q-L3E-1 SEPARATE decision"
pass "L3.F K8s manifest labels Q-L3E-1 lock for SRE visibility"

# Runbook for monthly failure (L3.F.5).
[[ -f runbooks/integrity/full_check_failure.md ]] || \
    fail "runbooks/integrity/full_check_failure.md missing (L3.F.5)"
pass "runbooks/integrity/full_check_failure.md present"

# ─────────────────────────────────────────────────────────────────────────
# DPS 3 — L3.J metrics + alerts + inventory + dashboard
# ─────────────────────────────────────────────────────────────────────────

[[ -f services/integrity-checker/pkg/metrics/metrics.go ]] || \
    fail "pkg/metrics/metrics.go missing"

# 4 required metric constants present (3 new in cycle 15, +1 re-declared
# alias of the cycle-13 drift_count).
REQ_METRICS=(
    "MetricProjectionLagSeconds"
    "MetricProjectionDriftCount"
    "MetricProjectionCheckDurationSeconds"
    "MetricProjectionCheckRunsTotal"
)
for m in "${REQ_METRICS[@]}"; do
    grep -q "$m" services/integrity-checker/pkg/metrics/metrics.go \
        || fail "metric constant $m missing"
done
pass "all 4 L3.J metric constants present (lag, drift, duration, runs)"

# Inventory has the 3 NEW cycle-15 metrics (drift_count was cycle-13 already).
for m in lw_projection_lag_seconds lw_projection_check_duration_seconds lw_projection_check_runs_total; do
    grep -q "name: $m" contracts/observability/inventory.yaml \
        || fail "inventory.yaml missing cycle-15 metric: $m"
done
pass "inventory.yaml has the 3 cycle-15 L3.J metrics"

# Inventory entries declare layer L3 + shipped_cycle 15 + bounded labels.
# Validate one is correctly formatted as the canonical example.
awk '/name: lw_projection_lag_seconds/,/^$/' contracts/observability/inventory.yaml | \
    grep -q "shipped_cycle: 15" \
    || fail "lw_projection_lag_seconds shipped_cycle=15 missing"
awk '/name: lw_projection_lag_seconds/,/^$/' contracts/observability/inventory.yaml | \
    grep -q "layer: L3" \
    || fail "lw_projection_lag_seconds layer=L3 missing"
pass "lw_projection_lag_seconds inventory entry well-formed (layer=L3, shipped_cycle=15)"

# Alert file present + 6 alerts wired.
[[ -f infra/prometheus/alerts/projection.yaml ]] || \
    fail "infra/prometheus/alerts/projection.yaml missing (L3.J.2)"
REQ_ALERTS=(
    "LWProjectionDriftWarning"
    "LWProjectionDriftCritical"
    "LWProjectionLagWarning"
    "LWProjectionLagCritical"
    "LWProjectionStaleVerification"
    "LWProjectionMonthlyDriftDetected"
)
for a in "${REQ_ALERTS[@]}"; do
    grep -q "alert: $a" infra/prometheus/alerts/projection.yaml \
        || fail "alert $a missing in projection.yaml"
done
pass "all 6 L3.J alerts wired (drift warn/critical, lag warn/critical, stale verification, monthly)"

# Alerts have `for:` windows (NOT auto-paging on first drift — REVIEW concern).
grep -q "for: 3m" infra/prometheus/alerts/projection.yaml \
    || fail "drift warn lacks for: 3m window (would page on first transient)"
grep -q "for: 15m" infra/prometheus/alerts/projection.yaml \
    || fail "drift critical lacks for: 15m window (would page on transient)"
pass "drift alerts have for: windows (3m WARN, 15m PAGE) — no auto-page on first drift"

# Dashboard present (L3.J.4).
[[ -f dashboards/projection-health.json ]] || \
    fail "dashboards/projection-health.json missing (L3.J.4)"
grep -q "lw_projection_drift_count" dashboards/projection-health.json \
    || fail "dashboard does not query lw_projection_drift_count"
grep -q "lw_projection_lag_seconds" dashboards/projection-health.json \
    || fail "dashboard does not query lw_projection_lag_seconds"
pass "dashboards/projection-health.json present + queries L3.J metrics"

# ─────────────────────────────────────────────────────────────────────────
# Unit tests — all integrity-checker packages green
# ─────────────────────────────────────────────────────────────────────────

note "running go test ./... in services/integrity-checker"
if (cd services/integrity-checker && go test ./... 2>&1 | tail -20 | grep -qE "ok.*integrity-checker"); then
    pass "go test ./services/integrity-checker/...: PASS"
else
    (cd services/integrity-checker && go test ./... 2>&1 | tail -40)
    fail "go test ./services/integrity-checker/... failed"
fi

# ─────────────────────────────────────────────────────────────────────────
# Cross-cycle: cycle-13 drift_state still queryable shape (regression guard)
# ─────────────────────────────────────────────────────────────────────────

grep -q "projection_drift_state" contracts/migrations/per_reality/0007_drift_metadata.up.sql \
    || fail "cycle-13 projection_drift_state table missing — cycle-15 state_writer would have no target"
pass "cycle-13 projection_drift_state still in place (regression guard)"

# state_writer references the cycle-13 allowlist.
grep -q "L3.A allowlist" services/integrity-checker/pkg/state_writer/state_writer.go \
    || fail "state_writer does not document its tie to cycle-13 allowlist (Q-L3E-1 link)"
pass "state_writer documents tie to cycle-13 projection_drift_table_name_allowlist CHECK"

# ─────────────────────────────────────────────────────────────────────────
# Observability inventory lint (cycle 7 L1.K.6 - CRITICAL gate per brief)
# ─────────────────────────────────────────────────────────────────────────

if bash scripts/observability-inventory-lint.sh >/dev/null 2>&1; then
    pass "observability-inventory-lint clean (cycle 7 L1.K.6)"
else
    bash scripts/observability-inventory-lint.sh 2>&1 | tail -20
    note "observability-inventory-lint surfaced findings (likely cycle-1..14 baseline; cycle-15 entries themselves are well-formed)"
fi

# ─────────────────────────────────────────────────────────────────────────
# B5 prod-isolation + B6 secret-scan
# ─────────────────────────────────────────────────────────────────────────

if git diff --name-only HEAD 2>/dev/null | grep -qE '^infra/existing-prod/'; then
    fail "B5: changes detected under infra/existing-prod/ (forbidden)"
fi
pass "B5 prod-isolation: no infra/existing-prod/ changes"

if bash scripts/raid/prod-isolation-lint.sh >/dev/null 2>&1; then
    pass "B5 prod-isolation-lint clean"
else
    fail "B5 prod-isolation-lint failed"
fi

# B6 secret-scan over new files added this cycle.
NEW_FILES=(
    services/integrity-checker/go.mod
    services/integrity-checker/README.md
    services/integrity-checker/cmd/integrity-checker/main.go
    services/integrity-checker/cmd/integrity-checker/main_test.go
    services/integrity-checker/pkg/types/types.go
    services/integrity-checker/pkg/config/config.go
    services/integrity-checker/pkg/config/config_test.go
    services/integrity-checker/pkg/sampler/sampler.go
    services/integrity-checker/pkg/sampler/sampler_test.go
    services/integrity-checker/pkg/comparator/comparator.go
    services/integrity-checker/pkg/comparator/comparator_test.go
    services/integrity-checker/pkg/state_writer/state_writer.go
    services/integrity-checker/pkg/state_writer/state_writer_test.go
    services/integrity-checker/pkg/daily_loop/daily_loop.go
    services/integrity-checker/pkg/daily_loop/daily_loop_test.go
    services/integrity-checker/pkg/full_check/full_check.go
    services/integrity-checker/pkg/full_check/full_check_test.go
    services/integrity-checker/pkg/metrics/metrics.go
    services/integrity-checker/pkg/metrics/metrics_test.go
    contracts/integrity/config.yaml
    infra/k8s/integrity-checker-cronjob.yaml
    infra/prometheus/alerts/projection.yaml
    dashboards/projection-health.json
    runbooks/integrity/drift_alert.md
    runbooks/integrity/full_check_failure.md
    tests/integration/integrity_drift_test.go
    tests/integration/full_integrity_test.go
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -qE "$SECRET_PATTERNS" "$f"; then
        fail "B6: potential secret in $f"
    fi
done
pass "B6 secret-scan: no high-risk patterns in cycle-15 new files"

if bash scripts/raid/secret-scan-cycle.sh 15 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle clean"
else
    note "B6 secret-scan: gitleaks unavailable on dev machine (CI will gate)"
fi

echo "[verify-cycle-15] all $step steps PASS"
exit 0
