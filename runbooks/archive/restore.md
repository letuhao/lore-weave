# Runbook — Restoring archived events (L2.J)

> **Status (cycle 11):** SKELETON. `cmd/archive-restore` ships V1 sub-commands
> `list` + `fetch` that print expected key shapes; the full restore-into-temp-table
> wiring is **deferred** alongside D-PUBLISHER-LIVE-WIRING (row 054). Until
> then, this runbook is the canonical manual procedure.

## When to invoke

- A forensic query needs events older than the archive cutoff (default 90d).
- A bug investigation needs to confirm an archived event's original payload.
- Disaster-recovery: a per-reality DB was lost and you need to re-replay the
  full event log from cold archive into a fresh DB.

## Pre-flight

1. Confirm the reality has archived months:

   ```bash
   psql "$PER_REALITY_DSN" -c "SELECT partition_name, archived_at, byte_size, row_count
                                  FROM archive_state
                                 WHERE reality_id = '$REALITY_ID'
                                 ORDER BY archived_at;"
   ```

2. Confirm the MinIO bucket is reachable:

   ```bash
   mc ls lw-platform/lw-event-archive/events/$REALITY_ID/
   ```

3. Confirm the `archive-restore` CLI's expected ABI matches the blob you're
   about to fetch:

   ```bash
   archive-restore fetch --reality $REALITY_ID --month 2025-11
   # Output includes: expected blob ABI: magic="LWP1" schema_version=1
   ```

## Manual restore — single month

Until the full CLI wiring lands, manually fetch the Parquet blob, decode the
header to confirm row count, and (for the temp-table workflow) hand-import:

```bash
# 1. Download blob
mc cp lw-platform/lw-event-archive/events/$REALITY_ID/2025-11.parquet ./2025-11.parquet

# 2. Verify header markers (LWP1 ... LWP1)
xxd ./2025-11.parquet | head -1
xxd ./2025-11.parquet | tail -1

# 3. (Future: decode rows into temp table for SQL query.)
#    V1: hand-write a Go program importing pkg/parquet_writer and ranging
#    over the decoded EventRow slice; insert into a temp table named
#    e.g. archive_restore_2025_11 (NOT in the live events partition tree).
```

## Disaster-recovery — full reality

If a reality DB is lost end-to-end, all archived months MUST be replayed
into a fresh per-reality DB AND every still-attached partition in the prior
DB MUST be exported via `pg_dump` and re-imported. Order matters:

1. Provision fresh per-reality DB via `services/provisioner/` (cycle 5).
2. Apply all migrations (`contracts/migrations/per_reality/0001..0005`).
3. For each archived month (oldest first), `archive-restore fetch` → decode
   → INSERT INTO `events`. The per-aggregate optimistic-CC invariant
   (Q-L2A-...) is preserved because the archived rows already passed it
   at original write time.
4. Restore the most-recent still-attached partitions via `pg_dump`
   round-trip.
5. Re-build snapshots via L3 catastrophic rebuild orchestrator (L3.E.4).

## Operational notes

- **NEVER** `mc rm` an archived object without operator sign-off — the
  archive-worker ACL prohibits `s3:DeleteObject`; only the `sre` role
  has manual delete capability.
- **NEVER** re-import an archived month INTO the live `events` partition
  tree. Always use a temp table — the partition was DROPped after archive,
  re-creating it via INSERT triggers partition-routing surprises.
- If `mc cp` fails partway through, the next attempt is safe — S3 GET is
  atomic at the object level.

## Erase-for-reality (GDPR right-to-be-forgotten)

For per-tenant erasure of archived data, use the `events/<reality_id>/`
key-prefix delete. This is operator-driven (the archive-worker SVID
cannot delete). See `runbooks/archive/erase_for_reality.md` (TBD —
deferred until first GDPR request).
