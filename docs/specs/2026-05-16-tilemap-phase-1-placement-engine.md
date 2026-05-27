# Spec — Tilemap Phase 1: zone-placement engine + modificator pipeline

> **Status:** DESIGN 2026-05-16. Default v2.2 (12-phase human-in-loop). Size **XL**.
> Branch `mmo-rpg/zone-map-amaw`.
> **Source:** [TMP_002](../03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_002_zone_placement.md)
> (zone placement) + [TMP_003](../03_planning/LLM_MMO_RPG/features/00_tilemap/TMP_003_pipeline_modificators.md)
> (modificator pipeline); handoff "Phase 1".
> **Scope decision (CLARIFY, PO):** full TMP_002 placement (§3 FR + §4 Penrose + §5
> fractalize) + the TMP_003 modificator framework + **1 modificator (TerrainPainter)**
> + a determinism integration test. Default v2.2 (user declined `/amaw`).

## 1. Goal

A deterministic procedural zone-placement engine for `tilemap-service`: given a
`TilemapTemplate` (zone graph) + a seed, produce a fully-placed `TilemapView` —
every zone has a `center_position`, an `assigned_tiles` mask, a `free_paths`
skeleton, and a painted `terrain_layer`. **The determinism axiom (TMP-A4) is the
load-bearing guarantee:** same `(template, seed)` → byte-identical output.

## 2. Scope

In: TMP_002 §3 (initial grid seed + Fruchterman-Reingold convergence + misplaced-zone
swap), §4 (Penrose P3 tiling → tile assignment → centroid recompute), §5 (fractalize
per-zone path skeleton); TMP_003 §2 modificator trait + registry + §4.1 topological
execution (**single-threaded** — see D6); the **TerrainPainter** modificator (TMP_003
§3.1); a `TileMask` type; ChaCha8 RNG plumbing; the determinism integration test.

Out (later phases): the other 6 modificators (need TMP_005/006/007); §4.2 *parallel*
execution + per-zone `RwLock` (Phase 1 is single-threaded — parallelism is an
optimization layered on a proven-deterministic base); treasure-density tuning of
fractalize (`ZoneSpec` has no treasure tiers yet); the HTTP server surface; DP
integration; progress-event streaming.

## 3. Design decisions

### D1 — RNG: ChaCha8 seeded from the blake3 `TilemapSeed`

`engine` uses `rand` + `rand_chacha`. The top seed is the existing
[`seed::TilemapSeed`](../../services/tilemap-service/src/seed.rs) (`u64` from
`derive_seed`). Per TMP_002 §8 + TMP-A4: sub-streams derive deterministically —
`sub_seed(label) = blake3(seed_le_bytes || label_bytes) → u64`. Per-zone fractalize
and per-modificator RNG each get a labelled sub-seed (`"fractalize:<zone_id>"`,
`"mod:<name>:<zone_id>"`) so the eventual parallel mode cannot break determinism.
A `seed::sub_seed(seed, label)` helper is added next to `derive_seed`.

### D2 — `TileMask` — a grid-sized bitset

New `types/tile_mask.rs`: `TileMask { width: u32, height: u32, bits: Vec<u64> }`,
indexed by `TileCoord::flat_index`. Ops: `set` / `get` / `clear`, `count_ones`,
`iter_set() -> impl Iterator<Item = TileCoord>`, `union`/`intersect`/`subtract`,
`is_empty`. `serde` derive (a bitset serializes compactly + deterministically). It
replaces the Phase 0a `ZoneRuntime.assigned_tiles: Vec<TileCoord>` placeholder; a new
`free_paths: TileMask` field is added. **Determinism:** `iter_set` walks bit order
(flat-index ascending) — never a `HashSet` — so iteration is reproducible.

### D3 — Module layout

```
src/engine/
  mod.rs                    — place_tilemap() top-level entry; re-exports
  placement/
    mod.rs                  — place_zones() orchestrator (TMP_002 §6)
    grid_seed.rs            — §3.1 distance graph (BFS) + initial grid assignment
    force_directed.rs       — §3.2 FR convergence + §3.3 misplaced-zone swap
    penrose.rs              — §4 P3 subdivision + vertex→zone + tile→vertex
    fractalize.rs           — §5 per-zone free-path skeleton
  pipeline/
    mod.rs                  — re-exports
    modificator.rs          — Modificator trait + ModificatorContext (TMP_003 §2)
    registry.rs             — ModificatorRegistry + Kahn topo-sort + execute (§4.1)
  modificators/
    mod.rs
    terrain_painter.rs      — TerrainPainter (TMP_003 §3.1)
```
Each file targets <300 lines; `force_directed.rs` and `penrose.rs` are the dense
ones. `error.rs` gains placement/pipeline `TilemapError` variants.

### D4 — Geometry uses `f64`; the grid is `u32`

FR convergence + Penrose run in normalized `f64` `[0,1]²` space; the final
`center_position` + tile assignment quantize to `u32` grid coords. Determinism note:
`f64` arithmetic is deterministic for a fixed sequence of IEEE-754 ops on one target;
the engine performs **no parallel float reduction** (Phase 1 single-threaded), so
replays are bit-identical. The determinism test enforces this empirically.

### D5 — FR convergence caps (TMP_002 §9 / TMP-Q5)

1000 iterations OR 5 s wall-clock, whichever first; 50 no-improvement iterations →
converged. Never error.

**Cap-without-convergence — split by which cap trips** (resolved at BUILD chunk 2,
2026-05-16; the original D5 wording was ambiguous between "fall back to the grid-seed
layout" and "the layout taken is the last accepted one"):

- **Iteration cap (1000):** seed-deterministic — every machine trips it at the same
  iteration — so the engine keeps the **FR best-found layout** (`converged: false`).
  The relaxation work is not discarded.
- **Wall-clock cap (5 s):** machine-dependent — a slow machine trips it earlier than
  a fast one — so the engine falls back to the **grid-seed layout** (`converged:
  false`, TMP-PLACE-Q2), a pure function of the template. This is the only choice
  that keeps the output byte-identical across machines (TMP-A4).

The iteration cap is checked before the wall-clock cap so a run that legitimately
reaches it is never mis-attributed to the machine-dependent path. Residual caveat: a
graph that *would* converge but is interrupted by the wall-clock cap on a slow
machine yields the grid-seed layout there while a fast machine yields the FR layout —
unavoidable for any wall-clock cap, and only reachable by pathological non-converging
large graphs (Phase-1 fixtures converge in well under both caps).

### D6 — Pipeline executes single-threaded in Phase 1

`ModificatorRegistry::execute` does Kahn topological sort (TMP_003 §4.1) and runs
modificators **sequentially** in topological order, ties broken by a deterministic
key (zone_id, then modificator name). This is TMP_003's `single_thread` path. The
parallel thread-pool + per-zone `RwLock` (§4.2) is deferred — it is an optimization
on top of a base that must first be provably deterministic. The determinism test
locks the single-threaded order.

### D7 — TerrainPainter only (the "1 modificator")

TerrainPainter (TMP_003 §3.1) is the one modificator with no cross-doc dependency —
it needs only `assigned_tiles` + `ZoneSpec.terrain_types`. Phase-1 cut of its
algorithm: zone terrain = `Sea` → `Water`; else first of `ZoneSpec.terrain_types`
(or seed-random over surface terrains if empty); paint every `assigned_tiles` tile
into `terrain_layer`; the 15 % decoration variant is **out** (cosmetic, no
`TileState` impact). Its declared deps (`TownPlacer`, `WaterAdopter`, …) reference
modificators that do not exist Phase 1 — the registry must tolerate a dependency on
an unregistered modificator (treat as already-satisfied) so a single-modificator
pipeline runs.

### D8 — fractalize Phase-1 cut

`ZoneSpec` has no treasure tiers (Phase 0a stub), so the §5.2 treasure-density
scaling of `span_factor`/`margin_factor` is **deferred** — Phase 1 fractalize uses
the base constants. `Hub` zones skip fractalize (single path); `Forbidden` zones
block all tiles; `Sea` uses the sparse `span_factor`. The connected-components
fixup (§5.2 end) IS implemented (determinism + correctness).

## 4. Acceptance criteria

- AC-1: `place_tilemap(template, seed, grid_size)` returns a `TilemapView` whose every
  zone has a non-empty `assigned_tiles`, a `free_paths` (empty only for `Forbidden`),
  a `center_position` inside its `assigned_tiles`, and a painted `terrain_layer`.
- AC-2: zone `assigned_tiles` are a **disjoint partition** — no tile in two zones;
  every grid tile assigned to exactly one zone.
- AC-3: FR convergence respects the §3 forces — connected zones end closer than
  unconnected; `Adversarial` edges end farther apart. (Tested on a small fixture.)
- AC-4: **determinism** — `place_tilemap` run twice with the same `(template, seed,
  grid_size)` yields byte-identical `TilemapView` (serde round-trip equal); a
  different seed yields a different layout.
- AC-5: `ModificatorRegistry` topologically orders modificators; a dependency cycle
  is rejected with a `TilemapError`; a dependency on an unregistered modificator is
  tolerated.
- AC-6: TerrainPainter paints every assigned tile; `Sea` zones → `Water`.
- AC-7: `cargo test --workspace` + `cargo clippy --workspace` green; the determinism
  test runs in CI (not `#[ignore]`d).

## 5. Risks

- R-A: Penrose P3 subdivision is the most intricate algorithm — getting the
  golden-ratio rhombus subdivision + vertex dedup right is the hard part. Mitigation:
  unit-test the subdivision against a known vertex count growth; a wrong tiling still
  yields *a* partition (AC-2 holds) — only the aesthetic suffers.
- R-B: `f64` determinism — see D4. The AC-4 test is the guard; if it ever flakes,
  the cause is an unordered reduction or a parallel float op (neither exists Phase 1).
- R-C: XL scope — this is a large engine. BUILD is structured in ordered chunks
  (grid-seed → FR → Penrose → fractalize → pipeline → TerrainPainter → determinism
  test); each chunk compiles + tests before the next. Multi-session is expected; the
  SESSION handoff carries the chunk boundary.

## 6. New dependencies

`rand` (`^0.8`), `rand_chacha` (`^0.3`) — workspace deps, used by `tilemap-service`.
No other new crates (`blake3` already present for seed derivation).
