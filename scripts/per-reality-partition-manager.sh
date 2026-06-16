#!/usr/bin/env bash
# scripts/per-reality-partition-manager.sh — L2.A (RAID cycle 9 DPS 1)
#
# Per-reality partition lifecycle manager for the `events` + `event_audit`
# monthly-range-partitioned tables (Q-L2-2). Two operations:
#
#   * `create-ahead`: create next-month partition 7d before the rollover so
#                     the first insert of the new month never hits a missing
#                     partition. Idempotent (CREATE TABLE IF NOT EXISTS).
#   * `detach-old`:   detach partitions older than `RETENTION_MONTHS` (default
#                     12). Detached partitions are renamed `<orig>__detached`
#                     and left in place so the L2.J archive-worker (cycle 11)
#                     can scoop them to MinIO Parquet/ZSTD before final DROP.
#
# This script ships the CONTRACT + dry-run + smoke harness in cycle 9. The
# wired-into-cron deployment lands in cycle 11 (L2.J/K archive + retention
# workers); until then the script is callable manually for ops drills.
#
# Idempotency contract:
#   * create-ahead: re-running with same target month is a no-op
#     (CREATE TABLE IF NOT EXISTS); never errors.
#   * detach-old:   skips already-detached partitions (the `__detached`
#                   suffix check); never throws.
#
# Usage:
#   per-reality-partition-manager.sh create-ahead [--dry-run] [--db <conn>] [--table events|event_audit]
#   per-reality-partition-manager.sh detach-old   [--dry-run] [--retention-months N] [--db <conn>] [--table events|event_audit]
#   per-reality-partition-manager.sh list         [--db <conn>] [--table events|event_audit]
#
# Exit codes: 0=ok, 1=usage error, 2=psql failure, 3=dry-run preview only.
#
# Environment fallbacks (when --db not given): PGURI, then DATABASE_URL, then
# `postgresql:///<current-user>` (libpq default — useful for local docker-compose).

set -euo pipefail

OP="${1:-}"
shift || true

DRY_RUN=0
DB_URI="${PGURI:-${DATABASE_URL:-}}"
TABLE="events"
RETENTION_MONTHS=12

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)            DRY_RUN=1; shift ;;
        --db)                 DB_URI="$2"; shift 2 ;;
        --table)              TABLE="$2"; shift 2 ;;
        --retention-months)   RETENTION_MONTHS="$2"; shift 2 ;;
        *)
            echo "[partition-manager] unknown arg: $1" >&2
            exit 1
            ;;
    esac
done

case "$TABLE" in
    events|event_audit) ;;
    *) echo "[partition-manager] --table must be 'events' or 'event_audit'" >&2; exit 1 ;;
esac

case "$OP" in
    create-ahead|detach-old|list) ;;
    *)
        echo "usage: per-reality-partition-manager.sh {create-ahead|detach-old|list} [opts]" >&2
        exit 1
        ;;
esac

# Build the psql invocation. When DB_URI is empty we omit -d so libpq uses
# the user's default — also lets `--dry-run` work without any DB at all
# (we just print the SQL).
psql_exec() {
    local sql="$1"
    if [ "$DRY_RUN" = "1" ]; then
        echo "[partition-manager] DRY-RUN sql:"
        echo "$sql" | sed 's/^/  /'
        return 0
    fi
    if [ -z "$DB_URI" ]; then
        echo "[partition-manager] no --db / PGURI / DATABASE_URL set; cannot execute live" >&2
        return 2
    fi
    psql "$DB_URI" -v ON_ERROR_STOP=1 -c "$sql"
}

next_month_range() {
    # Compute [start_of_next_month, start_of_month_after_next) windows in
    # YYYY-MM-DD form. Uses python for portable date math.
    python - <<'PY'
import datetime as dt
today = dt.date.today()
y, m = today.year, today.month
nm_y, nm_m = (y + 1, 1) if m == 12 else (y, m + 1)
nnm_y, nnm_m = (nm_y + 1, 1) if nm_m == 12 else (nm_y, nm_m + 1)
start = dt.date(nm_y, nm_m, 1)
end   = dt.date(nnm_y, nnm_m, 1)
print(f"{start} {end} events_p_{start:%Y_%m} event_audit_p_{start:%Y_%m}")
PY
}

retention_cutoff_month() {
    python - "$RETENTION_MONTHS" <<'PY'
import sys, datetime as dt
n = int(sys.argv[1])
today = dt.date.today()
y, m = today.year, today.month
for _ in range(n):
    y, m = (y - 1, 12) if m == 1 else (y, m - 1)
print(f"{y:04d}_{m:02d}")
PY
}

case "$OP" in
    create-ahead)
        read -r START END EVENTS_NAME AUDIT_NAME <<<"$(next_month_range)"
        if [ "$TABLE" = "events" ]; then
            P_NAME="$EVENTS_NAME"
        else
            P_NAME="$AUDIT_NAME"
        fi
        sql="CREATE TABLE IF NOT EXISTS ${P_NAME} PARTITION OF ${TABLE} FOR VALUES FROM ('${START}') TO ('${END}');"
        psql_exec "$sql"
        echo "[partition-manager] create-ahead OK: ${TABLE} → ${P_NAME} [${START},${END})"
        ;;
    detach-old)
        cutoff="$(retention_cutoff_month)"
        # We can't enumerate partitions without a live DB; in dry-run print
        # the discovery SQL + the rename pattern for reviewer.
        discover_sql="SELECT inhrelid::regclass::text FROM pg_inherits WHERE inhparent='${TABLE}'::regclass;"
        if [ "$DRY_RUN" = "1" ]; then
            echo "[partition-manager] DRY-RUN detach-old:"
            echo "  cutoff_month=${cutoff} retention_months=${RETENTION_MONTHS}"
            echo "  discovery: ${discover_sql}"
            echo "  for each partition matching '${TABLE}_p_YYYY_MM' WHERE YYYY_MM < ${cutoff}:"
            echo "    ALTER TABLE ${TABLE} DETACH PARTITION <p>;"
            echo "    ALTER TABLE <p> RENAME TO <p>__detached;"
            exit 3
        fi
        if [ -z "$DB_URI" ]; then
            echo "[partition-manager] no DB URI; cannot detach live" >&2
            exit 2
        fi
        partitions="$(psql "$DB_URI" -At -c "$discover_sql")"
        detached_count=0
        for p in $partitions; do
            # Extract YYYY_MM suffix
            suffix="${p##*_p_}"
            if [[ ! "$suffix" =~ ^[0-9]{4}_[0-9]{2}$ ]]; then continue; fi
            # Skip already-detached partitions (the rename suffix)
            if [[ "$p" == *__detached ]]; then continue; fi
            if [[ "$suffix" < "$cutoff" ]]; then
                psql "$DB_URI" -v ON_ERROR_STOP=1 -c "ALTER TABLE ${TABLE} DETACH PARTITION ${p};"
                psql "$DB_URI" -v ON_ERROR_STOP=1 -c "ALTER TABLE ${p} RENAME TO ${p}__detached;"
                detached_count=$((detached_count + 1))
            fi
        done
        echo "[partition-manager] detach-old OK: ${TABLE} detached=${detached_count} cutoff=${cutoff}"
        ;;
    list)
        if [ -z "$DB_URI" ]; then
            echo "[partition-manager] no DB URI; cannot list live" >&2
            exit 2
        fi
        psql "$DB_URI" -At -c "SELECT inhrelid::regclass::text FROM pg_inherits WHERE inhparent='${TABLE}'::regclass ORDER BY 1;"
        ;;
esac

exit 0
