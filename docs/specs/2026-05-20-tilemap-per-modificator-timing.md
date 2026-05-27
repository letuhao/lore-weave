# Spec — Per-modificator timing in `tilemap-service measure`

> **Status:** CLARIFY → DESIGN.
> **Track:** `LLM_MMO_RPG` (tilemap-service).
> **Size:** M (default v2.2 human-in-loop).
> **Follows:** the 2026-05-20 perf fix (#016 + #018 cleared) and the
> reframing of finding O-1 — modificator pipeline = 99.98 % of continent
> wall time (DEFERRED #029).

---

## 1. Problem

The 2026-05-20 per-stage continent measurement showed:

```
place_zones    : 0.110 s
modificators   : 687.139 s  ← 99.98 % of total — but which placer?
place_tilemap  : 687.249 s
```

DEFERRED #029 names the modificator pipeline as the next bottleneck but
*does not* identify which of the six placers dominates. Without that
breakdown the targeted fix in #029 has no target — and the measurement
re-run takes ~11 min per try, so eyeballing per-placer cost by toggling
modificators is expensive.

Likely suspect per the captured lesson: `TreasurePlacer::place_and_connect_object`
is ~O(zone_tiles²) per placement, compounded across 456 placements. But
the road / river / obstacle / connection passes all run Dijkstra `search_path`
calls, any of which could dominate. The point of this task is to **stop
guessing and measure**.

## 2. Goal

Add per-modificator wall-time to the `measure` output so finding O-1 reframes
into a concrete next-target.

## 3. Approach

Add a sibling `ModificatorRegistry::execute_with_timing(&self, ctx) ->
crate::Result<Vec<(String, Duration)>>` that mirrors `execute` but
timestamps each `Modificator::process` call. The existing `execute` is
untouched (zero overhead for production callers).

Then add a sibling `engine::place_tilemap_with_timings(...) ->
crate::Result<(TilemapView, PlacementStageTimings)>` that returns the view
alongside `PlacementStageTimings { place_zones: Duration, modificators:
Vec<(String, Duration)> }`. `measure_offline` calls it (replacing the
current "dry call to place_zones then full place_tilemap" — net code is
cleaner because no double-run).

The existing public `place_tilemap` is untouched — production callers
pay zero cost.

## 4. Determinism contract

- `execute_with_timing` must return modificators in **the same execution
  order** as `execute` — topological order, deterministic per spec D6.
- Timing addition does **not** change `TilemapView` output. The byte-exact
  golden test continues to pass with no rebaseline.

## 5. Files touched (estimate)

| Path | Change |
|---|---|
| `services/tilemap-service/src/engine/pipeline/registry.rs` | NEW `execute_with_timing` method + 1 unit test |
| `services/tilemap-service/src/engine/mod.rs` | NEW `place_tilemap_with_timings` + `PlacementStageTimings` struct |
| `services/tilemap-service/src/harness/continent.rs` | `OfflineMeasurement.modificator_timings` field; `measure_offline` switches to the new helper; `render_offline` prints the per-modificator breakdown |
| `docs/specs/2026-05-20-tilemap-per-modificator-timing.md` | THIS FILE |
| `docs/measurements/2026-05-18-continent.md` | append 2026-05-20 per-modificator measurement once it runs |

5 files. **M.**

## 6. Acceptance criteria

- **AC-1** `execute_with_timing_returns_per_modificator_durations_in_execution_order`
  — unit test in `registry.rs` using the existing `LogMod` pattern; assert
  the returned `Vec<(String, Duration)>` matches the execution order
  asserted by `execute_runs_modificators_in_topological_order`.
- **AC-2** `place_tilemap_with_timings_returns_the_same_view_as_place_tilemap`
  — integration assertion that the new helper produces a `TilemapView`
  equal (`PartialEq`) to the existing `place_tilemap`.
- **AC-3** `cargo test --workspace` green; `cargo clippy --workspace
  --all-targets` 0 warnings; golden test `golden_baseline_byte_identical`
  unchanged.
- **AC-4** running `cargo run --release --package tilemap-service -- measure`
  reports the per-modificator breakdown — recorded in the SESSION entry.
