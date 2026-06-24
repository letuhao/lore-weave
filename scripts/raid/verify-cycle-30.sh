#!/usr/bin/env bash
# verify-cycle-30.sh — L6.F + L6.G admission runtimes (2 DPS).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 30 scope (2 DPS):
#
#   DPS 1 (L6.F — observability admission runtime, Q-L6F-1):
#     * contracts/observability/admission.go — Admission.Inventory() method
#     * pkg/metrics/admission_lib.go         — service-side Lib wrapper
#     * pkg/metrics/admission_lib_test.go
#     * contracts/observability/migration.md — V1→V1+30d runbook
#     * contracts/observability/inventory.yaml — 2 new L6 metrics
#         (lw_metric_admission_warn_total, lw_metric_admission_rejections_total)
#     * tests/integration/admission_v1_warn_test.go — V1 warn vs V1+30d reject
#
#   DPS 2 (L6.G — capacity admission webhook, Q-L6G-1 K8s):
#     * contracts/capacity/override_handler.go     — 24h auto-expire + cache
#     * contracts/capacity/override_handler_test.go
#     * infra/k8s/admission-webhook/capacity_checker.go — Decision logic
#     * infra/k8s/admission-webhook/capacity_checker_test.go
#     * infra/k8s/admission-webhook/deployment.yaml — K8s VWC + service
#     * runbooks/capacity/budget_breach_at_deploy.md
#     * contracts/observability/inventory.yaml — 2 new L6 metrics
#         (lw_capacity_admission_decisions_total, lw_capacity_admission_latency_seconds)
#     * tests/integration/capacity_admission_test.go — 4 decision paths
#
# LOCKED decisions enforced:
#   Q-L6F-1 — V1 → V1+30d transition = time-based flag-flip (admin can flip earlier)
#   Q-L6G-1 — K8s ValidatingWebhookConfiguration (ECS variant V2+)
#   S5 Tier 2 — 24h capacity override auto-expire
#
# Cross-service note (per CLAUDE.md VERIFY rule): cycle 30 touches
# pkg/metrics + contracts/{observability,capacity} + infra/k8s/* +
# tests/integration. All cross-component flow exercised by integration
# tests `TestAdmission_V1WarnAndV1Plus30dReject` +
# `TestCapacityAdmissionWebhook_RejectsAndAdmits`.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-30] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-30] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-30] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# 1. File presence — DPS 1 (L6.F)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    pkg/metrics/go.mod \
    pkg/metrics/admission_lib.go \
    pkg/metrics/admission_lib_test.go \
    contracts/observability/migration.md \
    tests/integration/admission_v1_warn_test.go ; do
    [[ -f "$f" ]] || fail "cycle-30 DPS 1 (L6.F) file missing: $f"
done
pass "L6.F files present (admission lib + migration runbook + integration test)"

# ─────────────────────────────────────────────────────────────────────────
# 2. File presence — DPS 2 (L6.G)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/capacity/override_handler.go \
    contracts/capacity/override_handler_test.go \
    infra/k8s/admission-webhook/go.mod \
    infra/k8s/admission-webhook/capacity_checker.go \
    infra/k8s/admission-webhook/capacity_checker_test.go \
    infra/k8s/admission-webhook/deployment.yaml \
    runbooks/capacity/budget_breach_at_deploy.md \
    tests/integration/capacity_admission_test.go ; do
    [[ -f "$f" ]] || fail "cycle-30 DPS 2 (L6.G) file missing: $f"
done
pass "L6.G files present (override handler + webhook + K8s manifest + runbook + integration test)"

# ─────────────────────────────────────────────────────────────────────────
# 3. Q-L6F-1: time-based flag-flip path documented + runtime SetMode honored
# ─────────────────────────────────────────────────────────────────────────
grep -q 'Q-L6F-1' contracts/observability/migration.md \
    || fail "Q-L6F-1: migration.md must cite the LOCKED Q-ID"
grep -q 'Time-based' contracts/observability/migration.md \
    || fail "Q-L6F-1: migration.md must document time-based flip per LOCKED"
grep -q 'SetMode' pkg/metrics/admission_lib.go \
    || fail "Q-L6F-1: admission_lib.go must reference runtime SetMode flip path"
grep -q 'flag-flip' contracts/observability/migration.md \
    || fail "Q-L6F-1: migration.md must mention flag-flip mechanism"
pass "Q-L6F-1: time-based flag-flip documented + runtime SetMode honored"

# ─────────────────────────────────────────────────────────────────────────
# 4. Q-L6G-1: K8s ValidatingWebhookConfiguration (NOT ECS)
# ─────────────────────────────────────────────────────────────────────────
grep -q 'kind: ValidatingWebhookConfiguration' infra/k8s/admission-webhook/deployment.yaml \
    || fail "Q-L6G-1: deployment.yaml must register a ValidatingWebhookConfiguration"
grep -q 'Q-L6G-1' infra/k8s/admission-webhook/deployment.yaml \
    || fail "Q-L6G-1: deployment.yaml must cite the LOCKED Q-ID"
grep -q 'Q-L6G-1' infra/k8s/admission-webhook/capacity_checker.go \
    || fail "Q-L6G-1: capacity_checker.go must cite the LOCKED Q-ID"
# Defensive: NO ECS-only constructs leak into V1 (S5 Tier 2 says ECS is V2+)
if grep -qE 'awscli|aws-sdk-go|TaskDefinition|service-discovery\.amazonaws' infra/k8s/admission-webhook/*.go infra/k8s/admission-webhook/*.yaml 2>/dev/null; then
    fail "Q-L6G-1: ECS-only constructs detected in K8s webhook (V2+ scope)"
fi
pass "Q-L6G-1: K8s ValidatingWebhookConfiguration (NOT ECS)"

# ─────────────────────────────────────────────────────────────────────────
# 5. S5 Tier 2: 24h override auto-expire
# ─────────────────────────────────────────────────────────────────────────
grep -q 'overrideTTL = 24 \* time.Hour' contracts/capacity/override_handler.go \
    || fail "S5 Tier 2: overrideTTL constant must equal 24h"
grep -q 'S5 Tier 2' contracts/capacity/override_handler.go \
    || fail "S5 Tier 2: override_handler.go must cite the policy"
grep -q 'auto-expire 24h\|24h.*auto-expire\|24h override TTL' runbooks/capacity/budget_breach_at_deploy.md \
    || fail "S5 Tier 2: runbook must document 24h auto-expire"
pass "S5 Tier 2: 24h override auto-expire enforced"

# ─────────────────────────────────────────────────────────────────────────
# 6. Inventory: 4 new L6 metrics declared (admission warn/reject + capacity decisions/latency)
# ─────────────────────────────────────────────────────────────────────────
for m in \
    lw_metric_admission_warn_total \
    lw_metric_admission_rejections_total \
    lw_capacity_admission_decisions_total \
    lw_capacity_admission_latency_seconds ; do
    grep -qE "name: $m\$" contracts/observability/inventory.yaml \
        || fail "inventory.yaml missing $m"
done
pass "inventory.yaml: 4 new L6 admission metrics declared"

# Cycle-30 metrics MUST be shipped_cycle: 30
for m in \
    lw_metric_admission_warn_total \
    lw_metric_admission_rejections_total \
    lw_capacity_admission_decisions_total \
    lw_capacity_admission_latency_seconds ; do
    if ! awk "/name: $m\$/{p=1} p && /shipped_cycle:/{print; exit}" contracts/observability/inventory.yaml | grep -q 'shipped_cycle: 30'; then
        fail "inventory.yaml: $m must have shipped_cycle: 30"
    fi
done
pass "inventory.yaml: 4 new metrics have shipped_cycle: 30"

# ─────────────────────────────────────────────────────────────────────────
# 7. Go build + test — contracts/observability (Admission.Inventory() method)
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd contracts/observability && go vet ./... && go test ./... > /tmp/c30-obs.log 2>&1) \
        || { cat /tmp/c30-obs.log; fail "contracts/observability tests failed"; }
    pass "contracts/observability go vet + test"
else
    note "go absent — skipping observability test"
fi

# ─────────────────────────────────────────────────────────────────────────
# 8. Go build + test — contracts/capacity (override_handler)
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd contracts/capacity && go vet ./... && go test ./... > /tmp/c30-cap.log 2>&1) \
        || { cat /tmp/c30-cap.log; fail "contracts/capacity tests failed"; }
    pass "contracts/capacity go vet + test (incl. override_handler_test)"
fi

# ─────────────────────────────────────────────────────────────────────────
# 9. Go build + test — pkg/metrics (admission lib)
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd pkg/metrics && go vet ./... && go test ./... > /tmp/c30-pkg.log 2>&1) \
        || { cat /tmp/c30-pkg.log; fail "pkg/metrics tests failed"; }
    pass "pkg/metrics go vet + test (admission lib)"
fi

# ─────────────────────────────────────────────────────────────────────────
# 10. Go build + test — infra/k8s/admission-webhook (capacity checker)
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd infra/k8s/admission-webhook && go vet ./... && go test ./... > /tmp/c30-wh.log 2>&1) \
        || { cat /tmp/c30-wh.log; fail "admission-webhook tests failed"; }
    pass "infra/k8s/admission-webhook go vet + test"
fi

# ─────────────────────────────────────────────────────────────────────────
# 11. Integration tests build (regression guard for the new replace entries)
# ─────────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    (cd tests/integration && go build -tags=integration ./... > /tmp/c30-it-build.log 2>&1) \
        || { cat /tmp/c30-it-build.log; fail "tests/integration build (integration tag) failed"; }
    pass "tests/integration build (integration tag) green"

    # Run the 2 new cycle-30 integration tests in isolation (avoid pulling
    # heavyweight live-Postgres tests).
    (cd tests/integration && go test -tags=integration \
        -run 'TestAdmission_V1WarnAndV1Plus30dReject|TestCapacityAdmissionWebhook_RejectsAndAdmits|TestCapacityAdmissionWebhook_OverrideExpiry24h' \
        ./... > /tmp/c30-it.log 2>&1) \
        || { cat /tmp/c30-it.log; fail "cycle-30 integration tests failed"; }
    pass "cycle-30 integration tests PASS (admission warn/reject + 4-decision webhook + 24h override expiry)"
fi

# ─────────────────────────────────────────────────────────────────────────
# 12. ValidatingWebhookConfiguration sanity — failurePolicy + timeoutSeconds
# ─────────────────────────────────────────────────────────────────────────
grep -q 'failurePolicy: Fail' infra/k8s/admission-webhook/deployment.yaml \
    || fail "VWC must have failurePolicy: Fail (cluster blocks deploys when webhook down — load-bearing capacity invariant)"
grep -q 'timeoutSeconds: 5' infra/k8s/admission-webhook/deployment.yaml \
    || fail "VWC must have timeoutSeconds: 5 (well below K8s 30s ceiling, 25s margin for cluster pressure)"
grep -q 'sideEffects: None' infra/k8s/admission-webhook/deployment.yaml \
    || fail "VWC must declare sideEffects: None (webhook is pure)"
grep -q 'admissionReviewVersions: \["v1"\]' infra/k8s/admission-webhook/deployment.yaml \
    || fail "VWC must declare admissionReviewVersions: [v1]"
pass "VWC: failurePolicy=Fail + timeoutSeconds=5 + sideEffects=None + admissionReviewVersions=[v1]"

# ─────────────────────────────────────────────────────────────────────────
# 13. Hot-path discipline — webhook MUST NOT block on DB during admission
# ─────────────────────────────────────────────────────────────────────────
# capacity.OverrideHandler caches 60s — webhook MUST go through this handler.
# Defensive grep: no direct database/sql or pgx imports in the webhook module.
if grep -lE 'database/sql|jackc/pgx|lib/pq' infra/k8s/admission-webhook/*.go 2>/dev/null; then
    fail "hot-path: webhook MUST NOT import a database driver (use capacity.OverrideHandler cache)"
fi
pass "hot-path: webhook does not import DB drivers (uses cached OverrideHandler)"

# ─────────────────────────────────────────────────────────────────────────
# 14. Cross-cycle invariants — cycle-19 contracts NOT regressed
# ─────────────────────────────────────────────────────────────────────────
# Cycle 19 shipped contracts/observability/admission.go::Admission with
# AdmissionWarn=0, AdmissionReject=1, atomic SetMode. Verify those
# constants + method are still exported (signature compatibility).
grep -q 'AdmissionWarn AdmissionMode = iota' contracts/observability/admission.go \
    || fail "cycle-19 invariant: AdmissionWarn constant lost"
grep -q 'AdmissionReject' contracts/observability/admission.go \
    || fail "cycle-19 invariant: AdmissionReject constant lost"
grep -q 'func (a \*Admission) SetMode' contracts/observability/admission.go \
    || fail "cycle-19 invariant: SetMode method lost"
grep -q 'func (a \*Admission) EmitMetric' contracts/observability/admission.go \
    || fail "cycle-19 invariant: EmitMetric method lost"
grep -q 'func (a \*Admission) Inventory' contracts/observability/admission.go \
    || fail "cycle-30 addition: Admission.Inventory() method missing"
pass "cycle-19 admission contract preserved + Inventory() added"

# Cycle 19 capacity.Admission — RegisterService / RemainingBudget intact.
grep -q 'func (a \*Admission) RegisterService' contracts/capacity/budgets_loader.go \
    || fail "cycle-19 invariant: capacity.RegisterService lost"
grep -q 'func (a \*Admission) RemainingBudget' contracts/capacity/budgets_loader.go \
    || fail "cycle-19 invariant: capacity.RemainingBudget lost"
pass "cycle-19 capacity Admission contract preserved"

# ─────────────────────────────────────────────────────────────────────────
# 15. B5 prod-isolation-lint — no edits to infra/existing-prod/
# ─────────────────────────────────────────────────────────────────────────
if [ -d infra/existing-prod ]; then
    if ! git diff --quiet HEAD -- infra/existing-prod/ 2>/dev/null; then
        fail "B5 prod-isolation: infra/existing-prod/ touched"
    fi
fi
pass "B5 prod-isolation-lint (no existing-prod/ edits)"

# ─────────────────────────────────────────────────────────────────────────
# 16. B6 secret-scan — defense against committed credentials
# ─────────────────────────────────────────────────────────────────────────
banned='AKIA[0-9A-Z]\{16,\}\|AIza[0-9A-Za-z_-]\{35,\}\|-----BEGIN [A-Z ]*PRIVATE KEY-----\|api_key=\|password=.\{8,\}'
for f in \
    pkg/metrics/*.go \
    contracts/capacity/override_handler*.go \
    infra/k8s/admission-webhook/*.go \
    infra/k8s/admission-webhook/*.yaml \
    contracts/observability/migration.md \
    runbooks/capacity/budget_breach_at_deploy.md ; do
    [[ -f "$f" ]] || continue
    if grep -qE "$banned" "$f"; then
        fail "B6 secret-scan: $f contains banned pattern"
    fi
done
pass "B6 secret-scan: no banned patterns in cycle-30 files"

# ─────────────────────────────────────────────────────────────────────────
# 17. cycle-7 observability-inventory-lint regression
# ─────────────────────────────────────────────────────────────────────────
if [ -x scripts/observability-inventory-lint.sh ]; then
    if scripts/observability-inventory-lint.sh > /tmp/c30-inv-lint.log 2>&1; then
        pass "scripts/observability-inventory-lint.sh"
    else
        cat /tmp/c30-inv-lint.log
        fail "scripts/observability-inventory-lint.sh"
    fi
else
    note "observability-inventory-lint.sh not executable — skipping (cycle-7 may not have set +x)"
fi

# ─────────────────────────────────────────────────────────────────────────
# 18. cycle-7 capacity-budget-lint regression
# ─────────────────────────────────────────────────────────────────────────
if [ -x scripts/capacity-budget-lint.sh ]; then
    if scripts/capacity-budget-lint.sh > /tmp/c30-cap-lint.log 2>&1; then
        pass "scripts/capacity-budget-lint.sh"
    else
        cat /tmp/c30-cap-lint.log
        fail "scripts/capacity-budget-lint.sh"
    fi
else
    note "capacity-budget-lint.sh not executable — skipping"
fi

# ─────────────────────────────────────────────────────────────────────────
echo
echo "[verify-cycle-30] all $step checks PASS"
exit 0
