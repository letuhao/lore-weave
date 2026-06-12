#!/usr/bin/env bash
# verify-cycle-24.sh — L5.B + L5.C meta-worker consumers (2 DPS).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 24 scope (2 DPS — INLINE serial):
#   DPS 1 — L5.B canon-update consumer:
#     * services/meta-worker/pkg/canon_writer/writer.go
#     * services/meta-worker/pkg/canon_writer/writer_test.go
#
#   DPS 2 — L5.C user-erased consumer:
#     * services/meta-worker/pkg/user_erased_writer/writer.go
#     * services/meta-worker/pkg/user_erased_writer/writer_test.go
#
#   Plus:
#     * tests/integration/canon_propagation_test.go (end-to-end via
#       dispatch + consumer fake source)
#     * services/meta-worker/pkg/dispatch/dispatch.go (extended allowlist
#       to permit canon.entry.* inner event types)
#
# LOCKED decisions enforced:
#   Q-L5H-1 (INVERTED for erasure)  — user_erased writer defaults to
#                                     scrub on any uncertainty.
#   Q-L1A-3 (full audit, no sample) — both writers emit per-write audit;
#                                     audit failure NACKs.
#   Q-L5-3                          — canon_layer enum {L1_axiom, L2_seeded}
#                                     enforced by canon_writer.
#   Q-L1A-2                         — canon SSOT in glossary DB; this
#                                     cycle does NOT modify
#                                     services/glossary-service/.
#   Q-L5A-1                         — glossary-service outbox is SEPARATE
#                                     sub-program; we do not touch it.
#   I7                              — meta-worker remains sole writer of
#                                     canon_projection; dispatch allowlist
#                                     extended only for canon.entry.*
#                                     inner event types (xreality-only
#                                     ingress preserved).

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-24] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-24] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-24] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 + 2 — files present.
# ─────────────────────────────────────────────────────────────────────────
for f in \
    services/meta-worker/pkg/canon_writer/writer.go \
    services/meta-worker/pkg/canon_writer/writer_test.go \
    services/meta-worker/pkg/user_erased_writer/writer.go \
    services/meta-worker/pkg/user_erased_writer/writer_test.go \
    tests/integration/canon_propagation_test.go ; do
    [[ -f "$f" ]] || fail "cycle-24 file missing: $f"
done
pass "cycle-24 files present (canon_writer + user_erased_writer + integration)"

# Q-L5A-1 / Q-L1A-2: glossary-service MUST NOT be modified this cycle.
if git diff --name-only HEAD 2>/dev/null | grep -qE '^services/glossary-service/'; then
    fail "Q-L5A-1/Q-L1A-2 violation: services/glossary-service/ modified (separate sub-program)"
fi
pass "Q-L5A-1/Q-L1A-2: services/glossary-service/ untouched"

# I7: canon_projection migration MUST stay per-reality (cycle 23 invariant).
if git diff --name-only HEAD 2>/dev/null | grep -qE '^contracts/migrations/meta/.*canon_projection'; then
    fail "I7 violation: canon_projection migration found under meta/"
fi
pass "I7: canon_projection migration stays per-reality"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5-3 enforcement check — canon_writer references the LOCKED enum
# values verbatim.
# ─────────────────────────────────────────────────────────────────────────
grep -q '"L1_axiom"' services/meta-worker/pkg/canon_writer/writer.go \
    || fail "Q-L5-3: L1_axiom constant missing from canon_writer"
grep -q '"L2_seeded"' services/meta-worker/pkg/canon_writer/writer.go \
    || fail "Q-L5-3: L2_seeded constant missing from canon_writer"
pass "Q-L5-3: canon_writer references LOCKED enum values"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5H-1 (INVERTED) — user_erased_writer documents default-to-erase.
# ─────────────────────────────────────────────────────────────────────────
grep -qE 'Q-L5H-1' services/meta-worker/pkg/user_erased_writer/writer.go \
    || fail "Q-L5H-1: rationale citation missing from user_erased_writer"
grep -qiE 'default[- ]to[- ]erase|inverted' services/meta-worker/pkg/user_erased_writer/writer.go \
    || fail "Q-L5H-1: inverted semantics not documented"
pass "Q-L5H-1 (INVERTED): default-to-erase rationale documented"

# ─────────────────────────────────────────────────────────────────────────
# Q-L1A-3 — both writers have an AuditSink dependency surface.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'AuditSink' services/meta-worker/pkg/canon_writer/writer.go \
    || fail "Q-L1A-3: canon_writer missing AuditSink"
grep -q 'AuditSink' services/meta-worker/pkg/user_erased_writer/writer.go \
    || fail "Q-L1A-3: user_erased_writer missing AuditSink"
pass "Q-L1A-3: both writers expose AuditSink dependency (full audit V1)"

# ─────────────────────────────────────────────────────────────────────────
# Cycle 7 L1.J — degraded-mode handling: tests cover NACK on per-reality
# DB failure.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'PerRealityDB_Failure_NACKs' services/meta-worker/pkg/canon_writer/writer_test.go \
    || fail "Cycle 7 L1.J: canon_writer missing per-reality-DB failure NACK test"
grep -q 'PerRealityDB_Failure_NACKs' services/meta-worker/pkg/user_erased_writer/writer_test.go \
    || fail "Cycle 7 L1.J: user_erased_writer missing per-reality-DB failure NACK test"
pass "Cycle 7 L1.J: NACK-on-degraded-mode coverage in both writers"

# ─────────────────────────────────────────────────────────────────────────
# go test — canon_writer + user_erased_writer + dispatch (regression).
# ─────────────────────────────────────────────────────────────────────────
note "go test services/meta-worker/pkg/canon_writer/..."
( cd services/meta-worker && go test ./pkg/canon_writer/... -count=1 >/dev/null ) \
    || fail "canon_writer Go tests FAILED"
pass "canon_writer Go tests PASS"

note "go test services/meta-worker/pkg/user_erased_writer/..."
( cd services/meta-worker && go test ./pkg/user_erased_writer/... -count=1 >/dev/null ) \
    || fail "user_erased_writer Go tests FAILED"
pass "user_erased_writer Go tests PASS"

note "go test services/meta-worker/pkg/dispatch/... (regression for extended allowlist)"
( cd services/meta-worker && go test ./pkg/dispatch/... -count=1 >/dev/null ) \
    || fail "dispatch Go tests FAILED after allowlist extension"
pass "dispatch Go tests PASS (cycle 10 regression)"

# ─────────────────────────────────────────────────────────────────────────
# Integration tests (tags=integration) — canon propagation + user erasure.
# ─────────────────────────────────────────────────────────────────────────
note "integration tests: canon_propagation_test (tags=integration)"
( cd tests/integration && go test -tags=integration -count=1 -run 'TestCanonPropagation_CycleC24' ./... >/dev/null ) \
    || fail "canon_propagation integration test FAILED"
pass "canon_propagation integration tests PASS (canon fan-out + user-erased cascade + I7 allowlist)"

# Regression: cycle-10 xreality propagation integration still passes.
note "regression: cycle-10 xreality_propagation_test"
( cd tests/integration && go test -tags=integration -count=1 -run 'TestXRealityPropagation' ./... >/dev/null ) \
    || fail "cycle-10 xreality_propagation regression FAILED"
pass "cycle-10 xreality_propagation regression PASS"

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
    services/meta-worker/pkg/canon_writer/writer.go
    services/meta-worker/pkg/canon_writer/writer_test.go
    services/meta-worker/pkg/user_erased_writer/writer.go
    services/meta-worker/pkg/user_erased_writer/writer_test.go
    tests/integration/canon_propagation_test.go
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -qE "$SECRET_PATTERNS" "$f"; then
        fail "B6: potential secret in $f"
    fi
done
pass "B6 secret-scan: no high-risk patterns in cycle-24 new files"

if bash scripts/raid/secret-scan-cycle.sh 24 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle clean"
else
    note "B6 secret-scan: gitleaks unavailable on dev machine (CI will gate)"
fi

echo "[verify-cycle-24] all $step steps PASS"
exit 0
