#!/usr/bin/env bash
# verify-cycle-35.sh — L7.B + L7.C Runbook library + On-call rotation.
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 35 scope (2 DPS):
#
#   DPS 1 (L7.B — SRE Runbook Library, SR3 27-runbook gate):
#     * docs/sre/runbooks/README.md
#     * docs/sre/runbooks/TEMPLATE.md
#     * docs/sre/runbooks/INDEX.md (auto-generated)
#     * 27 runbooks across 11 subsystems (auth/ws/meta/publisher/projection/
#       llm-provider/canon/admin/reality/deploy/capacity) — STUBS OK per Q-L7B-1
#     * scripts/runbook-index-generator.sh
#     * scripts/runbook-verification-lint.sh
#     * scripts/runbook-drift-check.sh
#     * infra/external-access-docs/README.md
#
#   DPS 2 (L7.C — On-call Rotation + Escalation Infrastructure):
#     * infra/pagerduty/README.md
#     * infra/pagerduty/services.yaml         (5 services match cycle-34 channels.yaml)
#     * infra/pagerduty/rotation_schedule.yaml (V1 solo + V1+30d 2-person + V2+ 4-person)
#     * infra/pagerduty/escalation_policy.yaml (5 policies, 3 layers each)
#     * infra/pagerduty/main.tf                (Terraform skeleton)
#     * infra/alertmanager/oncall_routing_extension.yaml (cross-cycle wiring doc)
#     * docs/sre/oncall-handoffs/README.md
#     * docs/sre/oncall-handoffs/TEMPLATE.md
#     * runbooks/oncall/handoff_missed.md
#     * runbooks/oncall/escalation_to_founder.md
#     * tests/integration/escalation_test.go
#
# LOCKED decisions enforced:
#   Q-L7B-1 — 27 runbooks present (stubs OK with last_verified=1970-01-01 + method=stub)
#   Q-L7C-1 — PagerDuty V1 (5 services + escalation policies + rotation)
#   Q-L7C-2 — Internal SLA only (docs/governance/oncall-sla.md from cycle 34)

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-35] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-35] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-35] note: $1"; }

# ─────────────────────────────────────────────────────────────────────
# 1. DPS 1 — L7.B library infrastructure files present
# ─────────────────────────────────────────────────────────────────────
for f in \
    docs/sre/runbooks/README.md \
    docs/sre/runbooks/TEMPLATE.md \
    docs/sre/runbooks/INDEX.md \
    scripts/runbook-index-generator.sh \
    scripts/runbook-verification-lint.sh \
    scripts/runbook-drift-check.sh \
    infra/external-access-docs/README.md ; do
    [[ -f "$f" ]] || fail "cycle-35 DPS 1 (L7.B) file missing: $f"
done
pass "L7.B library infrastructure files present (README + TEMPLATE + INDEX + 3 scripts + external-access)"

# ─────────────────────────────────────────────────────────────────────
# 2. DPS 1 — 27 runbooks present (Q-L7B-1 launch gate)
# ─────────────────────────────────────────────────────────────────────
runbook_count=$(find docs/sre/runbooks -name "*.md" \
    -not -name "README.md" \
    -not -name "TEMPLATE.md" \
    -not -name "INDEX.md" | wc -l)
if [ "$runbook_count" -ne 27 ]; then
    fail "Q-L7B-1 V1 LAUNCH GATE: found ${runbook_count} runbooks; expected exactly 27 (SR3 §12AF.4)"
fi
pass "Q-L7B-1: 27 runbooks present in docs/sre/runbooks/ (V1 launch gate)"

# ─────────────────────────────────────────────────────────────────────
# 3. DPS 1 — 11 categories x correct sub-counts per L7.B.5-L7.B.15
# ─────────────────────────────────────────────────────────────────────
declare -A expected_counts=(
    [auth]=3
    [ws]=3
    [meta]=3
    [publisher]=2
    [projection]=2
    [llm-provider]=3
    [canon]=2
    [admin]=2
    [reality]=3
    [deploy]=2
    [capacity]=2
)
for cat in "${!expected_counts[@]}"; do
    want="${expected_counts[$cat]}"
    got=$(find "docs/sre/runbooks/$cat" -name "*.md" 2>/dev/null | wc -l || echo 0)
    if [ "$got" -ne "$want" ]; then
        fail "L7.B category ${cat}: ${got} runbooks; expected ${want}"
    fi
done
pass "L7.B 11 categories x correct sub-counts (3+3+3+2+2+3+2+2+3+2+2 = 27)"

# ─────────────────────────────────────────────────────────────────────
# 4. DPS 1 — every runbook has stub frontmatter (Q-L7B-1)
# ─────────────────────────────────────────────────────────────────────
stub_count=0
non_stub_violations=0
while IFS= read -r f; do
    head_block=$(head -20 "$f")
    if ! echo "$head_block" | grep -q "verification_method: stub"; then
        non_stub_violations=$((non_stub_violations+1))
        echo "[verify-cycle-35] non-stub runbook: $f" >&2
    fi
    if ! echo "$head_block" | grep -q "last_verified: 1970-01-01"; then
        non_stub_violations=$((non_stub_violations+1))
        echo "[verify-cycle-35] non-stub last_verified: $f" >&2
    fi
    if ! echo "$head_block" | grep -q "Q-L7B-1"; then
        non_stub_violations=$((non_stub_violations+1))
        echo "[verify-cycle-35] missing Q-L7B-1 LOCKED reference: $f" >&2
    fi
    stub_count=$((stub_count+1))
done < <(find docs/sre/runbooks -name "*.md" \
    -not -name "README.md" -not -name "TEMPLATE.md" -not -name "INDEX.md")
if [ "$non_stub_violations" -gt 0 ]; then
    fail "Q-L7B-1: ${non_stub_violations} stub-discipline violations"
fi
pass "Q-L7B-1: all ${stub_count} runbooks have verification_method: stub + last_verified: 1970-01-01 + Q-L7B-1 ref"

# ─────────────────────────────────────────────────────────────────────
# 5. DPS 1 — runbook-verification-lint.sh passes
# ─────────────────────────────────────────────────────────────────────
if bash scripts/runbook-verification-lint.sh > /tmp/c35-rb-vlint.log 2>&1 ; then
    pass "scripts/runbook-verification-lint.sh — all 27 runbooks valid (advisories printed for unlinked alerts)"
else
    cat /tmp/c35-rb-vlint.log
    fail "scripts/runbook-verification-lint.sh failed"
fi

# ─────────────────────────────────────────────────────────────────────
# 6. DPS 1 — runbook-drift-check.sh passes
# ─────────────────────────────────────────────────────────────────────
if bash scripts/runbook-drift-check.sh > /tmp/c35-rb-drift.log 2>&1 ; then
    pass "scripts/runbook-drift-check.sh — no service drift"
else
    cat /tmp/c35-rb-drift.log
    fail "scripts/runbook-drift-check.sh detected drift"
fi

# ─────────────────────────────────────────────────────────────────────
# 7. DPS 1 — runbook-index-generator.sh writes INDEX.md (idempotent re-run)
# ─────────────────────────────────────────────────────────────────────
if bash scripts/runbook-index-generator.sh > /tmp/c35-rb-idx.log 2>&1 ; then
    pass "scripts/runbook-index-generator.sh rebuilt INDEX.md"
else
    cat /tmp/c35-rb-idx.log
    fail "scripts/runbook-index-generator.sh failed"
fi
# INDEX.md content sanity — must list 27 runbooks
if grep -q "Total runbooks:\*\* 27" docs/sre/runbooks/INDEX.md ; then
    pass "INDEX.md declares Total runbooks: 27"
else
    fail "INDEX.md missing 'Total runbooks: 27' marker"
fi

# ─────────────────────────────────────────────────────────────────────
# 8. DPS 2 — L7.C oncall infrastructure files present
# ─────────────────────────────────────────────────────────────────────
for f in \
    infra/pagerduty/README.md \
    infra/pagerduty/services.yaml \
    infra/pagerduty/rotation_schedule.yaml \
    infra/pagerduty/escalation_policy.yaml \
    infra/pagerduty/main.tf \
    infra/alertmanager/oncall_routing_extension.yaml \
    docs/sre/oncall-handoffs/README.md \
    docs/sre/oncall-handoffs/TEMPLATE.md \
    runbooks/oncall/handoff_missed.md \
    runbooks/oncall/escalation_to_founder.md \
    tests/integration/escalation_test.go ; do
    [[ -f "$f" ]] || fail "cycle-35 DPS 2 (L7.C) file missing: $f"
done
pass "L7.C oncall infrastructure files present (pagerduty/ + alertmanager extension + handoffs/ + 2 runbooks + test)"

# ─────────────────────────────────────────────────────────────────────
# 9. DPS 2 — Q-L7C-1 PagerDuty: 5 services match cycle-34 channels.yaml
# ─────────────────────────────────────────────────────────────────────
for svc in sev0 sev1 sre security data ; do
    grep -q "name: ${svc}" infra/pagerduty/services.yaml \
        || fail "services.yaml missing service: ${svc}"
    grep -q "name: ${svc}" infra/alertmanager/channels.yaml \
        || fail "cycle-34 channels.yaml missing service: ${svc} (carry-forward broken)"
done
for env in \
    PAGERDUTY_INTEGRATION_KEY_SEV0 \
    PAGERDUTY_INTEGRATION_KEY_SEV1 \
    PAGERDUTY_INTEGRATION_KEY_SRE \
    PAGERDUTY_INTEGRATION_KEY_SECURITY \
    PAGERDUTY_INTEGRATION_KEY_DATA ; do
    grep -q "env: ${env}" infra/pagerduty/services.yaml \
        || fail "services.yaml missing env binding: ${env}"
done
grep -q "expected_service_count: 5" infra/pagerduty/services.yaml \
    || fail "services.yaml drift guard missing: expected_service_count: 5"
pass "Q-L7C-1: 5 PagerDuty services match cycle-34 channels.yaml (env-var bindings intact)"

# ─────────────────────────────────────────────────────────────────────
# 10. DPS 2 — 5 escalation policies declared per oncall-sla.md TTA
# ─────────────────────────────────────────────────────────────────────
for p in sev0-immediate sev1-15min-tta sre-primary-rotation security-oncall data-oncall ; do
    grep -q "id: ${p}" infra/pagerduty/escalation_policy.yaml \
        || fail "escalation_policy.yaml missing policy: ${p}"
done
grep -q "expected_policy_count: 5" infra/pagerduty/escalation_policy.yaml \
    || fail "escalation_policy.yaml drift guard missing: expected_policy_count: 5"
# TTA layer-2 delays — must match oncall-sla.md (5/15/30 min)
for delay in "escalation_delay_in_minutes: 5" "escalation_delay_in_minutes: 15" "escalation_delay_in_minutes: 30" ; do
    grep -q "${delay}" infra/pagerduty/escalation_policy.yaml \
        || fail "escalation_policy.yaml missing TTA layer-2 delay: ${delay}"
done
pass "L7.C.3: 5 escalation policies with TTA layer-2 delays matching oncall-sla.md (5/15/30 min)"

# ─────────────────────────────────────────────────────────────────────
# 11. DPS 2 — rotation schedule: 3 phases, 1 active (V1 = solo-dev-247)
# ─────────────────────────────────────────────────────────────────────
for phase in "phase: v1" "phase: v1plus30d" "phase: v2plus" ; do
    grep -q "${phase}" infra/pagerduty/rotation_schedule.yaml \
        || fail "rotation_schedule.yaml missing phase: ${phase}"
done
grep -q "expected_schedule_count: 3" infra/pagerduty/rotation_schedule.yaml \
    || fail "rotation_schedule.yaml drift guard missing: expected_schedule_count: 3"
grep -q "expected_active_schedule: solo-dev-247" infra/pagerduty/rotation_schedule.yaml \
    || fail "rotation_schedule.yaml: expected_active_schedule != solo-dev-247 (V1)"
active_count=$(grep -c "^\s*active: true" infra/pagerduty/rotation_schedule.yaml || true)
if [ "$active_count" -ne 1 ]; then
    fail "rotation_schedule.yaml: ${active_count} schedules active: true; expected exactly 1"
fi
pass "L7.C.2: 3 rotation phases (V1/V1+30d/V2+); exactly 1 active (solo-dev-247)"

# ─────────────────────────────────────────────────────────────────────
# 12. DPS 2 — Q-L7C-2 oncall-sla.md (carry-forward from cycle 34)
# ─────────────────────────────────────────────────────────────────────
[[ -f docs/governance/oncall-sla.md ]] || fail "Q-L7C-2: docs/governance/oncall-sla.md missing (cycle-34 carry-forward broken)"
grep -q "Q-L7C-2 LOCKED" docs/governance/oncall-sla.md \
    || fail "Q-L7C-2: oncall-sla.md missing LOCKED reference banner"
grep -q "internal-only" docs/governance/oncall-sla.md \
    || fail "Q-L7C-2: oncall-sla.md must mark V1 internal-only"
pass "Q-L7C-2: oncall-sla.md present + internal-only banner (cycle 34 carry-forward intact)"

# ─────────────────────────────────────────────────────────────────────
# 13. DPS 2 — alertmanager oncall_routing_extension.yaml cross-references
# ─────────────────────────────────────────────────────────────────────
for recv in pagerduty-sev0 pagerduty-sev1 pagerduty-sre pagerduty-security pagerduty-data ; do
    grep -q "${recv}" infra/alertmanager/oncall_routing_extension.yaml \
        || fail "oncall_routing_extension.yaml missing receiver: ${recv}"
    grep -q "name: ${recv}" infra/alertmanager/main.yaml \
        || fail "cycle-34 main.yaml missing receiver: ${recv} (carry-forward broken)"
done
for p in sev0-immediate sev1-15min-tta sre-primary-rotation security-oncall data-oncall ; do
    grep -q "${p}" infra/alertmanager/oncall_routing_extension.yaml \
        || fail "oncall_routing_extension.yaml missing policy ref: ${p}"
done
grep -q "expected_receiver_count: 5" infra/alertmanager/oncall_routing_extension.yaml \
    || fail "oncall_routing_extension.yaml drift guard missing: expected_receiver_count: 5"
pass "L7.C.6: alertmanager-pagerduty wiring CI cross-checks (5 receivers <-> 5 policies)"

# ─────────────────────────────────────────────────────────────────────
# 14. Handoff schema files present
# ─────────────────────────────────────────────────────────────────────
grep -q "append-only" docs/sre/oncall-handoffs/README.md \
    || fail "oncall-handoffs/README.md missing 'append-only' policy statement"
for section in "Open incidents" "SLI burn status" "Expected blips" "Anomalies seen" "Action items handed off" ; do
    grep -q "${section}" docs/sre/oncall-handoffs/TEMPLATE.md \
        || fail "oncall-handoffs/TEMPLATE.md missing section: ${section}"
done
pass "L7.C.4 + L7.C.5: handoff log schema (5 required sections + append-only policy)"

# ─────────────────────────────────────────────────────────────────────
# 15. Oncall runbooks reference correct LOCKED + escalation chain
# ─────────────────────────────────────────────────────────────────────
grep -q "founder-direct\|founder direct\|founder.*phone\|Phone direct" runbooks/oncall/escalation_to_founder.md \
    || fail "runbooks/oncall/escalation_to_founder.md missing founder-direct procedure"
grep -q "handoff" runbooks/oncall/handoff_missed.md \
    || fail "runbooks/oncall/handoff_missed.md missing 'handoff' keyword"
# Both runbooks cross-reference each other + oncall-sla.md
for r in runbooks/oncall/handoff_missed.md runbooks/oncall/escalation_to_founder.md ; do
    grep -q "oncall-sla.md" "$r" \
        || fail "$r missing oncall-sla.md cross-reference"
done
pass "L7.C.9 + L7.C.10: oncall runbooks cross-reference oncall-sla.md + escalation chain"

# ─────────────────────────────────────────────────────────────────────
# 16. Q-L7C-1 secret hygiene — no 32-hex PagerDuty key in repo (cycle 35 files)
# ─────────────────────────────────────────────────────────────────────
for f in \
    infra/pagerduty/main.tf \
    infra/pagerduty/services.yaml \
    infra/pagerduty/rotation_schedule.yaml \
    infra/pagerduty/escalation_policy.yaml ; do
    if grep -E '[0-9a-f]{32}' "$f" 2>/dev/null | grep -v '^#' | grep -v '^\s*//' | head -1 | grep -q . ; then
        fail "Q-L7C-1 + B6 secret-scan: $f contains 32-hex string (PagerDuty key leak?)"
    fi
done
pass "Q-L7C-1 secret hygiene: no literal 32-hex PagerDuty keys in cycle-35 files"

# ─────────────────────────────────────────────────────────────────────
# 17. tests/integration/escalation_test.go compiles
# ─────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    if (cd "$repo_root/tests/integration" && go build -tags=integration ./... > /tmp/c35-int-build.log 2>&1) ; then
        pass "tests/integration go build -tags=integration (cycle-35 escalation_test compiles)"
    else
        cat /tmp/c35-int-build.log
        fail "tests/integration cycle-35 escalation_test fails to build"
    fi
else
    note "go absent — skipping integration test compile"
fi

# ─────────────────────────────────────────────────────────────────────
# 18. tests/integration/escalation_test.go runs (vet only — no live infra)
# ─────────────────────────────────────────────────────────────────────
if command -v go >/dev/null 2>&1; then
    if (cd "$repo_root/tests/integration" && go vet -tags=integration ./... > /tmp/c35-int-vet.log 2>&1) ; then
        pass "tests/integration go vet -tags=integration (cycle-35 escalation_test vets)"
    else
        cat /tmp/c35-int-vet.log
        fail "tests/integration cycle-35 escalation_test go vet failed"
    fi
fi

# ─────────────────────────────────────────────────────────────────────
# 19. Stub upgrade checklist present in every runbook (lifecycle hook)
# ─────────────────────────────────────────────────────────────────────
missing_checklist=0
while IFS= read -r f; do
    if ! grep -q "Upgrade checklist" "$f"; then
        missing_checklist=$((missing_checklist+1))
        echo "[verify-cycle-35] runbook missing 'Upgrade checklist' section: $f" >&2
    fi
done < <(find docs/sre/runbooks -name "*.md" \
    -not -name "README.md" -not -name "TEMPLATE.md" -not -name "INDEX.md")
if [ "$missing_checklist" -gt 0 ]; then
    fail "${missing_checklist} runbooks missing 'Upgrade checklist' section (stub lifecycle hook required)"
fi
pass "Q-L7B-1: all 27 runbooks include 'Upgrade checklist' section (stub -> reading_review hook)"

# ─────────────────────────────────────────────────────────────────────
# 20. L7.B.19 external-access-docs present + lists curated subset
# ─────────────────────────────────────────────────────────────────────
for keyword in "escalation-chains.md" "break-glass.md" "failover-to-standby.md" "oncall-sla.md" ; do
    grep -q "${keyword}" infra/external-access-docs/README.md \
        || fail "external-access-docs/README.md missing curated mirror reference: ${keyword}"
done
pass "L7.B.19: external-access-docs/README.md lists curated out-of-band mirror set"

# ─────────────────────────────────────────────────────────────────────
# 21. B5 prod-isolation lint (do not touch infra/existing-prod/)
# ─────────────────────────────────────────────────────────────────────
if git status --short 2>/dev/null | grep -q "infra/existing-prod" ; then
    fail "B5 prod-isolation: cycle-35 modifies infra/existing-prod/ (forbidden)"
fi
pass "B5 prod-isolation: cycle 35 does not touch infra/existing-prod/"

# ─────────────────────────────────────────────────────────────────────
# 22. B6 secret-scan-cycle.sh equivalent (no obvious secrets in cycle-35 files)
# ─────────────────────────────────────────────────────────────────────
suspect_count=0
for f in $(git diff --name-only HEAD 2>/dev/null || find infra/pagerduty docs/sre/runbooks runbooks/oncall -type f 2>/dev/null) ; do
    [[ -f "$f" ]] || continue
    # Look for PagerDuty / Slack / API key patterns
    if grep -E '(pd_[a-zA-Z0-9]{20,}|xoxb-[0-9]{10,}|sk-[a-zA-Z0-9]{30,}|AKIA[A-Z0-9]{16})' "$f" 2>/dev/null | head -1 | grep -q . ; then
        suspect_count=$((suspect_count+1))
        echo "[verify-cycle-35] possible secret in: $f" >&2
    fi
done
if [ "$suspect_count" -gt 0 ]; then
    fail "B6 secret-scan: ${suspect_count} files with suspect secret patterns"
fi
pass "B6 secret-scan: no obvious secret patterns in cycle-35 files"

# ─────────────────────────────────────────────────────────────────────
# 23. Cycle 34 carry-forward — alertmanager + alert-recorder + slo-budget-calculator intact
# ─────────────────────────────────────────────────────────────────────
for f in \
    infra/alertmanager/main.yaml \
    infra/alertmanager/channels.yaml \
    services/alert-recorder/go.mod \
    services/slo-budget-calculator/go.mod ; do
    [[ -f "$f" ]] || fail "cycle-34 carry-forward broken: $f missing"
done
pass "Cycle 34 carry-forward intact (alertmanager + alert-recorder + slo-budget-calculator)"

# ─────────────────────────────────────────────────────────────────────
# 24. cycle-19 envelope alignment in services.yaml
# ─────────────────────────────────────────────────────────────────────
grep -q "alert-recorder:8091/v1/alerts/inbox" infra/pagerduty/services.yaml \
    || fail "services.yaml: cycle-19 envelope wiring reference missing (alert-recorder webhook)"
grep -q "envelope_alignment:" infra/pagerduty/services.yaml \
    || fail "services.yaml: envelope_alignment section missing"
pass "Cycle 19 envelope alignment declared in services.yaml"

# ─────────────────────────────────────────────────────────────────────
# 25. CYCLE_LOG.md row 35 exists (PENDING acceptable; flips to DONE at SESSION)
# ─────────────────────────────────────────────────────────────────────
if grep -E '^\| 35 \|' docs/raid/CYCLE_LOG.md >/dev/null 2>&1 ; then
    pass "CYCLE_LOG.md row 35 present"
else
    fail "CYCLE_LOG.md row 35 missing"
fi

echo "[verify-cycle-35] ALL ${step} STEPS PASS"
exit 0
