#!/usr/bin/env bash
# verify-cycle-38.sh — L7.K Deploy Pipeline + Canary Controller (FINAL cycle).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 38 scope (1 DPS, inline-built): all 13 L7.K artifacts —
#   CI workflows: .github/workflows/{deploy,lint,canary}.yml
#   canary-controller Go service (canary state machine + cohort_router + controller)
#   admin-cli deploy/break_glass.go (PR-label break-glass workflow)
#   CI lints: scripts/deploy-class-check.sh + scripts/deploy-freeze-check.sh
#   dashboards/deploy-progress.json + 2 runbooks + 2 integration tests
#
# LOCKED decisions enforced:
#   Q-L7K-1 — GitHub Actions V1 only (no ArgoCD; ArgoCD V2+ if multi-cluster).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-38] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-38] step $step FAIL: $1" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────────────
# 1. All 13 L7.K artifact paths present
# ─────────────────────────────────────────────────────────────────────
for f in \
    .github/workflows/deploy.yml \
    .github/workflows/lint.yml \
    .github/workflows/canary.yml \
    services/canary-controller/go.mod \
    services/canary-controller/cmd/canary-controller/main.go \
    services/canary-controller/internal/canary/canary.go \
    services/canary-controller/internal/deployclass/deployclass.go \
    services/canary-controller/internal/cohort_router/cohort_router.go \
    services/canary-controller/internal/controller/controller.go \
    services/canary-controller/pkg/canaryflow/canaryflow.go \
    services/canary-controller/Dockerfile \
    scripts/deploy-class-check.sh \
    scripts/deploy-freeze-check.sh \
    services/admin-cli/commands/deploy/break_glass.go \
    contracts/admin/registry/deploy.yaml \
    dashboards/deploy-progress.json \
    tests/integration/canary_advance_test.go \
    tests/integration/deploy_freeze_test.go \
    runbooks/deploy/canary_abort.md \
    runbooks/deploy/freeze_override.md ; do
    [[ -f "$f" ]] || fail "L7.K artifact missing: $f"
done
pass "all 13 L7.K artifacts present (3 workflows + canary-controller + 2 lint scripts + break-glass + dashboard + 2 integration tests + 2 runbooks)"

# ─────────────────────────────────────────────────────────────────────
# 2. canary-controller — internal/cohort_router subdir present (L7.K.5)
# ─────────────────────────────────────────────────────────────────────
[[ -d services/canary-controller/internal/cohort_router ]] \
    || fail "L7.K.5 internal/cohort_router/ missing"
pass "L7.K.5 internal/cohort_router/ present"

# ─────────────────────────────────────────────────────────────────────
# 3. canary-controller builds + vets clean
# ─────────────────────────────────────────────────────────────────────
( cd services/canary-controller && go build ./... ) || fail "canary-controller build failed"
( cd services/canary-controller && go vet ./... )  || fail "canary-controller vet failed"
pass "canary-controller builds + go vet clean"

# ─────────────────────────────────────────────────────────────────────
# 4. canary-controller unit tests green (state machine + router + controller + class)
# ─────────────────────────────────────────────────────────────────────
( cd services/canary-controller && go test ./... ) || fail "canary-controller unit tests failed"
pass "canary-controller unit tests green (canary + deployclass + cohort_router + controller)"

# ─────────────────────────────────────────────────────────────────────
# 5. admin-cli (L7.K.8 deploy/break_glass) builds + vets + tests
# ─────────────────────────────────────────────────────────────────────
( cd services/admin-cli && go build ./... ) || fail "admin-cli build failed"
( cd services/admin-cli && go vet ./... )  || fail "admin-cli vet failed"
( cd services/admin-cli && go test ./... ) || fail "admin-cli tests failed (incl commands/deploy)"
pass "admin-cli builds + vet + tests green (L7.K.8 deploy/break_glass)"

# ─────────────────────────────────────────────────────────────────────
# 6. Cross-service integration tests (canary advance/abort + deploy freeze)
# ─────────────────────────────────────────────────────────────────────
( cd tests/integration && go build -tags=integration ./... ) || fail "integration test build failed"
( cd tests/integration && go test -tags=integration \
    -run 'TestCanary|TestCohortRouter|TestDeployFreeze|TestDeployClassify' ./... ) \
    || fail "cycle 38 integration tests failed"
pass "integration tests green (canary auto-advance + auto-abort + deploy-freeze block/override)"

# ─────────────────────────────────────────────────────────────────────
# 7. New shell lints: syntax-check + functional smoke
# ─────────────────────────────────────────────────────────────────────
bash -n scripts/deploy-class-check.sh  || fail "deploy-class-check.sh syntax error"
bash -n scripts/deploy-freeze-check.sh || fail "deploy-freeze-check.sh syntax error"

# deploy-class-check: multi-service ⇒ major; declared-mismatch ⇒ exit 1.
printf 'services/a/x.go\nservices/b/y.go\n' > /tmp/vc38_files.txt
cls="$(bash scripts/deploy-class-check.sh --files /tmp/vc38_files.txt | tail -n1)"
[[ "$cls" == "major" ]] || fail "deploy-class-check: multi-service should be major, got '$cls'"
if bash scripts/deploy-class-check.sh --files /tmp/vc38_files.txt --declared patch >/dev/null 2>&1; then
    fail "deploy-class-check: declared/detected mismatch must exit non-zero"
fi
rm -f /tmp/vc38_files.txt

# deploy-freeze-check: burn≥90% blocks; break-glass label overrides.
if bash scripts/deploy-freeze-check.sh --class minor --burn-rate 0.92 --pr-labels "" >/dev/null 2>&1; then
    fail "deploy-freeze-check: burn 0.92 must block (exit 1)"
fi
bash scripts/deploy-freeze-check.sh --class minor --active-freezes scheduled \
    --pr-labels "break-glass-deploy" >/dev/null 2>&1 \
    || fail "deploy-freeze-check: break-glass-deploy label must override a scheduled freeze"
# all 4 freeze types recognised + emergency exempt from slo_burn.
bash scripts/deploy-freeze-check.sh --class emergency --burn-rate 0.99 --pr-labels "emergency" >/dev/null 2>&1 \
    || fail "deploy-freeze-check: emergency must be exempt from slo_burn freeze"
pass "deploy-class-check + deploy-freeze-check: syntax OK + classification/freeze/override/emergency behaviours correct"

# ─────────────────────────────────────────────────────────────────────
# 8. Q-L7K-1 — GitHub Actions V1 only (no ArgoCD USAGE in the new CI).
#    The decision comment ("no ArgoCD; ArgoCD V2+") is allowed; only flag a
#    real ArgoCD reference on a non-comment YAML line (strip leading-# lines).
# ─────────────────────────────────────────────────────────────────────
argo_usage=$(grep -rinE 'argocd|argo-cd|gitops' \
    .github/workflows/deploy.yml .github/workflows/canary.yml .github/workflows/lint.yml 2>/dev/null \
    | grep -vE ':[[:space:]]*#' || true)
if [[ -n "$argo_usage" ]]; then
    echo "$argo_usage" >&2
    fail "Q-L7K-1: ArgoCD/GitOps usage found in new CI workflows (V1 is GitHub Actions only)"
fi
pass "Q-L7K-1: GitHub Actions V1 only — no ArgoCD/GitOps usage in new workflows"

# ─────────────────────────────────────────────────────────────────────
# 9. Existing CI workflows NOT clobbered (game-subtree-ci + lint-foundation)
# ─────────────────────────────────────────────────────────────────────
[[ -f .github/workflows/game-subtree-ci.yml ]] || fail "game-subtree-ci.yml was deleted (must NOT clobber)"
[[ -f .github/workflows/lint-foundation.yml ]] || fail "lint-foundation.yml was deleted (must NOT clobber)"
# lint.yml must be ADDITIVE: it must not redeclare the 15 L1.K lints as its own legs.
if grep -q 'meta-write-discipline-lint' .github/workflows/lint.yml ; then
    fail "lint.yml duplicates an L1.K lint (must be additive; lint-foundation.yml owns the 15)"
fi
grep -q 'lint-foundation.yml' .github/workflows/lint.yml \
    || fail "lint.yml must document its relationship to lint-foundation.yml"
pass "existing workflows intact; lint.yml is additive (references lint-foundation.yml; no L1.K duplication)"

# ─────────────────────────────────────────────────────────────────────
# 10. Canary stage timing (§12AH.4) + 2× abort threshold present in code
# ─────────────────────────────────────────────────────────────────────
for w in '10 \* time.Minute' '30 \* time.Minute' '2 \* time.Hour' '4 \* time.Hour' ; do
    grep -qE "$w" services/canary-controller/internal/canary/canary.go \
        || fail "canary.go missing stage window: $w"
done
grep -q 'BaselineBurnMultiplier = 2.0' services/canary-controller/internal/canary/canary.go \
    || fail "canary.go missing 2× baseline auto-abort threshold (§12AH.4)"
pass "§12AH.4 stage timing (10m/30m/2h/4h) + 2× baseline auto-abort present"

# ─────────────────────────────────────────────────────────────────────
# 11. deploy_audit + reality_registry.deploy_cohort dependency referenced
# ─────────────────────────────────────────────────────────────────────
grep -q 'deploy_audit' services/canary-controller/internal/controller/controller.go \
    || fail "controller must reference deploy_audit (L1.A.6.3 dependency)"
grep -q 'deploy_cohort' services/canary-controller/internal/cohort_router/cohort_router.go \
    || fail "cohort_router must reference reality_registry.deploy_cohort (L1.A dependency)"
pass "consumes deploy_audit (controller) + reality_registry.deploy_cohort (cohort_router)"

# ─────────────────────────────────────────────────────────────────────
# 12. admin command registry still loads (deploy domain added cleanly)
# ─────────────────────────────────────────────────────────────────────
bash scripts/admin-command-registry-lint.sh >/dev/null 2>&1 \
    || fail "admin-command-registry-lint failed after adding deploy.yaml"
grep -q 'domain: deploy' contracts/admin/registry/deploy.yaml \
    || fail "deploy.yaml missing 'domain: deploy'"
grep -q 'break-glass-deploy' services/admin-cli/commands/deploy/break_glass.go \
    || fail "break_glass.go missing break-glass-deploy label constant"
pass "admin-command-registry-lint green; deploy domain + break-glass-deploy label present"

# ─────────────────────────────────────────────────────────────────────
# 13. Dashboard conformance (deploy-progress.json passes the validator)
# ─────────────────────────────────────────────────────────────────────
bash scripts/dashboard-validator.sh >/dev/null 2>&1 \
    || fail "dashboard-validator failed (deploy-progress.json non-conformant)"
pass "dashboard-validator green (deploy-progress.json STANDARDS-conformant)"

# ─────────────────────────────────────────────────────────────────────
# 14. B5 prod-isolation — nothing under infra/existing-prod/ + lint exit 0
# ─────────────────────────────────────────────────────────────────────
if find infra/existing-prod -type f 2>/dev/null | grep -q . ; then
    fail "B5 prod-isolation: files appeared under infra/existing-prod/"
fi
bash scripts/raid/prod-isolation-lint.sh >/dev/null 2>&1 \
    || fail "B5 prod-isolation-lint exited non-zero"
pass "B5 prod-isolation: infra/existing-prod/ untouched + prod-isolation-lint exit 0"

# ─────────────────────────────────────────────────────────────────────
# 15. B6 secret-scan — no high-confidence credential shapes in cycle-38 src
# ─────────────────────────────────────────────────────────────────────
suspicious=$(grep -RnE 'sk-[A-Za-z0-9]{40,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}|xoxb-[A-Za-z0-9-]{20,}|password\s*=\s*"[^$"]{8,}' \
    services/canary-controller \
    services/admin-cli/commands/deploy \
    scripts/deploy-class-check.sh scripts/deploy-freeze-check.sh \
    .github/workflows/deploy.yml .github/workflows/canary.yml .github/workflows/lint.yml \
    2>/dev/null | grep -v '_test.go:' || true)
if [[ -n "$suspicious" ]]; then
    echo "$suspicious" >&2
    fail "B6 secret-scan: suspicious credential shapes in cycle 38 src"
fi
pass "B6 secret-scan: no high-confidence credential shapes in cycle 38 src"

# ─────────────────────────────────────────────────────────────────────
# 16. CYCLE_LOG row 38 exists (PENDING during VERIFY; DONE after SESSION)
# ─────────────────────────────────────────────────────────────────────
grep -qE '^\| 38 \|' docs/raid/CYCLE_LOG.md \
    || fail "CYCLE_LOG.md row 38 missing"
pass "CYCLE_LOG.md row 38 present"

# ─────────────────────────────────────────────────────────────────────
echo "[verify-cycle-38] all ${step} steps PASS — cycle 38 acceptance gate OPEN (L7 layer COMPLETE)"
exit 0
