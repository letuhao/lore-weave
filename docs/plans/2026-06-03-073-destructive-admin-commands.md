# 073 — Destructive/griefing admin command wiring (capacity-override live; rebuild gated)

**Date:** 2026-06-03 · **Task:** DEFERRED-073 (destructive tier admin commands) · **Size:** XL (cross-language Rust+Go) · **Mode:** human-in-loop + /review-impl at REVIEW (security-critical destructive paths)

## Context / discovery

073's remaining piece was "live-wire the destructive admin command bodies": `reality capacity-override`,
`reality rebuild-projection`, `reality catastrophic-rebuild`. They currently fall through to the
fail-closed `NotWiredHandler` (tier-1/2 → error, never silent no-op).

DESIGN-phase investigation found the three split sharply:

| Command | Registry tier | Buildable now? |
|---|---|---|
| `reality capacity-override` | tier-2-griefing | **Yes** — pure `MetaWrite` INSERT into `scaling_events` (table + allowlist exist; 24h-expiry CHECK). |
| `reality rebuild-projection` | tier-1-destructive | Bin buildable; **destructive command gated** (see below). |
| `reality catastrophic-rebuild` | tier-1-destructive | Bin buildable; **destructive command gated**. |

**Why the rebuilds are special:** their `RebuildInvoker` needs a real projection-replay worker.
`crates/rebuilder` is a **library with stub writers**; its doc says it is invoked *"via a binary in
`services/world-service/src/bin/`"* with *"real sqlx impls wired in cycle 15+ when world-service consumes
this crate"* (`crates/rebuilder/src/lib.rs:43-48`). No such binary exists, **nothing depends on the crate**,
and **no live `ProjectionRunner`→SQL path exists anywhere** (`embedding_queue/live/mod.rs:27`:
*"no `ProjectionRunner` exists at foundation level"*). So building the bin = building the **first live
projection-apply layer** across the 10 `0006_projections` tables — normally validated by the L3.E/F
integrity-checker, which does not exist yet.

**Safety decision (user, 2026-06-03):** ship capacity-override live; **build** the rebuilder bin +
adapters with unit/PG-gated tests, but keep `rebuild-projection`/`catastrophic-rebuild` **fail-closed
behind an explicit operator opt-in** (`ADMIN_CLI_ENABLE_UNPROVEN_REBUILD=1`) + a loud "UNPROVEN — needs
L3.E/F validation" banner + a DEFERRED row. Rationale: wiring a *catastrophic recovery* tool to an
unproven projection-apply layer is more dangerous than leaving it fail-closed; an operator could trust it
in a real disaster.

## Architecture (locked Q-L3-3 / Q-L3-5)

```
admin capacity-override (Go) ──MetaWrite──▶ scaling_events (meta)         [LIVE]

admin rebuild-projection (Go, GATED)
  1. LifecycleGate.Freeze  : AttemptStateTransition active→frozen  (reality_registry, +lifecycle audit)
  2. ProjectionTruncator   : TRUNCATE <projection_name> RESTART IDENTITY   (per-reality shard DB)
  3. RebuildInvoker        : exec  world-service `rebuilder` bin  → JSON stats on stdout
  4. LifecycleGate.Thaw    : AttemptStateTransition frozen→active  (on success only)
        └─ on rebuild fail / partial: leave FROZEN, operator inspects dead-letter

admin catastrophic-rebuild (Go, GATED) ──▶ rolling_rebuild.Orchestrator
        └─ per reality ──▶ (the rebuild-projection primitives above)

world-service `rebuilder` bin (Rust)
   sqlx event-source (events table, per-aggregate, version-ordered)
     ──▶ ProjectionRunner(6 projection crates) ──▶ generic ProjectionUpdate→SQL writer
                                                       (Insert/Update/Delete/Tombstone, 10 tables)
   ParallelRebuilder (checkpoints + dead-letter) → stats JSON {aggregates_rebuilt/failed, events_replayed}
```

## Build phases

- **A. capacity-override (LIVE).** `internal/commands/capacity_override.go` orchestrator + `…_pg.go`
  `PgScalingEventWriter` (MetaWrite INSERT: `event_type='override'`, `initiator_type='admin'`,
  `override_expires_at`, `payload`, `reason`). `main.go` `buildCapacityOverrideHandler`. Unit + PG-gated tests.
- **B. Rust rebuilder bin.** `services/world-service/src/bin/rebuilder.rs` + `src/rebuild/{event_source,writer,registry}.rs`.
  Add `crates/projections/*` + sqlx to world-service `Cargo.toml`. Generic JSON→SQL writer (table→pk map for
  UPSERT). Stats JSON to stdout. Unit tests + PG-gated integration test where a test DB is available.
- **C. rebuild-projection wiring (GATED).** Go `LifecycleGate` (contracts/meta `AttemptStateTransition`,
  transitions.yaml active↔frozen), `ProjectionTruncator` (validated projection_name allowlist — DDL-injection
  guard), `RebuildInvoker` (subprocess exec + JSON parse). Registration guarded by
  `ADMIN_CLI_ENABLE_UNPROVEN_REBUILD=1`; default = fail-closed NotWired.
- **D. catastrophic-rebuild wiring (GATED).** `RealityRebuilder` closure over Phase-C primitives; reality
  enumeration (all-realities) + aggregate-file parse. Same gate.

## Safety invariants

- projection_name reaching `TRUNCATE` / the bin MUST be validated against a fixed allowlist of the 10
  known projection tables (operator input → DDL). No raw interpolation otherwise.
- Reality stays FROZEN on any rebuild failure/partial (existing `ApplyRebuildProjection` contract).
- Destructive commands remain fail-closed unless the explicit unproven-gate env is set.

## Validation limits / deferrals

- End-to-end correctness of the 6 projections against real seeded events is **not** independently provable
  this session (no integrity-checker, no live seeded stack). PG-gated tests prove the writer mechanics +
  event-source against real tables; full cross-process admin→bin→multi-reality live-smoke is deferred.
- **New DEFERRED rows:** (a) remove the unproven-gate once L3.E/F validates the projection-apply layer;
  (b) cross-process live-smoke; (c) any per-projection upsert-shape gaps found in PG tests.
