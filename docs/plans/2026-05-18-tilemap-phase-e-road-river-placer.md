# Phase E — RoadPlacer + RiverPlacer — Build Plan

> **Spec:** [`docs/specs/2026-05-18-tilemap-phase-e-road-river-placer.md`](../specs/2026-05-18-tilemap-phase-e-road-river-placer.md)
> **Size:** XL · **Workflow:** default v2.2 human-in-loop
> 6 TDD build chunks — failing test first, then implementation, `cargo test` green before the next chunk.

---

## Chunk 1 — Schema (additive, TMP-A8)

**Files:** `src/types/tilemap.rs`, `src/engine/build_state.rs`, `src/engine/mod.rs`

- `tilemap.rs`: add `RoadSegment { waypoints }`, `CrossingKind { Bridge, Ford }`
  (`#[serde rename_all snake_case]`), `RiverCrossing { at, kind }`,
  `RiverSegment { tiles, crossings }`. Add `#[serde(default)]
  road_segments: Vec<RoadSegment>` + `river_segments: Vec<RiverSegment>` to
  `TilemapView`; init both in `TilemapView::empty`.
- `build_state.rs`: add `road_segments` + `river_segments` to
  `TilemapBuildState`, init empty in `from_zones`.
- `engine/mod.rs`: `place_tilemap` moves `state.road_segments` /
  `state.river_segments` into the returned view (the literal gains 2 fields).

**Tests (`tilemap.rs`):** `RoadSegment`/`RiverSegment` serde round-trip;
`CrossingKind` serialises `"bridge"`/`"ford"`; **AC-12** — a pre-Phase-E
`TilemapView` JSON without `road_segments`/`river_segments` deserializes (fields
default empty) and a view with empty segments omits nothing that breaks the
golden. Gate: `cargo test` green.

## Chunk 2 — Prim MST primitive

**Files:** `src/engine/geometry/mst.rs` (NEW), `src/engine/geometry/mod.rs`

- `minimum_spanning_tree(coords: &[TileCoord]) -> Vec<(usize, usize)>` — Prim's
  algorithm, edge weight = Manhattan distance, start = index 0 (caller passes a
  flat-index-sorted list), ties broken by candidate node index. `< 2` coords ⇒
  empty edge list.
- `mod.rs`: `pub mod mst; pub use mst::minimum_spanning_tree`.

**Tests:** n−1 edges for n≥1 nodes; the edge set spans every node (union-find
reachability); determinism (same input ⇒ same edges); a known 4-point square →
the expected 3 edges; property test over random coord sets (tree weight ≤ the
naive sequential-chain weight). Gate: `cargo test` green.

## Chunk 3 — RoadPlacer

**Files:** `src/engine/modificators/road_placer.rs` (NEW),
`src/engine/modificators/mod.rs`

- `RoadPlacer` — `name = "road_placer"`,
  `dependencies = ["terrain_painter", "connections_placer", "treasure_placer"]`.
- Pure helpers: `collect_anchors` (zone centres of non-Forbidden zones ∪
  `road_nodes` ∪ `MonsterLair` anchors, deduped); `routing_proxy` (anchor if
  passable, else lowest-flat-index passable 4-neighbour, else `None`);
  `road_search_area` (map-wide `Walkable ∪ Open` minus `Sea`-zone tiles);
  `road_cost` (`Road` terrain 0.5 / `Walkable` 1.0 / `Open` 2.0 by dest tile).
- `process`: collect → proxy → drop unproxyable → sort by flat index → Prim MST
  → per edge `search_path`; `Some(path)` ⇒ push `RoadSegment`, paint each
  waypoint `terrain_layer = Road`; `None` ⇒ skip (AC-5).
- Register the module + re-export in `modificators/mod.rs`.

**Tests:** anchor collection incl. all three sources + dedup; proxy falls back
to a neighbour for an `Occupied` anchor and drops a fully-blocked one; a
hand-built 2-anchor fixture produces a `RoadSegment` whose waypoints are painted
`Road` and stay passable (AC-4); a sea-separated anchor pair produces no segment
and no panic (AC-5); an empty-connection template places no road (AC-13). Gate:
`cargo test` green.

## Chunk 4 — RiverPlacer

**Files:** `src/engine/modificators/river_placer.rs` (NEW),
`src/engine/modificators/mod.rs`

- `RiverPlacer` — `name = "river_placer"`,
  `dependencies = ["obstacle_placer", "road_placer"]`.
- Pure helpers: `river_sources` (one lowest-flat-index `Mountain` obstacle per
  mountain-bearing zone, zones in flat-index order); `river_sink_mask`
  (`Lake`-tagged obstacle anchors ∪ `Sea`-zone tiles); `river_search_area`
  (non-`Obstacle` tiles ∪ source ∪ sinks); `elevation_cost` (terrain proxy
  Mountain 10 / Snow·Rough 4 / Water 0.5 / rest 2).
- `process`: per source `search_path` to the sink mask; discard if `None` or
  `path.len() > grid.width + grid.height`; else walk the path — the §5.4 D-Q8
  bridge/ford/carve classifier (dual `would_seal_a_gap`: owning-zone passable
  **and** map-wide passable); push `RiverSegment`.
- Register the module + re-export.

**Tests:** source = lowest-flat-index mountain per zone, sink mask spans Lake +
Sea; a hand-built fixture carves a river of `Obstacle`+`Water` tiles (AC-7); a
river crossing a pre-painted `Road` tile records a `Bridge` and leaves it
passable (AC-9); a 1-tile-wide land bridge forces a `Ford` (the carve would seal
a gap) — assert the tile stays passable and a `Ford` crossing is recorded; the
`FORD_INTERVAL`-th tile of a long straight river is a `Ford`; a no-mountain
template places no river (AC-13). Gate: `cargo test` green.

## Chunk 5 — Pipeline integration

**Files:** `src/engine/mod.rs`

- `place_tilemap`: `registry.add(Box::new(RoadPlacer))` +
  `registry.add(Box::new(RiverPlacer))`; confirm the topo-sort yields
  `terrain → connections → treasure → road → obstacle → river`.
- Extend the `engine/mod.rs` test module: register all six modificators; assert
  the run order (AC-1, AC-2); **AC-8** — extend the `ac10`-style independent
  flood-fill end-to-end test through `RiverPlacer`, asserting **both** that no
  non-Forbidden zone's passable region is split **and** that the map-wide
  passable region is not split; AC-10 determinism over several seeds.

**Tests:** topo order; AC-8 dual connectivity; same-seed byte-identity at the
`TilemapBuildState` level. Gate: `cargo test` green.

## Chunk 6 — Golden rebaseline + VERIFY

**Files:** `tests/determinism.rs`, `tests/golden/tilemap_baseline.json`

- `determinism.rs`: give a fixture zone `vec![TerrainKind::Mountain]` so
  ObstaclePlacer produces mountain obstacles and the golden geometry can carry a
  river; add AC assertions (`road_segments` non-empty given the fixture's
  connections; a river present iff the `GOLDEN_SEED` geometry routes one — a
  conditional no-op detector, not a hard requirement).
- Rebaseline: `cargo test regenerate_golden_baseline -- --ignored`.
- `golden_baseline_byte_identical` green; `cargo test --workspace` green;
  `cargo clippy --workspace --all-targets` 0 warnings.

**VERIFY gate:** full `cargo test --workspace` + `cargo clippy` evidence, golden
reproduces.

---

## Chunk → AC map

| Chunk | ACs |
|---|---|
| 1 Schema | AC-12 |
| 2 MST | (D-Q2 primitive) |
| 3 RoadPlacer | AC-3, AC-4, AC-5, AC-13(roads) |
| 4 RiverPlacer | AC-6, AC-7, AC-9, AC-13(rivers) |
| 5 Integration | AC-1, AC-2, AC-8, AC-10 |
| 6 Golden | AC-11 |
