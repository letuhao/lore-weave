# WAL archive — L1.E.7

> **Cycle:** RAID c1 (L1.E Meta HA Infrastructure)
> **Owning chunk:** C03 §12O.3
> **LOCKED Qs:** Q-L1H-1 (MinIO pre-existing; foundation adds `lw-db-backups` + `lw-meta-wal-archive` buckets only)

## Purpose

Continuously ship WAL segments from the meta Postgres primary to MinIO/S3 so
PITR restore (L1.E.8) can recover to any point within the 30-day retention
window.

## Artifacts

| File | Role |
|---|---|
| `lw-wal-ship.sh` | `archive_command` script — Postgres invokes per WAL segment |
| `README.md` | This file |

## Bootstrap target

| V1 (foundation-dev) | V1 (staging, +30d) | V3+ |
|---|---|---|
| MinIO bucket `lw-meta-wal-archive` in `infra/docker-compose.meta-ha.yml` | Same bucket on shared MinIO (per Q-L1H-1) | Cross-region replication of bucket (per Q-L1E-1 — V3+ DR) |

## RPO budget

`archive_timeout=60` in `infra/postgres/postgresql.conf` bounds RPO to **60s**
even when no commits force WAL rotation. Combined with `synchronous_commit=on`
this gives:

- **RPO = 0s** for committed transactions to sync replica
- **RPO ≤ 60s** for WAL segments to archive
- **RTO = 30s** for primary failover via Patroni (see L1.E.4)

## Operational notes

- `lw-wal-ship.sh` exits non-zero on any failure → Postgres retries at next
  checkpoint. Silent failure is the most dangerous bug class here, so the
  script propagates errors loudly.
- Bucket auth uses env vars `WAL_ARCHIVE_ACCESS_KEY` / `WAL_ARCHIVE_SECRET_KEY`
  — NEVER hardcoded. Per CLAUDE.md "No hardcoded secrets".
- Object keys are date-partitioned `<YYYY>/<MM>/<DD>/<WAL_FILENAME>` for
  restore-tooling efficiency.

## Verification

The cycle-1 verify script (`scripts/raid/verify-cycle-1.sh`) parses this script
for the required `set -euo pipefail` line and bucket-name env-var contract.
Full end-to-end WAL ship verification requires the running meta-ha docker stack
+ MinIO bucket — deferred to V1+30d staging acceptance per Q-L1C-1.
