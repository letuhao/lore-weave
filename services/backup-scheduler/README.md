# backup-scheduler — L1.H tiered backup orchestrator

## What it does

Reads `reality_registry.status` for every reality on every scheduled tick (per
`contracts/backup/policy.yaml::tiers.<status>.full_interval` cadence), then:

1. Resolves the per-status policy tier
2. Dispatches incremental + full backup jobs at the cadence the tier specifies
3. Ships output to MinIO `lw-db-backups` (Q-L1H-1 dedicated bucket)
4. Writes a `meta_write_audit` row via `MetaWrite()` for every dispatch
   (audit trail required for restore-drill integrity)

## Restore drill (Q-L1H-2)

- **Monthly per-shard:** `cron/restore-drill.cron` triggers
  `scripts/restore-drill.sh` against one random reality per shard. Result lands
  in `archive_verification_log` with `verifier_id='backup-scheduler:auto'`.
- **Quarterly full-system:** SRE runs `runbooks/backup/restore.md` manually.

Drill failure (non-zero exit) drives `BackupDrillFailed` PagerDuty alert per
`infra/prometheus/alerts/meta.yaml`.

## Cycle status

- **Cycle 7 (this cycle):** ships the package skeleton (config loader, tier
  resolver, dispatcher interface, fakes) so other cycle-7 artifacts can
  reference the service in compose / docs. The live MinIO + Postgres-base-backup
  wiring lives in `services/backup-scheduler/cmd/backup-scheduler/` and is
  expected to ship with the L1.E backup-tool integration cycle. Cycle 7 ships
  the **policy contract**, **dispatcher contract**, **restore-drill shell
  script** and **chaos drill yaml**.
- **Next steps (future cycle):** wire libpq base-backup + pg_basebackup
  invocation, ship `cmd/backup-scheduler/main.go` with a real scheduler loop.

## Test pattern

`scheduler_test.go` uses an in-memory `FakeRegistry` + `FakeDispatcher` to
verify (a) every status is mapped, (b) the right tier is chosen, (c) policy
load is idempotent.
