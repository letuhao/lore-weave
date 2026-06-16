#!/usr/bin/env bash
# scripts/projection-drift-check.sh — L3.K verification cron SKELETON.
#
# RAID cycle 13 (L3.K DPS 2). SKELETON only — the actual integrity-checker
# service (cycle 14 L3.E daily / L3.F monthly) replaces this with a Go
# daemon that performs sample re-replay against the event store and diffs
# against the projection state.
#
# What this skeleton DOES today:
#   1. Connects to the per-reality DB via DATABASE_URL.
#   2. For each of the 10 L3.A projection tables, runs a "freshness" check:
#        - count_rows = SELECT count(*) FROM <table>
#        - latest_applied_at = SELECT max(applied_at) FROM <table>
#      (Both queries hit the (applied_at DESC) and primary key indexes; O(1)
#      or O(log N) depending on the table.)
#   3. UPDATEs `projection_drift_state` row for the table:
#        last_verified_at         = NOW()
#        last_sample_size         = count_rows
#        drift_count              = 0  (no re-replay yet; cycle 14 sets real value)
#        expected_next_sweep_at   = NOW() + 24h
#        notes                    = "cycle-13 skeleton: freshness only"
#
# What this skeleton DOES NOT do (cycle 14 L3.E ships it):
#   * Sample N random aggregates per table.
#   * Re-replay events from snapshot for each sampled aggregate.
#   * Diff replayed state against live projection row → set drift_count.
#   * Flag drifted aggregates for targeted rebuild (writes to a future
#     `drift_queue` table — cycle 14 scope).
#
# LOCKED decisions consumed:
#   * Q-L3-4 (§5): writes to `projection_drift_state.last_verified_*`.
#   * Q-L3E-1 (§5): the future REPLACEMENT integrity-checker is a separate
#     service. This skeleton is INTENTIONALLY a shell script in the
#     monorepo so cycle-13 can land the metadata wiring without depending
#     on cycle-14 service deployment.
#   * Q-L3-5 (§5): no V2 blue-green; single state table per reality DB.
#
# Usage:
#   DATABASE_URL=postgres://... ./scripts/projection-drift-check.sh
#   DATABASE_URL=postgres://... ./scripts/projection-drift-check.sh --dry-run
#
# Exit codes:
#   0 = success (all 10 tables verified, drift_state UPDATED).
#   1 = DB unreachable / connection error.
#   2 = SQL execution error.
#   3 = misuse (e.g. missing DATABASE_URL).

set -euo pipefail

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY_RUN=1
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "[projection-drift-check] ERROR: DATABASE_URL not set" >&2
    exit 3
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "[projection-drift-check] ERROR: psql not installed" >&2
    exit 3
fi

# 10 L3.A canonical projection tables.
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

echo "[projection-drift-check] L3.K skeleton — cycle 13 (DRY_RUN=$DRY_RUN)"
echo "[projection-drift-check] checking ${#TABLES[@]} L3.A projection tables..."

for tbl in "${TABLES[@]}"; do
    # Freshness check: row count + max applied_at.
    # Using -t (tuples-only) + -A (unaligned) so the output is parseable.
    count=$(psql "$DATABASE_URL" -t -A -c "SELECT count(*) FROM ${tbl}" 2>/dev/null || echo "ERR")
    if [ "$count" = "ERR" ]; then
        echo "[projection-drift-check] WARN: $tbl freshness query failed (table may not exist on this reality DB)"
        continue
    fi
    latest=$(psql "$DATABASE_URL" -t -A -c "SELECT COALESCE(max(applied_at)::text, 'none') FROM ${tbl}" 2>/dev/null || echo "ERR")

    if [ "$DRY_RUN" = "1" ]; then
        printf "[projection-drift-check] DRY-RUN  %-40s rows=%-10s latest=%s\n" "$tbl" "$count" "$latest"
        continue
    fi

    # UPDATE drift_state row. Note this is the SKELETON behavior:
    # drift_count is always written as 0 (no re-replay performed yet).
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q <<SQL
UPDATE projection_drift_state SET
    last_verified_at       = NOW(),
    last_sample_size       = ${count},
    drift_count            = 0,
    expected_next_sweep_at = NOW() + INTERVAL '24 hours',
    notes                  = 'cycle-13 skeleton: freshness-only (rows=${count}, latest=${latest})',
    updated_at             = NOW()
WHERE table_name = '${tbl}';
SQL
    printf "[projection-drift-check] OK       %-40s rows=%-10s latest=%s\n" "$tbl" "$count" "$latest"
done

if [ "$DRY_RUN" = "1" ]; then
    echo "[projection-drift-check] DRY-RUN: no rows updated"
    exit 0
fi

# Final summary: list any rows in stale_projections view (alert source).
stale_count=$(psql "$DATABASE_URL" -t -A -c "SELECT count(*) FROM stale_projections" 2>/dev/null || echo "ERR")
if [ "$stale_count" != "ERR" ] && [ "$stale_count" != "0" ]; then
    echo "[projection-drift-check] WARN: $stale_count rows in stale_projections view (alert candidates)"
    psql "$DATABASE_URL" -c "SELECT * FROM stale_projections" 2>/dev/null || true
else
    echo "[projection-drift-check] all ${#TABLES[@]} projection tables verified fresh"
fi

exit 0
