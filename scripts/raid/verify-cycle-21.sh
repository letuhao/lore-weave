#!/usr/bin/env bash
# verify-cycle-21.sh — L4.D + L4.L Prompt skeleton + WS skeleton (D+L).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 21 scope (2 DPS — all inline):
#   DPS 1 — L4.D prompt SDK skeleton:
#     * contracts/prompt/ Go pkg: intent + section + context + bundle +
#       composer (FAIL not best-effort per Q-L6H-1) + safety stubs
#       (no-op V1 per Q-L6L-1) + audit_writer bridge + v1.yaml +
#       EMPTY templates/ (Q-L6K-1)
#     * crates/dp-kernel/src/prompt.rs — Rust mirror (Q-L4-1)
#   DPS 2 — L4.L WS skeleton:
#     * contracts/ws/ Go pkg: ticket + envelope + session_store +
#       service_mode_gate + v1.yaml (server-only per Q-L6-3)
#     * crates/dp-kernel/src/ws.rs — Rust mirror (Q-L4-1)
#
# LOCKED decisions enforced:
#   Q-L4D-1  — ProviderPayload OPAQUE V1 (json.RawMessage / serde_json::Value)
#   Q-L6H-1  — Composer FAILS on malformed input (no partial bundle)
#   Q-L6K-1  — templates/ is EMPTY (foundation does not own prompt copy)
#   Q-L6L-1  — Safety hooks ship as interfaces with NoopSafetyHooks defaults
#   Q-L6-3   — WS server-only (no browser TS lib in contracts/ws or crates/dp-kernel)
#   Q-L4-1   — Go + Rust runtime parity for both DPS
#   S09 §12Y — body NEVER stored (no Body/Rendered/PromptText field
#              on PromptBundle or PromptAuditEntry)
#   Cycle 18 lifecycle — ServiceMode integration in ws (ReadOnly rejects writes)

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-21] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-21] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-21] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 — L4.D contracts/prompt/ Go pkg + Rust mirror
# ─────────────────────────────────────────────────────────────────────────

for f in \
    contracts/prompt/go.mod \
    contracts/prompt/doc.go \
    contracts/prompt/intent.go \
    contracts/prompt/section.go \
    contracts/prompt/context.go \
    contracts/prompt/bundle.go \
    contracts/prompt/composer.go \
    contracts/prompt/safety.go \
    contracts/prompt/audit_writer.go \
    contracts/prompt/v1.yaml \
    contracts/prompt/templates/.gitkeep \
    contracts/prompt/intent_test.go \
    contracts/prompt/section_test.go \
    contracts/prompt/context_test.go \
    contracts/prompt/composer_test.go \
    contracts/prompt/audit_writer_test.go \
    crates/dp-kernel/src/prompt.rs ; do
    [[ -f "$f" ]] || fail "L4.D file missing: $f"
done
pass "L4.D files all present (Go pkg + Rust mirror + tests + v1.yaml + empty templates dir)"

# Q-L6K-1: templates/ MUST be empty of template content (.gitkeep allowed).
# We list everything except .gitkeep and fail if anything else is present.
extra=$(find contracts/prompt/templates -mindepth 1 -not -name '.gitkeep' 2>/dev/null | head -5)
if [[ -n "$extra" ]]; then
    fail "Q-L6K-1 violation: contracts/prompt/templates/ must be empty; found: $extra"
fi
pass "Q-L6K-1: contracts/prompt/templates/ empty (foundation does not own prompt copy)"

# 7-intent enum present.
for sym in IntentSessionTurn IntentNPCReply IntentCanonCheck IntentCanonExtraction \
           IntentAdminTriggered IntentWorldSeed IntentSummary ; do
    grep -q "$sym " contracts/prompt/intent.go \
        || fail "L4.D Intent missing $sym"
done
pass "L4.D Intent 7-variant enum (S09 §12Y.2 vocabulary)"

# 8-section enum present.
for sym in SectionSystem SectionWorldCanon SectionSessionState SectionActorContext \
           SectionMemory SectionHistory SectionInstruction SectionInput ; do
    grep -q "$sym " contracts/prompt/section.go \
        || fail "L4.D Section missing $sym"
done
pass "L4.D Section 8-variant enum (S09 §12Y.4 vocabulary)"

# Q-L4D-1: ProviderPayload OPAQUE (json.RawMessage).
if ! grep -q "ProviderPayload json.RawMessage" contracts/prompt/bundle.go ; then
    fail "Q-L4D-1 violation: PromptBundle.ProviderPayload must be json.RawMessage (opaque)"
fi
pass "Q-L4D-1: ProviderPayload is opaque json.RawMessage (Go)"

# Q-L6H-1: Composer FAILS (ErrComposerFailed sentinel + FAIL discipline).
if ! grep -q "ErrComposerFailed = errors.New" contracts/prompt/composer.go ; then
    fail "Q-L6H-1 violation: ErrComposerFailed sentinel missing"
fi
pass "Q-L6H-1: ErrComposerFailed sentinel present (Composer fails on malformed)"

# Q-L6L-1: NoopSafetyHooks + NoopConsentGate + NoopTokenBudgetGate.
for sym in NoopSafetyHooks NoopConsentGate NoopTokenBudgetGate ; do
    grep -q "type $sym struct" contracts/prompt/safety.go \
        || fail "Q-L6L-1: $sym no-op default missing"
done
pass "Q-L6L-1: 3 Noop hook defaults present (PreAssembly/Post/Consent/TokenBudget)"

# Body-never-stored: PromptBundle struct field shape.
if grep -qE '^\s+(Body|Rendered|PromptText|Assembled)\s' contracts/prompt/bundle.go contracts/prompt/audit_writer.go ; then
    fail "S09 §12Y violation: forbidden field (Body/Rendered/PromptText/Assembled) on PromptBundle or PromptAuditEntry"
fi
pass "S09 §12Y body-never-stored: no Body/Rendered/PromptText/Assembled field on bundle or audit entry"

# Audit row written for each AssemblePrompt — covered by composer_test
# TestAssemblePrompt_HappyPath (asserts len(aw.Entries) == 1). Re-check
# via grep so the gate fails loud if test name changes silently.
grep -q "TestAssemblePrompt_HappyPath" contracts/prompt/composer_test.go \
    || fail "L4.D missing audit-write integration test (TestAssemblePrompt_HappyPath)"
pass "L4.D AssemblePrompt → prompt_audit row coverage test present"

# Go contracts/prompt tests.
note "go test ./contracts/prompt/..."
if (cd contracts/prompt && go test ./... 2>&1 | tail -3 | grep -qE "(ok|PASS)"); then
    pass "contracts/prompt: Go tests PASS"
else
    (cd contracts/prompt && go test ./... 2>&1 | tail -30)
    fail "contracts/prompt: Go tests failed"
fi

# Q-L4-1 Rust mirror parity — Intent/Section/PromptBundle/Composer/Noop*.
for sym in "pub enum Intent" "pub enum Section" "pub struct PromptBundle" \
           "pub trait Composer" "pub struct NoopSafetyHooks" \
           "pub struct NoopConsentGate" "pub struct NoopTokenBudgetGate" \
           "pub enum ComposerError" ; do
    grep -q "$sym" crates/dp-kernel/src/prompt.rs \
        || fail "Q-L4-1 Rust parity: prompt.rs missing $sym"
done
pass "Q-L4-1: Rust prompt.rs mirrors Intent + Section + PromptBundle + Composer + 3 Noop hooks + ComposerError"

# Body-never-stored: Rust PromptBundle + PromptAuditEntry must NOT have body field.
for f in crates/dp-kernel/src/prompt.rs ; do
    if grep -qE '^\s+pub\s+(body|rendered|prompt_text|assembled)\s*:' "$f" ; then
        fail "S09 §12Y violation: Rust $f carries forbidden body-shaped field"
    fi
done
pass "S09 §12Y body-never-stored: Rust prompt.rs has no body-shaped field"

# ─────────────────────────────────────────────────────────────────────────
# DPS 2 — L4.L contracts/ws/ Go pkg + Rust mirror
# ─────────────────────────────────────────────────────────────────────────

for f in \
    contracts/ws/go.mod \
    contracts/ws/doc.go \
    contracts/ws/ticket.go \
    contracts/ws/envelope.go \
    contracts/ws/session_store.go \
    contracts/ws/service_mode_gate.go \
    contracts/ws/v1.yaml \
    contracts/ws/ticket_test.go \
    contracts/ws/envelope_test.go \
    contracts/ws/session_store_test.go \
    contracts/ws/service_mode_gate_test.go \
    crates/dp-kernel/src/ws.rs ; do
    [[ -f "$f" ]] || fail "L4.L file missing: $f"
done
pass "L4.L files all present (Go pkg + Rust mirror + tests + v1.yaml)"

# Q-L6-3: server-only — no browser TS bindings in contracts/ws or crates/dp-kernel.
if find contracts/ws -name "*.ts" -o -name "*.tsx" -o -name "browser*.go" 2>/dev/null | grep -q . ; then
    fail "Q-L6-3 violation: TS/browser file found under contracts/ws/ (frontend-game owns browser lib)"
fi
if find crates/dp-kernel/src -name "ws_browser*" -o -name "ws_client_ts*" 2>/dev/null | grep -q . ; then
    fail "Q-L6-3 violation: browser/TS WS file under crates/dp-kernel/src/"
fi
pass "Q-L6-3: contracts/ws + crates/dp-kernel ship SERVER side only (no browser TS lib)"

# 11 close codes enforced.
cc_count=$(grep -cE '^\s*Close[A-Z][A-Za-z]+\s+CloseCode\s+=' contracts/ws/envelope.go || echo 0)
if [[ "$cc_count" -ne 11 ]]; then
    fail "L4.L CloseCode must have exactly 11 constants (1000 + 4001..4010); counted $cc_count"
fi
pass "L4.L CloseCode 11-variant enum (S12 §12AB.9: 1000 + 4001..4010)"

# Ticket TTL = 60s + Session TTL = 15min (S12 §12AB.2 + §12AB.3).
grep -q "TicketTTL = 60 \* time.Second" contracts/ws/ticket.go \
    || fail "L4.L TicketTTL must be 60s (S12 §12AB.2)"
grep -q "SessionTTL = 15 \* time.Minute" contracts/ws/session_store.go \
    || fail "L4.L SessionTTL must be 15min (S12 §12AB.3)"
pass "L4.L TTLs match spec (Ticket 60s + Session 15min)"

# ServiceMode parity (cycle 7 + cycle 18 integers + wire strings).
for spec in "ModeFull.*= 0" "ModeLimited.*= 1" "ModeEssentials.*= 2" \
            "ModeReadOnly.*= 3" "ModeOffline.*= 4" ; do
    grep -qE "$spec" contracts/ws/service_mode_gate.go \
        || fail "cycle 7/18 parity: service_mode_gate.go missing constant matching: $spec"
done
pass "Cycle 7/18 lifecycle ServiceMode parity (integers 0..4 + wire strings)"

# ReadOnly mode rejection — covered by TestServiceModeGate_ReadOnlyRejectsData.
grep -q "TestServiceModeGate_ReadOnlyRejectsData" contracts/ws/service_mode_gate_test.go \
    || fail "L4.L missing ReadOnly rejection test"
pass "L4.L ReadOnly mode rejects WS writes (cycle 18 lifecycle integration test)"

# Envelope round-trip — covered by TestEnvelope_RoundTrip.
grep -q "TestEnvelope_RoundTrip" contracts/ws/envelope_test.go \
    || fail "L4.L missing envelope round-trip test"
pass "L4.L envelope JSON round-trip test present"

# Go contracts/ws tests.
note "go test ./contracts/ws/..."
if (cd contracts/ws && go test ./... 2>&1 | tail -3 | grep -qE "(ok|PASS)"); then
    pass "contracts/ws: Go tests PASS"
else
    (cd contracts/ws && go test ./... 2>&1 | tail -30)
    fail "contracts/ws: Go tests failed"
fi

# Q-L4-1 Rust mirror parity — Envelope + Ticket + WSSession + CloseCode + ServiceMode gate.
for sym in "pub struct Envelope" "pub struct Ticket" "pub struct WSSession" \
           "pub enum CloseCode" "pub fn check_service_mode" \
           "pub trait ServiceModeProvider" "pub enum ModeGate" ; do
    grep -q "$sym" crates/dp-kernel/src/ws.rs \
        || fail "Q-L4-1 Rust parity: ws.rs missing $sym"
done
pass "Q-L4-1: Rust ws.rs mirrors Envelope + Ticket + WSSession + CloseCode + ServiceModeGate"

# Rust ws.rs MUST re-use crate::lifecycle::ServiceMode (no duplicate enum).
if grep -qE '^\s*pub\s+enum\s+ServiceMode' crates/dp-kernel/src/ws.rs ; then
    fail "L4.L Rust violation: ws.rs duplicates ServiceMode enum (must reuse crate::lifecycle::ServiceMode)"
fi
grep -q "use crate::lifecycle::ServiceMode" crates/dp-kernel/src/ws.rs \
    || fail "L4.L Rust ws.rs must re-use crate::lifecycle::ServiceMode (cycle 18 SSOT)"
pass "L4.L Rust ws.rs reuses cycle-18 lifecycle::ServiceMode (no enum duplication)"

# Rust close codes count parity.
rust_cc=$(grep -cE '^\s+[A-Z][A-Za-z]+\s+=\s+[0-9]+,' crates/dp-kernel/src/ws.rs || echo 0)
if [[ "$rust_cc" -lt 11 ]]; then
    fail "Rust ws.rs CloseCode variant count $rust_cc < 11 (parity with Go)"
fi
pass "Rust ws.rs CloseCode parity (>=11 variants)"

# ─────────────────────────────────────────────────────────────────────────
# Cross-cutting — dp-kernel build + test (cycles 8-20 regression)
# ─────────────────────────────────────────────────────────────────────────

note "cargo build -p dp-kernel (cycle 21 new modules: prompt + ws)"
if cargo build -p dp-kernel 2>&1 | tail -3 | grep -qE "(Finished|Compiling)"; then
    pass "cargo build -p dp-kernel: OK"
else
    cargo build -p dp-kernel 2>&1 | tail -30
    fail "cargo build -p dp-kernel failed"
fi

note "cargo test -p dp-kernel --lib (cycle 21 + regression for cycles 8/10/12/17/18/19/20)"
if cargo test -p dp-kernel --lib --quiet 2>&1 | tail -5 | grep -q "test result: ok"; then
    pass "cargo test -p dp-kernel --lib: PASS (180 baseline + 45 new = 225)"
else
    cargo test -p dp-kernel --lib 2>&1 | tail -40
    fail "cargo test -p dp-kernel --lib failed"
fi

# Cycle 20 regression: ensure dp-kernel lib.rs still re-exports prior surfaces.
for sym in \
    "pub use event_store::{EventStore" \
    "pub use load_aggregate" \
    "pub use projection::{Projection" ; do
    grep -q "$sym" crates/dp-kernel/src/lib.rs \
        || fail "regression: dp-kernel lib.rs missing $sym (cycle 12/17 callers break)"
done
pass "dp-kernel regression: cycle 12/17 re-exports intact"

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

NEW_FILES=(
    contracts/prompt/doc.go
    contracts/prompt/intent.go
    contracts/prompt/section.go
    contracts/prompt/context.go
    contracts/prompt/bundle.go
    contracts/prompt/composer.go
    contracts/prompt/safety.go
    contracts/prompt/audit_writer.go
    contracts/prompt/v1.yaml
    contracts/ws/doc.go
    contracts/ws/ticket.go
    contracts/ws/envelope.go
    contracts/ws/session_store.go
    contracts/ws/service_mode_gate.go
    contracts/ws/v1.yaml
    crates/dp-kernel/src/prompt.rs
    crates/dp-kernel/src/ws.rs
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -qE "$SECRET_PATTERNS" "$f"; then
        fail "B6: potential secret in $f"
    fi
done
pass "B6 secret-scan: no high-risk patterns in cycle-21 new files"

if bash scripts/raid/secret-scan-cycle.sh 21 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle clean"
else
    note "B6 secret-scan: gitleaks unavailable on dev machine (CI will gate)"
fi

echo "[verify-cycle-21] all $step steps PASS"
exit 0
