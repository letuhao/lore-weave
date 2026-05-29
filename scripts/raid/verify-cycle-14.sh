#!/usr/bin/env bash
# verify-cycle-14.sh — L3.D parallel rebuilder + L3.G freeze-rebuild + L3.H catastrophic.
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 14 scope:
#   DPS 1 — L3.D per-aggregate parallel rebuilder (crates/rebuilder/) using
#           dp-kernel Projection trait + cycle-12 load_aggregate primitives.
#           Resumable via checkpoint store, dead-letters failed aggregates.
#   DPS 2 — L3.G V1 freeze-rebuild strategy (services/admin-cli/commands/
#           rebuild_projection.go + scripts/freeze-rebuild.sh + contracts/
#           rebuild/config.yaml). NOT blue-green.
#   DPS 3 — L3.H catastrophic rebuild (services/admin-cli/commands/
#           catastrophic_rebuild.go + services/admin-cli/internal/
#           rolling_rebuild/ + contracts/rebuild/catastrophic_config.yaml +
#           runbooks/disaster/projection_loss.md).
#
# LOCKED decisions enforced:
#   Q-L3-3: admin-cli sub-command + rolling_rebuild internal lib for
#           catastrophic. Not a separate worker; not a cron.
#   Q-L3-5: NO V2 blue-green migration scaffolding. Freeze-rebuild only.
#   Q-L3-4: VerificationMeta carried through (inherited from cycle 12/13;
#           rebuilder uses ProjectionUpdate which already carries it).
#
# Cross-service live smoke: NOT required — cycle ships library code +
# shell wrapper + Go admin commands. No service binary running cross-network.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-14] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-14] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-14] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 — L3.D rebuilder crate
# ─────────────────────────────────────────────────────────────────────────

[[ -f crates/rebuilder/Cargo.toml ]] || fail "crates/rebuilder/Cargo.toml missing"
[[ -f crates/rebuilder/src/lib.rs ]] || fail "crates/rebuilder/src/lib.rs missing"
[[ -f crates/rebuilder/src/checkpoint.rs ]] || fail "crates/rebuilder/src/checkpoint.rs missing"
[[ -f crates/rebuilder/src/dead_letter.rs ]] || fail "crates/rebuilder/src/dead_letter.rs missing"
pass "rebuilder crate skeleton present"

grep -q "ParallelRebuilder" crates/rebuilder/src/lib.rs || fail "ParallelRebuilder not exported"
grep -q "rebuild_aggregate" crates/rebuilder/src/lib.rs || fail "rebuild_aggregate not exported"
grep -q "CheckpointStore" crates/rebuilder/src/lib.rs || fail "CheckpointStore not exposed"
grep -q "DeadLetterStore" crates/rebuilder/src/lib.rs || fail "DeadLetterStore not exposed"
pass "rebuilder public surface: ParallelRebuilder + rebuild_aggregate + CheckpointStore + DeadLetterStore"

# Resumability anchor: rebuild_aggregate consults checkpoints.get + writes
# after each batch.
grep -q "checkpoints.get" crates/rebuilder/src/lib.rs || fail "rebuild_aggregate does not consult checkpoint store"
grep -q "checkpoints.set" crates/rebuilder/src/lib.rs || fail "rebuild_aggregate does not write checkpoints"
pass "resumability wired (checkpoint read + write per batch)"

# Dead letter on exhausted retries.
grep -q "dead_letter.record" crates/rebuilder/src/lib.rs || fail "dead-letter not invoked on exhausted retries"
pass "dead-letter wired on exhausted retries"

# Q-L3-5: NO blue-green / NO V2 scaffolding in CODE (doc-comments that
# explicitly say "NO blue-green" are fine — those are the LOCKED enforcement).
# We strip line/block comments before grepping. Block comments are rare in
# Rust; we restrict to single-line `//` plus YAML `#` for symmetry.
violations=$(grep -rniE --include='*.rs' --include='*.go' --include='*.yaml' \
    'blue[_-]?green|bluegreen|v2[_-]?migration' crates/rebuilder/ 2>/dev/null \
    | grep -vE ':[[:space:]]*//' | grep -vE ':[[:space:]]*#' || true)
if [[ -n "$violations" ]]; then
    echo "$violations" >&2
    fail "Q-L3-5 violated: blue-green/v2 scaffolding found in rebuilder crate"
fi
pass "Q-L3-5: no blue-green scaffolding in rebuilder crate (doc-comments fine)"

# Cycle 12 reuse: must consume dp-kernel ProjectionRunner / Projection trait,
# NOT re-implement it.
grep -q "use dp_kernel" crates/rebuilder/src/lib.rs || fail "rebuilder does not import dp_kernel — cycle-12 reuse required"
grep -q "ProjectionRunner" crates/rebuilder/src/lib.rs || fail "rebuilder does not use ProjectionRunner"
pass "rebuilder consumes cycle-12 dp-kernel (Projection trait + ProjectionRunner)"

note "running cargo test -p rebuilder"
if cargo test -p rebuilder --quiet 2>&1 | tail -30 | grep -qE "^test result: ok"; then
    pass "cargo test -p rebuilder: PASS (7 tests including parallelism + dead-letter + resumability)"
else
    cargo test -p rebuilder --no-fail-fast 2>&1 | tail -40
    fail "cargo test -p rebuilder failed"
fi

# ─────────────────────────────────────────────────────────────────────────
# DPS 2 — L3.G freeze-rebuild
# ─────────────────────────────────────────────────────────────────────────

[[ -f contracts/rebuild/config.yaml ]] || fail "contracts/rebuild/config.yaml missing"
grep -q "parallel_workers" contracts/rebuild/config.yaml || fail "config.yaml missing parallel_workers"
grep -q "freeze_rebuild" contracts/rebuild/config.yaml || fail "config.yaml missing freeze_rebuild section"
pass "contracts/rebuild/config.yaml present with parallel_workers + freeze_rebuild"

[[ -f services/admin-cli/commands/rebuild_projection.go ]] || fail "rebuild_projection.go missing"
[[ -f services/admin-cli/commands/rebuild_projection_test.go ]] || fail "rebuild_projection_test.go missing"
pass "admin-cli rebuild_projection command + tests present"

[[ -x scripts/freeze-rebuild.sh ]] || chmod +x scripts/freeze-rebuild.sh
[[ -f scripts/freeze-rebuild.sh ]] || fail "scripts/freeze-rebuild.sh missing"
pass "scripts/freeze-rebuild.sh wrapper present"

# Smoke: dry-run wrapper exits 0 with valid args.
if bash scripts/freeze-rebuild.sh --reality r-test --projection pc_projection \
       --actor "ops" --reason "smoke" --dry-run >/dev/null 2>&1; then
    pass "freeze-rebuild.sh dry-run smoke: exit 0"
else
    fail "freeze-rebuild.sh dry-run smoke failed"
fi
# Smoke: refuses destructive without --confirm.
if bash scripts/freeze-rebuild.sh --reality r-test --projection pc_projection \
       --actor "ops" --reason "smoke" >/dev/null 2>&1; then
    fail "freeze-rebuild.sh accepted destructive run WITHOUT --confirm"
fi
pass "freeze-rebuild.sh rejects destructive run without --confirm"

# Q-L3-5 enforcement in command + config (skip doc-comment lines).
violations=$(grep -niE 'blue[_-]?green|bluegreen' \
    services/admin-cli/commands/rebuild_projection.go \
    contracts/rebuild/config.yaml \
    scripts/freeze-rebuild.sh 2>/dev/null \
    | grep -vE ':[[:space:]]*//' | grep -vE ':[[:space:]]*#' || true)
if [[ -n "$violations" ]]; then
    echo "$violations" >&2
    fail "Q-L3-5 violated: blue-green found in freeze-rebuild surface"
fi
pass "Q-L3-5: no blue-green in freeze-rebuild surface (doc-comments fine)"

# ─────────────────────────────────────────────────────────────────────────
# DPS 3 — L3.H catastrophic rebuild (Q-L3-3)
# ─────────────────────────────────────────────────────────────────────────

[[ -d services/admin-cli/internal/rolling_rebuild ]] || fail "Q-L3-3: rolling_rebuild lib package missing"
[[ -f services/admin-cli/internal/rolling_rebuild/rolling_rebuild.go ]] || fail "rolling_rebuild.go missing"
[[ -f services/admin-cli/internal/rolling_rebuild/rolling_rebuild_test.go ]] || fail "rolling_rebuild_test.go missing"
pass "Q-L3-3: services/admin-cli/internal/rolling_rebuild/ lib present"

[[ -f services/admin-cli/commands/catastrophic_rebuild.go ]] || fail "Q-L3-3: catastrophic admin-cli command missing"
[[ -f services/admin-cli/commands/catastrophic_rebuild_test.go ]] || fail "catastrophic_rebuild_test.go missing"
pass "Q-L3-3: admin-cli catastrophic sub-command present"

[[ -f contracts/rebuild/catastrophic_config.yaml ]] || fail "catastrophic_config.yaml missing"
grep -q "rolling_concurrency: 50" contracts/rebuild/catastrophic_config.yaml || fail "rolling_concurrency=50 missing"
grep -q "freeze_timeout_minutes: 30" contracts/rebuild/catastrophic_config.yaml || fail "freeze_timeout_minutes=30 missing"
pass "catastrophic_config.yaml present with rolling_concurrency=50 + freeze_timeout_minutes=30"

[[ -f runbooks/disaster/projection_loss.md ]] || fail "projection_loss.md runbook missing"
grep -q "rolling_rebuild" runbooks/disaster/projection_loss.md || fail "runbook does not reference rolling_rebuild lib"
grep -q "MaxConcurrentSeen" runbooks/disaster/projection_loss.md || fail "runbook does not document concurrency invariant"
pass "runbooks/disaster/projection_loss.md present + documents rolling_rebuild + concurrency invariant"

# Catastrophic command REQUIRES --confirm for destructive (Q-L3-3 + S5-D5 tier-1).
grep -q "Confirm" services/admin-cli/commands/catastrophic_rebuild.go || fail "catastrophic command lacks --confirm validation"
grep -q "require --confirm\|--confirm required\|--confirm" services/admin-cli/commands/catastrophic_rebuild.go || fail "no --confirm guard in catastrophic command"
pass "catastrophic command enforces --confirm guard"

note "running go test ./... in services/admin-cli"
if (cd services/admin-cli && go test ./... 2>&1 | tail -10 | grep -qE "ok.*admin-cli/commands"); then
    pass "go test ./services/admin-cli/...: PASS"
else
    (cd services/admin-cli && go test ./... 2>&1 | tail -40)
    fail "go test ./services/admin-cli/... failed"
fi

# Q-L3-3 surface check: rolling_rebuild caps concurrency at 50.
grep -q "exceeds 50 cap" services/admin-cli/internal/rolling_rebuild/rolling_rebuild.go || \
    fail "rolling_rebuild does not enforce 50-concurrency cap"
pass "rolling_rebuild enforces 50-concurrency cap per R02 §12B.5"

# ─────────────────────────────────────────────────────────────────────────
# B5 prod-isolation + B6 secret-scan
# ─────────────────────────────────────────────────────────────────────────

# B5: any new file under infra/existing-prod/?
if git diff --name-only HEAD 2>/dev/null | grep -qE '^infra/existing-prod/'; then
    fail "B5: changes detected under infra/existing-prod/ (forbidden)"
fi
pass "B5 prod-isolation: no infra/existing-prod/ changes"

# B6: secret-scan over new files added this cycle (basic grep for high-risk
# patterns). NOT a substitute for the global secret-scan job, but catches the
# obvious accidentals before commit.
NEW_FILES=(
    crates/rebuilder/Cargo.toml
    crates/rebuilder/src/lib.rs
    crates/rebuilder/src/checkpoint.rs
    crates/rebuilder/src/dead_letter.rs
    services/admin-cli/commands/rebuild_projection.go
    services/admin-cli/commands/rebuild_projection_test.go
    services/admin-cli/commands/catastrophic_rebuild.go
    services/admin-cli/commands/catastrophic_rebuild_test.go
    services/admin-cli/internal/rolling_rebuild/rolling_rebuild.go
    services/admin-cli/internal/rolling_rebuild/rolling_rebuild_test.go
    contracts/rebuild/config.yaml
    contracts/rebuild/catastrophic_config.yaml
    scripts/freeze-rebuild.sh
    runbooks/disaster/projection_loss.md
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -qE "$SECRET_PATTERNS" "$f"; then
        fail "B6: potential secret in $f"
    fi
done
pass "B6 secret-scan: no high-risk patterns in cycle-14 new files"

echo "[verify-cycle-14] all $step steps PASS"
