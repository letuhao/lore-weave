# Runbook — Migration persistent failure

> **Owner:** SRE on-call (#oncall-sre)
> **Triggered by:** Prometheus alert `lw_migration_persistent_failure` (defined
> in `infra/prometheus/alerts/meta.yaml`, fires when
> `reality_migration_audit.event_type='migration_failed'` count
> for a given `(migration_id)` exceeds the 5-attempt warning threshold).
>
> **LOCKED decision:** Q-L1D-1 (`OPEN_QUESTIONS_LOCKED.md` line 38) —
> V1 = doc-only manual rollback by SRE. V2+ will add auto-rollback for
> non-data-changing migrations only. **This runbook IS the V1 rollback
> path.** Do NOT add scripts that mutate state without the steps below.

---

## What just happened

The `migration-orchestrator` service exhausted all retries (default 3
attempts with exponential backoff 100ms / 200ms / 400ms) for a
`(reality_id, migration_id)` pair and wrote a `migration_failed` audit
row plus a `failure_reason='persistent'` row to
`instance_schema_migrations`. The orchestrator did NOT roll back —
that's intentional for V1. The reality is now in a partial-apply state
that requires human judgment to resolve.

---

## Triage checklist (work top-to-bottom)

### 1. Identify scope

```bash
# Find the most recent failure events
psql -c "
  SELECT reality_id, migration_id, attempt_number, failure_detail, occurred_at
  FROM reality_migration_audit
  WHERE event_type IN ('migration_failed','migration_aborted')
    AND occurred_at > NOW() - INTERVAL '1 hour'
  ORDER BY occurred_at DESC
  LIMIT 50;
"
```

- **Single reality?** → goto step 2 (per-reality manual restore).
- **Many realities, same migration_id?** → goto step 4 (suspect breaking
  migration; check canary trail).

### 2. Snapshot the affected reality

```bash
# Find the shard hosting the reality
psql -c "
  SELECT db_host, db_name, status, last_migration_id
  FROM reality_registry WHERE reality_id = '<REALITY_ID>';
"

# Take an immediate WAL-archive checkpoint so PITR baseline is fresh
infra/wal-archive/lw-wal-ship.sh --reality <REALITY_ID> --force-checkpoint
```

### 3. Inspect partial-apply state

The orchestrator applies migration DDL inside a transaction per **statement**,
not per **migration**, so a mid-migration crash CAN leave some statements
applied. Compare the per-reality DB schema against the migration's SQL:

```bash
# Connect to the per-reality DB
psql -h <db_host> -d <db_name>

# Inspect the migration SQL
cat contracts/migrations/per_reality/<MIGRATION_ID>.up.sql

# Compare: which objects from the SQL exist? Which don't?
psql -h <db_host> -d <db_name> -c "\dt"
psql -h <db_host> -d <db_name> -c "\di"
```

Common partial states:

| State | What to do |
|---|---|
| **0% applied** — no objects present | Re-run the migration: `migrate <migration_id>` (idempotent — see step 5). |
| **Partial** — some tables created, some not | Manually apply the missing DDL. If structurally risky, restore from PITR: `runbooks/meta/pitr_restore.md`. |
| **100% applied but `instance_schema_migrations` row missing** | Manually insert the row: `INSERT INTO instance_schema_migrations(reality_id, migration_id, applied_at, applied_by) VALUES (...);` |
| **100% applied + data corruption** | Restore from latest backup per `runbooks/backup/restore.md`. |

### 4. Canary aborted breaking migration

If the failure was a **breaking** migration (check
`contracts/migrations/manifest.yaml` for `breaking: true`), the canary
flow halted before fan-out. The migration_aborted rows in
`reality_migration_audit` enumerate the realities that did NOT receive
the migration. Only the canary reality is partially applied; everything
else is untouched.

- Investigate the canary's failure_detail before re-attempting.
- If the canary's problem was data-shape-specific to the canary reality
  (e.g., a deprecated row format), fix it on the canary, then re-run the
  full set with `migrate <migration_id>` (will skip already-applied
  realities by the orchestrator's `instance_schema_migrations` precheck).
- If the migration itself is buggy → revert the manifest entry, ship a
  fixed version with a new id, and re-run.

### 5. Idempotency invariant

Every shipped migration MUST be idempotent per
`scripts/migration-idempotency-validator.sh` (L1.D.7). That means
re-applying a partially-applied migration is safe — every DDL uses
`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` /
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. If a migration is genuinely
not safe to re-apply, the validator should have rejected it at CI; if
you're holding such a migration, file a bug against the validator.

### 6. Re-run the migration

```bash
# Inspects which (reality, migration) pairs are already DONE and skips them.
migrate <MIGRATION_ID> --dry-run    # always dry-run first
migrate <MIGRATION_ID>
```

### 7. Verify resolution

```bash
psql -c "
  SELECT reality_id, migration_id, applied_at, failure_reason
  FROM instance_schema_migrations
  WHERE migration_id = '<MIGRATION_ID>'
  ORDER BY applied_at DESC LIMIT 20;
"
```

- `failure_reason = NULL` for all rows → success.
- Some still NULL applied_at → re-run for those specific realities.

### 8. Post-incident

- File a brief on the migration's bug + how it slipped past the
  idempotency validator (if it did).
- If the same migration failed on >1 reality with the same root cause,
  add a pre-flight check to the orchestrator that catches the root
  cause cheaper. Track as enhancement for V1+30d.

---

## Auto-rollback (V2+)

The auto-rollback path lands in V2+ for **non-data-changing** migrations
only (CREATE INDEX, COMMENT, GRANT). It will:

1. Detect the failed migration's DDL is purely structural (lint).
2. Run the matching DOWN migration in the same TX semantics.
3. Record `migration_rolled_back` in `reality_migration_audit`.

Data-changing migrations (ALTER TABLE ADD COLUMN with DEFAULT, INSERT
SELECT, etc.) will NEVER auto-rollback — they always require this
runbook.

## Related runbooks

- `runbooks/meta/failover.md` — if the meta-HA primary failed during a migration run
- `runbooks/meta/pitr_restore.md` — if per-reality data corruption is suspected
- `runbooks/backup/restore.md` — if a tier-2/3 backup restore is needed (cycle 7 ships)
- `runbooks/provisioner/orphan_resolution.md` — if the reality is in `status=provisioning` indefinitely
