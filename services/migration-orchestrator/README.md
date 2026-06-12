# migration-orchestrator (L1.D)

> Go service that drives schema migrations across N per-reality databases.
>
> Shipped in **RAID cycle 6** as 9 deliverables L1.D.1–L1.D.9.

## Responsibilities (L1.D §2)

1. Read `contracts/migrations/manifest.yaml` → ordered migration set.
2. For each pending `(reality_id, migration_id)`:
   - dispatch one "migration run" through `internal/runner`
   - concurrency cap = **10** active runners; queue the rest
   - per-run retry with exponential backoff (3 attempts then dead-letter)
3. For migrations marked `breaking: true`: route through `internal/canary`
   to apply on a **single** reality first, wait for verification, then
   fan out to the rest.
4. Persist outcome to two meta tables (writes go through MetaWrite() so
   audit + outbox land in the same TX):
   - `instance_schema_migrations` — final state per (reality, migration)
   - `reality_migration_audit` — every event (start / succeed / fail / etc.)

## Locked decisions

- **Q-L1D-1** (`OPEN_QUESTIONS_LOCKED.md` line 38): V1 = doc-only manual
  rollback by SRE (see `runbooks/migration/persistent_failure.md`). V2+
  will add auto-rollback for non-data-changing migrations only.
  **This cycle ships NO rollback code path.**

## Layout

```
services/migration-orchestrator/
  README.md                        — this file
  go.mod / go.sum                  — module deps
  cmd/migrate/                     — admin CLI (L1.D.4)
  pkg/
    manifest/                      — manifest.yaml loader + validator (L1.D.5 backing)
    runner/                        — concurrency-10 + retry/backoff dispatcher (L1.D.2)
    canary/                        — 1-reality-first breaking-migration gate (L1.D.3)
```

## CLI usage

```
migrate list                                  # show declared migrations
migrate <migration_id> --dry-run              # print the plan
migrate <migration_id>                        # cycle 7+ wires live dispatch
```

## Cross-cycle dependencies

- **Cycle 2 (L1.B)** — `contracts/meta` provides `MetaWrite()` +
  `instance_schema_migrations` / `reality_migration_audit` tables.
- **Cycle 5 (L1.C)** — `contracts/migrations/per_reality/0001_initial.sql`
  is the first migration manifest entry. Provisioner's
  `register_prometheus_scrape` Effect (L1.I.1 integration hook).
- **Cycle 7+** — live MetaWriter / per-reality Applier wiring. Tracked
  as deferred row `D-MIGRATE-CLI-LIVE-WIRING` in `docs/deferred/DEFERRED.md`.

## Test coverage

- `pkg/manifest/*_test.go` — manifest schema + the cycle-5
  skeleton invariant
- `pkg/runner/*_test.go` — concurrency-cap (50 jobs, peak ≤ 10),
  transient retry, persistent dead-letter, exponential backoff, V1
  no-auto-rollback assertion
- `pkg/canary/*_test.go` — 1-reality-first dispatch, hard wait
  on verification gate (not async), canary failure aborts fan-out,
  verification timeout aborts
- `cmd/migrate/main_test.go` — CLI list / dry-run / unknown-migration
- `tests/integration/migration_run_test.go` (build-tag `integration`) —
  end-to-end 10-reality run with mixed transient + persistent failures
  + manifest skeleton reference + canary integration

## Idempotency lint

`scripts/migration-idempotency-validator.sh` (L1.D.7) scans the
shipped per-reality migration SQL for non-idempotent patterns:

- `CREATE TABLE` without `IF NOT EXISTS`
- `CREATE INDEX` without `IF NOT EXISTS`
- `DROP TABLE` / `DROP INDEX` without `IF EXISTS`
- `ALTER TABLE ADD/DROP COLUMN` without `IF [NOT] EXISTS`
