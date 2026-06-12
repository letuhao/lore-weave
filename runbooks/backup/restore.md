# Runbook: Database backup restore

**Owning chunk:** L1.H.7 / R04 §12D.3
**Cadence:** quarterly full-system drill manual; monthly per-shard automated via `scripts/restore-drill.sh`

## When this fires

- Quarterly full-system restore drill (Q-L1H-2 LOCKED) — SRE runs this proactively
- DR scenario — actual data loss requires restore from `lw-db-backups`
- Post-incident verification — restore a snapshot and compare row counts

## Inputs

```
ENV vars
  LW_META_PRIMARY_URL          — meta-primary conn URL
  LW_MINIO_ENDPOINT            — MinIO endpoint (Q-L1H-1 — `lw-db-backups` bucket)
  LW_BACKUP_BUCKET             — defaults to `lw-db-backups`
  LW_RESTORE_TARGET_HOST       — Postgres host to restore INTO (NEVER the primary)
```

## Procedure: per-shard quarterly full drill

### Step 1: Pick target backup

```bash
# List backups for one reality (latest 7)
mc ls --json lw-platform/lw-db-backups/<shard_host>/<reality_id>/ | jq -r '.key' | sort -r | head -n 7
```

Pick the most recent FULL backup (`.full.dump`) — not incremental.

### Step 2: Create isolated restore target

```bash
TARGET_DB="restore_drill_$(date -u +%Y%m%dT%H%M%SZ)"
psql "$LW_RESTORE_TARGET_HOST" -c "CREATE DATABASE $TARGET_DB"
```

NEVER restore into a production database. The drill target is a side
database on a non-production host.

### Step 3: Restore the dump

```bash
mc cp lw-platform/lw-db-backups/<shard>/<reality>/<latest>.full.dump /tmp/
pg_restore -d "$TARGET_DB" -h "$LW_RESTORE_TARGET_HOST" /tmp/<latest>.full.dump
```

### Step 4: Verify

```bash
# Row count sanity (compare vs the live reality if available)
psql "$LW_RESTORE_TARGET_HOST/$TARGET_DB" <<'SQL'
SELECT 'events', count(*) FROM events;
SELECT 'outbox', count(*) FROM outbox;
SELECT 'snapshots', count(*) FROM snapshots;
SQL
```

Acceptance: row counts within 5% of the live reality (allowing for time
since backup). Larger drift = restore is bad → fail the drill.

### Step 5: Record outcome

```bash
psql "$LW_META_PRIMARY_URL" <<SQL
INSERT INTO archive_verification_log
  (verification_id, reality_id, verifier_id, checks_passed,
   status, sample_size, temp_db_host, verified_at)
VALUES
  (gen_random_uuid(), '<reality_id>', 'sre:<your-id>',
   '{"rowcount_match": true, "schema_match": true}'::jsonb,
   'passed', 100, '$LW_RESTORE_TARGET_HOST', now());
SQL
```

### Step 6: Tear down

```bash
psql "$LW_RESTORE_TARGET_HOST" -c "DROP DATABASE $TARGET_DB"
```

## On drill failure

1. Open INCIDENT (SEV1) — backup integrity is broken.
2. Confirm the failure: rerun on a SECOND backup of a DIFFERENT reality on the SAME shard.
3. If both fail: shard's backup pipeline is broken. Page on-call SRE + backup-scheduler engineer.
4. If first failed, second passed: single-backup corruption. Log the bad object name + delete from MinIO so it's not chosen again.

## DR scenario procedure

If actual data loss (NOT a drill):

1. Identify scope — which realities? which time range?
2. Find the latest known-good full backup PRIOR to the data loss event.
3. Restore via Step 2-3 of "per-shard quarterly full drill" above, but
   target a fresh reality DB host that will REPLACE the corrupted one.
4. Apply WAL incrementals up to T-1min before the data-loss event.
5. Update `reality_registry.db_host` for affected realities to point at the
   restored host (via `AttemptStateTransition` only — never raw UPDATE).
6. Confirm via SLO dashboards that traffic resumes.
7. Postmortem within 5 days (SEV0/SEV1 mandate per SR02).
