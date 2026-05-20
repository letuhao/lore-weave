# GEO World-Tier Phase 1 — Spherical Topology

> **Spec:** [`docs/03_planning/LLM_MMO_RPG/GEO_WORLD_TIER_REDESIGN.md`](../03_planning/LLM_MMO_RPG/GEO_WORLD_TIER_REDESIGN.md) §3 + §3a + §3b + §8 phase 1.
>
> **Task size:** XL (10+ files, 15+ logic changes, 1 known side-effect: `content_hash` rebases for every fixture).
>
> **Workflow:** default 12-phase v2.2 with `/review-impl` adversarial pass after BUILD. CLARIFY + DESIGN + REVIEW(design) complete (`./scripts/workflow-gate.sh status`); this file is the **PLAN**.
>
> **PO decisions on this plan (2026-05-20):**
> - **3D hull algorithm:** hand-roll Quickhull first; `chull` crate as VERIFY-stage fallback if degenerate-input bugs surface (§3 B1, §8 risk row).
> - **Cell coords:** 3D Cartesian primary (`Cell.center_unit: [f32;3]`); `lat()` / `lon()` are derived methods (§3 B2).
> - **Projection enum:** **two** projections in Phase 1 — `Equirectangular` (default, 2:1 world map) **and** `Orthographic { camera: [f32;3] }` (globe view, circular disc, anti-meridian-split-free). Mollweide / Mercator deferred (§3 B5).
>
> **Goal:** replace the flat-`[0,1]²` mesh with a **true-sphere** mesh — Fibonacci-lattice sampling on the unit sphere + spherical Voronoi via 3D convex hull — and reproject all downstream stages (heightmap, climate, biome, render) onto the sphere. **Keep one continent** (multi-continent comes in Phase 2 / plate-tectonics).

---

## 1 — Why this phase exists

The `Gigaplanet` benchmark proved cell count is *resolution* not *scope*: a 501k-cell map still reads as one province. The generator is structurally a *region* generator on a flat square with 4 hard edges. Phase 1 retires the flat topology and switches to a globe. Phase 1 alone produces a believable Earth-shaped one-continent world; Phase 2 adds plate tectonics for multi-continent.

The cylinder alternative was rejected in PO review (2026-05-20) — sphere chosen for max realism.

---

## 2 — Scope (in)

| File | Change |
|---|---|
| `crates/world-gen/src/mesh.rs` | **rewritten** — Fibonacci-sphere sampling + 3D convex hull → adjacency + spherical Voronoi polygons. `delaunator` removed. |
| `crates/world-gen/src/world_map.rs` | `Cell.center: (f32, f32)` → `Cell.center_unit: [f32; 3]` (3D unit-sphere); `vertex_polygon: Vec<(f32, f32)>` → `Vec<[f32; 3]>`. Add `Cell::lat()` + `Cell::lon()` helpers. `compute_hash` reshaped to new fields. |
| `crates/world-gen/src/noise.rs` | NEW `gradient_noise_3d` + `fbm_3d` + `ridged_fbm_3d` (3D Perlin via lattice cube hash + 8-corner trilinear blend). Existing 2D fns retained for the `relief.rs` 2D image-space domain warp. |
| `crates/world-gen/src/terrain.rs` | `height_at` takes a 3D unit point. All inputs become 3D noise. `CoastlineProfile` heuristics reframed for sphere (great-circle distance, placement by `(lat, lon)`). |
| `crates/world-gen/src/climate.rs` | latitude derived from cell's 3D point; orographic wind march unchanged (graph-based). |
| `crates/world-gen/src/hydrology.rs` | **no change** — graph-only. |
| `crates/world-gen/src/erosion.rs` | **no change** — graph-only. |
| `crates/world-gen/src/biome.rs` | **no change**. |
| `crates/world-gen/src/political.rs` / `settlement.rs` / `routes.rs` / `culture.rs` / `pathfind.rs` | **adapt** — only place that uses 2D coords is "spatial distance" (e.g. Poisson-disk in settlement, route Dijkstra cost). Switch Euclidean → great-circle for sphere. |
| `crates/world-gen/src/render.rs` | NEW `Projection` enum (`Equirectangular` only, Phase 1). All `*_image` functions take a `Projection`. Anti-meridian polygon split. |
| `crates/world-gen/src/relief.rs` | re-triangulation uses 3D unit points → projected to 2D image at render time. Detail fBm in 3D. |
| `crates/world-gen/src/creative_seed.rs` | `WorldScale` semantics unchanged for Phase 1 (still N total cells); add a `Projection` field placeholder for forward compat (default Equirectangular). |
| `crates/world-gen/src/main.rs` | CLI gains `--projection equirectangular` (only choice). |
| `crates/world-gen/tests/structure.rs` + `determinism.rs` + `serde.rs` | re-baseline all expected hashes; add sphere-specific invariants (see §6). |
| `crates/world-gen/Cargo.toml` | remove `delaunator`. Hand-rolled 3D Quickhull (no new dep) OR add `chull` if hand-roll is too risky in time. **Recommendation: hand-roll** — small N (≤ 501k), determinism via sorted insertion order, no HashMap. |

**Total: ~14 files touched.**

## 2a — Scope (explicit out)

- **Multi-continent / plate tectonics** — Phase 2.
- **Köppen climate** — Phase 3; Phase 1 keeps today's 8-`ClimateZone` derivation (just on lat from sphere instead of `y` from rectangle).
- **Two-tier scale (tier-1 / tier-2)** — Phase 5.
- **Fantasy archetypes / anomaly regions** — Phase 6.
- **Mollweide / Mercator / Orthographic projections** — Phase 1 ships Equirectangular only; the `Projection` enum is wired so adding others is purely a render-side patch later.
- **Spherical relief renderer enhancements** (per-pixel sphere ray-march, latitude-weighted detail) — only the minimum needed to keep relief reading correctly post-projection.

---

## 3 — Implementation order (BUILD)

Six sub-tasks, each with its own VERIFY checkpoint. Order chosen so each step has a runnable smoke test.

### B1 — Mesh: Fibonacci sphere + 3D convex hull → adjacency
**Touches:** `mesh.rs` rewrite; `Cargo.toml` (remove `delaunator`).

- `place_points(N, rng) -> Vec<[f32; 3]>` — Fibonacci lattice with seed-jittered global rotation. Formula: for `i ∈ 0..N`, `z = 1 − (2i+1)/N`, `r = sqrt(1 − z²)`, `φ = i · (π·(3−√5)) + seed_offset`, `(x, y, z) = (r·cos φ, r·sin φ, z)`. Then a seed-driven 3D rotation (`Rng::next_quat` → unit quaternion) applied uniformly so different seeds give different orientations. No 2D jitter; the lattice itself is the "natural" distribution.
- `convex_hull_3d(points: &[[f32; 3]]) -> Vec<[u32; 3]>` — hand-rolled Quickhull. Returns CCW-ordered triangles (outward normal). For all points on unit sphere, every point is on the hull; the triangulation is the spherical Delaunay. Determinism: tie-break by ascending index when distances are equal.
- `adjacency` derived from triangle edges, sorted+deduped (unchanged signature).
- `voronoi_polygons` — spherical: vertex of cell `i`'s polygon = unit-normalized circumcentre on sphere of each incident Delaunay triangle, ordered CCW around `points[i]` (use tangent-plane projection at `points[i]` for angle ordering).
- `repair_degree` deleted — Fibonacci sphere has no hull corners, every cell has ≥ 5 neighbours by construction.

### B2 — Cell / WorldMap field migration
**Touches:** `world_map.rs`, `serde.rs` test, `tests/determinism.rs` golden hashes (just to keep tests compiling — will re-baseline at VERIFY).

- `Cell { center_unit: [f32; 3], elevation: u16, vertex_polygon_unit: Vec<[f32; 3]> }` + helper methods `lat() -> f32` (radians, `asin(z)`) and `lon() -> f32` (radians, `atan2(y, x)`).
- `compute_hash`: feed `center_unit` (12 bytes) + each polygon vertex (12 bytes each).
- All consumers (`render.rs`, `terrain.rs`, etc.) updated minimally — they compile but produce wrong output until B3.

### B3 — Heightmap on sphere
**Touches:** `noise.rs` (3D), `terrain.rs`.

- `noise::gradient_noise_3d(x, y, z, seed)` — 3D Perlin: 8 lattice corners, gradient hashed onto a unit-sphere direction, trilinear blend with smootherstep fade. No grid-aligned artefacts.
- `noise::fbm_3d` + `noise::ridged_fbm_3d` — same recipe as 2D, summed over octaves.
- `terrain::height_at(p: [f32; 3]) -> f32` — feeds `p` into 3D fBm / ridged fBm. Domain warp = `p + warp_amp · (warp_x(p), warp_y(p), warp_z(p))` — a small 3D vector field, applied before sampling continent / ridge / hill noise. Result normalized to `[0, 1]` then to `u16`.
- `CoastlineProfile` heuristics on sphere:
  - `Continental` — radial falloff from a placement point `c` chosen by RNG: `mask(p) = smooth_falloff(angle(p, c) / r_max)` where `angle` is the great-circle angle.
  - `Archipelago` — 5 placement points (icosahedron vertex subset for pleasant symmetry), each with spherical disc radius `r_arch`. Mask = max of the 5 disc masks. Discs picked so pairwise great-circle separation ≥ 2·r_arch + ε.
  - `Coastal` / `Inland` / `Highland` — straightforward reframing using great-circle distance to a placement point.
- `apply_falloff` operates on 3D points + great-circle distance instead of (x,y) + Euclidean. Same signature shape, swapped metric.
- `enforce_coherence` — unchanged (graph-based).

### B4 — Climate + downstream (Phase-1-minimal)
**Touches:** `climate.rs`, `political.rs`, `settlement.rs`, `routes.rs`, `culture.rs`, `pathfind.rs`.

- `climate::build` uses `cell.lat()` instead of `cell.center.1` as the latitude input. Hemisphere orientation logic unchanged.
- Orographic wind march: wind direction is now a 3D tangent-plane vector at each cell, derived from the `PrevailingWind` enum (e.g. `West` → −longitude direction at each cell). Adjacency traversal unchanged.
- `settlement::build` Poisson-disk: spatial distance becomes great-circle angle (`acos(p·q)`); the `min_separation` constant retunes to a radians value (mapped from the prior `[0,1]²`-units value by `r_new = r_old · sqrt(4π / 1)` — surface-area equivalence — but actually just *retune empirically* on the test fixture).
- `routes::build` Dijkstra path cost: leg cost uses great-circle distance for the geographic component; existing terrain-cost multiplier untouched.
- `pathfind::dijkstra` — graph-based, no change.
- `political::build` — flood-fill, no change.
- `culture::build` — flood-fill, no change.

### B5 — Render projection
**Touches:** `render.rs`, `relief.rs`.

- NEW `Projection` enum:
  ```rust
  #[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
  pub enum Projection { Equirectangular }
  ```
  (Mollweide/Mercator/Orthographic deferred.)
- `Projection::Equirectangular::project(p_unit: [f32; 3]) -> (f32, f32)` returns `(u, v)` in `[0,1]²` — `u = (lon + π) / 2π`, `v = (π/2 − lat) / π`.
- All `*_image` functions take a `&Projection`. The image canvas stays a rectangle but its aspect is fixed at 2:1 (equirectangular standard).
- **Anti-meridian polygon split** — when a cell's projected polygon has `max_lon − min_lon > π`, the polygon crosses the anti-meridian; split it into two parts at `lon = ±π`, project each half, draw both. Standard cartography trick.
- **Pole-pinching cells** — Fibonacci sphere does have cells touching the poles; these project to flat-top rectangles in equirectangular (the "polar smear"). Accept it visually for Phase 1; document.
- `relief.rs` re-triangulation: barycentric sampling over **spherical** triangles. Each render pixel back-projects to a 3D point on the sphere (inverse equirectangular), then standard barycentric over its containing spherical triangle. The cell-locator structure (today's grid index in `[0,1]²`) is replaced by a longitude-band binning (split sphere into `K` longitude bands × `K` latitude bands; each band holds the cells whose centre falls within it; per-pixel lookup checks the home band + 3×3 neighbour bands).
- Detail fBm switches to `fbm_3d` evaluated at the per-pixel back-projected 3D point — seamless across the anti-meridian for free.

### B6 — CLI + main + tests + Cargo
**Touches:** `main.rs`, `creative_seed.rs` (Projection field), `tests/*.rs`, `Cargo.toml`.

- CLI: `--projection equirectangular` (default; rejects anything else). The CLI `--png` / `--political-png` / `--relief-png` use the chosen projection.
- `CreativeSeed` gains `#[serde(default)] projection: Projection` (defaults to Equirectangular). Schema bump.
- Tests:
  - `structure::generates_a_coherent_map` — assertion list updated for sphere (no perimeter ring assertions; total cell area ≈ 4π steradians; degree distribution 4–10).
  - `structure::gigaplanet_generates_a_coherent_map` — same.
  - NEW `mesh::east_west_wrap_adjacency` — pick a low-latitude cell near lon=0 and one near lon=2π−ε; assert they are connected via shortest path through the wrap (or, simpler: assert there exist mutual neighbour cells across the seam).
  - NEW `mesh::pole_no_special_case` — assert that the cells with highest/lowest latitudes have normal degree (not 0, not WhopperNum).
  - NEW `mesh::fibonacci_uniform_area` — assert max-cell-area / min-cell-area < 4× (Fibonacci is near-uniform but not perfect; some tolerance OK).
  - `determinism::same_seed_byte_identical` — unchanged in spirit, baselined to new hashes.
  - `serde::compute_hash_covers_every_field` — extend coverage to the new 3D fields.
  - `serde::roundtrip_stable_*` — unchanged in spirit.
- `benches/generate.rs` — kept; benchmark numbers will shift (3D convex hull vs 2D Delaunay; expect 2-5× slower at Megaplanet, OK for Phase 1; can revisit in Phase 5 huge-scale).

---

## 4 — Determinism rules

- Mesh ordering: Fibonacci index `i ∈ 0..N` is the cell id. The seed-driven 3D rotation does **not** reorder indices.
- 3D Quickhull tie-break: when picking the farthest point from a face, ties resolved by ascending point index.
- Spherical Voronoi vertex ordering: CCW around cell centre using tangent-plane angle (`atan2` of projected offsets).
- 3D noise lattice hash: cube-corner hash uses ix/iy/iz; seed mixed in via existing pattern.

The blake3 `content_hash` is the global determinism gate. Same seed + scale + CreativeSeed ⇒ byte-identical `WorldMap`. Re-baselining is intentional (algorithm change, per spec §3).

---

## 5 — Re-baselining strategy

Every existing test that pins a specific hash will break. Strategy:

1. Run all tests after B1 + B2 — they fail loudly (mesh + cells changed).
2. Update structural invariants first (the `structure.rs` checks of "≥1 sea, ≥1 land, X% land within Y% of profile band, etc.").
3. Once `cargo test --release` produces clean runs end-to-end (all generation works, all structural tests pass), generate fresh golden hashes via `cargo test -- --nocapture` or a small helper bin and paste into the determinism tests.
4. The CLI `generate --seed 12345` output is the integration smoke — visually inspect the PNG before signing off on the hash bake.

This is the same flow used in the Path B heightmap rework (commit `1bfa54e0`) where `content_hash` intentionally broke. Documented in `GEO_GENERATOR_PLAN.md` already.

---

## 6 — VERIFY (Evidence Gate) — Phase 6 of workflow

Each invariant gets a fresh test run. Acceptance:

| Invariant | Test |
|---|---|
| Determinism | `cargo test determinism -- --nocapture` byte-identical pass over 5 fixture seeds × all WorldScales (gigaplanet ignored, run manually). |
| Mesh cell count = `WorldScale::cell_count()` | `mesh::cell_count_matches_scale` (kept). |
| No degenerate cells (degree 4–10) | `mesh::degree_in_range`. |
| Sphere coverage | `mesh::fibonacci_uniform_area` — Σ cell areas ≈ 4π ±0.5%. |
| E–W wrap | `mesh::east_west_wrap_adjacency`. |
| Pole regularity | `mesh::pole_no_special_case`. |
| Heightmap reaches land coherence | `structure::generates_a_coherent_map` (sphere-adapted). |
| Render produces valid PNG | CLI `generate --seed 42 --png /tmp/m.png` writes a non-empty PNG with the equirectangular 2:1 aspect. |
| Hash coverage | `serde::compute_hash_covers_every_field`. |
| Clippy clean | `cargo clippy --all-targets`. |

VERIFY is **not** "tests probably pass" — fresh run, output read, no shortcuts (per CLAUDE.md Phase 6).

---

## 7 — REVIEW (code) + `/review-impl`

Stage 1 spec compliance:
- Does the mesh actually wrap and pole-handle correctly?
- Are all 14 files updated coherently (no half-2D, half-sphere state)?
- Is `compute_hash` covering the new fields?

Stage 2 code quality:
- 3D Quickhull correctness on degenerate inputs (coplanar quads on sphere — handle with epsilon test).
- 3D noise period — `f32` precision at large argument values (sphere is unit-sphere so this is fine, but watch domain-warp amplification).
- `Projection::Equirectangular` anti-meridian split correctness — visual smoke test.
- Cell-locator (longitude-band index) for per-pixel renderer — perf cliff if poorly tuned.
- Polygon CCW orientation on sphere — use tangent-plane projection at cell centre for ordering; signed-area check.

`/review-impl` is **mandatory** after BUILD per the GEO arc's discipline. The user has consistently directed "fix all" (HIGH + MED + LOW + cosmetic) on every recent /review-impl pass; expect the same.

---

## 8 — Risk register

| Risk | Mitigation |
|---|---|
| 3D Quickhull is bug-prone | Start with smallest WorldScale (Pocket, ~1k cells) and verify; scale up only after smoke. Have `chull` crate as fallback. |
| Anti-meridian split renders glitchy | Visual smoke on a known seed; split test cases written first (TDD-able). |
| Polar smear in equirectangular ugly | Document, accept. Mollweide / Orthographic = Phase 5 if needed. |
| Heightmap distance metric retuning ugly | Visually compare to existing maps; tweak `r_max` per profile until similar visual scale. |
| Performance regression (3D hull > 2D Delaunay) | Phase 5 (huge-scale) is the budget. Phase 1 target: Megaplanet < 200 ms (currently ~91 ms). |
| `content_hash` rebaselining mistakes (pin wrong golden) | Re-baseline only after every other invariant passes; eyeball CLI render PNG. |

---

## 9 — Out-of-band notes

- The PO standing constraint per `SESSION_HANDOFF.md`: **nothing pushed, no PR**. Commit locally to `geo-generator-amaw`.
- This phase will close the spec's resolved-question table for §9 Q1/Q2/Q4/Q5; Q3 (tier-2 persistence) revisits at Phase 5.
- After commit, update `GEO_GENERATOR_PLAN.md` "Phase status board" with a Phase-1 row + brief log mirroring the prior 7 enhancements' entries.
- After commit, update `SESSION_HANDOFF.md` with a session entry recording the arc (consistent with the 2026-05-18 / TVL_005 / TVL_003 / GEO-enhancements pattern).
- Audit log: `docs/audit/AUDIT_LOG.jsonl` — append a START + COMMIT line for this task. The workflow-gate.py already does this automatically when AMAW is enabled (it is, from the prior geo-phase-4 task).

---

## 10 — Workflow-gate evidence trail

```
$ ./scripts/workflow-gate.sh size XL 10 15 1                    # done
$ ./scripts/workflow-gate.sh phase clarify && complete clarify  # done (PO answered 4/5 §9 Qs)
$ ./scripts/workflow-gate.sh phase design && complete design    # done (spec §3 + §3a + §3b)
$ ./scripts/workflow-gate.sh phase review-design && complete    # done (7 concerns surfaced)
$ ./scripts/workflow-gate.sh phase plan && complete plan        # NEXT — this file
$ ./scripts/workflow-gate.sh phase build                        # then B1..B6
…
$ ./scripts/workflow-gate.sh phase commit                       # final
```
