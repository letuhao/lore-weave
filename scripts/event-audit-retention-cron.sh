#!/usr/bin/env bash
# scripts/event-audit-retention-cron.sh — L2.B (RAID cycle 9 DPS 2)
#
# Nightly retention worker for `event_audit`. Per R01 §12A.3:
#   - non-flagged audit rows: retain 30 days
#   - flagged audit rows:     retain 90 days
#
# Strategy:
#   * Partition-aware (event_audit is range-partitioned monthly on recorded_at):
#     once an ENTIRE partition is older than 90d, drop it wholesale (cheap).
#   * Within still-live partitions, DELETE rows older than the per-flag class
#     threshold. Bounded batch size to keep TX small.
#
# Idempotency: re-runnable. The "already pruned" rows yield 0-row DELETEs.
#
# Wired to cron in cycle 11 (L2.K retention-worker). Until then, this script
# is the contract + dry-run harness.
#
# Usage:
#   event-audit-retention-cron.sh [--dry-run] [--db <conn>] [--batch-size N]
#
# Exit codes: 0=ok, 1=usage error, 2=psql failure, 3=dry-run preview only.

set -euo pipefail

DRY_RUN=0
DB_URI="${PGURI:-${DATABASE_URL:-}}"
BATCH_SIZE=10000
NON_FLAGGED_DAYS=30
FLAGGED_DAYS=90

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)         DRY_RUN=1; shift ;;
        --db)              DB_URI="$2"; shift 2 ;;
        --batch-size)      BATCH_SIZE="$2"; shift 2 ;;
        --non-flagged-days) NON_FLAGGED_DAYS="$2"; shift 2 ;;
        --flagged-days)    FLAGGED_DAYS="$2"; shift 2 ;;
        *)
            echo "[audit-retention] unknown arg: $1" >&2
            exit 1
            ;;
    esac
done

dry_drop_partitions_sql=$(cat <<EOF
-- Discover audit partitions older than the flagged threshold (${FLAGGED_DAYS}d).
-- A partition is "fully expired" when its UPPER bound < now() - ${FLAGGED_DAYS}d.
-- For monthly partitions: name suffix YYYY_MM determines the lower bound;
-- upper bound is the first of the following month.
SELECT
    inhrelid::regclass::text AS partition_name
FROM pg_inherits
WHERE inhparent = 'event_audit'::regclass
ORDER BY 1;
EOF
)

dry_delete_nonflagged_sql=$(cat <<EOF
DELETE FROM event_audit
 WHERE flagged = FALSE
   AND recorded_at < NOW() - INTERVAL '${NON_FLAGGED_DAYS} days'
 LIMIT ${BATCH_SIZE};   -- repeat until 0 rows
EOF
)

dry_delete_flagged_sql=$(cat <<EOF
DELETE FROM event_audit
 WHERE flagged = TRUE
   AND recorded_at < NOW() - INTERVAL '${FLAGGED_DAYS} days'
 LIMIT ${BATCH_SIZE};   -- repeat until 0 rows
EOF
)

if [ "$DRY_RUN" = "1" ]; then
    echo "[audit-retention] DRY-RUN preview:"
    echo "  non_flagged_days=${NON_FLAGGED_DAYS} flagged_days=${FLAGGED_DAYS} batch_size=${BATCH_SIZE}"
    echo ""
    echo "  Step 1 — Discover partitions:"
    echo "$dry_drop_partitions_sql" | sed 's/^/    /'
    echo "  Step 2 — Drop partitions whose upper bound < now() - ${FLAGGED_DAYS}d:"
    echo "    DROP TABLE <partition_name>;   -- per fully-expired partition"
    echo "  Step 3 — Per-class DELETE in still-live partitions (batched):"
    echo "$dry_delete_nonflagged_sql" | sed 's/^/    /'
    echo "$dry_delete_flagged_sql"    | sed 's/^/    /'
    exit 3
fi

if [ -z "$DB_URI" ]; then
    echo "[audit-retention] no --db / PGURI / DATABASE_URL set" >&2
    exit 2
fi

# Step 1+2 — partition-level drops. We compute the cutoff month then drop
# partitions whose name suffix is < cutoff_month.
cutoff_month=$(python - "$FLAGGED_DAYS" <<'PY'
import sys, datetime as dt
n = int(sys.argv[1])
today = dt.date.today() - dt.timedelta(days=n)
print(f"{today.year:04d}_{today.month:02d}")
PY
)

partitions=$(psql "$DB_URI" -At -c "$dry_drop_partitions_sql")
dropped=0
for p in $partitions; do
    suffix="${p##*_p_}"
    if [[ ! "$suffix" =~ ^[0-9]{4}_[0-9]{2}$ ]]; then continue; fi
    if [[ "$p" == *__detached ]]; then continue; fi
    if [[ "$suffix" < "$cutoff_month" ]]; then
        psql "$DB_URI" -v ON_ERROR_STOP=1 -c "DROP TABLE IF EXISTS ${p};"
        dropped=$((dropped + 1))
    fi
done
echo "[audit-retention] dropped ${dropped} fully-expired event_audit partitions (cutoff_month=${cutoff_month})"

# Step 3 — per-class DELETE in still-live partitions, batched.
total_nf=0
total_f=0
while true; do
    n=$(psql "$DB_URI" -At -c "WITH d AS (DELETE FROM event_audit WHERE flagged = FALSE AND recorded_at < NOW() - INTERVAL '${NON_FLAGGED_DAYS} days' AND ctid IN (SELECT ctid FROM event_audit WHERE flagged = FALSE AND recorded_at < NOW() - INTERVAL '${NON_FLAGGED_DAYS} days' LIMIT ${BATCH_SIZE}) RETURNING 1) SELECT count(*) FROM d;")
    total_nf=$((total_nf + n))
    if [ "$n" -lt "$BATCH_SIZE" ]; then break; fi
done
while true; do
    n=$(psql "$DB_URI" -At -c "WITH d AS (DELETE FROM event_audit WHERE flagged = TRUE AND recorded_at < NOW() - INTERVAL '${FLAGGED_DAYS} days' AND ctid IN (SELECT ctid FROM event_audit WHERE flagged = TRUE AND recorded_at < NOW() - INTERVAL '${FLAGGED_DAYS} days' LIMIT ${BATCH_SIZE}) RETURNING 1) SELECT count(*) FROM d;")
    total_f=$((total_f + n))
    if [ "$n" -lt "$BATCH_SIZE" ]; then break; fi
done
echo "[audit-retention] deleted non_flagged=${total_nf} flagged=${total_f}"

exit 0
