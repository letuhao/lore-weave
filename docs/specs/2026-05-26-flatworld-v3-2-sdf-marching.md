# Spec — Flatworld v3.2 SDF Capsule Chain + Marching Squares

> **Status:** DRAFT — kickoff 2026-05-26.
> **Parent roadmap:** [`../plans/2026-05-25-phase-a-v3-roadmap.md`](../plans/2026-05-25-phase-a-v3-roadmap.md) §4 Tier 1 row v3.2, §11 acceptance.
> **Predecessor:** [`2026-05-25-flatworld-v3-1-shape-dispatcher.md`](2026-05-25-flatworld-v3-1-shape-dispatcher.md) (v3.1a+b+c shipped 26492465 / 007ccf68 / 8a0c3352).
> **Mode:** v2.2 human-in-loop (PO opted out of AMAW in CLARIFY). Branch `geo-generator-amaw`.
> **Scope:** single v3.2 commit — SDF capsule chain + marching squares + dispatcher weights v3.2 + v5.5 eval baseline.
> **Size class:** XL (files=8, logic=10, side_effects=1 baseline regen).

---

## 1 — Problem

After v3.1 (Bézier spine, Polar, Boolean) the dispatcher has 4 algorithms but only one of them can produce **branching topologies** (BezierSpine), and that one is constrained to a single open spine. PO directive in roadmap §0: "thay vì hiện tại chỉ có mỗi oval" (instead of currently only oval). v3.1 lifted the "only oval" constraint but the visual variety is still limited to roughly elongated / star / annulus.

v3.2 fixes two gaps:

1. **True branching shapes** — SDF capsule chain with smooth-min blending lets one generator emit Y-branches, Z-zigzags, crab-radial, worm-chain topologies that no spline-based algorithm can match cleanly.
2. **Implicit-field shapes** — marching squares on a noise field unlocks non-parametric continent silhouettes (anything the noise field draws), including holes / lakes / multi-component output even though v3.2 returns single-component (multi-component deferred to v3.3 per roadmap).

Both share a raster→polygon pipeline (256×256 grid, marching squares, Chaikin smoothing) — that's why roadmap §4 keeps them in the same phase.

---

## 2 — Goals

### 2.1 — SDF capsule chain (ShapeKind::SdfCapsuleChain)
- NEW `shape/sdf.rs` (~250 LOC).
- `SdfCapsuleChainGenerator` impls `ShapeGenerator`.
- 4 templates picked deterministically from `ctx.seed` hash:
  - **Y-branch** — 3 capsules meeting at one joint, 120° apart (continents with three arms).
  - **Z-zigzag** — 4 capsules in zig-zag chain (elongated crinkled coast).
  - **Crab-radial** — 5 capsules from one centre, 72° apart (crab/starfish topology).
  - **Worm-chain** — 6 capsules in slight curving chain (worm continent).
- Smooth-min blending (`smin_k` parameter per template) merges capsules into one organic silhouette.
- Per-rank radius/joint-spacing bands so Giant Y-branch ≠ Micro Y-branch.
- Output: single polygon via shared raster pipeline.

### 2.2 — Marching squares pipeline (ShapeKind::MarchingNoise)
- NEW `shape/raster.rs` (~200 LOC) — **shared between SDF and MarchingNoise**.
- Pipeline: function `fn(x,y)->f32` → 256×256 grid → marching squares iso-contour at 0 → contour ordering → Chaikin smoothing (2 passes) → simplification (Douglas-Peucker, ε = 0.5% of bbox diagonal).
- `MarchingNoiseGenerator` builds an fbm noise field (3 octaves), threshold = noise mean, calls shared pipeline.
- Output: single polygon (largest contour by area; other components dropped — v3.3 will return multi-component).

### 2.3 — Dispatcher integration
- NEW `engine_v3_2_weights()` returns full 6-kind per-rank table from roadmap §14 Q4. **Replaces v3.1b 4-kind default.**
- `flatworld::generate` default flips from `Weighted(engine_v3_1b_weights())` to `Weighted(engine_v3_2_weights())`.
- `engine_v3_1b_weights()` retained as `pub fn` for reproducing v3.1 baselines.
- `ShapeRegistry::engine_default()` extended to register the 2 new generators.

### 2.4 — Eval framework adaptation (per roadmap §14 Q6)
- `lat_banding` metric: tolerate Y-branch / crab-radial plates that legitimately span 2+ lat bands. Threshold tuning, not metric rewrite.
- New baseline `eval/baselines/v5.5.json` locks v3.2 mean composite (whatever it lands at). v5.4 retained for v3.1 reproducibility.
- No strict pass/fail gate — eval is a tool per PO directive.

### 2.5 — Visual review artifacts
- Render seeds **13, 42, 108, 256, 512** (5 seeds, drop seed 7 per PO).
- For each seed: `plates_s{seed}.png` + `biome_s{seed}.png` = 10 PNG artifacts under `eval/compare-v3-2/`.
- At least 1 plate per render must show a v3.2-only shape (SdfCapsuleChain or MarchingNoise).

---

## 3 — Non-goals

- Multi-component plates (v3.3 — marching squares extension).
- Hole-in-polygon (v3.3 — Boolean ring already documented gap).
- Slime/Physarum, stamps (v3.4, v3.5).
- Zone / sub-zone templating (v4.1, v4.2).
- LLM dispatch / Manual override (v4.0 / v4.3).
- New crate deps — SDF + marching squares implemented from scratch in pure Rust.
- Chaikin pass count > 2 (configurable but locked at 2 for v3.2).
- Adaptive raster resolution (fixed 256×256; v4+ may add).

---

## 4 — Design

### 4.1 — Module layout

```
crates/world-gen/src/shape/
├── mod.rs           # extend: add SdfCapsuleChain + MarchingNoise to enum + engine_default
├── dispatch.rs      # extend: engine_v3_2_weights() returning 6-kind per-rank HashMap
├── ellipse.rs       # unchanged
├── spine.rs         # unchanged
├── polar.rs         # unchanged
├── csg.rs           # unchanged
├── sdf.rs           # NEW — SdfCapsuleChainGenerator + 4 templates + smooth-min
└── raster.rs        # NEW — shared marching-squares pipeline + MarchingNoiseGenerator
```

`lib.rs` already has `pub mod shape;`.

### 4.2 — SDF math (sdf.rs)

```rust
/// Signed distance from point `p` to capsule defined by endpoints `a,b` and radius `r`.
/// Standard formulation: project p onto segment ab, clamp t ∈ [0,1], distance = |p - lerp(a,b,t)| - r.
fn sdf_capsule(p: (f32,f32), a: (f32,f32), b: (f32,f32), r: f32) -> f32 { ... }

/// Polynomial smooth minimum (Quílez): h = clamp(0.5 + 0.5*(d2-d1)/k, 0, 1);
/// lerp(d2, d1, h) - k*h*(1-h).
fn smin_poly(d1: f32, d2: f32, k: f32) -> f32 { ... }

pub struct CapsuleTemplate {
    pub name: &'static str,
    pub joints: Vec<(f32,f32)>,     // unit-space anchor points
    pub radii: Vec<f32>,            // per-segment radii (len == joints.len() - 1 if open, == joints.len() if closed)
    pub edges: Vec<(usize,usize)>,  // joint indices forming each capsule
    pub smin_k: f32,                // smoothing strength
}

const TEMPLATES: [CapsuleTemplate; 4] = [
    CapsuleTemplate { name: "y_branch",  /* 4 joints / 3 edges meeting at one centre */ ... },
    CapsuleTemplate { name: "z_zigzag",  /* 5 joints / 4 edges */ ... },
    CapsuleTemplate { name: "crab_radial", /* 6 joints / 5 edges from centre */ ... },
    CapsuleTemplate { name: "worm_chain", /* 7 joints / 6 edges curving */ ... },
];
```

### 4.3 — Generator flow (sdf.rs)

```rust
pub struct SdfCapsuleChainGenerator;
impl ShapeGenerator for SdfCapsuleChainGenerator {
    fn kind(&self) -> ShapeKind { ShapeKind::SdfCapsuleChain }
    fn generate(&self, ctx: &ShapeContext, rng: &mut Rng) -> Vec<Polygon> {
        // 1. Pick template deterministically from ctx.seed hash.
        // 2. Per-rank scale: scale joints by radius_band, radii by capsule_radius_band(size_rank).
        // 3. Anchor at ctx.center, rotate by rng-drawn angle (small jitter).
        // 4. Build SDF closure: |p| -> capsules.iter().fold(big, |acc, cap| smin_poly(acc, sdf_capsule(p, cap.a, cap.b, cap.r), template.smin_k))
        // 5. Hand off to raster::sdf_to_polygon(sdf_fn, bbox, ctx.edge_jitter, rng).
    }
}
```

### 4.4 — Marching squares pipeline (raster.rs)

Public API:

```rust
/// Rasterize an SDF-style function (negative = inside, positive = outside) into a single closed polygon.
pub fn field_to_polygon(
    field: &dyn Fn((f32,f32)) -> f32,
    bbox: (f32,f32,f32,f32),       // (xmin, ymin, xmax, ymax) in world coords
    iso_level: f32,                // contour level (typically 0.0 for SDF)
    grid_res: usize,               // 256 for v3.2
    chaikin_passes: usize,         // 2 for v3.2
    simplify_eps_frac: f32,        // 0.005 = 0.5% of bbox diagonal
    rng: &mut Rng,                 // tiebreak for ambiguous saddle cases
) -> Polygon;
```

Pipeline stages:

1. **Grid sample** — eval `field(p)` at every `(x,y)` in 256×256 grid covering `bbox`.
2. **Marching squares** — 16 cases, per-cell. Ambiguous cases 5 and 10 (saddles) resolved by sampling cell centre: same sign as corners → connect; opposite → split.
3. **Contour stitching** — walk segments edge-to-edge to build closed rings. Multiple rings produced if field has multiple components — return only **largest by signed area**.
4. **Chaikin smoothing** — 2 passes: for each edge `(p_i, p_{i+1})`, replace `p_i` with `0.75 p_i + 0.25 p_{i+1}` and insert `0.25 p_i + 0.75 p_{i+1}`. Polygon length quadruples per pass; cap at 512 vertices via Douglas-Peucker.
5. **Douglas-Peucker simplification** — ε = `simplify_eps_frac * bbox_diagonal`. Cap final vertex count at 96 (matches Bézier spine maximum).
6. **Centroid alignment** — translate so polygon centroid == intended `ctx.center` (marching-squares centroid may drift from analytical centre).

Internal RNG use:
- Saddle tiebreak (very small consumption — ~0.1% of cells).
- `edge_jitter` applied as Gaussian noise on Chaikin output (consistent with `EllipseGenerator` v3.0 behaviour).

### 4.5 — MarchingNoise generator (raster.rs)

```rust
pub struct MarchingNoiseGenerator;
impl ShapeGenerator for MarchingNoiseGenerator {
    fn kind(&self) -> ShapeKind { ShapeKind::MarchingNoise }
    fn generate(&self, ctx: &ShapeContext, rng: &mut Rng) -> Vec<Polygon> {
        let bbox = bbox_from_envelope(ctx.center, ctx.envelope);
        let salt = ctx.plate_salt;
        let field = move |p: (f32,f32)| -> f32 {
            // 3-octave fbm, centred so threshold = 0
            let n = fbm3(p, salt);
            let radial_falloff = ((p.0 - ctx.center.0).hypot(p.1 - ctx.center.1)) / ctx.envelope.0;
            n - radial_falloff       // negative inside the continent shape
        };
        let poly = field_to_polygon(&field, bbox, 0.0, 256, 2, 0.005, rng);
        vec![poly]
    }
}
```

The radial falloff guarantees a closed inside region near `ctx.center` even when noise field is otherwise unbounded.

### 4.6 — Dispatcher weights (dispatch.rs)

```rust
pub fn engine_v3_2_weights() -> HashMap<SizeRank, HashMap<ShapeKind, f32>> {
    // Per roadmap §14 Q4 table (final-locked):
    // Giant:  Ellipse 0.15, BezierSpine 0.20, Polar 0.10, Boolean 0.10, SdfCapsuleChain 0.20, MarchingNoise 0.10, Slime 0.05, Stamp 0.10
    // Large:  ... (Stamp 0.05, etc.)
    // Medium: ... (no Stamp, no extra weight on Sdf)
    // Small:  ...
    // Micro:  ...
    //
    // v3.2 implementation: Slime + Stamp weights merged into Ellipse (since not implemented).
    // Result for v3.2 (6 active kinds, weights renormalised):
    //   Giant:  Ellipse 0.30, BezierSpine 0.20, Polar 0.10, Boolean 0.10, SdfCapsuleChain 0.20, MarchingNoise 0.10
    //   Large:  Ellipse 0.25, BezierSpine 0.25, Polar 0.10, Boolean 0.15, SdfCapsuleChain 0.15, MarchingNoise 0.10
    //   Medium: Ellipse 0.30, BezierSpine 0.25, Polar 0.20, Boolean 0.10, SdfCapsuleChain 0.10, MarchingNoise 0.05
    //   Small:  Ellipse 0.40, BezierSpine 0.20, Polar 0.25, Boolean 0.05, SdfCapsuleChain 0.10, MarchingNoise 0.00
    //   Micro:  Ellipse 0.55, BezierSpine 0.10, Polar 0.30, Boolean 0.05, SdfCapsuleChain 0.00, MarchingNoise 0.00
}
```

**Rationale for SDF/Marching weight assignment by rank:**
- Giant favours SdfCapsuleChain (Eurasia-style branching).
- Large/Medium gets both.
- Small/Micro **excludes** SdfCapsuleChain (capsule chain on a 30-pixel plate degenerates to a blur) and MarchingNoise (no room for noise variation).

PO can tune in v4.5 calibration; these values are starting point.

### 4.7 — Schema impact

Zero changes to `Plate` struct. `ShapeKind` enum already declares `SdfCapsuleChain` and `MarchingNoise` variants since v3.1a (reserved). Only the `ShapeRegistry::engine_default()` body grows.

`Plate::shape_kind` field is already populated by dispatcher in v3.1b — no migration needed.

---

## 5 — RNG order discipline

Same rule as v3.1: each generator owns its RNG stream rooted at `ctx.seed`. Two RNG-order risks specific to v3.2:

1. **Template selection consumes RNG.** `SdfCapsuleChainGenerator` uses 1 `rng.next_u32()` to pick template index, then 1 `rng.next_f32()` for global rotation. Order MUST be `[template, rotation, ...per-template-internal]`. Switching breaks reproducibility.
2. **Saddle tiebreak in marching squares.** Cell-centre tiebreak consumes 1 `rng.next_f32()` per ambiguous cell. To avoid scattered RNG order across grids of different sizes, the implementation collects all ambiguous cells in scan order (row-major top-to-bottom) and resolves them sequentially.

Determinism test: for a fixed `ctx`, two `generate` calls with cloned RNG MUST produce bit-identical polygons.

---

## 6 — Eval adaptation strategy

`lat_banding` (latitudinal band coverage uniformity) currently penalises plates whose vertices span >2 lat bands. v3.2 introduces:
- Y-branch: typically 3 lat bands by design (north arm, equator centre, south arm).
- Crab-radial: 3-5 lat bands.

**Adaptation:** instead of vertex-count threshold, measure **area-weighted band distribution entropy**. A Y-branch that puts 1/3 of its area in each of 3 bands gets high entropy → low penalty. A degenerate sliver across all 11 bands gets low entropy → still penalised.

```python
# scripts/climate_eval.py — v5.5 update
def lat_banding_score_v5_5(plates, n_bands=11):
    # Per-plate area-weighted band histogram → normalised → entropy
    # Composite = 1.0 - mean(entropy_per_plate)  (lower entropy → less spread → higher score)
```

`v5.4.json` retained. `v5.5.json` regenerated post-build.

---

## 7 — Acceptance criteria (per roadmap §11 v3.2 + this spec)

- [ ] NEW `crates/world-gen/src/shape/sdf.rs` exists, compiles, ≥4 unit tests pass.
- [ ] NEW `crates/world-gen/src/shape/raster.rs` exists, compiles, ≥6 unit tests pass (field_to_polygon edge cases).
- [ ] `ShapeRegistry::engine_default()` registers 6 generators (was 4).
- [ ] `engine_v3_2_weights()` returns full table; `flatworld::generate` default uses it.
- [ ] `engine_v3_1b_weights()` preserved as `pub` for reproducibility.
- [ ] 4 SDF templates render correctly (visual: each one shows distinct topology at seed 42).
- [ ] Determinism test: same `(seed, plate_idx)` → bit-identical polygon across 2 runs (for both generators).
- [ ] `cargo test --lib -p world-gen` passes (target ≥260 tests, was 253 in v3.1).
- [ ] `cargo clippy --all-targets --all-features` clean (3 pre-existing warnings tolerated).
- [ ] Render artifacts: 10 PNGs in `eval/compare-v3-2/` (seeds 13/42/108/256/512 × {plates, biome}).
- [ ] At least 1 plate per render uses SdfCapsuleChain or MarchingNoise (verified by examining `Plate::shape_kind` array dumped during render).
- [ ] `eval/baselines/v5.5.json` committed; old v5.4.json untouched.
- [ ] PO visual review of 5 PNG pairs: approve before SESSION + COMMIT.

---

## 8 — Risks + mitigations

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | Marching squares saddle ambiguity creates flickering polygons across seeds | Medium | Deterministic saddle tiebreak via cell-centre sample; document in comments; test 5+ seeds for visual stability. |
| 2 | Chaikin 2-pass output too smooth → loses sharp coast character | Low | Apply post-Chaikin Gaussian jitter using `ctx.edge_jitter` (consistent with Ellipse v3.0). |
| 3 | Douglas-Peucker over-simplifies small protrusions on Y-branch arms | Medium | ε = 0.5% bbox diagonal is conservative; verify visually at seed 42; lower to 0.3% if needed. |
| 4 | SDF smooth-min creates "bulge" artefacts where capsules meet at acute angles | Medium | Per-template `smin_k` tuned: Y-branch (k=0.15), Z-zigzag (k=0.10), Crab-radial (k=0.20), Worm-chain (k=0.08). Higher k = smoother but more bulge. |
| 5 | Eval composite swings >10 points (PO directive tolerates "tool not gate" but >10 needs explanation) | Medium | Per phase §14 Q6: eval framework adaptation work is part of phase. Lock v5.5 baseline at whatever lands, document delta from v5.4. |
| 6 | Weighted table change breaks v3.1 reproducibility | Low | `engine_v3_1b_weights()` preserved as `pub fn`. `FlatParams` could opt back via custom dispatch mode if needed for regression test (not required for v3.2 acceptance). |
| 7 | 256×256 raster + 2 generators × 12 plates × per-render cost = slowdown | Low | Each raster ~10ms (256² evals + marching squares O(N²) cells + Chaikin); 12 plates × 10ms = 120ms per world generation. Acceptable for v3.2. Caching in v4+. |
| 8 | Marching-squares contour winding order inconsistent with v3.0 polygon convention | Medium | Explicit CCW orientation check on output (compute signed area, reverse if negative). Unit test asserts CCW. |
| 9 | Per-rank weight rebalance shifts SizeRank distribution composite | Low | Distribution itself unchanged (1+2+3+4+2 plates); only shape assignment within each rank changes. Eval continentality metric (JSD from v3.1c) is shape-invariant. |
| 10 | Bbox computation for non-elliptical shapes drifts plate centres | Medium | `field_to_polygon` step 6 (centroid alignment) explicitly translates polygon to `ctx.center` post-marching. Unit test asserts. |

---

## 9 — Implementation order (TDD)

1. `raster.rs` skeleton + `field_to_polygon` API + unit tests for trivial fields (circle, square SDFs) — must produce closed CCW polygons.
2. Marching-squares 16-case lookup table + saddle resolution + tests.
3. Chaikin + Douglas-Peucker passes + tests (vertex count caps, no self-intersection on simple inputs).
4. `sdf.rs` capsule + smin functions + tests (capsule against known point distances).
5. 4 SDF templates + `SdfCapsuleChainGenerator::generate` + tests (centre containment, area-in-band, determinism).
6. `MarchingNoiseGenerator::generate` (uses `raster::field_to_polygon` with fbm + radial falloff) + tests.
7. `mod.rs` register both generators in `engine_default()` + `dispatch.rs::engine_v3_2_weights()`.
8. `flatworld::generate` flip default to v3.2 weights.
9. Integration test: render 5 seeds, verify Plate::shape_kind array contains at least one of each new kind.
10. Eval adaptation: `scripts/climate_eval.py` lat_banding update, regenerate v5.5 baseline.

Each step ships as a logical block of edits; final commit groups all changes per phase boundary (single v3.2 commit per PO choice).

---

## 10 — Approval

PO sign-off required on:
- [ ] §4.6 dispatcher weights (numeric values)
- [ ] §6 lat_banding adaptation approach (entropy-based)
- [ ] §7 acceptance criteria list

After approval → DESIGN phase produces implementation plan, BUILD begins.

---

## 11 — References

- Parent roadmap: `docs/plans/2026-05-25-phase-a-v3-roadmap.md`
- Research: `docs/research/2026-05-25-phase-a-research-3-topology-game-algos.md` §1.A2 (SDF capsule chain) + §1.A11 (marching squares)
- v3.1 predecessor: `docs/specs/2026-05-25-flatworld-v3-1-shape-dispatcher.md`
- Quílez smin reference: <https://iquilezles.org/articles/smin/>
- Marching squares reference: Lorensen + Cline 1987 (lookup table standard form)
