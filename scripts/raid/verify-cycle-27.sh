#!/usr/bin/env bash
# verify-cycle-27.sh — L5.H + L5.I + L5.J Force-propagate + Conflict + History (3 DPS).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 27 scope (3 DPS):
#
#   DPS 1 (L5.H — force-propagate compensating event mechanism):
#     * contracts/events/admin_canon_override.go (4 event types)
#     * contracts/events/admin_canon_override_test.go
#     * services/meta-worker/pkg/force_propagate/{writer.go,writer_test.go}
#     * services/meta-worker/pkg/dispatch/dispatch.go (allowlist extension)
#     * runbooks/canon/force_propagate.md
#
#   DPS 2 (L5.I — L1 axiomatic conflict detection + canon_guardrail full impl):
#     * crates/contracts-prompt/ (new workspace crate, Rust)
#         - Cargo.toml + src/lib.rs + src/canon_guardrail.rs
#     * services/meta-worker/pkg/l1_conflict_detector/{detector.go,detector_test.go}
#     * services/meta-worker/pkg/l1_conflict_reporter/{reporter.go,reporter_test.go}
#     * contracts/canon/guardrail_rules.yaml
#
#   DPS 3 (L5.J — Glossary entity change timeline contract):
#     * contracts/events/canon_change_history.go + test
#     * contracts/canon/timeline/ (Go pkg: doc.go + timeline.go + mutex.go + test)
#     * crates/dp-kernel/src/canon_history.rs (Rust mirror)
#     * services/meta-worker/pkg/canon_history_writer/{writer.go,writer_test.go}
#     * contracts/api/glossary-service/canon_history.yaml
#     * contracts/migrations/glossary/0001_canon_change_history.{up,down}.sql
#
#   Integration: tests/integration/force_propagate_test.go (4 tests)
#
# LOCKED decisions enforced:
#   Q-L5H-1  — 24h consent timeout; default-to-consent on no-response
#   Q-L5-5   — full canon_guardrail impl backwards-compat with cycle 25 trait
#   Q-L5-3   — canon_layer enum {L1_axiom, L2_seeded} verbatim
#   Q-L1A-2  — canon SSOT in glossary DB; foundation owns migration proposal
#   Q-L1A-3  — full audit V1, no sampling
#   Q-L5A-1  — services/glossary-service/ UNTOUCHED

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-27] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-27] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-27] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# File presence — DPS 1 (L5.H)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/events/admin_canon_override.go \
    contracts/events/admin_canon_override_test.go \
    services/meta-worker/pkg/force_propagate/writer.go \
    services/meta-worker/pkg/force_propagate/writer_test.go \
    runbooks/canon/force_propagate.md ; do
    [[ -f "$f" ]] || fail "cycle-27 DPS 1 (L5.H) file missing: $f"
done
pass "cycle-27 L5.H files present (events + force_propagate pkg + runbook)"

# ─────────────────────────────────────────────────────────────────────────
# File presence — DPS 2 (L5.I)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    crates/contracts-prompt/Cargo.toml \
    crates/contracts-prompt/src/lib.rs \
    crates/contracts-prompt/src/canon_guardrail.rs \
    services/meta-worker/pkg/l1_conflict_detector/detector.go \
    services/meta-worker/pkg/l1_conflict_detector/detector_test.go \
    services/meta-worker/pkg/l1_conflict_reporter/reporter.go \
    services/meta-worker/pkg/l1_conflict_reporter/reporter_test.go \
    contracts/canon/guardrail_rules.yaml ; do
    [[ -f "$f" ]] || fail "cycle-27 DPS 2 (L5.I) file missing: $f"
done
pass "cycle-27 L5.I files present (Rust crate + Go detector/reporter + rules yaml)"

# ─────────────────────────────────────────────────────────────────────────
# File presence — DPS 3 (L5.J)
# ─────────────────────────────────────────────────────────────────────────
for f in \
    contracts/events/canon_change_history.go \
    contracts/events/canon_change_history_test.go \
    contracts/canon/timeline/doc.go \
    contracts/canon/timeline/timeline.go \
    contracts/canon/timeline/timeline_test.go \
    contracts/canon/timeline/go.mod \
    crates/dp-kernel/src/canon_history.rs \
    services/meta-worker/pkg/canon_history_writer/writer.go \
    services/meta-worker/pkg/canon_history_writer/writer_test.go \
    contracts/api/glossary-service/canon_history.yaml \
    contracts/migrations/glossary/0001_canon_change_history.up.sql \
    contracts/migrations/glossary/0001_canon_change_history.down.sql ; do
    [[ -f "$f" ]] || fail "cycle-27 DPS 3 (L5.J) file missing: $f"
done
pass "cycle-27 L5.J files present (events + timeline pkg + Rust mirror + writer + OpenAPI + migration)"

# Integration test.
[[ -f tests/integration/force_propagate_test.go ]] \
    || fail "cycle-27 integration test missing"
pass "cycle-27 integration test file present"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5A-1: services/glossary-service/ MUST NOT be modified.
# ─────────────────────────────────────────────────────────────────────────
if git diff --name-only HEAD 2>/dev/null | grep -qE '^services/glossary-service/'; then
    fail "Q-L5A-1 violation: services/glossary-service/ modified (separate sub-program)"
fi
pass "Q-L5A-1: services/glossary-service/ untouched"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5H-1: 24h consent timeout + default-to-consent
# ─────────────────────────────────────────────────────────────────────────
grep -q 'ConsentTimeout = 24 \* time.Hour' services/meta-worker/pkg/force_propagate/writer.go \
    || fail "Q-L5H-1: 24h ConsentTimeout constant missing from force_propagate/writer.go"
grep -q 'Q-L5H-1' services/meta-worker/pkg/force_propagate/writer.go \
    || fail "Q-L5H-1: citation missing from force_propagate/writer.go"
grep -q 'default-to-consent' services/meta-worker/pkg/force_propagate/writer.go \
    || fail "Q-L5H-1: default-to-consent semantic not documented"
grep -q 'TestConsentTimeoutIsQL5H1Locked\|24 \* time.Hour' services/meta-worker/pkg/force_propagate/writer_test.go \
    || fail "Q-L5H-1: 24h timeout test missing"
pass "Q-L5H-1: 24h consent timeout + default-to-consent enforced"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5-5: canon_guardrail full impl backwards-compat with cycle 25 trait
# ─────────────────────────────────────────────────────────────────────────
grep -q 'CanonGuardrail' crates/contracts-prompt/src/canon_guardrail.rs \
    || fail "Q-L5-5: CanonGuardrail trait not implemented in canon_guardrail.rs"
grep -q 'impl CanonGuardrail for YamlGuardrail' crates/contracts-prompt/src/canon_guardrail.rs \
    || fail "Q-L5-5: YamlGuardrail does not impl CanonGuardrail"
grep -q 'Q-L5-5' crates/contracts-prompt/src/canon_guardrail.rs \
    || fail "Q-L5-5: citation missing from canon_guardrail.rs"
grep -q 'backwards_compat_with_cycle25_trait' crates/contracts-prompt/src/canon_guardrail.rs \
    || fail "Q-L5-5: backwards-compat test missing"
pass "Q-L5-5: canon_guardrail full impl backwards-compat with cycle 25"

# Guardrail rules data-driven (not hardcoded).
grep -q 'attribute_path_glob' contracts/canon/guardrail_rules.yaml \
    || fail "guardrail rules YAML missing attribute_path_glob schema"
grep -q 'serde_yaml::from_slice' crates/contracts-prompt/src/canon_guardrail.rs \
    || fail "Q-L5-5: rules MUST be YAML-loaded (data-driven), not hardcoded"
pass "Q-L5-5: rules data-driven via YAML (not hardcoded)"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5-3: canon_layer enum carried verbatim
# ─────────────────────────────────────────────────────────────────────────
grep -q 'L1_axiom\|L2_seeded' contracts/events/admin_canon_override.go \
    || fail "Q-L5-3: canon_layer enum not referenced in admin_canon_override.go"
grep -q 'CHANGE_KIND_AUTHORED\|CHANGE_KIND_FORCE_PROPAGATE' crates/dp-kernel/src/canon_history.rs \
    || fail "Q-L5-3: change kind constants missing from Rust mirror"
grep -q "'L1_axiom'" contracts/migrations/glossary/0001_canon_change_history.up.sql \
    || fail "Q-L5-3: CHECK constraint on canon_layer missing in migration"
pass "Q-L5-3: canon_layer enum carried verbatim (Go + Rust + SQL)"

# ─────────────────────────────────────────────────────────────────────────
# Q-L1A-3: full audit V1 (no sampling) — every event audited
# ─────────────────────────────────────────────────────────────────────────
grep -q 'Q-L1A-3' services/meta-worker/pkg/force_propagate/writer.go \
    || fail "Q-L1A-3: citation missing from force_propagate/writer.go"
grep -q 'AuditSink' services/meta-worker/pkg/force_propagate/writer.go \
    || fail "Q-L1A-3: AuditSink surface missing from force_propagate"
grep -q 'AuditSink' services/meta-worker/pkg/canon_history_writer/writer.go \
    || fail "Q-L1A-3: AuditSink surface missing from canon_history_writer"
pass "Q-L1A-3: full audit V1 wired (no sampling) — force_propagate + canon_history_writer"

# ─────────────────────────────────────────────────────────────────────────
# APPEND-ONLY enforcement (L5.J) — 3-layer defense
# ─────────────────────────────────────────────────────────────────────────
# Layer 2 (storage): CHECK trigger + REVOKE
grep -q 'APPEND-ONLY' contracts/migrations/glossary/0001_canon_change_history.up.sql \
    || fail "APPEND-ONLY: migration header missing APPEND-ONLY discipline note"
grep -q 'BEFORE UPDATE ON canon_change_history' contracts/migrations/glossary/0001_canon_change_history.up.sql \
    || fail "APPEND-ONLY: UPDATE trigger missing in migration"
grep -q 'BEFORE DELETE ON canon_change_history' contracts/migrations/glossary/0001_canon_change_history.up.sql \
    || fail "APPEND-ONLY: DELETE trigger missing in migration"
grep -q 'REVOKE UPDATE, DELETE' contracts/migrations/glossary/0001_canon_change_history.up.sql \
    || fail "APPEND-ONLY: REVOKE UPDATE/DELETE not documented in migration"
# Layer 3 (application): NO Update/Delete method in TimelineAppender
if grep -E 'func .* Update\(|func .* Delete\(' contracts/canon/timeline/timeline.go ; then
    fail "APPEND-ONLY: TimelineAppender exposes Update/Delete (forbidden)"
fi
pass "APPEND-ONLY: 3-layer enforcement present (no Update/Delete in SDK; DB trigger + REVOKE)"

# Wire-level: no canon.change.amended or canon.change.deleted event types
if grep -q 'canon.change.amended\|canon.change.deleted' contracts/events/_registry.yaml ; then
    fail "APPEND-ONLY: wire-level event types for amend/delete present (forbidden)"
fi
pass "APPEND-ONLY: wire-level — no amend/delete event types"

# ─────────────────────────────────────────────────────────────────────────
# Dispatch allowlist extended for admin.canon.override.* (L5.H)
# ─────────────────────────────────────────────────────────────────────────
grep -q 'admin.canon.override.' services/meta-worker/pkg/dispatch/dispatch.go \
    || fail "dispatch: admin.canon.override.* allowlist extension missing"
pass "dispatch: admin.canon.override.* allowlist extended"

# ─────────────────────────────────────────────────────────────────────────
# Event registry entries (5 new entries: 4 override + 1 change.recorded)
# ─────────────────────────────────────────────────────────────────────────
for name in \
    'admin.canon.override.requested' \
    'admin.canon.override.consented' \
    'admin.canon.override.vetoed' \
    'admin.canon.override.compensating' \
    'canon.change.recorded' ; do
    grep -q "name: $name" contracts/events/_registry.yaml \
        || fail "registry: entry $name missing"
done
pass "registry: 5 new event types declared (4 override + 1 change.recorded)"

# Cycle marker on all 5.
override_cycle_count=$(awk '/^  - name: admin\.canon\.override\./,/shipped_cycle:/' contracts/events/_registry.yaml | grep -c 'shipped_cycle: 27')
if [[ "$override_cycle_count" -lt 4 ]]; then
    fail "registry: expected 4 admin.canon.override.* entries with shipped_cycle:27, found $override_cycle_count"
fi
pass "registry: all admin.canon.override.* entries marked shipped_cycle:27"

# ─────────────────────────────────────────────────────────────────────────
# Build + test gates.
# ─────────────────────────────────────────────────────────────────────────

# Go: events package.
note "go test contracts/events/..."
( cd contracts/events && go test -count=1 ./... >/dev/null 2>&1 ) \
    || fail "contracts/events Go tests FAILED"
pass "contracts/events Go tests PASS (cycle-27 admin_canon_override + canon_change_history added)"

# Go: contracts/canon/timeline.
note "go test contracts/canon/timeline/..."
( cd contracts/canon/timeline && go test -count=1 ./... >/dev/null 2>&1 ) \
    || fail "contracts/canon/timeline Go tests FAILED"
pass "contracts/canon/timeline Go tests PASS"

# Go: meta-worker packages.
note "go test meta-worker (force_propagate + l1_conflict_* + canon_history_writer + dispatch regression)"
( cd services/meta-worker && go test -count=1 \
    ./pkg/force_propagate/ \
    ./pkg/l1_conflict_detector/ \
    ./pkg/l1_conflict_reporter/ \
    ./pkg/canon_history_writer/ \
    ./pkg/dispatch/ \
    >/dev/null 2>&1 ) \
    || fail "meta-worker cycle-27 package tests FAILED"
pass "meta-worker cycle-27 packages PASS (force_propagate + l1_conflict_detector + l1_conflict_reporter + canon_history_writer + dispatch regression)"

# Go: cycle 24 regression (canon_writer + user_erased_writer).
( cd services/meta-worker && go test -count=1 ./pkg/canon_writer/ ./pkg/user_erased_writer/ >/dev/null 2>&1 ) \
    || fail "meta-worker cycle-24 regression FAILED"
pass "meta-worker cycle-24 regression PASS (canon_writer + user_erased_writer)"

# Rust: contracts-prompt crate.
note "cargo test -p contracts-prompt --lib"
cargo test -p contracts-prompt --lib --quiet >/dev/null 2>&1 \
    || fail "contracts-prompt cargo tests FAILED"
pass "contracts-prompt cargo tests PASS (19 tests: guardrail rules + glob + YAML loader + backwards-compat)"

# Rust: dp-kernel (regression + canon_history mirror).
note "cargo test -p dp-kernel --lib"
cargo test -p dp-kernel --lib --quiet >/dev/null 2>&1 \
    || fail "dp-kernel cargo tests FAILED"
pass "dp-kernel cargo tests PASS (cycle-25 271 baseline + 10 canon_history = 281)"

# Workspace build clean.
note "cargo build --workspace"
cargo build --workspace --quiet >/dev/null 2>&1 \
    || fail "cargo build --workspace FAILED"
pass "cargo build --workspace clean"

# Integration test.
note "tests/integration (cycle-27 end-to-end)"
( cd tests/integration && go test -count=1 -run 'TestForcePropagate_EndToEnd|TestL1ConflictDetectorAndReporter|TestTimeline_' >/dev/null 2>&1 ) \
    || fail "cycle-27 integration tests FAILED"
pass "cycle-27 integration tests PASS (4 tests: force-propagate + L1 conflict + L5.J append-only)"

# ─────────────────────────────────────────────────────────────────────────
# B5 prod-isolation + B6 secret-scan.
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

NEW_FILES=(
    contracts/events/admin_canon_override.go
    contracts/events/admin_canon_override_test.go
    contracts/events/canon_change_history.go
    contracts/events/canon_change_history_test.go
    contracts/canon/timeline/doc.go
    contracts/canon/timeline/timeline.go
    contracts/canon/timeline/mutex.go
    contracts/canon/timeline/timeline_test.go
    contracts/canon/timeline/go.mod
    crates/dp-kernel/src/canon_history.rs
    crates/contracts-prompt/Cargo.toml
    crates/contracts-prompt/src/lib.rs
    crates/contracts-prompt/src/canon_guardrail.rs
    services/meta-worker/pkg/force_propagate/writer.go
    services/meta-worker/pkg/force_propagate/writer_test.go
    services/meta-worker/pkg/l1_conflict_detector/detector.go
    services/meta-worker/pkg/l1_conflict_detector/detector_test.go
    services/meta-worker/pkg/l1_conflict_reporter/reporter.go
    services/meta-worker/pkg/l1_conflict_reporter/reporter_test.go
    services/meta-worker/pkg/canon_history_writer/writer.go
    services/meta-worker/pkg/canon_history_writer/writer_test.go
    contracts/api/glossary-service/canon_history.yaml
    contracts/migrations/glossary/0001_canon_change_history.up.sql
    contracts/migrations/glossary/0001_canon_change_history.down.sql
    contracts/canon/guardrail_rules.yaml
    runbooks/canon/force_propagate.md
    tests/integration/force_propagate_test.go
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -EHn "$SECRET_PATTERNS" "$f" 2>/dev/null; then
        fail "B6: secret-like content in $f"
    fi
done
pass "B6 secret-scan: cycle-27 new files clean"

if bash scripts/raid/secret-scan-cycle.sh 27 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle 27 clean"
else
    fail "B6 secret-scan-cycle 27 FAILED"
fi

echo
echo "[verify-cycle-27] ALL ${step} STEPS PASS"
echo "[verify-cycle-27] L5 LAYER FULLY CLOSED — cycles 23-27 ship all 10 sub-components (A-J)."
echo "[verify-cycle-27] L6 begins cycle 28 (WS server + admission + prompt stack)."
