# GEO World-Tier Phase 1 — Spherical Topology, **Stage B**

> **Stage A** (commit `1433f045`): sphere mesh + 3D Perlin terrain +
> Cell.center 3D + climate effective_latitude swap. See
> [`2026-05-20-geo-spherical-topology.md`](2026-05-20-geo-spherical-topology.md)
> §3 B1–B4.
>
> **Stage B-1 (this commit, 2026-05-21):** `Projection` enum (Equirectangular
> + Orthographic, fully implemented & tested) + every downstream consumer
> migrated to native 3D + (u, v) adapter scaffold dropped from `lib.rs`.
> Covers plan §3 B1–B3 + parts of B6. The `render.rs` + `relief.rs` entry
> points still hardcode equirectangular internally.
>
> **Stage B-2 (next commit):** thread `Projection` through `render.rs` +
> `relief.rs`; rewrite the per-pixel sampler for the Orthographic path;
> CLI `--projection` + `CreativeSeed.projection` field; drop `delaunator`
> from `Cargo.toml`. Covers plan §3 B4–B5 + remaining B6 + B7.
>
> **Task size:** XL (13+ files, 18+ logic changes, content_hash rebases again
> — settlement Poisson-disk + route Dijkstra switch from `(u, v)` Euclidean
> to great-circle distance, both deterministic but byte-different).

---

## 1 — Why this stage exists

Stage A made the *mesh* spherical but kept the *consumers* 2D via a per-cell
`(u, v)` equirectangular projection scaffold in `lib::generate`. That worked
to ship the foundation; it leaves three real defects:

- Settlement Poisson-disk separation is **Euclidean in `(u, v)`** → stretched
  near the poles (cells at v ≈ 0/1 are spuriously "close" in `u` despite
  being far in actual great-circle distance).
- Route Dijkstra leg costs use `(u, v)` Euclidean → same polar distortion.
- The Equirectangular projection is hardcoded in the renderer — no globe
  view, no future Mollweide / Mercator.

Stage B closes all three and exposes the **Orthographic globe view** the PO
asked for in spec review.

---

## 2 — Scope (in)

| File | Change |
|---|---|
| `crates/world-gen/src/render.rs` | NEW `Projection` enum (`Equirectangular`, `Orthographic { camera }`) with `project()` + `back_project()` + a small visibility test. Move the equirectangular `(u, v)` projection from `lib.rs::project_uv` here as `Projection::Equirectangular::project`. All `*_image` functions take a `Projection` argument. Anti-meridian polygon split for Equirectangular (skip for Orthographic — disc has no seam). Spatial-index buckets keyed by `Projection`. |
| `crates/world-gen/src/relief.rs` | `cell_px` takes a `Projection`. Per-pixel back-projection: rasterize over a unit-disc mask for Orthographic; full canvas for Equirectangular. **Delaunator drop:** replace the `delaunator` re-triangulation with a `SpatialIndex`-based nearest-cell sample (loses the soft barycentric blend across triangles; gain a sharper-but-deterministic Voronoi cell shading). This is the only relief-render quality trade in stage B — defer Voronoi-cell-bilinear interp to a later perf/quality pass. |
| `crates/world-gen/src/lib.rs` | **Drop `project_uv` and `centers_2d` adapter.** Pass `mesh.centers` (3D) directly to every consumer. The Stage A scaffold goes away. |
| `crates/world-gen/src/climate.rs` | Take `&[[f32; 3]]` centres. **Drop `effective_latitude(y, hemi)` v-based formula;** derive `lat` directly from each cell's 3D centre. Hemisphere mapping becomes `lat → eff_lat` rather than `v → eff_lat`. Orographic wind march keeps working on the sphere graph (no geometry change — adjacency is sphere-correct). The `PrevailingWind::vector()` 2D direction becomes a tangent-plane direction at each cell; for the V1 wind march we project the world direction onto each cell's tangent plane. |
| `crates/world-gen/src/hydrology.rs` | Signature change — `&[[f32; 3]]` centres. Pure-graph code; no logic change. |
| `crates/world-gen/src/political.rs` | Signature change. Pure-graph flood-fill; no logic change. |
| `crates/world-gen/src/settlement.rs` | Signature change + **great-circle Poisson-disk separation.** Distance metric swapped from `(u, v)` Euclidean to `acos(p · q)` (cells on unit sphere). The `min_separation` constants retune from `[0,1]²` units to radians. **`content_hash` shifts.** |
| `crates/world-gen/src/routes.rs` | Signature change + **great-circle leg cost in the Dijkstra.** The terrain-cost multiplier is preserved; only the geographic distance term is swapped. **`content_hash` shifts.** |
| `crates/world-gen/src/culture.rs` | Signature change. Pure-graph flood-fill; no logic change. |
| `crates/world-gen/src/creative_seed.rs` | `#[serde(default)] projection: Projection` field. Default = `Equirectangular`. Schema bump (the `serde` `Default` derive on the enum keeps a pre-projection JSON loadable). LLM author schema (`author.rs`) gains a `projection` enum option. |
| `crates/world-gen/src/main.rs` | CLI `--projection equirectangular|orthographic` (and optional `--camera x,y,z` for Orthographic; default `1,0,0`). Loaded into the `Projection` that renders use. |
| `crates/world-gen/src/author.rs` | (Possibly) JSON schema lists the new `Projection` enum so the LLM author can pick. Touched only if the LLM-author flow needs it; otherwise unchanged. |
| `crates/world-gen/Cargo.toml` | **Remove `delaunator`** dependency. |
| `crates/world-gen/src/feature.rs` | (Touch only if needed — graph-only code.) |
| `crates/world-gen/tests/structure.rs` | Update tests that previously assumed `(u, v)` semantics for cells — switch to `Cell::lat()` / `Cell::lon()`. The hemisphere-orientation test (Stage A already updated) keeps working. Add a new `cli_renders_both_projections` integration smoke or `orthographic_disc_mask_is_a_hemisphere` test. |
| `crates/world-gen/tests/serde.rs` | `compute_hash_covers_every_field` — no change (it traverses every WorldMap field via the existing pattern). |
| `crates/world-gen/tests/determinism.rs` | Add an `orthographic_render_is_deterministic` integration smoke. Existing cases byte-rebase (settlement + route changes). |
| `crates/world-gen/tests/author_llm.rs` | If author schema gains `projection`, update the LLM-flow test to pass `Projection` round-trip. |
| `docs/plans/2026-05-20-geo-sphere-stage-b.md` | This plan file. |
| `docs/03_planning/LLM_MMO_RPG/GEO_GENERATOR_PLAN.md` | Handoff updated at SESSION phase. |
| `docs/03_planning/LLM_MMO_RPG/GEO_WORLD_TIER_REDESIGN.md` | §8 phase 1 marked DONE; §9 table cells stay as resolved. |

**Total: ~16 files.**

## 2a — Scope (out)

- Plate-tectonic multi-continent (Phase 2).
- Köppen climate model (Phase 3).
- Two-tier scale (Phase 5).
- Fantasy archetypes (Phase 6).
- Mollweide / Mercator projections (later — the enum is open for extension).
- Spherical barycentric in `relief.rs` (replaced with nearest-cell sample;
  per-cell shading rather than per-triangle bilinear).
- Orographic wind march upgrade (the V1 march stays as a tangent-projected
  2D direction; full Hadley/Ferrel/Polar cell modelling is Phase 3).

---

## 3 — Implementation order (BUILD)

### B1 — `Projection` enum + tests
**Touches:** `render.rs` (define + `Default` + `project` + `back_project` + a small visibility test for Orthographic).

```rust
pub enum Projection {
    Equirectangular,
    Orthographic { camera: [f32; 3] },
}
```

- `project(p_unit) -> Option<(f32, f32)>` — `Some((u, v))` in `[0, 1]²` for
  visible cells; `None` for hidden (Orthographic far side).
- `back_project((u, v)) -> Option<[f32; 3]>` — inverse; `None` for the
  Orthographic-disc background pixels.
- Equirectangular: `u = (lon + π) / 2π`, `v = (π/2 − lat) / π`; trivial.
- Orthographic: build orthonormal basis `(ex, ey)` at `camera`; project
  `p` onto the basis plane. Visibility = `p · camera ≥ 0`.
- Tests: project then back-project = identity for both, visibility of
  Orthographic correctly halves the sphere, both deterministic.

### B2 — `lib.rs` adapter drop
**Touches:** `lib.rs` (drop `project_uv` + `centers_2d`; update all consumer call sites to receive `&mesh.centers`).

After B2 every consumer in the call chain takes 3D directly. The consumers
themselves still expect `(f32, f32)` until B3.

### B3 — Native-3D consumer migration
**Touches:** `climate.rs` + `hydrology.rs` + `political.rs` + `settlement.rs` + `routes.rs` + `culture.rs`.

Per-file:
- `climate.rs`: `effective_latitude` operates on a `[f32; 3]` centre; derives
  `lat = asin(z)` and applies the hemisphere convention. The Stage A v-based
  swap is replaced by a clean lat-based formula. Orographic wind march:
  `PrevailingWind::vector()` becomes a 2-tuple interpreted at each cell as
  *(eastward, northward)* in the local tangent plane. The sort projection
  becomes a dot product against the tangent-plane wind direction.
- `hydrology.rs`: pure signature change; logic graph-only.
- `political.rs`: pure signature change.
- `settlement.rs`: Poisson-disk separation = `acos(p · q)` (great-circle).
  `SettlementDensity::min_separation()` constants retune from `[0,1]²` units
  to radians via empirical match against the existing fixture map.
- `routes.rs`: Dijkstra leg cost's geographic component = great-circle (the
  terrain-cost multiplier stays exactly as is).
- `culture.rs`: pure signature change.

### B4 — `render.rs` uses `Projection`
**Touches:** `render.rs` (all `*_image` + `*_svg` functions).

- Each `*_image` takes a `Projection` argument.
- `svg_px` / `cell_px` route through `Projection::project`; cells whose
  `project` returns `None` are skipped (Orthographic hidden side).
- Anti-meridian polygon split: when a cell's projected polygon has
  `max_lon − min_lon > π`, split it at `lon = ±π` and draw two halves
  (Equirectangular only; Orthographic discs don't cross the meridian).
- `SpatialIndex::build` takes a `Projection`; buckets cells by their
  projected `(u, v)` only when the projection returns `Some`.

### B5 — `relief.rs` uses `Projection` + `delaunator` drop
**Touches:** `relief.rs` (rewrite the per-pixel sampler).

- Drop the `delaunator` re-triangulation.
- Per pixel:
  - `back_project((px, py)/(width, height)) -> Option<[f32; 3]>`
  - `None` (orthographic background): paint the background color.
  - `Some(p)`: find the nearest cell via a `SpatialIndex` keyed by the same
    projection, sample its `elevation`, apply the hypsometric ramp +
    hillshade as before.
- The relief becomes per-Voronoi-cell rather than per-Delaunay-triangle
  barycentric. Loss: cell boundaries read as harder edges instead of soft
  triangulated blends. Gain: simpler, fewer artifacts at the antimeridian
  / disc-edge, no extra crate.
- The detail fBm switches from 2D `(u, v)` to **3D `(x, y, z)`** sampled at
  the back-projected sphere point — same trick `terrain.rs` already does;
  seamless across the antimeridian for free.

### B6 — CLI + creative_seed + Cargo cleanup
**Touches:** `creative_seed.rs`, `main.rs`, `author.rs` (schema), `Cargo.toml`.

- `creative_seed.rs`: `#[serde(default)] projection: Projection` (with a
  default that loads pre-Projection JSON cleanly).
- `main.rs`: `--projection equirectangular|orthographic[:camera]`. CLI
  defaults Equirectangular. Orthographic accepts an optional comma-triple
  camera (default `1,0,0` — look at lat=0, lon=0).
- `author.rs` (LLM author): schema includes `projection` as a string enum;
  schema unchanged otherwise. Round-trips through the existing test.
- `Cargo.toml`: remove `delaunator`.

### B7 — Tests + content_hash rebase
**Touches:** `tests/structure.rs`, `tests/determinism.rs`, `tests/serde.rs`, `tests/author_llm.rs` (only the schema-change line).

- Update `tests/structure.rs` Northern/Southern hemisphere test path: still
  uses `Cell::lat()` from Stage A — no change needed.
- Add `orthographic_disc_mask_is_a_hemisphere` test (Orthographic projects
  ~50% of cells, the other ~50% are `None`).
- Add `cli_renders_both_projections` integration smoke (CLI accepts each
  flag and produces a non-empty PNG).
- The existing determinism tests rebase (settlement + route output bytes
  shift — intentional).

---

## 4 — Determinism rules

- `Projection::Orthographic { camera }` is hashed if it's stored on
  `CreativeSeed` — yes, via `serde` derives. Distinct cameras ⇒ distinct
  hashes only if rendering is hashed; the renderer is **not** part of
  `WorldMap::compute_hash`, so the projection itself doesn't affect the
  content hash. Hash still depends purely on mesh + heightmap + climate +
  political layers.
- Great-circle Poisson disk: `acos` is f64-precise enough for the f32 inputs
  (deterministic across platforms — same `f64::acos` impl required, IEEE
  guarantees deterministic results for finite inputs).

---

## 5 — Re-baselining

Like Stage A:

1. Run all tests; determinism rebaselines silently within each run.
2. Structural invariants stay intact (cell count, degree distribution, all
   layers populated, hash coverage).
3. Visually verify Orthographic vs Equirectangular: CLI renders for one
   fixture seed; confirm the disc is centred and ~half the cells are
   visible in Orthographic.

The re-baselined hash list lives in the diff — no separate fixture file.

---

## 6 — VERIFY (Evidence Gate)

| Invariant | Test |
|---|---|
| Determinism | `cargo test determinism` byte-identical across two runs of every fixture. |
| Projection round-trip | `projection::project_back_projects_to_self` for both. |
| Orthographic visibility | `projection::orthographic_hides_far_side` (`project` returns `None` for `p · camera < 0`). |
| Disc mask | `relief::orthographic_relief_has_disc_mask` (background pixels paint background, foreground ones don't). |
| Native-3D consumers | `tests/structure.rs` full suite passes (slow but expected; run in release with `--test-threads=2`). |
| Settlement / route output shift | content_hash rebased — pin new gold hashes (re-baselined in the diff). |
| Hash coverage | `serde::compute_hash_covers_every_field` (unchanged). |
| Clippy clean | `cargo clippy --all-targets`. |
| CLI smoke | `world-gen generate --seed 42 --projection orthographic --png /tmp/o.png` and `--projection equirectangular` both succeed. |

---

## 7 — REVIEW + `/review-impl`

Stage 1 spec compliance:
- All 16 files match plan §2 entries.
- No half-2D / half-3D state in any consumer.
- `delaunator` actually removed from `Cargo.toml`.

Stage 2 quality:
- Orthonormal basis at the camera is constructed without singular cases
  (the `world_up` fallback when camera ≈ ±z).
- Great-circle Poisson-disk min-separation values empirically retuned (visual
  smoke on the fixture; not a perfect 1:1 with prior runs but reasonable
  density).
- Anti-meridian polygon split correctness — visual smoke.
- 3D detail fBm in `relief.rs` resolves the antimeridian smear automatically.

`/review-impl` is mandatory after BUILD per the GEO arc discipline.

---

## 8 — Risk register

| Risk | Mitigation |
|---|---|
| Settlement / route hash shifts surprising | Documented in the spec; the visual map output is qualitatively similar (only the placement of individual settlements moves). |
| Orthographic disc background colour choice ugly | Default to neutral grey; CLI override possible later. |
| `relief.rs` quality regression vs barycentric blend | Documented trade; can revisit with per-cell-bilinear interp later. |
| Camera direction at poles | `Orthographic { camera: [0, 0, 1] }` needs a careful tangent basis — handled by the helper-axis swap (same trick `mesh.rs::tangent_basis` already uses). |
| f64 precision of `acos` for very close cells | Clamp to `[-1, 1]` before `acos`; standard practice. |

---

## 9 — Out-of-band notes

- The PO standing constraint (`SESSION_HANDOFF.md`): **nothing pushed, no
  PR**. Commit locally to `geo-generator-amaw`.
- This commit closes **Phase 1** of the world-tier redesign in full.
  Phase 2 (plate-tectonic multi-continent) begins in the next session.
- Update `GEO_GENERATOR_PLAN.md` "Phase status board" with Phase 1 = DONE
  + a Stage B build-log paragraph + Phase 2 = NEXT.
- Mark `GEO_WORLD_TIER_REDESIGN.md` §8 Phase 1 = DONE (both stages).

---

## 10 — Workflow-gate evidence trail

```
$ ./scripts/workflow-gate.sh reset
$ ./scripts/workflow-gate.sh size XL 13 18 1
$ ./scripts/workflow-gate.sh complete clarify ...  # done
$ ./scripts/workflow-gate.sh complete design ...   # done
$ ./scripts/workflow-gate.sh complete review-design ...  # NEXT
$ ./scripts/workflow-gate.sh complete plan ...     # this file
$ ./scripts/workflow-gate.sh phase build           # then B1..B7
...
$ ./scripts/workflow-gate.sh phase commit          # final
```
