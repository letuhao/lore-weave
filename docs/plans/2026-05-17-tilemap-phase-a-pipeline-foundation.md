# Plan — tilemap-service Phase A: Pipeline Foundation

> **Spec:** [`docs/specs/2026-05-17-tilemap-phase-a-pipeline-foundation.md`](../specs/2026-05-17-tilemap-phase-a-pipeline-foundation.md)
> (D1-D12, AC-1..AC-10, §6 module design — REVIEW(design) closed r5 APPROVED_WITH_WARNINGS).
> **Size:** XL · **Mode:** AMAW · **Date:** 2026-05-17

## Build chunks

Six chunks, dependency-ordered, each TDD (failing test → implement → `cargo test`
green before the next). `cargo test --workspace` must stay green at every chunk
boundary — Phase A changes no generation output, so the golden snapshot (chunk 1)
is a live regression gate from chunk 5 on.

### Chunk 1 — Golden baseline snapshot (AC-9)

**Must run before any other Phase A change.** Capture the **pre-Phase-A**
`place_tilemap` output as a committed golden file so later chunks prove they
change nothing.

- Read `tests/determinism.rs` to identify its fixture template + seed(s).
- Add a small `xtask`/test-only path: run the current engine, serialize the
  `TilemapView` to `tests/golden/phase_a_baseline.json` (one file per fixture
  seed), commit it.
- Add `tests/determinism.rs::ac9_golden_baseline_byte_identical` — `include_str!`
  the golden, deserialize, assert `==` the freshly generated `TilemapView`.
- At chunk 1 the test passes trivially (engine unchanged); it becomes the
  regression tripwire once chunks 2-6 land.

Files: `tests/golden/phase_a_baseline.json` (new), `tests/determinism.rs` (mod).

### Chunk 2 — Leaf types + schema extensions

No engine dependencies — pure type definitions.

- `types/object_template.rs` (new) — `FootprintCell { dx, dy, blocking }`,
  `TilemapObjectTemplate { name, cells }`, `footprint_at` (all cells),
  `blocking_footprint_at` (blocking cells only), `fits`, `area`; both projections
  return `None` on any out-of-bounds cell.
- `types/treasure.rs` (new) — `TreasureTierSpec { min, max, density }`.
- `types/zone.rs` (mod) — `RoadOption { True, False, Random }` enum.
- `types/template.rs` (mod) — `TemplateConnection` += `guard_strength: u32` +
  `road: RoadOption`; `ZoneSpec` += `treasure_tiers: Vec<TreasureTierSpec>`. All
  `#[serde(default)]`.
- `types/mod.rs` (mod) — re-exports. `error.rs` (mod) — `Error::Placement`.

Tests: **AC-5** (`fits` / both projections, mixed blocking/non-blocking
template), **AC-8** (serde round-trip with + without the new fields; existing
fixtures still deserialize).

### Chunk 3 — Geometry primitives (correctness-critical)

`engine/geometry/{mod,connectivity,pathfind}.rs` (new). Depends only on
`TileMask` / `TileCoord`. **Heaviest test rigor — a bug here compounds into B-E.**

- `connectivity.rs` — `connected_components` (4-connected flood-fill, flat-index
  order); `would_seal_a_gap` (D5 label-mapping: flood-fill-label `passable` and
  `blocked_after`, flag any `passable`-label spanning >1 `blocked_after`-label;
  plus the elimination clause).
- `pathfind.rs` — `Path`, `search_path` (Dijkstra; frontier min-heap keyed
  `(cost, flat_index)`; predecessor set on first settle, never overwritten on an
  equal-cost tie; neighbours relaxed in flat-index order; nearest goal =
  lowest-flat-index among minimal-cost).

Tests: **AC-2** (hand fixtures incl. multi-component split-and-eliminate +
differential all-pairs-reachability property test), **AC-3**, **AC-4** (tie-break
fixtures: ≥2 equidistant goals, ≥2 equal-length paths).

### Chunk 4 — Build state

`engine/build_state.rs` (new) — `TilemapBuildState`, `ZoneBuildState`,
`from_zones` (D2/§6.4 init rule), `tile_state_at` / `set_tile_state`,
`zone_area_open`, `zone_passable`. Depends on chunk 2 types.

Tests: **AC-1** (every tile exactly one state; `Walkable`⟺`free_paths`;
`Forbidden`→`Obstacle`; `Sea` non-free→`Open`; full-grid coverage).

### Chunk 5 — ModificatorContext reshape + engine rewire

The ripple chunk. After it, `place_tilemap` runs on `TilemapBuildState` and
produces **byte-identical** output — golden test (chunk 1) is the proof.

- `engine/pipeline/modificator.rs` (mod) — `ModificatorContext` →
  `{ template, grid, seed, state: &mut TilemapBuildState }`.
- `engine/modificators/terrain_painter.rs` (mod) — read/write via `ctx.state`;
  update its unit tests to the new context.
- `engine/pipeline/registry.rs` + `modificator.rs` test fixtures (mod) — rebuild
  on the new context.
- `engine/mod.rs` (mod) — `place_tilemap` builds a `TilemapBuildState`, runs the
  pipeline, assembles `ZoneRuntime` from it; `object_placements` still empty.

Tests: existing terrain_painter / registry / placement tests stay green; **AC-9**
golden byte-identical.

### Chunk 6 — ObjectManager service + final VERIFY

`engine/object_manager.rs` (new) — `OptimizeType`, `PlacementResult`,
`PlacementError`, `MonsterTemplate`, `place_and_connect_object` (§6.3 algorithm:
candidates → reject 2a/2b/2c → score with first-placement `Center` fallback →
commit → pinned `access_path`), `choose_guard` (total 10-`TerrainKind` table,
infallible), map-wide `nearest_object_distance` update. Depends on chunks 2-4.
A standalone service — not registered in the pipeline (D3), so output unchanged.

Tests: **AC-6** (placement, reject paths, `access_path` no-overlap + shortest,
first-placement not-corner), **AC-7** (all 10 terrains).
Final VERIFY: `cargo test --workspace` + `cargo clippy --workspace` (**AC-10**).

## Chunk → AC coverage

| Chunk | ACs |
|---|---|
| 1 | AC-9 (scaffold) |
| 2 | AC-5, AC-8 |
| 3 | AC-2, AC-3, AC-4 |
| 4 | AC-1 |
| 5 | AC-9 (live), regression-green |
| 6 | AC-6, AC-7, AC-10 |

## VERIFY gate (Phase 6)

`cargo test --workspace` green + `cargo clippy --workspace` clean + the golden
snapshot byte-identical. Connectivity + pathfinding property tests included. Any
red → hard stop (roadmap §8).

## Notes / risks

- Chunk 1 ordering is load-bearing — capture the golden from the *unmodified*
  engine; if any chunk-2+ change lands first, the baseline is contaminated.
- Chunk 3 is the correctness core; budget the most test effort there.
- Chunk 5 touches existing tests — expect churn in `terrain_painter.rs` /
  `registry.rs` / `modificator.rs` test code; behaviour must not change.
- `would_seal_a_gap` per-zone scope (spec D5) → DEFERRED item logged at SESSION,
  re-validated in Phase D.
