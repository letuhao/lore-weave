# Plan — tilemap-service Phase C: TreasurePlacer

> **Spec:** [`docs/specs/2026-05-17-tilemap-phase-c-treasure-placer.md`](../specs/2026-05-17-tilemap-phase-c-treasure-placer.md) (D1–D10, AC-1..AC-12).
> **Mode:** AMAW (`/amaw`) · **Size:** XL · design review 6 rounds → APPROVED_WITH_WARNINGS.
> Build is **TDD** — each chunk writes the failing test(s) first, then the code.

## Build chunks

**Chunk 1 — additive schema (D9, D10).**
- `types/object.rs` — `TilemapObjectPlacement.value: Option<u32>` (`#[serde(default, skip_serializing_if = "Option::is_none")]`).
- `types/template.rs` — `ZoneSpec.inherit_treasure_from: Option<ZoneId>` (`#[serde(default)]`).
- `engine/object_manager.rs` — `place_and_connect_object` gains a `value: Option<u32>` parameter (next to `kind`), threaded into the `TilemapObjectPlacement` it pushes; update every Phase-A test call with `None`.
- `engine/modificators/obstacle_placer.rs` — `fill_zone`'s `TilemapObjectPlacement` literal gets `value: None`.
- Tests: AC-11 — `ZoneSpec` with/without `inherit_treasure_from`, `TilemapObjectPlacement` with/without `value`, pre-Phase-C JSON still deserializes.
- Gate: `cargo test --workspace` green (schema only — no behaviour change yet, golden still reproduces).

**Chunk 2 — treasure-object pool (D1).**
- `engine/treasure_pool.rs` NEW — `TreasureObject { id, value, rarity }`; `engine_treasure_pool()` — fixed V1+30d set, wide value spread.
- Tests: AC-1 — non-empty, deterministic, `value > 0` / `rarity > 0`, real spread.

**Chunk 3 — pile composition + scaling (D2, D3).**
- `engine/treasure_select.rs` NEW — `TreasurePile { value, object_count }`; `sample_weighted_by_rarity` (fixed-order, one `gen_range` over the value-eligible subset); `compose_pile` (filler-tier `None`, `object_count ≥ 1` loop, `MAX_COMPOSE_ATTEMPTS`); `min_distance(value)`.
- Tests: AC-2 (reachable / unreachable / filler tier; sampler value-cap), AC-3 (`min_distance` monotonic, `≥ 5.0`).

**Chunk 4 — `TreasurePlacer` modificator (D4, D5, D6, D8, D9).**
- `engine/modificators/treasure_placer.rs` NEW — `TreasurePlacer`; effective-tier resolution (D9 — `inherit_treasure_from`, one-level, dangling → empty); per-tier high-`max`-first compose/place/guard loop (D4/D6 — `emergency` bound on pile failures only); guard placement (D5 — `choose_guard`, grid-dimensioned `guard_search_area`, `NoSpace` → skip); `treasure_pile_template()` / `guard_template()` (1×1 blocking).
- `engine/modificators/mod.rs` — re-export `TreasurePlacer`.
- `engine/mod.rs` — register `TreasurePlacer` (TerrainPainter → TreasurePlacer → ObstaclePlacer, D8).
- Tests: AC-4 (guard policy), AC-5 (a–e — exact `target_count`, high-`max`-first, truncation boundary, `value` recorded, failure-path gate), AC-6 (guards on guard-placeable geometry), AC-10 (inherit — disjoint-own / 3-zone-chain / cycle / dangling).

**Chunk 5 — golden rebaseline + connectivity + VERIFY (D7, AC-7/8/9/12).**
- Run `regenerate_golden_baseline` (the `#[ignore]`d tool) → rewrite `tests/golden/tilemap_baseline.json` from the Phase-C engine.
- `tests/determinism.rs` / a build-state harness — AC-7 (hand-built non-empty-tier connectivity, independent flood-fill), AC-8 (`ac4_same_seed`), AC-9 (`golden_baseline_byte_identical`).
- Gate: AC-12 — `cargo test --workspace` green, `cargo clippy --workspace --all-targets` clean.

## Chunk → AC map

| Chunk | ACs |
|---|---|
| 1 schema | AC-11 |
| 2 pool | AC-1 |
| 3 compose | AC-2, AC-3 |
| 4 placer | AC-4, AC-5, AC-6, AC-10 |
| 5 golden + connectivity | AC-7, AC-8, AC-9, AC-12 |

## VERIFY gate

`cargo test --workspace` green + `cargo clippy --workspace --all-targets` clean; the golden rebaselined and `golden_baseline_byte_identical` reproducing it; `object_placements` non-empty with `Treasure` + `MonsterLair` records. Then REVIEW (code) — cold-start Adversary.
