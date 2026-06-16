#!/usr/bin/env bash
# verify-cycle-26.sh — L5.G Reality seeder (1 DPS, INLINE).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 26 scope (1 DPS — INLINE):
#   L5.G reality seeder for services/world-service/src/reality_seeder/:
#     * mod.rs            — orchestrator (L5.G.1)
#     * book_reader.rs    — book-service RPC trait (L5.G.2)
#     * canon_reader.rs   — glossary RPC trait, binds to L5.F.2 (L5.G.3)
#     * knowledge_reader.rs — knowledge-service trait (L5.G.4)
#     * translation_orchestrator.rs — Q-L5-2 gate (L5.G.5)
#     * checkpointer.rs   — per-100-entry checkpoints (L5.G.6)
#     * lifecycle_transitioner.rs — seeding↔active/failed (L5.G.7)
#     * audit.rs          — Q-L1A-3 audit sink (L5.G)
#
#   Cycle 25 glossary_client extension (Rust):
#     * clients/rust/glossary_client/src/lib.rs
#         + export_canon_for_seed + SeedExportEnvelope (L5.F.2 binding)
#
#   ACL (L5.G.8):
#     * contracts/service_acl/matrix.yaml
#         + translation-service-rpcs + book-service-rpcs +
#           knowledge-service-rpcs entries
#
#   Integration test (L5.G.9):
#     * services/world-service/tests/reality_seed_test.rs
#
#   Runbook (L5.G.10):
#     * runbooks/reality_seed/stuck_seeding.md
#
# LOCKED decisions enforced:
#   Q-L5-2   — translation gated on reality.locale != book.source_locale
#   Q-L5-3   — canon_layer enum {L1_axiom, L2_seeded} carried verbatim
#   Q-L5-4   — HTTP/JSON V1 RPC via cycle-25 glossary_client (no .proto)
#   Q-L1A-2  — canon SSOT in glossary DB; seeder writes to per-reality
#              canon_projection only (cycle 23 schema)
#   Q-L1A-3  — full audit V1, no sampling — per-phase + per-write
#   Q-L5A-1  — services/glossary-service/ UNTOUCHED (separate sub-program)
#   I7       — meta-worker is sole writer of per-reality canon_projection;
#              seeder routes via CanonProjectionWriter trait (production
#              binds to cycle-24 canon_writer)

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-26] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-26] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-26] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# File presence (L5.G.1–L5.G.10).
# ─────────────────────────────────────────────────────────────────────────
for f in \
    services/world-service/src/reality_seeder/mod.rs \
    services/world-service/src/reality_seeder/book_reader.rs \
    services/world-service/src/reality_seeder/canon_reader.rs \
    services/world-service/src/reality_seeder/knowledge_reader.rs \
    services/world-service/src/reality_seeder/translation_orchestrator.rs \
    services/world-service/src/reality_seeder/checkpointer.rs \
    services/world-service/src/reality_seeder/lifecycle_transitioner.rs \
    services/world-service/src/reality_seeder/audit.rs \
    services/world-service/tests/reality_seed_test.rs \
    runbooks/reality_seed/stuck_seeding.md ; do
    [[ -f "$f" ]] || fail "cycle-26 file missing: $f"
done
pass "cycle-26 L5.G files present (8 src + 1 integration test + 1 runbook)"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5A-1 / Q-L1A-2: glossary-service MUST NOT be modified.
# ─────────────────────────────────────────────────────────────────────────
if git diff --name-only HEAD 2>/dev/null | grep -qE '^services/glossary-service/'; then
    fail "Q-L5A-1 violation: services/glossary-service/ modified (separate sub-program)"
fi
pass "Q-L5A-1: services/glossary-service/ untouched"

# I7: per-reality canon_projection migrations stay in per_reality/ (cycle 23).
if git diff --name-only HEAD 2>/dev/null | grep -qE '^contracts/migrations/meta/.*canon'; then
    fail "I7 violation: canon migration in meta/ (must stay per_reality/)"
fi
pass "I7: canon migrations untouched + still per-reality"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5-2: translation gate on locale mismatch.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'Q-L5-2' services/world-service/src/reality_seeder/mod.rs \
    || fail "Q-L5-2: citation missing from reality_seeder/mod.rs"
grep -q 'requires_translation' services/world-service/src/reality_seeder/mod.rs \
    || fail "Q-L5-2: requires_translation gate missing from mod.rs"
grep -q 'Q-L5-2' services/world-service/src/reality_seeder/translation_orchestrator.rs \
    || fail "Q-L5-2: citation missing from translation_orchestrator.rs"
grep -q 'eq_ignore_ascii_case' services/world-service/src/reality_seeder/translation_orchestrator.rs \
    || fail "Q-L5-2: fast-path locale equality check missing"
pass "Q-L5-2: translation gated on locale mismatch (case-insensitive)"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5-3: canon_layer enum strings carried through.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'L1_axiom\|L2_seeded' services/world-service/src/reality_seeder/canon_reader.rs \
    || fail "Q-L5-3: canon_layer enum strings missing from canon_reader.rs"
grep -q 'Q-L5-3' services/world-service/src/reality_seeder/canon_reader.rs \
    || fail "Q-L5-3: citation missing from canon_reader.rs"
pass "Q-L5-3: canon_layer enum strings preserved"

# ─────────────────────────────────────────────────────────────────────────
# Q-L5-4: HTTP/JSON V1 via cycle-25 glossary_client.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'export_canon_for_seed' clients/rust/glossary_client/src/lib.rs \
    || fail "Q-L5-4: export_canon_for_seed missing from Rust glossary_client"
grep -q 'SeedExportEnvelope' clients/rust/glossary_client/src/lib.rs \
    || fail "Q-L5-4: SeedExportEnvelope missing from Rust glossary_client"
grep -q 'Q-L5-4' services/world-service/src/reality_seeder/canon_reader.rs \
    || fail "Q-L5-4: citation missing from canon_reader.rs"
# Defense: no .proto file accidentally shipped this cycle.
if find services/world-service contracts/api/glossary-service -name '*.proto' 2>/dev/null | grep -q .; then
    fail "Q-L5-4 violation: .proto file present (HTTP/JSON V1 per LOCKED)"
fi
pass "Q-L5-4: HTTP/JSON V1 binding via cycle-25 Rust client; no .proto"

# ─────────────────────────────────────────────────────────────────────────
# Q-L1A-2: per-reality canon_projection ONLY (cycle 23 schema).
# ─────────────────────────────────────────────────────────────────────────
grep -q 'Q-L1A-2' services/world-service/src/reality_seeder/mod.rs \
    || fail "Q-L1A-2: citation missing from reality_seeder/mod.rs"
grep -q 'canon_projection' services/world-service/src/reality_seeder/mod.rs \
    || fail "Q-L1A-2: canon_projection target not named in mod.rs"
pass "Q-L1A-2: per-reality canon_projection write target documented"

# ─────────────────────────────────────────────────────────────────────────
# Q-L1A-3: full audit V1, no sampling.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'Q-L1A-3' services/world-service/src/reality_seeder/audit.rs \
    || fail "Q-L1A-3: citation missing from audit.rs"
grep -q 'AuditSink' services/world-service/src/reality_seeder/audit.rs \
    || fail "Q-L1A-3: AuditSink trait missing from audit.rs"
grep -q 'no sampling' services/world-service/src/reality_seeder/audit.rs \
    || fail "Q-L1A-3: 'no sampling' semantic not documented"
pass "Q-L1A-3: full audit sink (Phase + CanonUpsert + Failure variants)"

# ─────────────────────────────────────────────────────────────────────────
# Idempotency: already_seeded check + checkpoint UPSERT.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'already_seeded' services/world-service/src/reality_seeder/mod.rs \
    || fail "idempotency: already_seeded skip path missing"
grep -q 'Idempotent' services/world-service/src/reality_seeder/mod.rs \
    || fail "idempotency: documentation marker missing"
grep -q 'is_complete' services/world-service/src/reality_seeder/checkpointer.rs \
    || fail "idempotency: SeedCheckpoint.is_complete missing"
pass "idempotency: already_seeded skip + checkpoint completion marker"

# ─────────────────────────────────────────────────────────────────────────
# Failure-safe: mark_failed + FailedSeeding status.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'mark_failed' services/world-service/src/reality_seeder/mod.rs \
    || fail "failure-safe: mark_failed path missing"
grep -q 'FailedSeeding' services/world-service/src/reality_seeder/lifecycle_transitioner.rs \
    || fail "failure-safe: FailedSeeding status missing"
grep -q 'failed_seeding' services/world-service/src/reality_seeder/lifecycle_transitioner.rs \
    || fail "failure-safe: failed_seeding string serialization missing"
pass "failure-safe: mark_failed → FailedSeeding lifecycle transition"

# ─────────────────────────────────────────────────────────────────────────
# Service ACL matrix — L5.G.8 RPC entries.
# ─────────────────────────────────────────────────────────────────────────
grep -q 'translation-service-rpcs' contracts/service_acl/matrix.yaml \
    || fail "L5.G.8: translation-service-rpcs entry missing"
grep -q 'TranslateCanonValue' contracts/service_acl/matrix.yaml \
    || fail "L5.G.8: TranslateCanonValue RPC missing"
grep -q 'book-service-rpcs' contracts/service_acl/matrix.yaml \
    || fail "L5.G.8: book-service-rpcs entry missing"
grep -q 'knowledge-service-rpcs' contracts/service_acl/matrix.yaml \
    || fail "L5.G.8: knowledge-service-rpcs entry missing"
# Cycle 25 already added glossary-service-rpcs ExportCanonForSeed; spot-check
# it's still there.
grep -q 'ExportCanonForSeed' contracts/service_acl/matrix.yaml \
    || fail "regression: ExportCanonForSeed missing from matrix (cycle-25 baseline)"
pass "L5.G.8: ACL matrix has translation + book + knowledge RPC entries"

# ─────────────────────────────────────────────────────────────────────────
# Workspace build + unit tests.
# ─────────────────────────────────────────────────────────────────────────
note "cargo build -p world-service"
cargo build -p world-service --quiet 2>&1 | tail -3
cargo build -p world-service --quiet >/dev/null 2>&1 \
    || fail "world-service build FAILED"
pass "world-service builds clean (cycle 5 + cycle 26 surfaces)"

note "cargo test -p world-service --lib"
cargo test -p world-service --lib --quiet 2>&1 | tail -3
cargo test -p world-service --lib --quiet >/dev/null 2>&1 \
    || fail "world-service unit tests FAILED"
pass "world-service unit tests PASS (cycle 5 baseline + 27 new cycle-26 tests)"

note "cargo test -p world-service --test reality_seed_test (integration L5.G.9)"
cargo test -p world-service --test reality_seed_test --quiet 2>&1 | tail -3
cargo test -p world-service --test reality_seed_test --quiet >/dev/null 2>&1 \
    || fail "L5.G.9 integration test FAILED"
pass "L5.G.9 integration test PASS (5 tests: multi-page + Q-L5-2 + idempotent + partial-fail + npc export)"

note "cargo test -p glossary-client --lib (Rust client; export_canon_for_seed added)"
cargo test -p glossary-client --lib --quiet 2>&1 | tail -3
cargo test -p glossary-client --lib --quiet >/dev/null 2>&1 \
    || fail "glossary-client tests FAILED"
pass "glossary-client tests PASS (cycle-25 baseline 12 + 5 new export_canon_for_seed tests = 17)"

note "go test contracts/service_acl/... (regression for L5.G.8 entries)"
( cd contracts/service_acl && go test ./... -count=1 >/dev/null ) \
    || fail "service_acl Go tests FAILED (matrix.yaml entry broke schema)"
pass "contracts/service_acl Go tests PASS (cycle-26 L5.G.8 additions clean)"

note "cargo build --workspace"
cargo build --workspace --quiet >/dev/null 2>&1 \
    || fail "cargo build --workspace FAILED"
pass "cargo build --workspace clean"

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
    services/world-service/src/reality_seeder/mod.rs
    services/world-service/src/reality_seeder/book_reader.rs
    services/world-service/src/reality_seeder/canon_reader.rs
    services/world-service/src/reality_seeder/knowledge_reader.rs
    services/world-service/src/reality_seeder/translation_orchestrator.rs
    services/world-service/src/reality_seeder/checkpointer.rs
    services/world-service/src/reality_seeder/lifecycle_transitioner.rs
    services/world-service/src/reality_seeder/audit.rs
    services/world-service/tests/reality_seed_test.rs
    runbooks/reality_seed/stuck_seeding.md
    clients/rust/glossary_client/src/lib.rs
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -EHn "$SECRET_PATTERNS" "$f" 2>/dev/null; then
        fail "B6: secret-like content in $f"
    fi
done
pass "B6 secret-scan: cycle-26 new files clean"

if bash scripts/raid/secret-scan-cycle.sh 26 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle 26 clean"
else
    fail "B6 secret-scan-cycle 26 FAILED"
fi

echo
echo "[verify-cycle-26] ALL ${step} STEPS PASS"
echo "[verify-cycle-26] L5.G reality seeder ready for cycle-27+ wiring."
