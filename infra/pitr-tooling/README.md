# PITR tooling — L1.E.8

> **Cycle:** RAID c1 (L1.E Meta HA Infrastructure)
> **Owning chunk:** C03 §12O.3
> **Retention:** 30 days (per parent layer plan)
> **Cross-cycle dep:** L1.H backup-scheduler (cycle 7) provides the base backup format this tool consumes.

## Purpose

Point-In-Time Recovery for the meta Postgres cluster. Combines the most recent
full base backup with WAL replay from `lw-meta-wal-archive` (L1.E.7) to
restore the meta DB to any timestamp within the 30-day retention window.

## Artifacts

| File | Role |
|---|---|
| `lw-pitr-restore.sh` | SRE-facing restore tool (V1 skeleton; full implementation ships with L1.H) |
| `README.md` | This file |

## V1 status

This cycle ships the tool **skeleton + interface contract**. The base-backup
retrieval depends on the L1.H backup-scheduler output format which is owned by
cycle 7 (`L1.A-4 Billing/SRE tables + L1.H Backup + L1.L Capacity + L1.J
Degraded + L1.K 15 lints`). The skeleton:

1. Validates retention-window bounds (rejects target-time older than 30d)
2. Declares the env-var contract (`WAL_ARCHIVE_*`, `BACKUP_BUCKET`, `RETENTION_DAYS`)
3. Emits a machine-readable result so the L1.H restore-drill wrapper
   (`scripts/restore-drill.sh`) can integrate without further coordination
4. Documents exit-code semantics so the SRE runbook
   (`runbooks/meta/pitr_restore.md`) can map errors to remediation

## Acceptance criteria for cycle 1

Per the cycle brief, this artifact's acceptance is **structural validation**:
- script exists, executable bit set
- `set -euo pipefail` present
- usage message documented in the header
- exit codes 64..68 distinct + documented
- env-var contract using `:?` for required secrets (CLAUDE.md "no hardcoded secrets")

End-to-end PITR drill validation defers to cycle 7 L1.H.

## Cross-references

- WAL ship script: `infra/wal-archive/lw-wal-ship.sh`
- Base config: `infra/postgres/postgresql.conf`
- Runbook: `runbooks/meta/pitr_restore.md`
- Backup-scheduler (future): `services/backup-scheduler/` (L1.H, cycle 7)
