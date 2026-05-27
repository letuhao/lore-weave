# Plan — tilemap-service Phase D: ConnectionsPlacer

> **Spec:** [`docs/specs/2026-05-17-tilemap-phase-d-connections-placer.md`](../specs/2026-05-17-tilemap-phase-d-connections-placer.md) (D1–D12, AC-1..AC-13).
> **Mode:** default v2.2 human-in-loop · **Size:** XL · design self-reviewed (REVIEW-design — 5 refinements applied).
> Build is **TDD** — each chunk writes the failing test(s) first, then the code.

## Build chunks

**Chunk 1 — additive schema (D12).**
- `types/object.rs` — `TilemapObjectKind::Ferry` (closed-enum extension — the Phase-B `Obstacle` precedent; serialises `"ferry"`).
- `engine/build_state.rs` — `TilemapBuildState.road_nodes: Vec<TileCoord>` (`from_zones` inits `Vec::new()`).
- Tests: AC-12 — `Ferry` placement round-trips; a pre-Phase-D placement JSON still deserializes.
- Gate: `cargo test --workspace` green (schema only — no pipeline change yet, golden still reproduces).

**Chunk 2 — pure helpers (D5, D7).**
- `engine/modificators/connections_placer.rs` NEW — `terrain_prohibits_transition` (D7 — the V1+30d Subterranean table); `neighbour_border_map` (D5 — per zone, the border tiles touching each neighbour zone); `monolith_tile` (D4 — the interior uncrowded tile); `score_passage_point` (D5 — the pinned formula + the safety check).
- Tests: deterministic-helper units — the prohibition table, the neighbour map on a hand-built 2-zone grid, the passage score, the monolith-tile pick.

**Chunk 3 — `ConnectionsPlacer` + Pass 1 + monolith fallback (D1, D2, D4, D6b).**
- `connections_placer.rs` — `ConnectionsPlacer` `Modificator` (`name()="connections_placer"`, `dependencies()=["terrain_painter"]`); the 3-pass `process` skeleton + the canonicalised-zone-pair dedup `HashSet`; Pass 1 (`Portal` → `place_monolith_pair`); the monotonic monolith `pair_id` counter.
- Tests: AC-1 (a `Portal` connection → one `Monolith` per zone, shared `pair_id`, both endpoints completed).

**Chunk 4 — Pass 2 direct passages (D5, D10).**
- `connections_placer.rs` — Pass 2: the neighbour-border map, passage-point scoring + the 3-way / crowding / safety rejections, the connection guard (D10 — `MonsterLair` 4-adjacent to `P`), `search_path` `our_path`/`their_path`, `attach_walkable_path` (`Open → Walkable`), `road_nodes` recording.
- Tests: AC-2 (`Open` passage between bordering zones, no guard, `free_paths` joined), AC-3 (`Threshold` guarded passage), AC-4 (no 3-way junction), AC-5 (`Hint`/`Adversarial` place nothing).

**Chunk 5 — Pass 3 water routes + §6 + §9 + §3.1 (D6, D7, D8, D9).**
- `connections_placer.rs` — Pass 3: the water route (D8 — shore detection, water-tile `search_path`, `Ferry` objects) and the monolith fallback (D6b); the §6 terrain-prohibit → Pass-3 path; §3.1 border separation; §9 coast sealing.
- Tests: AC-6 (terrain-prohibited pair → realized by Pass 3), AC-7 (a Sea zone between → ferry; no Sea → monolith pair).

**Chunk 6 — register + golden rebaseline + connectivity + VERIFY (D1, D11, AC-8/9/10/11/13).**
- `engine/modificators/mod.rs` — re-export `ConnectionsPlacer`.
- `engine/mod.rs` — register `ConnectionsPlacer` (first placer; the Kahn topo-sort orders it before `TreasurePlacer`/`ObstaclePlacer` via their existing `connections_placer` dependency edges).
- Run `regenerate_golden_baseline` → rewrite `tests/golden/tilemap_baseline.json` from the Phase-D engine.
- `tests/determinism.rs` / a build-state harness — AC-8 (every author connection realized), AC-10 (connectivity — hand-built multi-zone fixture, independent flood-fill — the Phase-B/C `flood`/`components` oracle, now incl. the cross-zone corridors joining zones), AC-11 (`ac4_same_seed` + `golden_baseline_byte_identical`).
- Gate: AC-13 — `cargo test --workspace` green, `cargo clippy --workspace --all-targets` clean.

## Chunk → AC map

| Chunk | ACs |
|---|---|
| 1 schema | AC-12 |
| 2 helpers | (pure-unit — feeds AC-4 / AC-6) |
| 3 Pass 1 | AC-1 |
| 4 Pass 2 | AC-2, AC-3, AC-4, AC-5 |
| 5 Pass 3 | AC-6, AC-7 |
| 6 register + golden | AC-8, AC-9, AC-10, AC-11, AC-13 |

## VERIFY gate

`cargo test --workspace` green + `cargo clippy --workspace --all-targets` clean; the golden rebaselined and `golden_baseline_byte_identical` reproducing it; `object_placements` carries `Monolith` + `MonsterLair` (connection guards) + `Ferry` records; every author connection realized (AC-8); no zone's passable region split (AC-10). Then REVIEW(code) — v2.2 Lead self-review (2-stage: spec compliance + code quality).
