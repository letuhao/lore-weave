# Implementation Plan — Flatworld v3.2 SDF + Marching Squares

> **Spec:** [`../specs/2026-05-26-flatworld-v3-2-sdf-marching.md`](../specs/2026-05-26-flatworld-v3-2-sdf-marching.md) (CLARIFY approved 2026-05-26).
> **Parent roadmap:** [`2026-05-25-phase-a-v3-roadmap.md`](2026-05-25-phase-a-v3-roadmap.md) §4 Tier 1 row v3.2.
> **Predecessor implementation plan:** [`2026-05-25-flatworld-v3-1-implementation.md`](2026-05-25-flatworld-v3-1-implementation.md).
> **Size class:** XL (files=8, logic=10, side_effects=1).
> **Estimated effort:** 14-18 hours.

---

## 1 — Build order (dependency-driven TDD)

```
raster.rs (no deps)
    ├─→ sdf.rs (uses field_to_polygon)
    └─→ raster.rs::MarchingNoiseGenerator (uses field_to_polygon + fbm from existing flatworld noise)

mod.rs + dispatch.rs (register generators, add engine_v3_2_weights) ── depends on both above

flatworld.rs (flip default to v3.2 weights) ── depends on mod.rs

scripts/climate_eval.py (lat_banding v5.5 adapt) ── independent

eval/baselines/v5.5.json (regenerate) ── depends on flatworld.rs + climate_eval.py
```

5 logical BUILD steps. Tests interleave with each step.

---

## 2 — Step 1: `raster.rs` (~200 LOC + ~150 LOC tests)

### 2.1 — Module skeleton

```rust
//! Marching-squares raster→polygon pipeline shared between SDF (v3.2) and
//! noise-field (v3.2) generators. Pipeline:
//!   field(p) → 256×256 grid sample → marching squares → contour stitch →
//!   Chaikin smoothing × 2 → Douglas-Peucker simplify → centroid-align.
//! See spec §4.4.

use crate::flatworld::Polygon;
use crate::rng::Rng;

use super::{ShapeContext, ShapeGenerator, ShapeKind, ShapeResult};
```

### 2.2 — Public API

```rust
/// Public entry: rasterize a 2D field into a single closed polygon.
pub fn field_to_polygon(
    field: &dyn Fn((f32, f32)) -> f32,
    bbox: (f32, f32, f32, f32),    // (xmin, ymin, xmax, ymax)
    iso_level: f32,                // typically 0.0 for SDF; mean(noise) for noise
    grid_res: usize,               // 256 for v3.2
    chaikin_passes: usize,         // 2 for v3.2
    simplify_eps_frac: f32,        // 0.005
    rng: &mut Rng,                 // saddle tiebreak + jitter
    target_center: (f32, f32),     // for centroid alignment (step 6)
) -> Polygon;
```

### 2.3 — Internal pipeline (private helpers)

```rust
struct Grid {                                          // step 1
    res: usize,
    bbox: (f32, f32, f32, f32),
    samples: Vec<f32>,                                 // res × res, row-major
}

fn sample_grid(field: &dyn Fn((f32,f32)) -> f32, bbox: ..., res: usize) -> Grid;

fn marching_squares(g: &Grid, iso: f32, rng: &mut Rng) -> Vec<Segment>;  // step 2
//   16-case lookup table; saddle ambiguity resolved by cell-centre sample.

struct Segment { a: (f32,f32), b: (f32,f32) }

fn stitch_contours(segments: Vec<Segment>) -> Vec<Polygon>;              // step 3
//   Hash endpoints to ~tile-edge resolution; walk segments to form rings.

fn largest_by_area(rings: Vec<Polygon>) -> Polygon;                      // step 3 (largest)

fn chaikin(poly: &Polygon, passes: usize) -> Polygon;                    // step 4

fn douglas_peucker(poly: &Polygon, eps: f32) -> Polygon;                 // step 5

fn align_centroid(mut poly: Polygon, target: (f32,f32)) -> Polygon;      // step 6

fn ensure_ccw(mut poly: Polygon) -> Polygon;                             // final orientation
```

### 2.4 — Marching squares lookup table

16 cases (binary mask of corner signs):
```
case 0  = 0000 → empty
case 1  = 0001 → segment from left edge to bottom edge
case 2  = 0010 → bottom to right
case 3  = 0011 → left to right
case 4  = 0100 → top to right
case 5  = 0101 → SADDLE — disambiguate by cell-centre sign
case 6  = 0110 → top to bottom
case 7  = 0111 → top to left
case 8  = 1000 → left to top
case 9  = 1001 → bottom to top
case 10 = 1010 → SADDLE — disambiguate by cell-centre sign
case 11 = 1011 → right to top
case 12 = 1100 → left to right (flipped)
case 13 = 1101 → bottom to right (flipped)
case 14 = 1110 → bottom to left
case 15 = 1111 → empty
```

Saddle resolution: sample `field(cell_center)` and compare sign:
- Sign matches "outside" corners → segments connect to keep "inside" separate (4 + B + R + L topology variant 1)
- Sign matches "inside" corners → segments connect to merge "inside" (variant 2)
- 1 `rng.next_f32()` consumed per saddle only when sample == iso exactly (tiebreak).

Linear interpolation along edges:
```rust
fn lerp_zero(a: f32, b: f32) -> f32 { a / (a - b) }   // returns t ∈ [0,1] where iso crosses
```

### 2.5 — Tests for `raster.rs` (≥6)

```rust
#[test] fn unit_circle_sdf_renders_closed_ccw_polygon() { /* field = |p|-r, expect ~256 vertices ring */ }
#[test] fn rotated_square_sdf_renders_4_corners_approximately() { /* max(|x|,|y|)-r */ }
#[test] fn off_center_circle_centroid_aligns_to_target() { /* assert |centroid - target| < eps */ }
#[test] fn chaikin_doubles_vertex_count_per_pass_then_caps_at_512() { /* check len growth */ }
#[test] fn dp_simplify_reduces_collinear_run_to_endpoints() { /* 100-vertex straight edge → 2 */ }
#[test] fn ccw_orientation_enforced_even_for_clockwise_input() { /* signed area > 0 */ }
#[test] fn determinism_field_to_polygon_bit_identical_two_runs() { /* clone RNG, run twice, hash polygons */ }
```

### 2.6 — `MarchingNoiseGenerator` (extends `raster.rs`)

```rust
pub struct MarchingNoiseGenerator;
impl ShapeGenerator for MarchingNoiseGenerator {
    fn kind(&self) -> ShapeKind { ShapeKind::MarchingNoise }
    fn generate(&self, ctx: &ShapeContext, _rng: &mut Rng) -> ShapeResult {
        // Internal RNG via Rng::for_stage(ctx.seed as u64, b"marching-noise")
        // (NOT caller rng — keeps caller's stream stable when noise alternates with other gens)
        let mut internal = Rng::for_stage(ctx.seed as u64, b"marching-noise");
        let (cx, cy) = ctx.center;
        let envelope = ctx.envelope.0;
        let salt = ctx.plate_salt;

        let field = move |p: (f32, f32)| -> f32 {
            // 3-octave fbm centred so threshold = 0; radial falloff guarantees closed inside region.
            let n = fbm3_at(p, salt, /*freq*/ 1.5 / envelope);
            let r = ((p.0 - cx).hypot(p.1 - cy)) / envelope;
            n - r       // negative inside (r small, n large), positive outside
        };
        let bbox = (cx - envelope, cy - envelope, cx + envelope, cy + envelope);
        let poly = field_to_polygon(&field, bbox, 0.0, 256, 2, 0.005, &mut internal, ctx.center);
        ShapeResult::single_kind(vec![poly], ShapeKind::MarchingNoise)
    }
}

fn fbm3_at(p: (f32,f32), salt: u32, freq: f32) -> f32 {
    // Reuse existing flatworld fbm OR inline 3-octave Perlin/value noise.
    // Choose existing — check flatworld::fbm_octaves signature.
}
```

**Resolution check (during BUILD)**: does `flatworld::fbm_octaves` accept `(x, y, salt)`? If yes, reuse. If not, inline a 3-octave fbm wrapper here (~30 LOC).

### 2.7 — Tests for `MarchingNoiseGenerator` (3)

```rust
#[test] fn marching_noise_returns_single_component() { /* result.polygons.len() == 1 */ }
#[test] fn marching_noise_polygon_contains_center() { /* center inside polygon */ }
#[test] fn marching_noise_deterministic_same_seed() { /* hash equal across 2 runs */ }
```

---

## 3 — Step 2: `sdf.rs` (~250 LOC + ~150 LOC tests)

### 3.1 — Math primitives

```rust
fn sdf_capsule(p: (f32,f32), a: (f32,f32), b: (f32,f32), r: f32) -> f32 {
    let ba = (b.0 - a.0, b.1 - a.1);
    let pa = (p.0 - a.0, p.1 - a.1);
    let dot_ba = ba.0 * ba.0 + ba.1 * ba.1;
    let dot_pa_ba = pa.0 * ba.0 + pa.1 * ba.1;
    let t = (dot_pa_ba / dot_ba).clamp(0.0, 1.0);
    let proj = (a.0 + t * ba.0, a.1 + t * ba.1);
    let d = (p.0 - proj.0).hypot(p.1 - proj.1);
    d - r
}

fn smin_poly(d1: f32, d2: f32, k: f32) -> f32 {
    let h = (0.5 + 0.5 * (d2 - d1) / k).clamp(0.0, 1.0);
    d2 * (1.0 - h) + d1 * h - k * h * (1.0 - h)
}
```

### 3.2 — Templates

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum CapsuleTemplate {
    YBranch,
    ZZigzag,
    CrabRadial,
    WormChain,
}

impl CapsuleTemplate {
    const ALL: [CapsuleTemplate; 4] = [/* declaration order */];

    /// Joints in unit space (rescaled by per-rank radius_band at generate-time).
    fn joints(self) -> Vec<(f32, f32)> {
        match self {
            // Y-branch: centre at (0,0), 3 arms at 90°/210°/330°
            CapsuleTemplate::YBranch => vec![(0.0, 0.0), (0.0, 0.9), (-0.78, -0.45), (0.78, -0.45)],
            // Z-zigzag: 4 joints W-E with up/down alternation
            CapsuleTemplate::ZZigzag => vec![(-0.9, 0.3), (-0.3, -0.3), (0.3, 0.3), (0.9, -0.3)],
            // Crab-radial: centre + 5 arms at 72° spacing
            CapsuleTemplate::CrabRadial => vec![
                (0.0, 0.0),
                (0.0, 0.85), (0.81, 0.26), (0.50, -0.69), (-0.50, -0.69), (-0.81, 0.26),
            ],
            // Worm-chain: 7 joints in slight curve
            CapsuleTemplate::WormChain => vec![
                (-1.0, 0.1), (-0.65, -0.1), (-0.3, 0.1), (0.0, -0.05), (0.3, 0.1), (0.65, -0.1), (1.0, 0.1),
            ],
        }
    }

    /// Edges (capsule = segment between two joint indices).
    fn edges(self) -> Vec<(usize, usize)> {
        match self {
            CapsuleTemplate::YBranch     => vec![(0,1), (0,2), (0,3)],
            CapsuleTemplate::ZZigzag     => vec![(0,1), (1,2), (2,3)],
            CapsuleTemplate::CrabRadial  => vec![(0,1), (0,2), (0,3), (0,4), (0,5)],
            CapsuleTemplate::WormChain   => vec![(0,1), (1,2), (2,3), (3,4), (4,5), (5,6)],
        }
    }

    /// Per-capsule radii (multiplied by per-rank capsule_radius_band at generate-time).
    fn radii(self) -> Vec<f32> {
        match self {
            CapsuleTemplate::YBranch     => vec![0.30, 0.25, 0.25],
            CapsuleTemplate::ZZigzag     => vec![0.20, 0.20, 0.20],
            CapsuleTemplate::CrabRadial  => vec![0.22, 0.20, 0.20, 0.20, 0.22],
            CapsuleTemplate::WormChain   => vec![0.18, 0.18, 0.18, 0.18, 0.18, 0.18],
        }
    }

    /// Smoothing strength — tuned per spec §8 risk #4.
    fn smin_k(self) -> f32 {
        match self {
            CapsuleTemplate::YBranch    => 0.15,
            CapsuleTemplate::ZZigzag    => 0.10,
            CapsuleTemplate::CrabRadial => 0.20,
            CapsuleTemplate::WormChain  => 0.08,
        }
    }
}
```

### 3.3 — Generator

```rust
pub struct SdfCapsuleChainGenerator;

impl ShapeGenerator for SdfCapsuleChainGenerator {
    fn kind(&self) -> ShapeKind { ShapeKind::SdfCapsuleChain }

    fn generate(&self, ctx: &ShapeContext, _caller_rng: &mut Rng) -> ShapeResult {
        // Internal RNG (won't perturb caller stream).
        let mut rng = Rng::for_stage(ctx.seed as u64, b"sdf-capsule-chain");

        // RNG order — frozen:
        //   1. template index (u32 → mod 4)
        //   2. global rotation angle (f32 × TAU)
        //   3. per-joint micro-jitter
        let template = CapsuleTemplate::ALL[(rng.next_u32() % 4) as usize];
        let rotation = rng.next_f32() * std::f32::consts::TAU;

        // Per-rank scale of unit-space joints + radii.
        let (rmin, rmax) = ctx.size_rank.radius_band();
        let scale = ctx.envelope.0 * (rmin + (rmax - rmin) * 0.5);   // mid-band; spec keeps simple
        let radius_mul = scale * 0.8;       // capsule radii: 80% of scale (tunable)

        // Build capsules: joint coords in world-space, post-rotation, post-translate.
        let joints_unit = template.joints();
        let edges = template.edges();
        let radii = template.radii();
        let cos_r = rotation.cos();
        let sin_r = rotation.sin();
        let mut joints_world: Vec<(f32, f32)> = joints_unit.iter().map(|(jx, jy)| {
            // micro-jitter: ±0.05 unit-space
            let dx = (rng.next_f32() - 0.5) * 0.1;
            let dy = (rng.next_f32() - 0.5) * 0.1;
            let jx_j = jx + dx;
            let jy_j = jy + dy;
            let rx = jx_j * cos_r - jy_j * sin_r;
            let ry = jx_j * sin_r + jy_j * cos_r;
            (ctx.center.0 + rx * scale, ctx.center.1 + ry * scale)
        }).collect();
        let radii_world: Vec<f32> = radii.iter().map(|r| r * radius_mul).collect();

        let smin_k = template.smin_k() * scale;     // smin_k scales with shape

        // Build SDF closure.
        let capsules: Vec<((f32,f32),(f32,f32),f32)> = edges.iter().enumerate().map(|(i, &(a, b))| {
            (joints_world[a], joints_world[b], radii_world[i])
        }).collect();
        let field = move |p: (f32, f32)| -> f32 {
            capsules.iter().fold(1e30f32, |acc, &(a, b, r)| smin_poly(acc, sdf_capsule(p, a, b, r), smin_k))
        };

        // BBox sized to envelope (matches MarchingNoise envelope discipline).
        let envelope = ctx.envelope.0;
        let bbox = (ctx.center.0 - envelope, ctx.center.1 - envelope,
                    ctx.center.0 + envelope, ctx.center.1 + envelope);

        let poly = field_to_polygon(&field, bbox, 0.0, 256, 2, 0.005, &mut rng, ctx.center);
        ShapeResult::single_kind(vec![poly], ShapeKind::SdfCapsuleChain)
    }
}
```

### 3.4 — Tests for `sdf.rs` (≥4)

```rust
#[test] fn capsule_sdf_zero_on_endpoint_minus_radius() { /* sdf_capsule(a, a, b, r) == -r */ }
#[test] fn capsule_sdf_radius_at_perpendicular_distance() { /* known point check */ }
#[test] fn smin_poly_matches_min_at_extremes() { /* smin(0, 10, 0.1) ≈ 0; smin(0, 0, 0.1) ≈ -0.025 */ }
#[test] fn all_four_templates_produce_centre_containing_polygon() {
    // For each template: generate plate, assert center inside polygon, no self-intersection.
}
#[test] fn sdf_generator_determinism_same_seed() { /* clone caller RNG, run twice */ }
#[test] fn sdf_generator_does_not_perturb_caller_rng() { /* caller RNG hash identical pre/post */ }
```

---

## 4 — Step 3: Wire-up in `mod.rs` + `dispatch.rs`

### 4.1 — `mod.rs` edits

```rust
pub mod csg;
pub mod dispatch;
pub mod ellipse;
pub mod polar;
pub mod raster;     // NEW
pub mod sdf;        // NEW
pub mod spine;

pub use csg::{BooleanGenerator, BooleanTemplate};
pub use dispatch::{DispatchMode, ShapeRegistry, engine_v3_1b_weights, engine_v3_2_weights};  // NEW: engine_v3_2_weights
pub use ellipse::EllipseGenerator;
pub use polar::{PolarGenerator, PolarTemplate};
pub use raster::MarchingNoiseGenerator;   // NEW
pub use sdf::{SdfCapsuleChainGenerator, CapsuleTemplate};   // NEW
pub use spine::{BezierSpineGenerator, BezierTemplate};
```

### 4.2 — `ShapeRegistry::engine_default()` extension

```rust
pub fn engine_default() -> Self {
    let mut r = Self::empty();
    r.register(Box::new(super::EllipseGenerator));
    r.register(Box::new(super::BezierSpineGenerator));
    r.register(Box::new(super::PolarGenerator));
    r.register(Box::new(super::BooleanGenerator));
    // v3.2 additions:
    r.register(Box::new(super::SdfCapsuleChainGenerator));
    r.register(Box::new(super::MarchingNoiseGenerator));
    r
}
```

### 4.3 — `engine_v3_2_weights()` (numeric values approved in CLARIFY)

```rust
/// **v3.2** per-rank weight table for `DispatchMode::Weighted`. Extends
/// v3.1b with `SdfCapsuleChain` + `MarchingNoise`. Small/Micro exclude
/// both (capsule chain degenerates on small plates; 256² raster wastes
/// resolution on micro-sized polygons). See spec §4.6.
pub fn engine_v3_2_weights() -> BTreeMap<SizeRank, Vec<(ShapeKind, f32)>> {
    let mut table = BTreeMap::new();
    table.insert(SizeRank::Giant, vec![
        (ShapeKind::Ellipse, 0.30),
        (ShapeKind::BezierSpine, 0.20),
        (ShapeKind::Polar, 0.10),
        (ShapeKind::Boolean, 0.10),
        (ShapeKind::SdfCapsuleChain, 0.20),
        (ShapeKind::MarchingNoise, 0.10),
    ]);
    table.insert(SizeRank::Large, vec![
        (ShapeKind::Ellipse, 0.25),
        (ShapeKind::BezierSpine, 0.25),
        (ShapeKind::Polar, 0.10),
        (ShapeKind::Boolean, 0.15),
        (ShapeKind::SdfCapsuleChain, 0.15),
        (ShapeKind::MarchingNoise, 0.10),
    ]);
    table.insert(SizeRank::Medium, vec![
        (ShapeKind::Ellipse, 0.30),
        (ShapeKind::BezierSpine, 0.25),
        (ShapeKind::Polar, 0.20),
        (ShapeKind::Boolean, 0.10),
        (ShapeKind::SdfCapsuleChain, 0.10),
        (ShapeKind::MarchingNoise, 0.05),
    ]);
    table.insert(SizeRank::Small, vec![
        (ShapeKind::Ellipse, 0.40),
        (ShapeKind::BezierSpine, 0.20),
        (ShapeKind::Polar, 0.25),
        (ShapeKind::Boolean, 0.05),
        (ShapeKind::SdfCapsuleChain, 0.10),
        (ShapeKind::MarchingNoise, 0.00),
    ]);
    table.insert(SizeRank::Micro, vec![
        (ShapeKind::Ellipse, 0.55),
        (ShapeKind::BezierSpine, 0.10),
        (ShapeKind::Polar, 0.30),
        (ShapeKind::Boolean, 0.05),
        (ShapeKind::SdfCapsuleChain, 0.00),
        (ShapeKind::MarchingNoise, 0.00),
    ]);
    table
}
```

### 4.4 — `flatworld.rs` default-flip

Find the line:
```rust
.unwrap_or_else(|| DispatchMode::Weighted(engine_v3_1b_weights()));
```
Change to:
```rust
.unwrap_or_else(|| DispatchMode::Weighted(engine_v3_2_weights()));
```
+ update import: `use crate::shape::{..., dispatch::engine_v3_2_weights};`.

### 4.5 — Tests for dispatcher (3)

```rust
#[test] fn engine_v3_2_weights_each_rank_sums_to_one() { /* ±0.001 tolerance */ }
#[test] fn engine_v3_2_weights_micro_excludes_sdf_and_marching() { /* assert weight == 0 */ }
#[test] fn engine_default_registers_six_kinds_in_v3_2() {
    let r = ShapeRegistry::engine_default();
    assert_eq!(r.kinds().len(), 6);
    assert!(r.get(ShapeKind::SdfCapsuleChain).is_some());
    assert!(r.get(ShapeKind::MarchingNoise).is_some());
}
```

---

## 5 — Step 4: Integration test in `flatworld.rs`

```rust
#[test]
fn v3_2_render_uses_new_kinds_at_seed_42() {
    let world = generate_flat_world(42, FlatParams::default());
    let kinds: Vec<ShapeKind> = world.plates.iter().map(|p| p.shape_kind).collect();
    assert!(kinds.iter().any(|k| matches!(k, ShapeKind::SdfCapsuleChain | ShapeKind::MarchingNoise)),
            "v3.2 default weights expected at least one SDF/Marching plate at seed 42; got {:?}", kinds);
}
```

---

## 6 — Step 5: Eval adaptation (`scripts/climate_eval.py`)

Existing `lat_banding` (line ~473-525 ecotone-aware per-pixel logic) stays. We add **per-plate shape-aware bonus** that PR-AT NEW shape kinds (Y-branch, Crab-radial) which legitimately span 3+ lat bands by design.

**Implementation: skip lat_banding code change in v3.2 BUILD.** Just regenerate `v5.5.json` baseline at whatever the existing metric reports. Document the delta from `v5.4.json` in SESSION_PATCH:
- If composite drops <5: accept as-is (PO directive: tool not gate).
- If composite drops 5-10: log as expected variance, still ship.
- If composite drops >10: investigate one outlier seed; either bug or genuine geometric reality of new shapes (still ship per PO directive, document why).

**Deferred** to v3.3 or v4.5 calibration: actual lat_banding entropy rewrite. Keeps v3.2 scope tight.

Update SESSION_PATCH after baseline lock with the actual deltas observed.

---

## 7 — Step 6: Baseline + render artifacts

```bash
# Render 5 seeds (NEW seeds per PO):
for seed in 13 42 108 256 512; do
    cargo run --release --bin world-gen -- --seed $seed --output eval/compare-v3-2/
done

# Regenerate baseline:
python scripts/climate_eval.py --output eval/baselines/v5.5.json
python scripts/climate_eval.py --baseline eval/baselines/v5.4.json   # diff vs v3.1c
```

Artifacts under `eval/compare-v3-2/`:
- `plates_s13.png`, `biome_s13.png`
- `plates_s42.png`, `biome_s42.png`
- `plates_s108.png`, `biome_s108.png`
- `plates_s256.png`, `biome_s256.png`
- `plates_s512.png`, `biome_s512.png`

**Note**: `--bin world-gen` exact name TBD during BUILD (verify in `crates/world-gen/Cargo.toml [[bin]]` section first).

---

## 8 — Estimated LOC budget

| File | New LOC | Test LOC | Total |
|------|--------:|---------:|------:|
| `raster.rs` | 200 | 150 | 350 |
| `sdf.rs` | 250 | 150 | 400 |
| `mod.rs` | +5 | 0 | 5 |
| `dispatch.rs` | +60 | +30 | 90 |
| `flatworld.rs` | +5 | +20 | 25 |
| **subtotal Rust** | **520** | **350** | **870** |
| `scripts/climate_eval.py` | 0 | 0 | 0 (v3.2 skips rewrite) |
| `eval/baselines/v5.5.json` | (regen) | 0 | (regen) |

Within roadmap's "~450 LOC" estimate (we're slightly over; test LOC is the variance).

---

## 9 — Verification checkpoints (per BUILD step)

| After | Command | Pass criteria |
|-------|---------|---------------|
| Step 1 (raster) | `cargo test --lib -p world-gen shape::raster` | ≥9 tests green (6 raster + 3 marching-noise) |
| Step 2 (sdf) | `cargo test --lib -p world-gen shape::sdf` | ≥6 tests green |
| Step 3 (wire-up) | `cargo test --lib -p world-gen shape::dispatch` | All dispatch tests + 3 new |
| Step 4 (integration) | `cargo test --lib -p world-gen` | All 260+ tests green |
| Step 4 (clippy) | `cargo clippy --all-targets --all-features -- -D warnings` | ≤3 pre-existing warnings |
| Step 6 (render) | render outputs exist + visually distinct from v3.1 baseline | manual PO review |

---

## 10 — Risks during BUILD (additions to spec §8)

| # | Risk | Mitigation |
|---|------|------------|
| 11 | `fbm_octaves` signature mismatch — flatworld may not expose what `MarchingNoise` needs | Inspect `flatworld.rs` first; if API too narrow, inline ~30 LOC fbm helper in `raster.rs`. |
| 12 | Marching-squares Vec<Polygon> stitching uses HashMap which has non-deterministic iteration | Use `BTreeMap<(i32,i32), Vec<usize>>` keyed by quantised endpoint (e.g. round to 4 decimal places); guaranteed sort order. |
| 13 | Per-rank scale of SDF templates produces too-small or too-large shapes for Giant vs Medium | Validate visually after step 2; tune `scale` factor in `sdf.rs::generate` (currently mid-band default). |
| 14 | f32 precision loss at 256² grid corners → degenerate cells | All `lerp_zero` callers gate `a != b` (with `abs(a - b) > 1e-6` epsilon); fallback returns 0.5. |
| 15 | Composite eval drops >10 — PO directive tolerates but visual review may flag specific seeds | Plan §6 fallback documented; if PO flags, drop into review-impl skill rather than blocking v3.2. |

---

## 11 — Deferred from v3.2 (tracked in DEFERRED.md)

After BUILD, append to `docs/deferred/DEFERRED.md`:
- **D-2026-05-26-1**: lat_banding entropy rewrite (target: v4.5 calibration phase).
- **D-2026-05-26-2**: Adaptive raster resolution (currently fixed 256×256; high-res Giant + low-res Micro could speed up generation). Target: v4+ perf phase.
- **D-2026-05-26-3**: Multi-component output from marching squares (true archipelagos). Target: v3.3 per roadmap.
- **D-2026-05-26-4**: Hole-in-polygon (e.g., Caspian-Sea-style inland water from Boolean ring + Marching). Target: v3.3 or v4.

---

## 12 — Out-of-scope for this plan (deferred to RETRO)

ContextHub `add_lesson` entries to write at RETRO:
- Marching-squares saddle ambiguity resolution choice (sample-centre vs interp-centre) and reasoning.
- Why internal RNG for SDF/Marching (preserves caller stream invariance).
- Why the per-rank weight table excludes Slime/Stamp (not impl yet, redistributed to Ellipse).
