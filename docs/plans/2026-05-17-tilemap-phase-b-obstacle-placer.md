# Plan — tilemap-service Phase B: ObstaclePlacer + Biomes

> **Spec:** [`docs/specs/2026-05-17-tilemap-phase-b-obstacle-placer.md`](../specs/2026-05-17-tilemap-phase-b-obstacle-placer.md)
> (D1-D9, AC-1..AC-11 — REVIEW(design) closed r5 APPROVED_WITH_WARNINGS).
> **Size:** XL · **Mode:** AMAW · **Date:** 2026-05-17

## Build chunks

Five chunks, dependency-ordered, each TDD (failing test → implement → `cargo
test` green before the next). `cargo test --workspace` green at every chunk
boundary.

### Chunk 1 — Schema types

- `types/biome.rs` (new) — `BiomeId`, `BiomeObjectType` (9-variant), `BiomeLevel`,
  `Alignment`, `BiomeSet`, `BiomeSelectionRules`, `BiomeSelectionRule`,
  `BiomePriority`, `BiomeSelection`. `BTreeSet` for deterministic iteration.
- `types/object.rs` (mod) — `TilemapObjectKind` += `Obstacle`;
  `TilemapObjectPlacement` += `biome_object_type: Option<BiomeObjectType>`
  (`#[serde(default)]`). (r1 Adversary confirmed no exhaustive `match` on
  `TilemapObjectKind` exists — the variant is safe to add.)
- `types/template.rs` (mod) — `ZoneSpec` += `biome_selection_rules:
  Option<BiomeSelectionRules>` (`#[serde(default)]`).
- `types/mod.rs` (mod) — re-exports.

Tests: **AC-8** (serde round-trip — `TilemapObjectPlacement` with/without
`biome_object_type`, `ZoneSpec` with/without `biome_selection_rules`; existing
fixtures still deserialize).

### Chunk 2 — Engine biome library

- `engine/biome_library.rs` (new) — `engine_biome_library() -> Vec<BiomeSet>`
  (the §6-faithful V1+30d library, 4-6 compact templates per set, 8 surface
  terrains; `Water` has no `Tree` biome — D2/AC-1) +
  `engine_default_biome_selection_rules() -> Vec<BiomeSelectionRule>` (the §2.3
  nine rules verbatim).
- `engine/mod.rs` (mod) — `pub mod biome_library;`.

Tests: **AC-1** (library coverage — land terrains get Mountain/Tree/Rock/Plant,
Water gets Mountain/Rock/Plant; 4-10 templates each; deterministic), **AC-2**
(default rules match §2.3).

### Chunk 3 — Biome selection

- `engine/biome_select.rs` (new) — `select_biomes(zone, terrain, rules, seed)
  -> BiomeSelection`: filter (terrain + level), group by `object_type`, apply
  rules in `First`→`Normal`→`Last` priority; xor handled with one two-coin
  decision per `{type, xor_with}` pair (`P(neither)=0.5`); §9 Q3 fallback when a
  needed type has no biome. Deterministic sub-seed.
- `engine/mod.rs` (mod) — `pub mod biome_select;`.

Tests: **AC-3** (filter, priority order, counts in range, xor never-both +
two-coin distribution, deterministic), **AC-4** (Q3 fallback — no panic).

### Chunk 4 — ObstaclePlacer

- `engine/modificators/obstacle_placer.rs` (new) — `ObstaclePlacer` modificator:
  D3 selection → D5 strip-loose-appendages erosion (sequential `would_seal_a_gap`
  gate on the passable mask; wall = non-`assigned_tiles` neighbour or
  `Obstacle`/`Occupied`) → D6 largest-first fill (footprint ⊆ `Obstacle` region,
  no `would_seal_a_gap` call — dead by construction). Mountain/Lake placements
  tagged `biome_object_type`.
- `engine/modificators/mod.rs` (mod) — re-export `ObstaclePlacer`.
- `engine/mod.rs` (mod) — register `ObstaclePlacer` in `place_tilemap`.

Tests: **AC-5** (erosion — `Open`→`Obstacle` only, terminates, split-OR-eliminate
oracle + all-pairs reachability property test incl. both corridor topologies),
**AC-6** (fill — footprint ⊆ `Obstacle` region, largest-first, `kind: Obstacle`
+ `biome_object_type`), **AC-7** (Mountain→`Some(Mountain)`, Lake→`Some(Lake)`).

### Chunk 5 — Golden rebaseline + VERIFY

- `tests/golden/phase_a_baseline.json` → `git mv` to `tests/golden/tilemap_baseline.json`;
  regenerate content from the Phase-B engine.
- `tests/determinism.rs` (mod) — golden test → `golden_baseline_byte_identical`;
  `regenerate_golden_baseline` kept (the deliberate-rebaseline tool); `ac4_same_seed`
  now also asserts non-empty `object_placements`.

Tests: **AC-9** (determinism via `ac4_same_seed`; `object_placements` non-empty),
**AC-10** (end-to-end connectivity — split-OR-eliminate oracle, no zone's
passable region split), **AC-11** (`cargo test --workspace` + `cargo clippy`).

## Chunk → AC coverage

| Chunk | ACs |
|---|---|
| 1 | AC-8 |
| 2 | AC-1, AC-2 |
| 3 | AC-3, AC-4 |
| 4 | AC-5, AC-6, AC-7 |
| 5 | AC-9, AC-10, AC-11 |

## VERIFY gate

`cargo test --workspace` green + `cargo clippy --workspace` clean. Connectivity
property tests (erosion) included. Any red → hard stop.

## Notes

- Chunk 4's erosion is the one correctness-critical step — heaviest test rigor
  (the split-OR-eliminate oracle, both corridor topologies).
- The golden rebaseline (chunk 5) is a deliberate one-time act — Phase B
  legitimately changes `place_tilemap` output.
- Deferred at SESSION: the river-footprint reference (`TilemapObjectPlacement`
  carries `anchor`, not the footprint extent — a Phase-E decision).
