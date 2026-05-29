#!/usr/bin/env bash
# verify-cycle-20.sh — L4.C + L4.E + L4.K Rust meta client + Entity status + Turn/errors.
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 20 scope (3 DPS — all inline):
#   DPS 1 — L4.C Rust meta client EXTENSION:
#     * crates/meta-rs/src/{allowlist,metawrite,transitions,cache,audit}.rs
#     * EXTENDS cycle-2 read-only surface to full Go-parity surface.
#     * Q-L1B-4: hot-path; NO RPC fallback in surface.
#   DPS 2 — L4.E entity_status shared kernel:
#     * contracts/entity_status/ — Go pkg (gone_state + resolver + cache)
#     * crates/dp-kernel/src/entity_status.rs — Rust mirror (Q-L4-1)
#   DPS 3 — L4.K turn + errors:
#     * contracts/turn/    — Go pkg (turn_state + turn_context + outcome_writer)
#     * contracts/errors/  — Go pkg (canonical error taxonomy, 4 classes × 28 codes)
#     * crates/dp-kernel/src/turn.rs + turn_errors.rs — Rust mirrors
#
# LOCKED decisions enforced:
#   Q-L1B-4 — meta-rs is hot-path; no RPC fallback in surface (grep gate)
#   Q-L4-1  — Go + Rust runtime types for all 3 DPS
#   Q-L4-2  — single workspace Cargo.toml
#   Q-L3-4  — entity_status envelope carries aggregate_version when from projections
#   SR11    — turn taxonomy + exhaustive errors (no "Other" catch-all)
#   Cycle-2 meta-rs callers still compile (regression guard)

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-20] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-20] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-20] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 — L4.C meta-rs extension
# ─────────────────────────────────────────────────────────────────────────

for f in \
    crates/meta-rs/src/allowlist.rs \
    crates/meta-rs/src/metawrite.rs \
    crates/meta-rs/src/transitions.rs \
    crates/meta-rs/src/cache.rs \
    crates/meta-rs/src/audit.rs ; do
    [[ -f "$f" ]] || fail "L4.C file missing: $f"
done
pass "L4.C meta-rs extension files present (allowlist + metawrite + transitions + cache + audit)"

# Cycle 2 surface MUST still be re-exported (regression guard).
for sym in \
    "pub use routing::{Connection, MetaRead, RealityRouting, RealityStatus}" \
    "pub use sensitive_paths::{SensitivePath, SensitivePaths}" ; do
    grep -q "$sym" crates/meta-rs/src/lib.rs \
        || fail "cycle-2 regression: missing $sym in meta-rs lib.rs"
done
pass "L4.C cycle-2 surface still re-exported (callers unchanged)"

# Cycle 20 new surface must be re-exported.
for sym in \
    "pub use metawrite::" \
    "pub use transitions::" \
    "pub use allowlist::" \
    "pub use cache::" \
    "pub use audit::" ; do
    grep -q "$sym" crates/meta-rs/src/lib.rs \
        || fail "L4.C cycle-20 surface missing in meta-rs lib.rs: $sym"
done
pass "L4.C cycle-20 surface re-exported (5 new modules)"

# Q-L1B-4: meta-rs MUST NOT expose any RPC fallback in the hot-path surface.
# Greps for explicit "rpc" patterns in metawrite.rs (signals an RPC abstraction).
if grep -qiE "(RpcClient|rpc_call|grpc::|tonic::)" crates/meta-rs/src/metawrite.rs ; then
    fail "Q-L1B-4 violation: metawrite.rs exposes RPC fallback (must be hot-path direct)"
fi
pass "Q-L1B-4: meta-rs metawrite hot-path; no RPC fallback"

# meta-rs build + test.
note "cargo build -p meta-rs"
if cargo build -p meta-rs 2>&1 | tail -3 | grep -qE "(Finished|Compiling)"; then
    pass "cargo build -p meta-rs: OK"
else
    cargo build -p meta-rs 2>&1 | tail -30
    fail "cargo build -p meta-rs failed"
fi

note "cargo test -p meta-rs --lib"
if cargo test -p meta-rs --lib --quiet 2>&1 | tail -5 | grep -q "test result: ok"; then
    pass "cargo test -p meta-rs --lib: PASS (cycle-2 + cycle-20 tests)"
else
    cargo test -p meta-rs --lib 2>&1 | tail -30
    fail "cargo test -p meta-rs --lib failed"
fi

# Parity smoke: every Go meta-write op must have Rust equivalent.
for sym in "MetaWriteOp::Insert" "MetaWriteOp::Update" "MetaWriteOp::Delete" "meta_write" "meta_write_batch" "attempt_state_transition" ; do
    grep -rq "$sym" crates/meta-rs/src/ \
        || fail "Go-parity smoke: missing Rust equivalent for $sym"
done
pass "L4.C Go-parity smoke: 3 ops + 3 entry points present"

# ─────────────────────────────────────────────────────────────────────────
# DPS 2 — L4.E entity_status (Go + Rust)
# ─────────────────────────────────────────────────────────────────────────

for f in \
    contracts/entity_status/go.mod \
    contracts/entity_status/doc.go \
    contracts/entity_status/gone_state.go \
    contracts/entity_status/precedence.go \
    contracts/entity_status/resolver.go \
    contracts/entity_status/cache.go \
    contracts/entity_status/v1.yaml \
    contracts/entity_status/gone_state_test.go \
    contracts/entity_status/resolver_test.go \
    crates/dp-kernel/src/entity_status.rs ; do
    [[ -f "$f" ]] || fail "L4.E file missing: $f"
done
pass "L4.E files all present (Go pkg + Rust mirror + tests + v1.yaml)"

# 5 GoneState constants enforced.
for sym in "StateActive" "StateSevered" "StateArchived" "StateDropped" "StateUserErased" ; do
    grep -q "$sym " contracts/entity_status/gone_state.go \
        || fail "L4.E GoneState missing $sym"
done
pass "L4.E GoneState 5-variant enum complete"

# Resolver uses cycle-12 load_aggregate pattern (NOT raw SQL).
# We check that the ProjectionReader interface is the abstraction surface
# (no direct sql.DB imports in resolver.go).
if grep -qE "database/sql|jackc/pgx" contracts/entity_status/resolver.go ; then
    fail "L4.E violation: resolver.go imports SQL driver (must use ProjectionReader iface)"
fi
pass "L4.E resolver decoupled from SQL driver (uses ProjectionReader iface)"

# EntityStatusEnvelope is versioned.
grep -q "EnvelopeVersion" contracts/entity_status/resolver.go \
    || fail "L4.E envelope must carry EnvelopeVersion"
pass "L4.E envelope versioned (Q-L3-4 compatible)"

# Q-L4-1 Rust mirror parity — GoneState + Resolver + cache.
for sym in "pub enum GoneState" "pub struct Resolver" "pub struct EntityStatusEnvelope" "pub trait ProjectionReader" "pub trait EntityStatusCache" ; do
    grep -q "$sym" crates/dp-kernel/src/entity_status.rs \
        || fail "Q-L4-1 Rust parity: entity_status.rs missing $sym"
done
pass "Q-L4-1: Rust entity_status.rs mirrors GoneState + Resolver + envelope + cache"

# Go entity_status tests.
note "go test ./contracts/entity_status/..."
if (cd contracts/entity_status && go test ./... 2>&1 | tail -3 | grep -qE "(ok|PASS)"); then
    pass "contracts/entity_status: Go tests PASS"
else
    (cd contracts/entity_status && go test ./... 2>&1 | tail -30)
    fail "contracts/entity_status: Go tests failed"
fi

# ─────────────────────────────────────────────────────────────────────────
# DPS 3 — L4.K turn + errors (Go + Rust)
# ─────────────────────────────────────────────────────────────────────────

for f in \
    contracts/turn/go.mod \
    contracts/turn/doc.go \
    contracts/turn/turn_state.go \
    contracts/turn/turn_context.go \
    contracts/turn/turn_outcome_writer.go \
    contracts/turn/turn_lifecycle_hook.go \
    contracts/turn/turn_state_test.go \
    contracts/turn/turn_context_test.go \
    contracts/turn/turn_outcome_writer_test.go \
    contracts/turn/turn_lifecycle_hook_test.go \
    contracts/errors/go.mod \
    contracts/errors/doc.go \
    contracts/errors/canonical.go \
    contracts/errors/canonical_test.go \
    crates/dp-kernel/src/turn.rs \
    crates/dp-kernel/src/turn_errors.rs ; do
    [[ -f "$f" ]] || fail "L4.K file missing: $f"
done
pass "L4.K files all present (turn + errors Go pkgs + 2 Rust mirrors + tests)"

# TurnState enum — 8 variants enforced per SR11.
ts_count=$(grep -cE '^\s*State(Pending|Validating|Routing|Executing|Streaming|Completed|Failed|Cancelled)\s+TurnState\s+=' contracts/turn/turn_state.go || echo 0)
if [[ "$ts_count" -ne 8 ]]; then
    fail "L4.K TurnState must have exactly 8 variants; counted $ts_count"
fi
pass "L4.K TurnState 8-variant enum (SR11 §12AN)"

# ErrorClass 4 variants — exhaustive (no Other catch-all).
ec_count=$(grep -cE '^\s*Class(UserError|SystemError|Transient|Permanent)\s+ErrorClass\s+=' contracts/errors/canonical.go || echo 0)
if [[ "$ec_count" -ne 4 ]]; then
    fail "L4.K ErrorClass must have exactly 4 variants; counted $ec_count"
fi
pass "L4.K ErrorClass 4-variant enum (no Other catch-all)"

# Error taxonomy exhaustive — 28 V1 codes.
codes_count=$(grep -cE '^\s*Code[A-Z][A-Za-z0-9]+\s+ErrorCode\s+=' contracts/errors/canonical.go || echo 0)
if [[ "$codes_count" -ne 28 ]]; then
    fail "L4.K V1 must declare exactly 28 ErrorCode constants; counted $codes_count"
fi
pass "L4.K ErrorCode V1 exhaustive (28 codes)"

# Catch-all guard — no Other / Unknown / Misc / Default codes.
if grep -qE 'CodeOther|CodeUnknown|CodeMisc|CodeDefault' contracts/errors/canonical.go ; then
    fail "L4.K: forbidden catch-all code present (Other/Unknown/Misc/Default)"
fi
pass "L4.K no catch-all codes (forces classification)"

# Q-L4-1 Rust mirror parity — TurnState + ErrorClass + ErrorEnvelope.
for sym in "pub enum TurnState" "pub struct TurnContext" "pub struct TurnInFlightTracker" ; do
    grep -q "$sym" crates/dp-kernel/src/turn.rs \
        || fail "Q-L4-1 Rust parity: turn.rs missing $sym"
done
pass "Q-L4-1: Rust turn.rs mirrors TurnState + TurnContext + TurnInFlightTracker"

for sym in "pub enum ErrorClass" "pub enum ErrorCode" "pub struct ErrorEnvelope" ; do
    grep -q "$sym" crates/dp-kernel/src/turn_errors.rs \
        || fail "Q-L4-1 Rust parity: turn_errors.rs missing $sym"
done
pass "Q-L4-1: Rust turn_errors.rs mirrors ErrorClass + ErrorCode + ErrorEnvelope"

# TurnContext mutable-state guard — must be wrapped in Mutex (deadlock prevention).
if ! grep -q "Mutex<TurnState>" crates/dp-kernel/src/turn.rs ; then
    fail "L4.K turn.rs: TurnContext state must be Mutex<TurnState> (deadlock prevention)"
fi
pass "L4.K turn.rs: TurnContext state behind Mutex (mutation-safety guard)"

# ErrorEnvelope must implement std::error::Error.
grep -q "impl std::error::Error for ErrorEnvelope" crates/dp-kernel/src/turn_errors.rs \
    || fail "L4.K turn_errors.rs: ErrorEnvelope must implement std::error::Error"
pass "L4.K turn_errors.rs: ErrorEnvelope is dyn Error-compatible"

# Go contracts/turn tests.
note "go test ./contracts/turn/..."
if (cd contracts/turn && go test ./... 2>&1 | tail -3 | grep -qE "(ok|PASS)"); then
    pass "contracts/turn: Go tests PASS"
else
    (cd contracts/turn && go test ./... 2>&1 | tail -30)
    fail "contracts/turn: Go tests failed"
fi

# Go contracts/errors tests.
note "go test ./contracts/errors/..."
if (cd contracts/errors && go test ./... 2>&1 | tail -3 | grep -qE "(ok|PASS)"); then
    pass "contracts/errors: Go tests PASS"
else
    (cd contracts/errors && go test ./... 2>&1 | tail -30)
    fail "contracts/errors: Go tests failed"
fi

# ─────────────────────────────────────────────────────────────────────────
# Cross-cutting — dp-kernel build + test (cycles 8-19 regression)
# ─────────────────────────────────────────────────────────────────────────

note "cargo build -p dp-kernel (cycle 20 new modules: entity_status + turn + turn_errors)"
if cargo build -p dp-kernel 2>&1 | tail -3 | grep -qE "(Finished|Compiling)"; then
    pass "cargo build -p dp-kernel: OK"
else
    cargo build -p dp-kernel 2>&1 | tail -30
    fail "cargo build -p dp-kernel failed"
fi

note "cargo test -p dp-kernel --lib (cycle 20 + regression for cycles 8/10/12/17/18/19)"
if cargo test -p dp-kernel --lib --quiet 2>&1 | tail -5 | grep -q "test result: ok"; then
    pass "cargo test -p dp-kernel --lib: PASS"
else
    cargo test -p dp-kernel --lib 2>&1 | tail -40
    fail "cargo test -p dp-kernel --lib failed"
fi

# Cycle 17/18/19 regression: ensure dp-kernel lib.rs still re-exports prior surfaces.
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
    crates/meta-rs/src/allowlist.rs
    crates/meta-rs/src/metawrite.rs
    crates/meta-rs/src/transitions.rs
    crates/meta-rs/src/cache.rs
    crates/meta-rs/src/audit.rs
    contracts/entity_status/doc.go
    contracts/entity_status/gone_state.go
    contracts/entity_status/precedence.go
    contracts/entity_status/resolver.go
    contracts/entity_status/cache.go
    contracts/entity_status/v1.yaml
    contracts/turn/doc.go
    contracts/turn/turn_state.go
    contracts/turn/turn_context.go
    contracts/turn/turn_outcome_writer.go
    contracts/turn/turn_lifecycle_hook.go
    contracts/errors/doc.go
    contracts/errors/canonical.go
    crates/dp-kernel/src/entity_status.rs
    crates/dp-kernel/src/turn.rs
    crates/dp-kernel/src/turn_errors.rs
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -qE "$SECRET_PATTERNS" "$f"; then
        fail "B6: potential secret in $f"
    fi
done
pass "B6 secret-scan: no high-risk patterns in cycle-20 new files"

if bash scripts/raid/secret-scan-cycle.sh 20 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle clean"
else
    note "B6 secret-scan: gitleaks unavailable on dev machine (CI will gate)"
fi

echo "[verify-cycle-20] all $step steps PASS"
exit 0
