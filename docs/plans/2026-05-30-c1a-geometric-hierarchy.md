# C-1a — Geometric Region Hierarchy (model only) — BUILD plan

> **Task size: L** (reclassified up from M at BUILD-orient: content_hash re-base +
> serde format change + new public types + CreativeSeed knob + ripple to
> hash-pinned tests). Session 99. Parent rationale +
> design: [`FLAT_TO_3D_MIGRATION_PLAN.md §7`](../03_planning/LLM_MMO_RPG/FLAT_TO_3D_MIGRATION_PLAN.md).
> Arc: C3 (geometric frame first, then political tiers). This is C-1a (model);
> C-1b (`--region-png`) and C-2 (political tiers) are later.

## Goal

Add a 3-level geometric region hierarchy to `world_gen::generate` on the sphere,
as a pure model layer (no render). Continents → subcontinents → regions, mostly
by reusing existing primitives.

## The hierarchy

```
L0 Continent     = pathfind::land_components(is_land, neighbors)     REUSE
                   (ocean basins are already feature::water_bodies; C-1a does
                    NOT add an ocean-side tree — land hierarchy only, keep scope)
L1 Subcontinent  = each Continent split by plates.plate_of           REUSE plate layer
                   (cells of a continent grouped by their plate id → one
                    subcontinent per (continent, plate) pair present)
L2 Region        = great-circle Voronoi inside each subcontinent      NEW (light)
                   (K seeds via farthest-point or RNG cells in the subcontinent;
                    assign each subcontinent cell to nearest seed by max dot
                    product — the plates.rs:99-114 pattern, NO 2D grid [R6])
```

## Data model (new)

`world_map.rs`:
- `Continent { id: u32, seed_cell: u32, #[serde(default)] name: String }`
- `Subcontinent { id: u32, continent: u32, plate: u32, seed_cell: u32, name }`
- `Region { id: u32, subcontinent: u32, seed_cell: u32, name }`
- `WorldMap` new fields:
  - `continent_of: Vec<u32>` (per cell; `u32::MAX` for ocean/non-land)
  - `subcontinent_of: Vec<u32>` (per cell; `u32::MAX` for ocean)
  - `region_of: Vec<u32>` (per cell; `u32::MAX` for ocean)
  - `continents: Vec<Continent>`, `subcontinents: Vec<Subcontinent>`,
    `regions: Vec<Region>`
- `name` fields excluded from `content_hash` (same carve-out as Province/State).

`creative_seed.rs`:
- new knob `region_subdivision: u8` (L2 seeds per subcontinent), `#[serde(default
  = "default_region_subdivision")]`, clamped (e.g. `1..=12`). Default scale-aware
  is overkill for v1 — a fixed sensible default (e.g. 4) + clamp.

## Determinism

- L0/L1: index-ordered (land_components is ascending-start DFS; plate grouping by
  ascending cell index). Stable.
- L2: seeded RNG stream `b"regions"` (sub_seed pattern). Seeds chosen
  deterministically (farthest-point sampling from the subcontinent's lowest cell
  index, or first-K by index — pick farthest-point for spread). Ties in
  nearest-seed → lowest seed index (strict `>` keeps first max), mirroring
  plates.rs.
- IDs assigned in deterministic traversal order (continent by component order;
  subcontinent by (continent, ascending plate id); region by (subcontinent,
  seed order)).

## compute_hash

Append after the existing plate-boundary loop (world_map.rs ~:479), in fixed
field order: `continent_of`, `subcontinent_of`, `region_of` (each: len u32 then
the u32s), then `continents`/`subcontinents`/`regions` (each: len then per-entity
id + parent ids + seed_cell — NOT name). Re-base the hash; pin the new value.

## lib.rs wiring

After `feature::extract` and before building `Cell`s (need `is_land` from biome
+ `plate_of` + `neighbors`). Compute `is_land` the same way the pipeline already
does (biome != Ocean, or elevation > sea_level — match existing convention; check
`hydrology.is_in_ocean` / biome). Call `hierarchy::build(...)`, populate the new
WorldMap fields.

## Tests (TDD — write first)

Partition invariants (the load-bearing VERIFY, since no render):
1. **No orphan land cell**: every land cell has `continent_of != MAX`,
   `subcontinent_of != MAX`, `region_of != MAX`.
2. **Ocean cells unassigned**: every ocean cell has all three == MAX.
3. **Containment**: for every cell, `regions[region_of].subcontinent ==
   subcontinent_of` and `subcontinents[subcontinent_of].continent ==
   continent_of`.
4. **Non-empty levels**: a default world has ≥1 continent, and every continent
   has ≥1 subcontinent, every subcontinent ≥1 region.
5. **Subcontinent ⊆ one plate**: all cells of a subcontinent share one plate id
   == `subcontinents[id].plate`.
6. **Determinism**: two generates → identical hierarchy + identical content_hash.
7. **Hash carve-out**: naming the hierarchy entities does not change
   content_hash (extend the existing name-carve-out test if present).
8. **Region count bound**: regions per subcontinent ≤ `region_subdivision`
   (can be fewer if the subcontinent has fewer cells than seeds).

## Files touched (≈6)

`hierarchy.rs` (new), `world_map.rs` (structs + 6 fields + compute_hash),
`creative_seed.rs` (knob), `lib.rs` (module decl + wiring + re-pin determinism
test), `pathfind.rs` (none — `land_components` already pub), integration test
file (`tests/` serde round-trip extends to new fields).

## Out of scope (defer)

- `--region-png` render (C-1b).
- Ocean-basin hierarchy (land only for C-1a).
- Re-anchoring province/state under region (C-2).
- Size-threshold splitting of single-plate continents (tuning pass).

## VERIFY evidence target

`cargo test -p world-gen` green (all partition-invariant tests + determinism +
re-pinned hash); `cargo clippy --all-targets` clean. Single-service crate change
→ no cross-service live-smoke needed (`live infra unavailable: world-gen is a
standalone crate, no service stack`).
