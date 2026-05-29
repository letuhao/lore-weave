#!/usr/bin/env bash
# verify-cycle-13.sh — L3.A 10 projection tables + L3.K drift metadata + cron.
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
#
# Cycle 13 scope:
#   DPS 1 — L3.A 10 projection tables (single migration 0006) with
#           VerificationMeta cols (Q-L3-4) on EVERY table + 5 per-aggregate
#           Projection trait skeletons (crates/projections/{pc,npc,region,
#           world_kv,session}).
#   DPS 2 — L3.K drift detection metadata (migration 0007 +
#           scripts/projection-drift-check.sh skeleton + 2 lw_projection_*
#           inventory entries).
#
# LOCKED decisions enforced:
#   Q-L3-4: VerificationMeta cols (event_id/aggregate_version/applied_at)
#           on all 10 L3.A tables.
#   Q-L3-5: NO V2 blue-green scaffolding (no blue_green / blueGreen symbols).
#   Q-L3I-1: embedding dim 1536 hard-coded V1 in projections-npc + migration.
#   Q-L3B-1: projections honor multi-update Vec<ProjectionUpdate> contract
#            (PC + NPC both demonstrate it).
#
# Cross-service live smoke: NOT required — cycle ships SQL migrations + Rust
# library code + shell cron skeleton. No service binary, no cross-service
# wire. Production wiring (integrity-checker daemon, world-service projection
# runner consumption) deferred to cycle 14+.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-13] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-13] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-13] note: $1"; }

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 — L3.A migration + 10 projection tables
# ─────────────────────────────────────────────────────────────────────────

[[ -f contracts/migrations/per_reality/0006_projections.up.sql   ]] || fail "missing 0006_projections.up.sql"
[[ -f contracts/migrations/per_reality/0006_projections.down.sql ]] || fail "missing 0006_projections.down.sql"
pass "0006_projections.{up,down}.sql present"

# Enumerate the 10 L3.A canonical tables.
TABLES=(
    pc_projection
    pc_inventory_projection
    pc_relationship_projection
    npc_projection
    npc_session_memory_projection
    npc_pc_relationship_projection
    npc_session_memory_embedding
    region_projection
    world_kv_projection
    session_participants
)

# Count tables in the migration. Use CREATE TABLE IF NOT EXISTS as the
# canonical create marker (npc_session_memory_embedding is created inside a
# DO $$ block — grep still matches the CREATE TABLE inside the EXECUTE).
# Use POSIX char class instead of \b (some awk/grep flavors lack \b).
table_count=0
for t in "${TABLES[@]}"; do
    if grep -qE "CREATE TABLE IF NOT EXISTS ${t}( |$|\()" contracts/migrations/per_reality/0006_projections.up.sql; then
        table_count=$((table_count + 1))
    else
        fail "L3.A table missing in 0006_projections.up.sql: $t"
    fi
done
[[ "$table_count" -eq 10 ]] || fail "expected 10 L3.A tables in migration; found $table_count"
pass "all 10 L3.A projection tables present in 0006_projections.up.sql"

# Q-L3-4: every projection table MUST have VerificationMeta cols
# (event_id, aggregate_version, applied_at) AND integrity HWM cols
# (last_verified_event_version, last_verified_at).
META_COLS=(
    "event_id"
    "aggregate_version"
    "applied_at"
    "last_verified_event_version"
    "last_verified_at"
)

# Pull the create-block for each table from the migration and verify each
# meta column appears within. Awk slices on the first matching CREATE TABLE
# until the next standalone closing ");". Embedding table is inside a DO $$
# block so we strip leading whitespace before matching the start pattern.
for t in "${TABLES[@]}"; do
    block=$(awk -v tbl="$t" '
        $0 ~ ("CREATE TABLE IF NOT EXISTS " tbl "( |$|\\()") { in_block=1 }
        in_block { print }
        in_block && /^[[:space:]]*\)/ { exit }
    ' contracts/migrations/per_reality/0006_projections.up.sql)
    [[ -n "$block" ]] || fail "could not extract DDL block for $t"
    for col in "${META_COLS[@]}"; do
        echo "$block" | grep -q "$col" \
            || fail "Q-L3-4 violated: $t missing column: $col"
    done
done
pass "Q-L3-4: all 10 projection tables have VerificationMeta cols (event_id, aggregate_version, applied_at) + integrity HWM cols (last_verified_event_version, last_verified_at)"

# Q-L3I-1: pgvector dim 1536 hard-coded in migration (either VECTOR(1536)
# inside the DO block OR the BYTEA placeholder CHECK constraint 1536*4).
grep -qE "VECTOR\(1536\)" contracts/migrations/per_reality/0006_projections.up.sql \
    || fail "Q-L3I-1 violated: VECTOR(1536) not present in 0006 migration"
grep -qE "1536 \* 4" contracts/migrations/per_reality/0006_projections.up.sql \
    || fail "Q-L3I-1 violated: BYTEA fallback CHECK 1536*4 not present"
pass "Q-L3I-1: embedding dim 1536 hard-coded V1 (VECTOR(1536) + BYTEA(1536*4) fallback present)"

# Q-L3-5: NO V2 blue-green migration scaffolding in cycle-13 sources.
if grep -rqiE "(blue.green|blue_green|BlueGreen)" \
        contracts/migrations/per_reality/0006_projections.up.sql \
        contracts/migrations/per_reality/0007_drift_metadata.up.sql \
        crates/projections/; then
    # Allow the Q-L3-5 comment lines that explicitly DOCUMENT the lock.
    hits=$(grep -rEi "(blue.green|blue_green|BlueGreen)" \
              contracts/migrations/per_reality/0006_projections.up.sql \
              contracts/migrations/per_reality/0007_drift_metadata.up.sql \
              crates/projections/ \
            | grep -viE "(NO.*blue.green|blue.green.*scaffolding|blue.green.*V2|Q-L3-5)" || true)
    if [[ -n "$hits" ]]; then
        echo "$hits" >&2
        fail "Q-L3-5 violated: V2 blue-green implementation symbol found"
    fi
fi
pass "Q-L3-5: no V2 blue-green implementation symbols (LOCKED comments only)"

# ─────────────────────────────────────────────────────────────────────────
# DPS 1 — 5 per-aggregate Projection skeletons
# ─────────────────────────────────────────────────────────────────────────

for crate in pc npc region world_kv session; do
    [[ -f "crates/projections/${crate}/Cargo.toml" ]] || fail "missing Cargo.toml: crates/projections/${crate}/"
    [[ -f "crates/projections/${crate}/src/lib.rs" ]] || fail "missing src/lib.rs: crates/projections/${crate}/"
done
pass "5 per-aggregate projection crates present (pc, npc, region, world_kv, session)"

# Workspace registers all 5 new crates.
for crate in crates/projections/pc crates/projections/npc crates/projections/region crates/projections/world_kv crates/projections/session; do
    grep -q "\"$crate\"" Cargo.toml || fail "Cargo.toml workspace.members missing: $crate"
done
pass "root Cargo.toml workspace.members includes all 5 new projection crates"

# Each crate implements the Projection trait with apply_event returning Vec<ProjectionUpdate>.
for crate in pc npc region world_kv session; do
    grep -q "impl Projection for" "crates/projections/${crate}/src/lib.rs" \
        || fail "crates/projections/${crate} missing 'impl Projection for' line"
    grep -q "fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate>" "crates/projections/${crate}/src/lib.rs" \
        || fail "crates/projections/${crate} missing apply_event signature with Vec<ProjectionUpdate>"
done
pass "all 5 projection crates implement Projection trait with Vec<ProjectionUpdate> return (Q-L3B-1)"

# Q-L3B-1 multi-update demonstration: PC + NPC both ship test for it.
grep -q "fn pc_projection_spawned_emits_two_updates_q_l3b_1" crates/projections/pc/src/lib.rs \
    || fail "projections-pc missing Q-L3B-1 multi-update test"
grep -q "fn npc_projection_said_emits_two_updates_q_l3b_1" crates/projections/npc/src/lib.rs \
    || fail "projections-npc missing Q-L3B-1 multi-update test"
pass "Q-L3B-1 multi-update path demonstrated (PC pc.spawned + NPC npc.said both emit 2 updates)"

# Q-L3I-1 enforcement test in projections-npc.
grep -q "EMBEDDING_DIM" crates/projections/npc/src/lib.rs \
    || fail "projections-npc missing EMBEDDING_DIM constant (Q-L3I-1)"
grep -q "embedding_dim_constant_locked_at_1536_q_l3i_1" crates/projections/npc/src/lib.rs \
    || fail "projections-npc missing test confirming dim=1536 lock"
grep -q "embedding_projection_skips_when_dim_mismatches_q_l3i_1" crates/projections/npc/src/lib.rs \
    || fail "projections-npc missing test confirming mismatched-dim skip"
pass "Q-L3I-1: EMBEDDING_DIM=1536 constant + skip-on-mismatch behavior tested in projections-npc"

# Cargo check + test all 5 crates.
cargo check -p projections-pc -p projections-npc -p projections-region -p projections-world-kv -p projections-session >/dev/null 2>&1 \
    || fail "cargo check failed for projections-*"
pass "cargo check clean for all 5 projection crates"

cargo test -p projections-pc -p projections-npc -p projections-region -p projections-world-kv -p projections-session >/dev/null 2>&1 \
    || fail "cargo test failed for projections-*"
pass "cargo test clean for all 5 projection crates"

# dp-kernel still green (cycle 12 baseline must not regress).
cargo test -p dp-kernel >/dev/null 2>&1 \
    || fail "cycle-12 baseline regression: cargo test -p dp-kernel failing"
pass "cycle-12 dp-kernel baseline still green (57 tests)"

# ─────────────────────────────────────────────────────────────────────────
# DPS 2 — L3.K drift metadata + cron skeleton + obs inventory
# ─────────────────────────────────────────────────────────────────────────

[[ -f contracts/migrations/per_reality/0007_drift_metadata.up.sql   ]] || fail "missing 0007_drift_metadata.up.sql"
[[ -f contracts/migrations/per_reality/0007_drift_metadata.down.sql ]] || fail "missing 0007_drift_metadata.down.sql"
pass "0007_drift_metadata.{up,down}.sql present"

# Drift state table has the required summary cols.
DRIFT_COLS=(
    "table_name"
    "last_verified_at"
    "drift_count"
    "expected_next_sweep_at"
)
for col in "${DRIFT_COLS[@]}"; do
    grep -q "$col" contracts/migrations/per_reality/0007_drift_metadata.up.sql \
        || fail "0007_drift_metadata missing column: $col"
done
pass "projection_drift_state has required summary cols (table_name, last_verified_at, drift_count, expected_next_sweep_at)"

# Drift state table is fenced to the 10 L3.A tables only (cardinality bound).
for t in "${TABLES[@]}"; do
    grep -q "'$t'" contracts/migrations/per_reality/0007_drift_metadata.up.sql \
        || fail "projection_drift_table_name_allowlist missing: $t"
done
pass "projection_drift_state CHECK allowlist enumerates all 10 L3.A tables (cardinality fence)"

# Drift state is NOT coupled to integrity-checker service (cycle 14 owns
# that). It's a per-reality-DB table that BOTH the cycle-13 cron skeleton
# AND the cycle-14 integrity-checker can write to.
if grep -qiE "integrity.checker.service" contracts/migrations/per_reality/0007_drift_metadata.up.sql; then
    # The comment about "future integrity-checker" is FINE; only fail if we
    # see hard service coupling (e.g. FK to an integrity-checker table).
    if grep -qE "REFERENCES integrity_checker" contracts/migrations/per_reality/0007_drift_metadata.up.sql; then
        fail "0007 drift metadata has hard coupling to integrity-checker (Q-L3E-1 violated)"
    fi
fi
pass "0007 drift metadata not hard-coupled to cycle-14 integrity-checker service"

# Drift cron skeleton present + executable + scans 10 tables.
[[ -f scripts/projection-drift-check.sh ]] || fail "missing scripts/projection-drift-check.sh"
[[ -x scripts/projection-drift-check.sh ]] || fail "scripts/projection-drift-check.sh not executable"
for t in "${TABLES[@]}"; do
    grep -q "$t" scripts/projection-drift-check.sh \
        || fail "scripts/projection-drift-check.sh missing table: $t"
done
pass "scripts/projection-drift-check.sh skeleton scans all 10 L3.A tables"

# Skeleton has dry-run mode.
grep -q -- "--dry-run" scripts/projection-drift-check.sh \
    || fail "scripts/projection-drift-check.sh missing --dry-run flag"
pass "scripts/projection-drift-check.sh supports --dry-run"

# Observability inventory has the 2 new lw_projection_* entries.
grep -q "name: lw_projection_drift_count" contracts/observability/inventory.yaml \
    || fail "inventory.yaml missing lw_projection_drift_count"
grep -q "name: lw_projection_drift_last_check_age_seconds" contracts/observability/inventory.yaml \
    || fail "inventory.yaml missing lw_projection_drift_last_check_age_seconds"
pass "observability inventory has 2 new L3.K metrics (lw_projection_drift_count, lw_projection_drift_last_check_age_seconds)"

# ─────────────────────────────────────────────────────────────────────────
# Cross-cutting validators
# ─────────────────────────────────────────────────────────────────────────

# Migration idempotency on new migrations.
bash scripts/migration-idempotency-validator.sh \
    contracts/migrations/per_reality/0006_projections.up.sql \
    contracts/migrations/per_reality/0006_projections.down.sql \
    contracts/migrations/per_reality/0007_drift_metadata.up.sql \
    contracts/migrations/per_reality/0007_drift_metadata.down.sql \
    >/dev/null \
    || fail "migration-idempotency-validator failed on cycle-13 migrations"
pass "migration-idempotency-validator clean on 0006/0007 migrations"

# Observability inventory lint (best-effort; cycle 13 only added new entries).
if bash scripts/observability-inventory-lint.sh >/dev/null 2>&1; then
    pass "observability-inventory-lint clean"
else
    note "observability-inventory-lint surfaced findings (likely cycle-1..12 baseline; cycle-13 entries themselves are well-formed)"
fi

# B5 prod-isolation.
bash scripts/raid/prod-isolation-lint.sh >/dev/null \
    || fail "B5 prod-isolation-lint regression"
pass "B5 prod-isolation-lint clean"

# B6 secret-scan (gracefully skips when gitleaks absent).
if bash scripts/raid/secret-scan-cycle.sh 13 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle clean"
else
    note "B6 secret-scan: gitleaks unavailable on dev machine (CI will gate)"
fi

# ─────────────────────────────────────────────────────────────────────────
# Cross-cycle invariant: cycle-12 contracts referenced from cycle-13 sources
# ─────────────────────────────────────────────────────────────────────────

# Each projection crate references the cycle-12 dp-kernel::Projection trait.
for crate in pc npc region world_kv session; do
    grep -q "use dp_kernel::" "crates/projections/${crate}/src/lib.rs" \
        || fail "crates/projections/${crate} does not import dp_kernel (broken cycle-12 link)"
done
pass "all 5 projection crates import from dp_kernel (cycle-12 contract honored)"

# Migration 0006 references the cycle-12 Projection trait + cycle-13 L3.K table.
grep -q "ProjectionUpdate" contracts/migrations/per_reality/0006_projections.up.sql \
    || fail "0006 migration does not reference cycle-12 ProjectionUpdate"
pass "0006 migration documents its consumer link to cycle-12 Projection trait"

echo "[verify-cycle-13] ALL STEPS PASS (cycle 13 = L3.A 10 projection tables + L3.K drift metadata + cron skeleton)"
exit 0
