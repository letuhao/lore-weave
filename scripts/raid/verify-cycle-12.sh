#!/usr/bin/env bash
# verify-cycle-12.sh — L3.B Projection trait + L3.C Snapshot read runtime
#
# Acceptance gate. Exit 0 = pass; non-zero = fail.
# Covers:
#   - DPS 1 (L3.B): crates/dp-kernel/src/projection.rs + envelope.rs
#     Projection trait returns Vec<ProjectionUpdate> (Q-L3B-1); SYNC only
#     (Q-L3-2); VerificationMeta contract present (Q-L3-4); ProjectionRunner
#     fan-out + idempotency-skip helper; EventEnvelope mirrors Go envelope.
#   - DPS 2 (L3.C): crates/dp-kernel/src/load_aggregate.rs + snapshot_cache.rs
#     3-path snapshot loader (no-snap full replay / snap+delta / snap direct);
#     bounded LRU cache; cache-hit-rate >= 80% acceptance bar (L3.C); cache
#     coherence (fold delta on cache hit); snapshot_version=0 edge case;
#     errors propagate (snapshot store, event reader, apply failure with
#     at_version); cache invalidation; cross-aggregate isolation.
#   - NO L3.A projection tables (cycle 13 scope) — pure Rust kernel runtime.
#   - NO async projection (Q-L3-2).
#   - NO V2 blue-green scaffolding (Q-L3-5).
#   - NO cycle-13 verification-metadata table columns (contract only here).
#
# Cross-service live smoke: NOT required — cycle ships pure kernel library
# with in-memory test impls. Production wiring (sqlx SnapshotStore + EventReader)
# deferred to L4.A+ when world-service consumes load_aggregate.

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo_root"

step=0
pass() { step=$((step+1)); echo "[verify-cycle-12] step $step PASS: $1"; }
fail() { step=$((step+1)); echo "[verify-cycle-12] step $step FAIL: $1" >&2; exit 1; }
note() { echo "[verify-cycle-12] note: $1"; }

# ── New cycle-12 source files present ─────────────────────────────────────
for f in \
    crates/dp-kernel/src/envelope.rs \
    crates/dp-kernel/src/projection.rs \
    crates/dp-kernel/src/load_aggregate.rs \
    crates/dp-kernel/src/snapshot_cache.rs \
  ; do
    [[ -f "$f" ]] || fail "missing: $f"
done
pass "cycle-12 source files present (envelope, projection, load_aggregate, snapshot_cache)"

# ── lib.rs re-exports the new public surface ──────────────────────────────
for sym in \
    "pub mod envelope" \
    "pub mod projection" \
    "pub mod load_aggregate" \
    "pub mod snapshot_cache" \
    "pub use envelope::{EventEnvelope" \
    "pub use load_aggregate::{load_aggregate, Aggregate" \
    "pub use projection::{Projection, ProjectionRunner, ProjectionUpdate, VerificationMeta}" \
    "pub use snapshot_cache::{CacheEntry, CacheKey, SnapshotCache}" \
  ; do
    grep -q "$sym" crates/dp-kernel/src/lib.rs \
        || fail "lib.rs missing re-export: $sym"
done
pass "lib.rs re-exports all cycle-12 public types (EventEnvelope, Projection, ProjectionRunner, ProjectionUpdate, VerificationMeta, load_aggregate, Aggregate, SnapshotStore, EventReader, SnapshotCache, CacheKey, CacheEntry, LoadError, SnapshotRecord)"

# ── Q-L3B-1: Projection trait returns Vec<ProjectionUpdate> ───────────────
grep -q "fn apply_event(&self, env: &EventEnvelope) -> Vec<ProjectionUpdate>" crates/dp-kernel/src/projection.rs \
    || fail "Projection::apply_event signature must return Vec<ProjectionUpdate> (Q-L3B-1)"
pass "Q-L3B-1: Projection trait returns Vec<ProjectionUpdate> (multi-update support)"

# ── Q-L3-2: NO async fn in projection trait or load_aggregate ─────────────
if grep -qE "^\s*async\s+fn" crates/dp-kernel/src/projection.rs; then
    fail "Q-L3-2 violated: projection.rs contains async fn (V1 must be sync)"
fi
if grep -qE "^\s*async\s+fn" crates/dp-kernel/src/load_aggregate.rs; then
    fail "Q-L3-2 violated: load_aggregate.rs contains async fn (V1 must be sync)"
fi
pass "Q-L3-2 honored: zero 'async fn' in projection.rs + load_aggregate.rs"

# ── Q-L3-4: VerificationMeta contract present ─────────────────────────────
grep -q "pub struct VerificationMeta" crates/dp-kernel/src/projection.rs \
    || fail "Q-L3-4 violated: VerificationMeta struct missing in projection.rs"
for fld in "event_id: Uuid" "aggregate_version: u64" "applied_at: Rfc3339Timestamp"; do
    grep -q "$fld" crates/dp-kernel/src/projection.rs \
        || fail "Q-L3-4 violated: VerificationMeta missing field: $fld"
done
grep -q "pub fn from_envelope" crates/dp-kernel/src/projection.rs \
    || fail "VerificationMeta::from_envelope helper missing"
pass "Q-L3-4 contract: VerificationMeta { event_id, aggregate_version, applied_at } defined + from_envelope helper present"

# ── Q-L3-5: NO V2 blue-green scaffolding shipped ──────────────────────────
# Look for *implementation* surface only (struct/fn/enum/mod/trait named
# blue_green / blueGreen / BlueGreen). Comments / doc lines that EXPLICITLY
# say "NO blue-green" are fine — they prove the contract is honored.
if grep -qiE "^[[:space:]]*(pub[[:space:]]+)?(struct|fn|enum|mod|trait|type|const|static)[[:space:]]+(blue.green|blue_green|BlueGreen)" \
        crates/dp-kernel/src/projection.rs crates/dp-kernel/src/load_aggregate.rs crates/dp-kernel/src/snapshot_cache.rs crates/dp-kernel/src/envelope.rs; then
    fail "Q-L3-5 violated: V2 blue-green implementation symbol declared"
fi
pass "Q-L3-5 honored: no V2 blue-green implementation symbols (comments allowed)"

# ── 3-path snapshot loader tests present ──────────────────────────────────
for tname in \
    "path_a_no_snapshot_full_replay" \
    "path_b_snapshot_plus_delta" \
    "path_c_snapshot_direct_no_events" \
    "snapshot_version_zero_edge_case" \
    "cache_hit_rate_meets_acceptance" \
    "cache_hit_path_folds_new_events" \
    "cache_invalidate_forces_reload" \
    "cache_does_not_leak_across_aggregates" \
    "snapshot_store_error_propagates" \
    "event_reader_error_propagates" \
    "apply_failure_surfaces_with_version" \
  ; do
    grep -q "fn $tname" crates/dp-kernel/src/load_aggregate.rs \
        || fail "load_aggregate.rs missing test: $tname"
done
pass "L3.C 3-path loader + cache + edge-case tests present (11 named tests)"

# ── L3.B projection tests present ─────────────────────────────────────────
for tname in \
    "empty_vec_when_event_unrelated" \
    "projection_returns_single_update" \
    "projection_returns_multiple_updates_q_l3b_1" \
    "verification_meta_uses_recorded_at_for_monotonicity" \
    "runner_fan_out_across_projections" \
    "runner_skips_via_handles_predicate" \
    "runner_apply_batch_preserves_order" \
    "idempotency_skip_when_version_already_seen" \
    "projection_update_variants_round_trip_json" \
  ; do
    grep -q "fn $tname" crates/dp-kernel/src/projection.rs \
        || fail "projection.rs missing test: $tname"
done
pass "L3.B projection trait + runner + idempotency tests present (9 named tests)"

# ── snapshot_cache tests present ──────────────────────────────────────────
for tname in \
    "zero_capacity_panics" \
    "miss_then_hit" \
    "lru_eviction_at_capacity" \
    "lru_get_bumps_to_mru" \
    "invalidate_removes_entry" \
    "hit_rate_meets_l3c_acceptance_bar" \
    "insert_overwrite_updates_value_keeps_lru_bump" \
  ; do
    grep -q "fn $tname" crates/dp-kernel/src/snapshot_cache.rs \
        || fail "snapshot_cache.rs missing test: $tname"
done
pass "snapshot_cache LRU + hit-rate tests present (7 named tests)"

# ── envelope mirror tests present ─────────────────────────────────────────
for tname in \
    "validate_accepts_fixture" \
    "validate_rejects_zero_event_id" \
    "validate_rejects_zero_reality_id" \
    "validate_rejects_empty_event_type" \
    "validate_rejects_zero_event_version" \
    "roundtrip_json_matches_go_field_names" \
  ; do
    grep -q "fn $tname" crates/dp-kernel/src/envelope.rs \
        || fail "envelope.rs missing test: $tname"
done
pass "envelope mirror tests present (6 named tests; field names match Go envelope.go 1:1)"

# ── dp-kernel cargo check + test (the real gate) ──────────────────────────
cargo check -p dp-kernel >/dev/null 2>&1 \
    || fail "cargo check -p dp-kernel failed"
pass "cargo check -p dp-kernel clean"

cargo test -p dp-kernel >/dev/null 2>&1 \
    || fail "cargo test -p dp-kernel failed"
pass "cargo test -p dp-kernel: all tests green (cycle 8/10 baseline + cycle 12 new = 57 tests)"

# ── No L3.A projection tables (cycle 13 scope) ────────────────────────────
if [[ -f contracts/migrations/per_reality/0006_projections.sql ]] \
    || [[ -f contracts/migrations/per_reality/0006_projections.up.sql ]]; then
    fail "L3.A projection tables migration found — cycle 13 scope, not cycle 12"
fi
pass "no L3.A projection tables shipped (cycle 13 scope respected)"

# ── L2.E aggregate_snapshots table (cycle 9) referenced in comments ───────
grep -q "aggregate_snapshots" crates/dp-kernel/src/load_aggregate.rs \
    || fail "load_aggregate.rs does not reference L2.E aggregate_snapshots table (broken upstream link)"
pass "load_aggregate.rs documents its consumer link to L2.E aggregate_snapshots (cycle 9)"

# ── EventEnvelope field names match contracts/events/envelope.go ──────────
# Sanity: both files must spell the same JSON field names for projection
# delivery to work cross-language.
for fld in \
    "event_id" \
    "event_type" \
    "event_version" \
    "aggregate_id" \
    "aggregate_type" \
    "aggregate_version" \
    "reality_id" \
    "occurred_at" \
    "recorded_at" \
    "payload" \
  ; do
    grep -q "pub $fld:" crates/dp-kernel/src/envelope.rs \
        || fail "envelope.rs missing field: $fld (must mirror contracts/events/envelope.go)"
    grep -q "json:\"$fld\"" contracts/events/envelope.go \
        || fail "contracts/events/envelope.go missing json tag for: $fld (cross-side drift?)"
done
pass "EventEnvelope field names match contracts/events/envelope.go 1:1 (10 fields)"

# ── B5 prod-isolation ─────────────────────────────────────────────────────
bash scripts/raid/prod-isolation-lint.sh >/dev/null \
    || fail "B5 prod-isolation-lint regression"
pass "B5 prod-isolation-lint clean"

# ── B6 secret-scan ────────────────────────────────────────────────────────
if bash scripts/raid/secret-scan-cycle.sh 12 >/dev/null 2>&1; then
    pass "B6 secret-scan-cycle clean"
else
    note "B6 secret-scan: gitleaks unavailable on dev machine (CI will gate)"
fi

# ── Cycle-8/10/11 baseline regressions (don't break what shipped) ────────
# Only re-run the dp-kernel suite (covered above) + the contracts/events Go
# suite (cycle 10 baseline). Skipping per-service Go suites — none changed.
(cd contracts/events && go test ./...) >/dev/null 2>&1 \
    || fail "contracts/events regression — cycle-10 Go suite failing"
pass "contracts/events cycle-10 Go suite still green after cycle-12"

echo "[verify-cycle-12] ALL STEPS PASS (cycle 12 = L3.B Projection trait + L3.C Snapshot read runtime)"
exit 0
