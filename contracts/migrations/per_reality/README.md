# `contracts/migrations/per_reality/`

Per-reality database schema migrations. Applied by the provisioner
(`services/world-service/src/provisioner.rs`, step 5) on every newly
provisioned per-reality DB, in lexical order (`0001_*`, `0002_*`, ...).

## Cycle 5 scope (SKELETON ONLY)

`0001_initial.up.sql` ships the **infrastructure placeholder** schema:

| Table             | Purpose                                              | Real DDL ships in |
|-------------------|------------------------------------------------------|-------------------|
| `events`          | Append-only event log (event-sourcing kernel)        | Cycle 8 (L2)      |
| `outbox`          | Transactional outbox for cross-reality events        | Cycle 8 (L2)      |
| `snapshots`       | Aggregate snapshot table                             | Cycle 12 (L3)     |
| `projection_meta` | Per-projection cursor + verification metadata        | Cycle 13 (L3)     |

The cycle-5 file establishes the minimum scaffolding so:
- the provisioner's step 5 has something concrete to apply
- `tests/integration/reality_lifecycle_test.go` can verify tables exist
- L2/L3 cycles can ADD columns / indexes / partitions via subsequent
  `000N_*.sql` migrations without rewriting this one

## What does NOT go here

- **Domain tables** like `canon_projection` (cycle 23, L5.D) — those are
  per-reality DOMAIN data, not infrastructure
- **Meta tables** like `reality_registry` — those live in `migrations/meta/`
  and apply to the meta DB only

## How to add a new per-reality migration

1. Use the next sequential `000N` prefix
2. Ship both `<name>.up.sql` and `<name>.down.sql`
3. Make UP idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`)
4. Wrap in `BEGIN; ... COMMIT;`
5. Add a row to the table above in this README
6. The L1.D migration orchestrator (cycle 6) will detect the new file
   and roll it out to every reality through its concurrency-10 runner

## Q-L1C-1 reminder

Per `docs/plans/2026-05-29-foundation-mega-task/OPEN_QUESTIONS_LOCKED.md`
Q-L1C-1: **foundation V1 = docker-compose single shard**. Real
Terraform-driven prod shards ship V1+30d. The provisioner integration
test (`tests/integration/reality_lifecycle_test.go`) runs against
`infra/docker-compose.meta-ha.yml` (cycle 1).
