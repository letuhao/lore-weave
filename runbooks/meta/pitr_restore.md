# Runbook: Meta Postgres Point-In-Time Recovery (PITR)

> **Artifact:** L1.E.10 (RAID cycle 1, L1.E Meta HA Infrastructure)
> **Owning chunk:** C03 §12O.3
> **Audience:** SRE on-call
> **Severity profile:** P0 (meta DB unavailable) → P1 (logical corruption recovery)
> **Tool:** `infra/pitr-tooling/lw-pitr-restore.sh`

## When to invoke

Use PITR when ONE of:

1. **Logical corruption** — operator mistake, faulty migration, application bug
   wrote bad data. Failover (`runbooks/meta/failover.md`) does NOT help — the
   sync replica has the same bad data.
2. **Catastrophic primary loss** — primary EBS volume corrupted AND sync
   replica also lost (extremely rare; cross-AZ DR ships V3+ per Q-L1E-1).
3. **Quarterly DR drill** (per Q-L1H-2 — quarterly full-system drill).

Do NOT use PITR when:
- Primary is just down — use `runbooks/meta/failover.md` instead (Patroni
  promotes sync replica, RTO 30s).
- Single table is corrupted — prefer logical restore via `pg_dump`/`pg_restore`
  of that table from latest nightly logical dump (L1.H tiered backup).

## Prerequisites

- SRE on-call has Bastion access to staging meta cluster
- Operator knows the `target-time` precisely (look at audit logs in
  `service_to_service_audit` table to find the bad write timestamp)
- `lw-meta-wal-archive` bucket is reachable from the restore host
- A spare Postgres host is available (do NOT restore over the existing damaged
  cluster; bring up a new instance, validate, then cut over)

## Procedure (T+0 minutes)

### Step 1 — Triage (5 min)

```bash
# Confirm meta DB state
patronictl -c /etc/patroni/patroni.yml list

# If primary down → failover, not PITR. STOP and read runbooks/meta/failover.md.
# If primary up but data is wrong → continue with PITR.
```

### Step 2 — Identify target time (5 min)

```sql
-- Find the bad write by audit
SELECT id, ts, actor, action, target
FROM service_to_service_audit
WHERE ts BETWEEN '<suspected start>' AND '<suspected end>'
ORDER BY ts DESC
LIMIT 50;
```

Choose `target-time` = timestamp ONE SECOND BEFORE the bad write.

### Step 3 — Provision restore host (10 min)

```bash
# On a fresh EC2 instance or `docker run` in dev
mkdir -p /var/lib/postgresql/pitr
export WAL_ARCHIVE_BUCKET=lw-meta-wal-archive
export BACKUP_BUCKET=lw-db-backups
export WAL_ARCHIVE_ENDPOINT=https://minio.loreweave.app
export WAL_ARCHIVE_ACCESS_KEY=...    # from Vault path /secrets/wal-archive
export WAL_ARCHIVE_SECRET_KEY=...    # from Vault path /secrets/wal-archive
```

### Step 4 — Restore (15 min)

```bash
infra/pitr-tooling/lw-pitr-restore.sh \
  --target-time "2026-05-29T14:23:14Z" \
  --restore-dir /var/lib/postgresql/pitr
```

The tool exits 0 with a JSON result on success. Common exit codes:

| Exit | Meaning | Action |
|---|---|---|
| 64 | Usage error | Check args; consult `--help` |
| 65 | Target-time exceeds 30d retention | Data is unrecoverable; escalate to ENG |
| 66 | Bucket access failure | Check Vault credentials; check MinIO health |
| 67 | Base backup missing | L1.H backup-scheduler issue — escalate to ENG |
| 68 | WAL replay failure | Inspect Postgres logs; possibly bad WAL segment |

### Step 5 — Validate restore (10 min)

```bash
# Start Postgres on the restore host in single-user mode
pg_ctl -D /var/lib/postgresql/pitr start

# Verify the bad write is GONE
psql -c "SELECT * FROM <table> WHERE id = '<bad row>'"
# Should return 0 rows (or pre-corruption state)

# Verify recent good writes are PRESENT (those before the bad write)
psql -c "SELECT count(*) FROM <table> WHERE ts < '<target-time>'"
# Should match expected count
```

### Step 6 — Cut over (15 min)

Coordinate with on-call ENG. Options:

- **Option A (preferred)**: Use the restored host as the new primary. Stop
  Patroni on old cluster, point Patroni's DCS (etcd) at the new host, restart
  replicas to follow the new primary.
- **Option B (last resort)**: Stop ALL meta writes via L1.J degraded-mode
  (force `ServiceMode=ReadOnly` across all services), `pg_dump` the restored
  table, `pg_restore` into the live primary, exit degraded mode.

Both options require an L1.J degraded-mode window. Option A is faster (~5
minutes downtime); Option B is safer for partial corruption (only one table
affected).

## Post-recovery

1. Write an incident report (R9 close confirmation required).
2. Run `scripts/restore-drill.sh` (L1.H.4) to confirm the next-scheduled drill
   still passes (catches "drill broke due to operator intervention").
3. Open a follow-up issue: "why did the bad write happen — what lint should
   have caught it?" (L1.K candidate).

## RPO / RTO targets

| Metric | Target | Reality |
|---|---|---|
| RPO (WAL ship) | ≤ 60s | Bounded by `archive_timeout=60` |
| RTO (PITR restore) | < 4h for 24h-old target | Bounded by base-backup retrieval + WAL replay |
| RTO (failover) | 30s | See `failover.md` (Patroni-driven) |

## Cross-references

- Tool: `infra/pitr-tooling/lw-pitr-restore.sh`
- WAL ship: `infra/wal-archive/lw-wal-ship.sh`
- Failover runbook: `runbooks/meta/failover.md`
- Backup scheduler (cycle 7): `services/backup-scheduler/`
- LOCKED Qs: Q-L1H-1 (MinIO bucket), Q-L1H-2 (monthly + quarterly drill cadence)
