# Plan — Tilemap Phase 1: zone-placement engine + modificator pipeline

> **Spec:** [docs/specs/2026-05-16-tilemap-phase-1-placement-engine.md](../specs/2026-05-16-tilemap-phase-1-placement-engine.md)
> **Size:** XL, default v2.2. Branch `mmo-rpg/zone-map-amaw`.
> **BUILD is chunked** — each chunk compiles + tests green before the next; the
> chunk boundary is a safe session-resumption point.

## Build order (7 chunks)

### Chunk 0 — foundations
- `Cargo.toml` (workspace + tilemap-service): add `rand`, `rand_chacha`.
- `seed.rs`: add `sub_seed(seed: TilemapSeed, label: &str) -> u64` (blake3-derived).
- `types/tile_mask.rs`: `TileMask` bitset (set/get/clear, count_ones, iter_set in
  flat-index order, union/intersect/subtract, is_empty) + serde + unit tests.
- `types/tilemap.rs`: `ZoneRuntime` — swap `assigned_tiles` to `TileMask`, add
  `free_paths: TileMask`, add `iteration_count`/`converged` carriers as needed.
- `error.rs`: add placement/pipeline `TilemapError` variants.
- Gate: `cargo build` + `cargo test` green.

### Chunk 1 — grid seed (TMP_002 §3.1)
- `engine/placement/grid_seed.rs`: BFS distance graph (exclude Adversarial/Portal);
  `N = ceil(sqrt(num_zones))` grid; deterministic per-zone cell assignment minimizing
  neighbour distance, Adversarial repulsion; normalized `[0,1]` centers.
- Tests: known small graph → expected grid; determinism (same seed → same).

### Chunk 2 — Fruchterman-Reingold convergence (TMP_002 §3.2-§3.3)
- `engine/placement/force_directed.rs`: FR attractive/repulsive forces, boundary
  repulsion, Adversarial repulsion; exponential annealing; fitness eval;
  misplaced-zone swap heuristic with `lastSwappedZones` tabu; caps (D5).
- Tests: connected zones converge closer; Adversarial pushes apart; cap → fallback.

### Chunk 3 — Penrose tiling + assignment (TMP_002 §4)
- `engine/placement/penrose.rs`: P3 sun/star subdivision (golden-ratio rhombi) to
  target vertex count; normalize + deterministic rotation; vertex→nearest-zone;
  tile→nearest-vertex → `assigned_tiles`; centroid recompute of `center_position`.
- Tests: subdivision vertex-count growth; disjoint partition (AC-2); centroid in mask.

### Chunk 4 — fractalize (TMP_002 §5, Phase-1 cut per spec D8)
- `engine/placement/fractalize.rs`: per-zone free-path skeleton, base constants (no
  treasure scaling); Hub skip / Forbidden block / Sea sparse; connected-components
  fixup via Dijkstra over Open tiles.
- `engine/placement/mod.rs`: `place_zones()` orchestrator wiring §3→§4→§5.
- Tests: free_paths connected; Hub/Forbidden/Sea special cases; determinism.

### Chunk 5 — modificator pipeline (TMP_003 §2 + §4.1)
- `engine/pipeline/modificator.rs`: `Modificator` trait + `ModificatorContext`.
- `engine/pipeline/registry.rs`: `ModificatorRegistry` — add/dependency/postfunction,
  Kahn topological sort (cycle → error; unregistered dep → satisfied), single-threaded
  `execute` in deterministic order (D6).
- Tests: topo order; cycle rejected; unregistered dep tolerated.

### Chunk 6 — TerrainPainter + top-level entry + determinism test
- `engine/modificators/terrain_painter.rs`: TMP_003 §3.1 Phase-1 cut (D7).
- `engine/mod.rs`: `place_tilemap(template, seed, grid_size) -> Result<TilemapView>`
  — seed → place_zones → registry(TerrainPainter) → execute → assemble `TilemapView`.
- `tests/determinism.rs`: AC-4 — `place_tilemap` ×2 same input → byte-identical serde;
  different seed → different. AC-1/AC-2/AC-3/AC-6 integration coverage.
- Gate: `cargo test --workspace` + `cargo clippy --workspace` green.

## VERIFY gate

`cargo test --workspace` (incl. the non-`#[ignore]` determinism test) + `cargo clippy
--workspace` green; AC-1..AC-7 each have covering tests; the determinism test passes
on repeated runs.

## Multi-session note

XL — BUILD spans sessions. Each chunk boundary (0–6) is a clean resume point: the code
compiles + its tests pass. SESSION_HANDOFF records the last completed chunk.

## Batch execution — 2026-05-16, fully autonomous (operator override)

Chunks 0–2 landed across two sessions (human-gated at each chunk). The operator
elected to run the **remainder as a single fully-autonomous AMAW batch** — chunks
3→4→5→6, then VERIFY → REVIEW → QC → POST-REVIEW → SESSION → COMMIT → RETRO, with
**no human checkpoint**. This is the operator override the SESSION_HANDOFF "execution
shape" note explicitly reserves to the operator; the handoff's documented caution
(map-gen is correctness-critical; the autonomous loop has mis-cleared a real bug
before) is acknowledged and overridden by choice.

Batch contract:

1. **BUILD chunks 3–6** — built in order; each chunk MUST `cargo test -p
   tilemap-service` + `cargo clippy` green before the next. A red gate halts the
   batch (no skipping forward on failure).
2. **VERIFY** — `cargo test --workspace` + `cargo clippy --workspace` green; AC-1..AC-7
   each have a covering test; the determinism test passes on repeated runs.
3. **REVIEW (code)** — AMAW Adversary cold-start sub-agent over chunks 0–6. Findings
   → fix → re-VERIFY → re-review until APPROVED.
4. **QC + POST-REVIEW** — AMAW Scope Guard sub-agent runs the conservative final gate
   (CLEAR / BLOCKED). BLOCKED halts the batch for the operator.
5. **SESSION + COMMIT + RETRO** — update SESSION_HANDOFF + DEFERRED; commit Phase 1
   (all 7 chunks + spec + plan land in one commit); `add_lesson` to ContextHub.

Halt conditions (batch stops + reports, does not push past): a chunk gate goes red
and the cause is not a 1-line fix; the Adversary REVIEW finds a HIGH it cannot
self-resolve; Scope Guard returns BLOCKED; the Debugging-Protocol 3-attempt hard stop
trips. Otherwise the batch runs to COMMIT unattended.
