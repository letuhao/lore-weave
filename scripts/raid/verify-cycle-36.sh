#!/usr/bin/env bash
# verify-cycle-36.sh — L7.A admin-cli framework + ~30 commands.
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 36 scope (5 DPS, inline-built):
#   DPS 1: framework + reality registry (8 commands)
#   DPS 2: erasure registry (3 commands)
#   DPS 3: canon + projection registry (4 commands)
#   DPS 4: backup + archive + migration registry (9 commands)
#   DPS 5: incident + ops registry (8 commands)
#
# Total: 32 commands across 9 domains (Q-L7A-1 per-domain split).
#
# LOCKED decisions enforced:
#   Q-L7A-1 — per-domain YAML files, auto-merged by framework loader.
#   Q-L7A-2 — single binary distribution (admin <domain> <verb>).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-36] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-36] step $step FAIL: $1" >&2; exit 1; }

# ─────────────────────────────────────────────────────────────────────
# 1. Framework code files present
# ─────────────────────────────────────────────────────────────────────
for f in \
    services/admin-cli/cmd/admin/main.go \
    services/admin-cli/internal/framework/registry.go \
    services/admin-cli/internal/framework/dispatcher.go \
    services/admin-cli/internal/framework/handlers.go \
    services/admin-cli/internal/framework/yaml_lite.go \
    services/admin-cli/internal/framework/registry_test.go \
    services/admin-cli/internal/audit_emitter/emitter.go \
    services/admin-cli/internal/confirmation/confirmation.go \
    services/admin-cli/internal/dry_run/dry_run.go \
    services/admin-cli/internal/impact_classifier/classifier.go \
    services/admin-cli/internal/auth/auth.go \
    services/admin-cli/internal/break_glass/break_glass.go \
    services/admin-cli/pkg/cliapi/cliapi.go \
    contracts/admin/doc.go ; do
    [[ -f "$f" ]] || fail "framework file missing: $f"
done
pass "framework + audit + auth + break_glass + cliapi files present"

# ─────────────────────────────────────────────────────────────────────
# 2. Per-domain registry YAMLs present (Q-L7A-1)
# ─────────────────────────────────────────────────────────────────────
for d in reality erasure canon projection backup archive migration incident ops ; do
    [[ -f "contracts/admin/registry/${d}.yaml" ]] \
        || fail "Q-L7A-1: per-domain registry missing: contracts/admin/registry/${d}.yaml"
done
pass "Q-L7A-1: 9 per-domain registry files present (reality/erasure/canon/projection/backup/archive/migration/incident/ops)"

# ─────────────────────────────────────────────────────────────────────
# 3. Q-L7A-2 single binary — admin-cli cmd/admin builds
# ─────────────────────────────────────────────────────────────────────
( cd services/admin-cli && go build ./cmd/admin ) || fail "Q-L7A-2: admin binary failed to build"
pass "Q-L7A-2: services/admin-cli/cmd/admin builds (single binary)"

# ─────────────────────────────────────────────────────────────────────
# 4. Full admin-cli module builds (no broken refs after framework add)
# ─────────────────────────────────────────────────────────────────────
( cd services/admin-cli && go build ./... ) || fail "admin-cli module-wide build failed"
pass "services/admin-cli ./... builds clean"

# ─────────────────────────────────────────────────────────────────────
# 5. admin-cli unit tests green (all subpackages)
# ─────────────────────────────────────────────────────────────────────
( cd services/admin-cli && go test ./... ) || fail "admin-cli unit tests failed"
pass "services/admin-cli unit tests green (framework + audit + auth + break_glass + confirmation + dry_run + impact + rolling_rebuild + commands)"

# ─────────────────────────────────────────────────────────────────────
# 6. go vet clean
# ─────────────────────────────────────────────────────────────────────
( cd services/admin-cli && go vet ./... ) || fail "go vet failed"
pass "go vet ./... clean"

# ─────────────────────────────────────────────────────────────────────
# 7. Command count: 28-32 (cycle 36 scope)
# ─────────────────────────────────────────────────────────────────────
admin_bin=$(mktemp -u)
( cd services/admin-cli && go build -o "$admin_bin" ./cmd/admin ) || fail "rebuild admin for --list smoke failed"
ADMIN_CLI_REGISTRY_DIR="$repo_root/contracts/admin/registry" cmd_count=$("$admin_bin" --list 2>/dev/null | grep -c '"name":' || true)
if [ "$cmd_count" -lt 28 ] || [ "$cmd_count" -gt 32 ]; then
    fail "command count = ${cmd_count}; cycle 36 target 28-32"
fi
pass "command count = ${cmd_count} (within cycle 36 28-32 target)"

# ─────────────────────────────────────────────────────────────────────
# 8. All 9 expected domains present in registry --list output
# ─────────────────────────────────────────────────────────────────────
list_json=$(ADMIN_CLI_REGISTRY_DIR="$repo_root/contracts/admin/registry" "$admin_bin" --list 2>/dev/null)
for d in reality erasure canon projection backup archive migration incident ops ; do
    echo "$list_json" | grep -q "\"domain\": \"${d}\"" \
        || fail "domain ${d} missing from --list JSON dump (Q-L7A-1 auto-merge dropped it?)"
done
pass "all 9 domains present in --list JSON (Q-L7A-1 auto-merge intact)"

# ─────────────────────────────────────────────────────────────────────
# 9. Consolidated CLIs referenced (no silent drop of prior cycles)
# ─────────────────────────────────────────────────────────────────────
for n in "reality capacity-override" "reality rebuild-projection" "reality catastrophic-rebuild" \
         "archive list" "archive fetch" \
         "migration up" "migration down" "migration status" ; do
    echo "$list_json" | grep -q "\"name\": \"${n}\"" \
        || fail "consolidated command missing: ${n} (prior-cycle CLI not unified into admin binary?)"
done
pass "consolidated cycle-6/7/11/14 commands present in unified admin binary"

# ─────────────────────────────────────────────────────────────────────
# 10. Tier-1 commands have dry_run_required + double_approval_required
# ─────────────────────────────────────────────────────────────────────
tier1_count=$(echo "$list_json" | grep -c 'tier-1-destructive' || true)
if [ "$tier1_count" -lt 1 ]; then
    fail "no tier-1-destructive commands found (registry policy broken?)"
fi
# Spot-check: spawn a synthetic invalid tier-1 yaml and confirm LoadRegistry rejects.
tmp_dir=$(mktemp -d)
cp contracts/admin/registry/*.yaml "$tmp_dir/"
cat > "$tmp_dir/bad.yaml" <<EOF
domain: bad
commands:
  - name: bad tier1-leak
    version: "1.0.0"
    summary: "missing tier-1 gates"
    handler: bad
    impact_class: tier-1-destructive
    dry_run_required: false
    double_approval_required: false
    carry_forward_cycle: "36"
EOF
if ADMIN_CLI_REGISTRY_DIR="$tmp_dir" "$admin_bin" --list >/dev/null 2>&1 ; then
    rm -rf "$tmp_dir"
    fail "tier-1 policy LEAKED: a tier-1 command without dry_run+double_approval was accepted"
fi
rm -rf "$tmp_dir"
pass "tier-1 policy enforced: ${tier1_count} tier-1 entries + LoadRegistry rejects a synthetic gap"

# ─────────────────────────────────────────────────────────────────────
# 11. Integration test green (cross-module admin-cli smoke)
# ─────────────────────────────────────────────────────────────────────
( cd tests/integration && go test -tags=integration -run TestAdminCLI ./... ) \
    || fail "cycle 36 integration tests failed"
pass "cycle 36 integration tests green (7 TestAdminCLI_* tests)"

# ─────────────────────────────────────────────────────────────────────
# 12. Admin registry lint script present + green
# ─────────────────────────────────────────────────────────────────────
[[ -x scripts/admin-command-registry-lint.sh ]] \
    || fail "scripts/admin-command-registry-lint.sh missing or not executable"
bash scripts/admin-command-registry-lint.sh >/dev/null 2>&1 \
    || fail "admin-command-registry-lint.sh failed (orphan ADMIN-SQL/RPC markers?)"
pass "scripts/admin-command-registry-lint.sh present + green (no orphan admin endpoints)"

# ─────────────────────────────────────────────────────────────────────
# 13. Governance catalog present + correct counts
# ─────────────────────────────────────────────────────────────────────
[[ -f docs/governance/admin-command-catalog.md ]] \
    || fail "docs/governance/admin-command-catalog.md missing"
grep -q "Q-L7A-1" docs/governance/admin-command-catalog.md \
    || fail "admin-command-catalog.md missing Q-L7A-1 reference"
grep -q "Q-L7A-2" docs/governance/admin-command-catalog.md \
    || fail "admin-command-catalog.md missing Q-L7A-2 reference"
grep -q "consolidated cycle 6\|consolidated cycle 7\|consolidated cycle 11\|consolidated cycle 14\|cycle 6 migration\|cycle 7\|cycle 11\|cycle 14" docs/governance/admin-command-catalog.md \
    || fail "admin-command-catalog.md missing consolidation refs to cycles 6/7/11/14"
pass "docs/governance/admin-command-catalog.md present with Q-L7A-1 + Q-L7A-2 + consolidation refs"

# ─────────────────────────────────────────────────────────────────────
# 14. admin_action_audit table still ownerless-then-cycle-36-owned in allowlist
# ─────────────────────────────────────────────────────────────────────
grep -q "admin_action_audit" contracts/meta/events_allowlist.yaml \
    || fail "events_allowlist.yaml lost admin_action_audit row (cycle 4 carry-forward broken)"
pass "admin_action_audit still declared in events_allowlist (cycle 4 carry-forward intact)"

# ─────────────────────────────────────────────────────────────────────
# 15. B5 prod-isolation — no admin-cli files under infra/existing-prod
# ─────────────────────────────────────────────────────────────────────
if find infra/existing-prod -type f 2>/dev/null | grep -q . ; then
    leaks=$(find infra/existing-prod -type f 2>/dev/null | head -5)
    fail "B5 prod-isolation: files appeared under infra/existing-prod/: $leaks"
fi
pass "B5 prod-isolation: infra/existing-prod/ untouched"

# ─────────────────────────────────────────────────────────────────────
# 16. B6 secret-scan — no JWT/PII/credential strings in cycle 36 src
# ─────────────────────────────────────────────────────────────────────
# Very conservative grep: look for high-confidence secret shapes only.
suspicious=$(grep -RnE 'sk-[A-Za-z0-9]{40,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}|password\s*=\s*"[^$"]{8,}' \
    services/admin-cli contracts/admin scripts/admin-command-registry-lint.sh 2>/dev/null \
    | grep -v '// admin-registry-lint' \
    | grep -v '_test.go:' \
    || true)
if [[ -n "$suspicious" ]]; then
    echo "$suspicious" >&2
    fail "B6 secret-scan: suspicious credential shapes in cycle 36 src"
fi
pass "B6 secret-scan: no suspicious credential shapes in admin-cli src"

# ─────────────────────────────────────────────────────────────────────
# 17. CYCLE_LOG row for cycle 36 exists and marked DONE
# ─────────────────────────────────────────────────────────────────────
grep -E '^\| 36 \| L7 admin-cli' docs/raid/CYCLE_LOG.md \
    | grep -q "DONE" \
    || fail "CYCLE_LOG.md row 36 missing or not DONE (Phase 10 SESSION incomplete?)"
pass "CYCLE_LOG.md row 36 = DONE"

# ─────────────────────────────────────────────────────────────────────
# 18. Q-L7A-1 + Q-L7A-2 declared in every registry file
# ─────────────────────────────────────────────────────────────────────
for d in reality erasure canon projection backup archive migration incident ops ; do
    grep -q "Q-L7A-1" "contracts/admin/registry/${d}.yaml" \
        || fail "${d}.yaml missing Q-L7A-1 reference"
    grep -q "Q-L7A-2" "contracts/admin/registry/${d}.yaml" \
        || fail "${d}.yaml missing Q-L7A-2 reference"
done
pass "all 9 registry files reference Q-L7A-1 + Q-L7A-2"

# ─────────────────────────────────────────────────────────────────────
echo "[verify-cycle-36] all ${step} steps PASS — cycle 36 acceptance gate OPEN"
exit 0
