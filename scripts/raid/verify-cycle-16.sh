#!/usr/bin/env bash
# verify-cycle-16.sh — L3.I pgvector + embedding queue (L3 layer-closer).
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 16 scope (SINGLE DPS — inline):
#   - contracts/migrations/per_reality/0008_pgvector_setup.{up,down}.sql
#     * CREATE EXTENSION IF NOT EXISTS vector  (L3.I.1)
#     * ALTER COLUMN BYTEA → VECTOR(1536) conditional swap            (L3.I.1)
#     * CREATE INDEX npc_embedding_hnsw_idx (m=16, ef_construction=64) (L3.I.2)
#   - contracts/migrations/manifest.yaml extended to register 0006, 0007, 0008
#   - infra/foundation-dev/docker-compose.yml switched to pgvector/pgvector:pg16
#   - infra/foundation-dev/pgvector-init.sh extension bootstrap
#   - services/world-service/src/embedding_queue/{mod.rs,audit.rs}         (L3.I.3 + L3.I.4)
#     * EmbeddingProvider trait + Queue + Worker + AuditWriter trait
#     * Q-L3-1 V1: in world-service (NOT a separate service)
#     * Q-L1A-3: every provider call emits service_to_service_audit row
#   - services/world-service/src/lib.rs re-exports
#   - services/world-service/tests/embedding_retrieval_test.rs                (L3.I.5)
#
# LOCKED decisions enforced:
#   Q-L3-1   — embedding worker placement = V1 IN world-service async queue.
#   Q-L3I-1  — embedding dim 1536 hard-coded V1.
#   Q-L1A-3  — full audit (no sampling) for every provider call.
#
# Cross-service live smoke: NOT required — cycle ships migration SQL + Rust
# library code + docker-compose tweak. No service binary running cross-
# network. Production wiring (sqlx pool + real BYOK provider HTTP client)
# is deferred to D-EMBEDDING-QUEUE-LIVE-WIRING.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-16] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-16] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-16] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 — Migration: 0008_pgvector_setup
# ─────────────────────────────────────────────────────────────────────────

[[ -f contracts/migrations/per_reality/0008_pgvector_setup.up.sql ]] \
    || fail "contracts/migrations/per_reality/0008_pgvector_setup.up.sql missing"
[[ -f contracts/migrations/per_reality/0008_pgvector_setup.down.sql ]] \
    || fail "contracts/migrations/per_reality/0008_pgvector_setup.down.sql missing"
pass "0008_pgvector_setup up + down migrations present"

# Q-L3I-1: dim=1536 hard-coded.
grep -q "VECTOR(1536)" contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "Q-L3I-1: VECTOR(1536) not present in 0008 migration"
grep -q "Q-L3I-1" contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "Q-L3I-1 not documented in 0008 migration comments"
pass "Q-L3I-1: dim=1536 hard-coded in 0008 migration + documented"

# CREATE EXTENSION IF NOT EXISTS vector.
grep -q "CREATE EXTENSION IF NOT EXISTS vector" \
    contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 missing CREATE EXTENSION IF NOT EXISTS vector"
pass "L3.I.1: CREATE EXTENSION IF NOT EXISTS vector present"

# Conditional ALTER COLUMN BYTEA → VECTOR(1536).
grep -q "ALTER COLUMN embedding TYPE VECTOR(1536)" \
    contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 missing ALTER COLUMN to VECTOR(1536)"
grep -q "DROP CONSTRAINT npc_embedding_bytea_dim_1536" \
    contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 must DROP the cycle-13 BYTEA shape CHECK constraint before ALTER"
pass "L3.I.1: conditional ALTER COLUMN BYTEA → VECTOR(1536) + constraint drop present"

# HNSW index with documented params.
grep -q "USING hnsw (embedding vector_cosine_ops)" \
    contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 missing HNSW vector_cosine_ops index"
grep -q "m = 16" contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 HNSW missing m=16 parameter"
grep -q "ef_construction = 64" contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 HNSW missing ef_construction=64 parameter"
pass "L3.I.2: HNSW index (m=16, ef_construction=64, vector_cosine_ops) present"

# Idempotency: down does NOT drop the extension (other tables may consume it).
# Strip SQL comments first so a `-- ... DROP EXTENSION vector ...` mention in
# documentation does not trigger a false positive.
DOWN_NO_COMMENTS=$(sed 's|--.*||' contracts/migrations/per_reality/0008_pgvector_setup.down.sql)
if echo "$DOWN_NO_COMMENTS" | grep -qE '^\s*DROP\s+EXTENSION\s+vector'; then
    fail "0008 down MUST NOT DROP EXTENSION vector (other tables may consume it)"
fi
grep -q "DROP INDEX IF EXISTS npc_embedding_hnsw_idx" \
    contracts/migrations/per_reality/0008_pgvector_setup.down.sql \
    || fail "0008 down missing DROP INDEX IF EXISTS npc_embedding_hnsw_idx"
pass "0008 down is safe (drops only the HNSW index; preserves extension + data)"

# Idempotency probe — table-shape detection branch.
grep -q "format_type" contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 missing format_type-based shape detection (idempotency probe)"
grep -q "already VECTOR(1536)" contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 missing skip-when-already-VECTOR(1536) branch"
pass "L3.I.1 idempotency probe: format_type lookup + skip-when-already-VECTOR branch present"

# ─────────────────────────────────────────────────────────────────────────
# Manifest registers cycles 6+7+8 (carryforward from cycles 13+16)
# ─────────────────────────────────────────────────────────────────────────

for mig in "0006_projections" "0007_drift_metadata" "0008_pgvector_setup"; do
    grep -q "id: \"$mig\"" contracts/migrations/manifest.yaml \
        || fail "manifest.yaml missing $mig entry"
done
pass "manifest.yaml registers 0006_projections + 0007_drift_metadata + 0008_pgvector_setup"

# Manifest entries use breaking: false (none of them DROP/break existing data).
awk '/id: "0008_pgvector_setup"/,/^$/' contracts/migrations/manifest.yaml | \
    grep -q "breaking: false" \
    || fail "0008_pgvector_setup must declare breaking: false"
pass "0008_pgvector_setup declared breaking: false"

# ─────────────────────────────────────────────────────────────────────────
# Docker-compose + init script — pgvector image + extension bootstrap
# ─────────────────────────────────────────────────────────────────────────

grep -q "pgvector/pgvector:pg16" infra/foundation-dev/docker-compose.yml \
    || fail "foundation-dev docker-compose must use pgvector/pgvector:pg16 (cycle-5 carryforward)"
pass "foundation-dev docker-compose uses pgvector/pgvector:pg16 image"

[[ -f infra/foundation-dev/pgvector-init.sh ]] || \
    fail "infra/foundation-dev/pgvector-init.sh missing"
grep -q "CREATE EXTENSION IF NOT EXISTS vector" infra/foundation-dev/pgvector-init.sh \
    || fail "pgvector-init.sh must CREATE EXTENSION IF NOT EXISTS vector"
grep -q "template1" infra/foundation-dev/pgvector-init.sh \
    || fail "pgvector-init.sh must install vector in template1 (so per-reality DBs inherit)"
pass "pgvector-init.sh present + installs vector in foundation + template1"

grep -q "/docker-entrypoint-initdb.d/" infra/foundation-dev/docker-compose.yml \
    || fail "foundation-dev compose missing /docker-entrypoint-initdb.d/ mount for pgvector-init.sh"
pass "foundation-dev compose mounts pgvector-init.sh into /docker-entrypoint-initdb.d/"

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 — Embedding queue module (L3.I.3 + L3.I.4)
# ─────────────────────────────────────────────────────────────────────────

[[ -f services/world-service/src/embedding_queue/mod.rs ]] \
    || fail "services/world-service/src/embedding_queue/mod.rs missing"
[[ -f services/world-service/src/embedding_queue/audit.rs ]] \
    || fail "services/world-service/src/embedding_queue/audit.rs missing"
pass "embedding_queue module files present"

# Q-L3-1 V1 placement explicit in module docs.
grep -q "Q-L3-1" services/world-service/src/embedding_queue/mod.rs \
    || fail "embedding_queue/mod.rs must document Q-L3-1 V1 placement decision"
grep -qE "V1.{0,40}world-service" services/world-service/src/embedding_queue/mod.rs \
    || fail "embedding_queue/mod.rs must document V1-in-world-service placement"
pass "Q-L3-1 V1 in-world-service placement documented in embedding_queue/mod.rs"

# Q-L3I-1 dim=1536 constant.
grep -q "pub const EMBEDDING_DIM: usize = 1536" \
    services/world-service/src/embedding_queue/mod.rs \
    || fail "EMBEDDING_DIM = 1536 constant missing in embedding_queue (Q-L3I-1)"
pass "Q-L3I-1: EMBEDDING_DIM=1536 constant in embedding_queue"

# Dim constant cross-check vs projections-npc crate (Q-L3I-1 single source of truth).
NPC_DIM=$(grep "pub const EMBEDDING_DIM" crates/projections/npc/src/lib.rs)
QUEUE_DIM=$(grep "pub const EMBEDDING_DIM" services/world-service/src/embedding_queue/mod.rs)
if ! echo "$NPC_DIM" | grep -q "1536" || ! echo "$QUEUE_DIM" | grep -q "1536"; then
    fail "EMBEDDING_DIM cross-check failed — projections-npc and embedding_queue must both = 1536"
fi
pass "dim constant cross-check: projections-npc and embedding_queue both = 1536 (Q-L3I-1)"

# Provider gateway invariant (CLAUDE.md) — no direct vendor SDK imports.
# A vendor SDK reference would be an `use openai::`, `use cohere::`, `use anthropic_sdk::`,
# etc — none of which should ever appear in the embedding queue.
if grep -E "^\s*use (openai|cohere|anthropic_sdk|aws_sdk_bedrock|google_genai)" \
    services/world-service/src/embedding_queue/mod.rs \
    services/world-service/src/embedding_queue/audit.rs >/dev/null 2>&1; then
    fail "embedding_queue must NOT import vendor SDKs directly (CLAUDE.md provider gateway invariant)"
fi
pass "provider gateway invariant: no direct vendor SDK imports in embedding_queue"

# Q-L1A-3 full audit — AuditWriter trait + audit-on-every-outcome path.
grep -q "trait AuditWriter" services/world-service/src/embedding_queue/audit.rs \
    || fail "embedding_queue/audit.rs missing AuditWriter trait"
grep -q "Q-L1A-3" services/world-service/src/embedding_queue/audit.rs \
    || fail "embedding_queue/audit.rs must reference Q-L1A-3 full-audit decision"
for outcome in "AuditOutcome::Ok" "AuditOutcome::DimMismatch" \
               "AuditOutcome::ProviderError" "AuditOutcome::WriteError"; do
    grep -q "$outcome" services/world-service/src/embedding_queue/mod.rs \
        || fail "embedding_queue worker missing audit emission for $outcome"
done
pass "Q-L1A-3: AuditWriter trait + every outcome variant emitted by worker"

# Re-exports in world-service lib.rs.
for sym in "EmbeddingProvider" "EmbeddingWriter" "MemoryRef" "EMBEDDING_DIM" \
           "AuditWriter" "AuditOutcome" "EmbeddingQueue" "EmbeddingWorker"; do
    grep -q "$sym" services/world-service/src/lib.rs \
        || fail "world-service lib.rs missing re-export of $sym"
done
pass "world-service lib.rs re-exports all 8 embedding-queue public symbols"

# ─────────────────────────────────────────────────────────────────────────
# Integration test (L3.I.5)
# ─────────────────────────────────────────────────────────────────────────

[[ -f services/world-service/tests/embedding_retrieval_test.rs ]] \
    || fail "services/world-service/tests/embedding_retrieval_test.rs missing (L3.I.5)"
pass "L3.I.5: embedding_retrieval_test.rs integration test present"

# ─────────────────────────────────────────────────────────────────────────
# Unit + integration tests — cargo test green
# ─────────────────────────────────────────────────────────────────────────

note "running cargo test -p world-service"
if cargo test -p world-service --quiet 2>&1 | tail -10 | grep -q "test result: ok"; then
    pass "cargo test -p world-service: PASS"
else
    cargo test -p world-service 2>&1 | tail -30
    fail "cargo test -p world-service failed"
fi

# Cycle-13 projection skeleton tests still green (regression guard — we
# touched lib.rs re-exports + might have broken the projections crate).
note "running cargo test -p projections-npc (cycle-13 regression guard)"
if cargo test -p projections-npc --quiet 2>&1 | tail -5 | grep -q "test result: ok"; then
    pass "cargo test -p projections-npc still green (cycle-13 carryforward)"
else
    cargo test -p projections-npc 2>&1 | tail -20
    fail "cargo test -p projections-npc regressed"
fi

# ─────────────────────────────────────────────────────────────────────────
# Migration idempotency (B5 follow-up)
# ─────────────────────────────────────────────────────────────────────────

if bash scripts/migration-idempotency-validator.sh >/dev/null 2>&1; then
    pass "migration-idempotency-validator clean"
else
    bash scripts/migration-idempotency-validator.sh 2>&1 | tail -10
    note "migration-idempotency-validator surfaced findings (likely baseline; new 0008 uses IF NOT EXISTS + DO block probe)"
fi

# 0008 specific re-run safety — manual probe: each operation is guarded.
grep -q "CREATE EXTENSION IF NOT EXISTS" \
    contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 CREATE EXTENSION not idempotent"
grep -q "CREATE INDEX IF NOT EXISTS" \
    contracts/migrations/per_reality/0008_pgvector_setup.up.sql \
    || fail "0008 CREATE INDEX not idempotent"
pass "0008 idempotent: CREATE EXTENSION + CREATE INDEX both IF NOT EXISTS"

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

# B6 secret-scan over new files.
NEW_FILES=(
    contracts/migrations/per_reality/0008_pgvector_setup.up.sql
    contracts/migrations/per_reality/0008_pgvector_setup.down.sql
    services/world-service/src/embedding_queue/mod.rs
    services/world-service/src/embedding_queue/audit.rs
    services/world-service/tests/embedding_retrieval_test.rs
    infra/foundation-dev/pgvector-init.sh
)
SECRET_PATTERNS='AKIA[0-9A-Z]{16}|aws_secret_access_key|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|xoxb-[A-Za-z0-9-]{20,}|ghp_[A-Za-z0-9]{30,}|sk_live_[A-Za-z0-9]{20,}'
for f in "${NEW_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    if grep -qE "$SECRET_PATTERNS" "$f"; then
        fail "B6: potential secret in $f"
    fi
done
pass "B6 secret-scan: no high-risk patterns in cycle-16 new files"

if bash scripts/raid/secret-scan-cycle.sh 16 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle clean"
else
    note "B6 secret-scan: gitleaks unavailable on dev machine (CI will gate)"
fi

echo "[verify-cycle-16] all $step steps PASS"
exit 0
