# Workload generator (S3)

A **seeded, deterministic** generator that produces valid foundation event
streams and writes them through the **real Go outbox path** so the base→derived
pipeline runs. It is **S3** of the foundation runtime test plan
([`docs/specs/2026-06-04-foundation-runtime-test-plan.md`](../../docs/specs/2026-06-04-foundation-runtime-test-plan.md))
— the dependency root that feeds the C/C2/C3 oracles, the B-shards, the fault
matrix, the perf rig, and the DST seed.

## Run it

```sh
cd tests/workload-gen
go test ./...

# dry-run: print the stream as JSONL (no DB) — inspect / diff for determinism
go run ./cmd/workload-gen -seed 1 -profile single-reality

# emit: write the stream via the real outbox path
go run ./cmd/workload-gen -seed 1 -profile single-reality -emit -dsn "$DSN"
```

A given `-seed` + `-profile` is **byte-deterministic** across runs (seed-derived
ids + a fixed logical clock, never wall-clock). The stream is **always
validated** (referential + causal + monotonic) before it is printed or written.

## Profiles

| Profile | Shape |
|---|---|
| `micro` | 1 reality, 1 region, 1 npc, 1 session — for C unit tests |
| `single-reality` | many aggregates/tables — the main spine flow |
| `multi-reality` | 3 realities (cross-shard — I5/I7) |
| `multi-user-session` | many sessions + participants (I6) |

## What it generates

Valid streams across the **currently projection-handled** event types (the
generator writes direct to the event store, so it may emit handled-but-not-yet-
registered types like `pc.*`/`region.*`/`session.*`/`world.kv.*`):

`region.created/ambient_changed` · `npc.created/said` ·
`session.started/ended/participant_joined/left` ·
`pc.spawned/moved/item_acquired/relationship_changed` ·
`world.kv_set/unset` · `canon.entry.created/updated/promoted/decanonized`.

Payload fields are kept in lockstep with each Rust projection `apply_event` arm
(`crates/projections/*/src/lib.rs`); `internal/schema.Specs` is the contract and
the schema tests are the drift guard. (`admin.canon.override.compensating` and
`canon.change.recorded` are **not** generated — their arms are still TODO.)

## The write path

`emit` reuses `contracts/events.OutboxWrite` verbatim, one transaction per event
in stream order:

```
BEGIN → INSERT INTO events(…) → events.OutboxWrite(tx, …) → COMMIT
```

— atomic (I13/Q-L1B-3), no SQL drift. Stream order is preserved so cross-
aggregate causality holds in the outbox (e.g. `session.started` is enqueued
before the `npc.said` that updates its session-memory row).

**Partitioning note:** the generator stamps a fixed logical clock
(`recorded_at` from 2026-01-01). `events` is RANGE-partitioned by `recorded_at`
(monthly), so the target DB must have a partition covering that range — the
pipeline smoke creates a `DEFAULT` partition; a production-provisioned per-reality
DB needs its 2026-01 (or DEFAULT) partition present or `-emit` fails with
"no partition for row".

## Pipeline scope (important)

`-emit` writes `events` + `events_outbox`; the **publisher** then drains the
outbox to Redis. The **projection-WRITE runtime** (events → projection tables)
is cycle-14+ `world-service` work and is **not part of the foundation yet** — the
cycle-13 projections are libraries with no DB-write side. So the end-to-end
`emit → … → integrity-checker clean` live-smoke cannot be closed until that
runtime lands; see the `D-WORKLOAD-GEN-PIPELINE-LIVE` deferred row.
