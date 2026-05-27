# Plan — River barrier reorder (split ObstaclePlacer)

> **Spec:** [`docs/specs/2026-05-22-tilemap-river-barrier-reorder.md`](../specs/2026-05-22-tilemap-river-barrier-reorder.md)
> **Workflow:** default v2.2; `/review-impl` mandatory at POST-REVIEW.

---

## Chunk 1 — `fill_region` generalization + erode-skips-Water

`obstacle_placer.rs`:
1. Replace `fill_zone(state, zone_idx, selection, library)` with
   `fill_region(state, zone_idx, selection, library, target: &TileMask,
   place_type: impl Fn(BiomeObjectType) -> bool, skip_water: bool) -> Vec<usize>`:
   - gather items only for `object_type`s where `place_type(t)`.
   - largest-first (unchanged sort).
   - anchor search over `target.iter_set()`, `footprint_fits` AND (if
     `skip_water`) every footprint cell not Water-terrain.
2. `erode_zone`: skip a candidate tile whose terrain is `Water` (a river ford).
3. Keep existing erode/simple-point tests green; adapt `fill_*` test call sites
   to `fill_region(..., zone_obstacle, |_| true, false)` (the old behaviour).

**Done:** module compiles; existing obstacle tests green via the new signature.

## Chunk 2 — split into `ObstacleSourcePlacer` + `ObstacleFillPlacer`

`obstacle_placer.rs`:
1. `ObstacleSourcePlacer` (name `"obstacle_source_placer"`): per non-Forbidden
   zone — `select_biomes` (same label) → `fill_region(zone_area_open,
   |t| matches!(t, Mountain|Lake), skip_water=false)`. No erosion.
2. Rename `ObstaclePlacer` → `ObstacleFillPlacer` (name `"obstacle_fill_placer"`):
   per non-Forbidden zone — `erode_zone` → `select_biomes` → `fill_region(
   zone_obstacle, |t| !matches!(t, Mountain|Lake), skip_water=true)`.
3. `modificators/mod.rs`: export both.

**Done:** both modificators compile + unit-test their own behaviour (AC-1, AC-3).

## Chunk 3 — RiverPlacer dep retarget + pipeline reorder

1. `river_placer.rs`: `dependencies()` `obstacle_placer`→`obstacle_source_placer`.
2. `engine/mod.rs`: register `ObstacleSourcePlacer` + `ObstacleFillPlacer`
   (drop `ObstaclePlacer`); the topo-sort orders them via deps. Update the 4
   test registrations (lines ~290/374/507) + the `"obstacle_placer"` literal
   (~590) + doc comments.

**Done:** crate compiles; pipeline runs source→river→fill.

## Chunk 4 — rebaseline golden + AC-5 determinism

1. `cargo test regenerate_golden_baseline -- --ignored` → new
   `tests/golden/tilemap_baseline.json`.
2. `golden_baseline_byte_identical` + `ac4_same_seed...` green against the new
   baseline.

## Chunk 5 — new tests AC-2 / AC-4

- **AC-2** (`river_placer.rs` or `obstacle_placer.rs`): a wide single-zone
  fixture run through the real pipeline (source→river→fill) — assert river
  ford-ratio < 0.4.
- **AC-4**: a forded (passable-Water) tile survives the fill placer's erosion.

## Chunk 6 — VERIFY + AC-6 measure

`cargo test --workspace` + `clippy`; `cargo run --release -- measure`; record
continent river ford ratio before (≈0.77) / after; append to measurements doc.

## Chunk 7 — REVIEW(code) + QC + POST-REVIEW(/review-impl) + SESSION + COMMIT + RETRO

`/review-impl` mandatory. SESSION: ford-ratio before/after, golden rebaselined,
#026 cleared. COMMIT explicit-stage.

---

## Risk register
| Risk | Mitigation |
|---|---|
| Golden churn masks a regression | AC-1..AC-5 pin intended changes; connectivity tests guard the invariant; /review-impl |
| Two-pass select_biomes diverges | verified pure (DESIGN); identical label string both passes |
| Erosion eats a ford | erode-skips-Water guard + AC-4 |
| Fill drops obstacle on river | fill skip_water + AC-3 |
| Forbidden-zone handling differs across passes | both passes keep the `if Forbidden continue` guard |
