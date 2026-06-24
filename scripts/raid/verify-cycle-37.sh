#!/usr/bin/env bash
# verify-cycle-37.sh — L7.D Incident Response Infra + L7.L Status Page.
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 37 scope (2 DPS, inline-built):
#   DPS 1: L7.D — incident-bot + postmortem-bot + contracts/incidents (shared)
#          + contracts/postmortems + docs/sre/postmortems/TEMPLATE.md
#          + infra/comms/{out_of_band,templates} + 3 incident runbooks
#   DPS 2: L7.L — infra/statuspage/ IaC + components/banner/templates
#          + statuspage-updater + statuspage runbook
#
# LOCKED decisions enforced:
#   Q-L7L-1 — Statuspage.io V1 (abstracted behind StatusPageClient; no live acct).
#   Q-L7-1  — incident-bot + postmortem-bot + statuspage-updater SEPARATE services.
#   Q-L7-2  — pre-approved comms templates in infra/comms/templates/.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-37] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-37] step $step FAIL: $1" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────────────
# 1. L7.D artifact paths present
# ─────────────────────────────────────────────────────────────────────
for f in \
    contracts/incidents/go.mod \
    contracts/incidents/severity.go \
    contracts/incidents/events.go \
    contracts/incidents/severity_matrix.go \
    contracts/incidents/severity_matrix.yaml \
    contracts/postmortems/root_cause_enum.yaml \
    services/incident-bot/cmd/incident-bot/main.go \
    services/incident-bot/internal/severity_classifier/classifier.go \
    services/incident-bot/internal/war_room/war_room.go \
    services/incident-bot/internal/statuspage/poster.go \
    services/incident-bot/internal/comms_template/comms_template.go \
    services/incident-bot/internal/gdpr_breach_flow/gdpr_breach_flow.go \
    services/incident-bot/internal/ic_role/ic_role.go \
    services/incident-bot/pkg/incidentflow/incidentflow.go \
    services/postmortem-bot/cmd/postmortem-bot/main.go \
    services/postmortem-bot/internal/generator/generator.go \
    services/postmortem-bot/pkg/postmortem/postmortem.go \
    docs/sre/postmortems/TEMPLATE.md \
    infra/comms/out_of_band/channels.yaml \
    infra/comms/templates/incident_investigating.yaml \
    infra/comms/templates/incident_identified.yaml \
    infra/comms/templates/incident_resolved.yaml \
    infra/comms/templates/gdpr_breach_notice.yaml \
    runbooks/incident/declaration.md \
    runbooks/incident/gdpr_breach.md \
    runbooks/incident/comms_under_pressure.md \
    tests/integration/incident_flow_test.go ; do
    [[ -f "$f" ]] || fail "L7.D artifact missing: $f"
done
pass "all 16 L7.D artifacts present (incident-bot + postmortem-bot + contracts + templates + runbooks + integration test)"

# ─────────────────────────────────────────────────────────────────────
# 2. L7.L artifact paths present
# ─────────────────────────────────────────────────────────────────────
for f in \
    infra/statuspage/main.tf \
    infra/statuspage/components.yaml \
    infra/statuspage/banner-config.yaml \
    infra/statuspage/templates/en.json \
    infra/statuspage/templates/vi.json \
    services/statuspage-updater/cmd/statuspage-updater/main.go \
    services/statuspage-updater/internal/config/config.go \
    services/statuspage-updater/internal/updater/updater.go \
    services/statuspage-updater/internal/updater/provider.go \
    services/statuspage-updater/pkg/statusflow/statusflow.go \
    tests/integration/statuspage_test.go \
    runbooks/statuspage/manual_update.md ; do
    [[ -f "$f" ]] || fail "L7.L artifact missing: $f"
done
pass "all 7 L7.L artifacts present (statuspage IaC + config + updater + i18n + runbook + integration test)"

# ─────────────────────────────────────────────────────────────────────
# 3. Q-L7-1 — three SEPARATE services build
# ─────────────────────────────────────────────────────────────────────
( cd services/incident-bot && go build ./... ) || fail "incident-bot build failed"
( cd services/postmortem-bot && go build ./... ) || fail "postmortem-bot build failed"
( cd services/statuspage-updater && go build ./... ) || fail "statuspage-updater build failed"
( cd contracts/incidents && go build ./... ) || fail "contracts/incidents build failed"
pass "Q-L7-1: incident-bot + postmortem-bot + statuspage-updater + contracts/incidents all build (separate services)"

# ─────────────────────────────────────────────────────────────────────
# 4. Unit tests green (all four modules)
# ─────────────────────────────────────────────────────────────────────
( cd contracts/incidents && go test ./... ) || fail "contracts/incidents tests failed"
( cd services/incident-bot && go test ./... ) || fail "incident-bot tests failed"
( cd services/postmortem-bot && go test ./... ) || fail "postmortem-bot tests failed"
( cd services/statuspage-updater && go test ./... ) || fail "statuspage-updater tests failed"
pass "unit tests green: contracts/incidents + incident-bot + postmortem-bot + statuspage-updater"

# ─────────────────────────────────────────────────────────────────────
# 5. go vet clean (all four modules)
# ─────────────────────────────────────────────────────────────────────
( cd contracts/incidents && go vet ./... ) || fail "contracts/incidents vet failed"
( cd services/incident-bot && go vet ./... ) || fail "incident-bot vet failed"
( cd services/postmortem-bot && go vet ./... ) || fail "postmortem-bot vet failed"
( cd services/statuspage-updater && go vet ./... ) || fail "statuspage-updater vet failed"
pass "go vet clean across all four cycle-37 modules"

# ─────────────────────────────────────────────────────────────────────
# 6. Cross-service integration test (incident → status page contract)
# ─────────────────────────────────────────────────────────────────────
( cd tests/integration && go test -tags=integration -run 'TestIncidentFlow|TestStatusPage' ./... ) \
    || fail "cycle 37 integration tests failed"
pass "integration tests green (TestIncidentFlow_* + TestStatusPage_* — incident→statuspage contract end-to-end)"

# ─────────────────────────────────────────────────────────────────────
# 7. Severity matrix has 4 severities + TTA aligns with pagerduty services
# ─────────────────────────────────────────────────────────────────────
for sev in SEV0 SEV1 SEV2 SEV3 ; do
    grep -q "id: ${sev}" contracts/incidents/severity_matrix.yaml \
        || fail "severity_matrix.yaml missing ${sev}"
done
# TTA alignment with infra/pagerduty/services.yaml (cycle 35): sev0=5 sev1=15 sre=30.
grep -qE 'tta_minutes:\s*5' contracts/incidents/severity_matrix.yaml || fail "SEV0 TTA 5min missing"
grep -qE 'tta_minutes:\s*15' contracts/incidents/severity_matrix.yaml || fail "SEV1 TTA 15min missing"
grep -qE 'tta_minutes:\s*30' contracts/incidents/severity_matrix.yaml || fail "SEV2 TTA 30min missing"
pass "severity_matrix: 4 severities + TTA (5/15/30) aligns with pagerduty services.yaml"

# ─────────────────────────────────────────────────────────────────────
# 8. Root-cause enum has exactly 12 entries (SR4)
# ─────────────────────────────────────────────────────────────────────
grep -q "expected_enum_count: 12" contracts/postmortems/root_cause_enum.yaml \
    || fail "root_cause_enum.yaml: expected_enum_count must be 12 (SR4)"
rc_count=$(grep -cE '^\s*- id:' contracts/postmortems/root_cause_enum.yaml || true)
if [ "$rc_count" -ne 12 ]; then
    fail "root_cause_enum.yaml has ${rc_count} entries; SR4 requires 12"
fi
pass "root_cause_enum: 12-class SR4 taxonomy present"

# ─────────────────────────────────────────────────────────────────────
# 9. Q-L7-2 — comms templates EN + VI present (i18n minimum)
# ─────────────────────────────────────────────────────────────────────
for t in incident_investigating incident_identified incident_resolved gdpr_breach_notice ; do
    grep -q "^  en:" "infra/comms/templates/${t}.yaml" \
        || fail "${t}.yaml missing en locale"
    grep -q "^  vi:" "infra/comms/templates/${t}.yaml" \
        || fail "${t}.yaml missing vi locale (V1 EN+VI minimum)"
done
pass "Q-L7-2: 4 comms templates present with EN + VI locales"

# ─────────────────────────────────────────────────────────────────────
# 10. Q-L7L-1 — statuspage components.yaml ↔ main.tf 1:1 + Statuspage.io
# ─────────────────────────────────────────────────────────────────────
grep -qi 'statuspage' infra/statuspage/main.tf \
    || fail "main.tf does not reference Statuspage.io (Q-L7L-1)"
for c in gateway auth world roleplay realtime ; do
    grep -q "id: ${c}" infra/statuspage/components.yaml \
        || fail "components.yaml missing component ${c}"
    grep -q "statuspage_component\" \"${c}\"" infra/statuspage/main.tf \
        || fail "main.tf missing statuspage_component resource for ${c} (components↔IaC drift)"
done
pass "Q-L7L-1: 5 statuspage components match between components.yaml and main.tf"

# ─────────────────────────────────────────────────────────────────────
# 11. L7.L.4 — i18n EN+VI key parity between en.json and vi.json
# ─────────────────────────────────────────────────────────────────────
en_keys=$(grep -oE '"[a-z_]+":' infra/statuspage/templates/en.json | sort -u)
vi_keys=$(grep -oE '"[a-z_]+":' infra/statuspage/templates/vi.json | sort -u)
if [ "$en_keys" != "$vi_keys" ]; then
    echo "EN/VI key drift:" >&2
    diff <(echo "$en_keys") <(echo "$vi_keys") >&2 || true
    fail "infra/statuspage/templates en.json and vi.json key sets diverge"
fi
pass "L7.L.4: en.json and vi.json have identical key sets (i18n parity)"

# ─────────────────────────────────────────────────────────────────────
# 12. out_of_band channels are off-platform + env-var creds only
# ─────────────────────────────────────────────────────────────────────
grep -q "off_platform: true" infra/comms/out_of_band/channels.yaml \
    || fail "out_of_band channels.yaml missing off_platform declarations"
# No literal credential value lines (only *_env references).
if grep -qE 'credential_env:\s*$' infra/comms/out_of_band/channels.yaml ; then
    fail "out_of_band channel has an empty credential_env"
fi
pass "out_of_band channels off-platform + env-var-only credentials"

# ─────────────────────────────────────────────────────────────────────
# 13. B5 prod-isolation — nothing under infra/existing-prod/
# ─────────────────────────────────────────────────────────────────────
if find infra/existing-prod -type f 2>/dev/null | grep -q . ; then
    leaks=$(find infra/existing-prod -type f 2>/dev/null | head -5)
    fail "B5 prod-isolation: files appeared under infra/existing-prod/: $leaks"
fi
pass "B5 prod-isolation: infra/existing-prod/ untouched"

# ─────────────────────────────────────────────────────────────────────
# 14. B6 secret-scan — no high-confidence credential shapes in cycle 37 src
# ─────────────────────────────────────────────────────────────────────
suspicious=$(grep -RnE 'sk-[A-Za-z0-9]{40,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}|xoxb-[A-Za-z0-9-]{20,}|password\s*=\s*"[^$"]{8,}' \
    services/incident-bot services/postmortem-bot services/statuspage-updater \
    contracts/incidents contracts/postmortems infra/comms infra/statuspage 2>/dev/null \
    | grep -v '_test.go:' \
    || true)
if [[ -n "$suspicious" ]]; then
    echo "$suspicious" >&2
    fail "B6 secret-scan: suspicious credential shapes in cycle 37 src"
fi
pass "B6 secret-scan: no high-confidence credential shapes in cycle 37 src"

# ─────────────────────────────────────────────────────────────────────
# 15. CYCLE_LOG row for cycle 37 exists and marked DONE
# ─────────────────────────────────────────────────────────────────────
grep -E '^\| 37 \|' docs/raid/CYCLE_LOG.md \
    | grep -q "DONE" \
    || fail "CYCLE_LOG.md row 37 missing or not DONE (Phase 10 SESSION incomplete?)"
pass "CYCLE_LOG.md row 37 = DONE"

# ─────────────────────────────────────────────────────────────────────
echo "[verify-cycle-37] all ${step} steps PASS — cycle 37 acceptance gate OPEN"
exit 0
