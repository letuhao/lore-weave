# Spec — Flatworld v3.1 Shape Dispatcher + 3 New Algorithms

> **Status:** DRAFT — kickoff 2026-05-25.
> **Parent roadmap:** [`../plans/2026-05-25-phase-a-v3-roadmap.md`](../plans/2026-05-25-phase-a-v3-roadmap.md).
> **Implementation plan:** [`../plans/2026-05-25-flatworld-v3-1-implementation.md`](../plans/2026-05-25-flatworld-v3-1-implementation.md).
> **Mode:** v2.2 human-in-loop (PO opted out of AMAW). Branch `geo-generator-amaw`.
> **Scope:** v3.1a (foundation) + v3.1b (3 algos), shipped as 2 separate commits with PO visual review between.

---

## 1 — Problem

Roadmap §4 v3.1 originally proposed "implement 3 algos with FlatParams::force_shape stub, dispatcher in v4.0". PO counter-proposal in CLARIFY (Session 60): **dispatcher first**. Building algorithms against a stable trait is cleaner than back-fitting them. Locked: **hybrid** — minimal dispatcher in v3.1a, then 3 algos in v3.1b that auto-register.

This spec covers BOTH sub-phases. Commits are split so v3.1a can be visually verified byte-identical before v3.1b changes any rendered geometry.

---

## 2 — Goals

### v3.1a — Foundation (byte-identical render)
- NEW `crates/world-gen/src/shape/` module hosting trait + enum + registry.
- `ShapeGenerator` trait: `generate(&ShapeContext, &mut Rng) -> Vec<Polygon>`.
- `ShapeKind` enum with all 8 future variants reserved (only `Ellipse` impl in v3.1a).
- `ShapeContext` struct: depth, center, envelope, size_rank, seed, plate_salt, parent_path, world_theme, edge_jitter, vertex_count_range.
- `ShapeRegistry` keyed by `ShapeKind`; `engine_default()` registers `EllipseGenerator`.
- `DispatchMode::{Random, Fixed}` only (other 5 modes deferred to v4.0).
- Extract v3.0 plate-ellipse vertex code into `EllipseGenerator::generate` with **bit-exact** RNG order preservation.
- Schema additive: `Plate::shape_kind: ShapeKind` (defaults to `Ellipse`).
- `flatworld::generate` routes plate generation through dispatcher; default `DispatchMode::Fixed(ShapeKind::Ellipse)` so render is byte-identical to v3.0.

### v3.1b — 3 algorithms + Weighted dispatch
- NEW algorithms: `BezierSpine` (3 templates), `Polar` (4 templates), `Boolean` (4 templates).
- NEW crate dep: `geo-clipper` (Boolean CSG ops).
- Templates picked deterministically from `ctx.seed` hash.
- NEW `DispatchMode::Weighted(HashMap<SizeRank, HashMap<ShapeKind, f32>>)` with per-rank table.
- Flip `flatworld::generate` default from `Fixed(Ellipse)` to `Weighted(v3_1b_weights())`.
- Eval framework adaptation (per PO directive §14 Q6: tool not gate): `lat_banding` measures per-component area distribution instead of per-plate centroid count.
- Visual: at seeds 7/13/42, at least 1 plate per render shows non-ellipse shape.

---

## 3 — Non-goals

- Multi-component plates (deferred to v3.3 marching-squares pipeline).
- SDF capsule chain, slime/Physarum, stamps (v3.2+).
- LLM-driven dispatch (v4.3).
- ByContext / Manual / Layered / PerDepth dispatch modes (v4.0).
- Zone / sub-zone templating (v4.1 / v4.2).
- Hole-in-polygon support (deferred; Boolean Ring template stores outer ring only and documents the gap).
- Changes to climate / hydrology / render code beyond what v3.1b eval-adapt requires.

---

## 4 — Design

### 4.1 — Module layout

```
crates/world-gen/src/shape/
├── mod.rs           # ShapeKind, ShapeContext, ShapeGenerator trait, re-exports
├── dispatch.rs      # ShapeRegistry, DispatchMode (Random/Fixed in v3.1a; +Weighted in v3.1b)
├── ellipse.rs       # EllipseGenerator — v3.0 algorithm extracted (v3.1a)
├── spine.rs         # BezierSpineGenerator + templates (v3.1b)
├── polar.rs         # PolarGenerator + superformula templates (v3.1b)
└── csg.rs           # BooleanGenerator + geo-clipper wrapper (v3.1b)
```

`lib.rs` adds `pub mod shape;`.

### 4.2 — Core types (v3.1a)

```rust
// shape/mod.rs
pub type Polygon = Vec<(f32, f32)>;  // re-exports flatworld::Polygon alias

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum ShapeKind {
    Ellipse,           // v3.0 default — only impl in v3.1a
    BezierSpine,       // v3.1b
    Polar,             // v3.1b
    Boolean,           // v3.1b
    SdfCapsuleChain,   // v3.2 reserved
    MarchingNoise,     // v3.2/v3.3 reserved
    Slime,             // v3.4 reserved
    Stamp,             // v3.5 reserved
}

#[derive(Debug, Clone)]
pub struct ShapeContext {
    /// 0 = plate, 1 = zone (v4.1), 2 = subzone (v4.2)
    pub depth: u32,
    /// World-space centre the generated polygon should be anchored at.
    pub center: (f32, f32),
    /// Maximum (x, y) extent the polygon should occupy from its centre.
    /// For plates: `(pitch, pitch)`. For zones (v4.1+): parent plate bbox.
    pub envelope: (f32, f32),
    /// Drives per-rank parameter bands (radius, aspect, etc.).
    pub size_rank: crate::flatworld::SizeRank,
    /// Per-shape RNG seed (matches `Plate::shape_seed`). Generators must
    /// derive their own internal RNG state from this when needed, NOT from
    /// the world seed.
    pub seed: u32,
    /// Salt for fbm noise lookups; preserved from v3.0 `plate_salt` derivation
    /// so Ellipse fbm output is bit-identical post-extraction.
    pub plate_salt: u32,
    /// Hierarchy path: `[]` for plates, `[plate_id]` for zones, `[plate_id, zone_id]` for subzones.
    pub parent_path: Vec<usize>,
    /// Optional theme hint for LLM dispatch (v4.3+); ignored in v3.1.
    pub world_theme: Option<&'static str>,
    /// Per-vertex jitter magnitude (0..1).
    pub edge_jitter: f32,
    /// Inclusive vertex-count range; generators clamp to `[3, range.1]`.
    pub vertex_count_range: (usize, usize),
}

pub trait ShapeGenerator: Send + Sync {
    fn kind(&self) -> ShapeKind;
    /// Generate 1+ closed polygon rings. Multi-component (`len > 1`) is reserved
    /// for v3.3 marching-squares; v3.1 generators MUST return `len == 1`.
    fn generate(&self, ctx: &ShapeContext, rng: &mut crate::rng::Rng) -> Vec<Polygon>;
}
```

### 4.3 — Registry + dispatch (v3.1a)

```rust
// shape/dispatch.rs
pub struct ShapeRegistry {
    generators: std::collections::BTreeMap<ShapeKind, Box<dyn ShapeGenerator>>,
}

impl ShapeRegistry {
    pub fn empty() -> Self { Self { generators: BTreeMap::new() } }

    /// v3.1a: registers `EllipseGenerator` only. v3.1b auto-extends to 4.
    pub fn engine_default() -> Self {
        let mut r = Self::empty();
        r.register(Box::new(EllipseGenerator));
        // v3.1b will add: BezierSpineGenerator, PolarGenerator, BooleanGenerator
        r
    }

    pub fn register(&mut self, gen: Box<dyn ShapeGenerator>) {
        self.generators.insert(gen.kind(), gen);
    }

    pub fn get(&self, kind: ShapeKind) -> Option<&dyn ShapeGenerator> {
        self.generators.get(&kind).map(|b| b.as_ref())
    }

    pub fn kinds(&self) -> Vec<ShapeKind> {
        self.generators.keys().copied().collect()  // BTreeMap → deterministic order
    }
}

#[derive(Debug, Clone)]
pub enum DispatchMode {
    /// Uniform random over registered kinds. With a single registered kind,
    /// returns it WITHOUT consuming any RNG — guarantees byte-identical render
    /// across `engine_default()` upgrades (Ellipse-only → 4 kinds).
    Random,
    /// Force one kind. No RNG consumption. Used for tests, debug, byte-identical
    /// fallback during v3.1a → v3.1b transition.
    Fixed(ShapeKind),
    // v3.1b will add:
    //   Weighted(HashMap<SizeRank, HashMap<ShapeKind, f32>>),
    // v4.0 will add: ByContext, Llm, Manual, Layered, PerDepth.
}

impl DispatchMode {
    pub fn select(&self, registry: &ShapeRegistry, _ctx: &ShapeContext, rng: &mut crate::rng::Rng) -> ShapeKind {
        match self {
            DispatchMode::Random => {
                let kinds = registry.kinds();
                debug_assert!(!kinds.is_empty(), "ShapeRegistry must register ≥1 generator");
                if kinds.len() == 1 {
                    return kinds[0];   // BYTE-IDENTICAL: no RNG consumption
                }
                kinds[(rng.next_u32() as usize) % kinds.len()]
            }
            DispatchMode::Fixed(k) => *k,
        }
    }
}
```

### 4.4 — EllipseGenerator extraction (v3.1a)

The closure body in `flatworld::generate` (currently lines 488–565) moves into `EllipseGenerator::generate`. **RNG consumption order MUST exactly match v3.0:** radius, aspect, theta_rot, nv, phase, then per-vertex (wobble, residual). If the order shifts by even one `next_f32()`, downstream plates (motion → velocity, zones, subzones) drift and break byte-identical.

```rust
// shape/ellipse.rs
pub struct EllipseGenerator;

impl ShapeGenerator for EllipseGenerator {
    fn kind(&self) -> ShapeKind { ShapeKind::Ellipse }
    fn generate(&self, ctx: &ShapeContext, rng: &mut Rng) -> Vec<Polygon> {
        // pitch comes from envelope; for plates envelope.0 == envelope.1 == pitch
        let pitch = ctx.envelope.0;
        let (rmin, rmax) = ctx.size_rank.radius_band();
        let radius = pitch * lerp(rmin, rmax, rng.next_f32());
        let (amin, amax) = ctx.size_rank.aspect_band();
        let aspect = lerp(amin, amax, rng.next_f32());
        let rx = radius * aspect.sqrt();
        let ry = radius / aspect.sqrt();
        let theta_rot = rng.next_f32() * TAU;
        let max_v = ctx.vertex_count_range.1.max(ctx.vertex_count_range.0);
        let nv = ctx.vertex_count_range.0
            + (rng.next_f32() * (max_v - ctx.vertex_count_range.0 + 1) as f32) as usize;
        let nv = nv.clamp(3, max_v.max(3));
        let phase = rng.next_f32() * TAU;
        let cos_t = theta_rot.cos();
        let sin_t = theta_rot.sin();
        let target_mean = 1.0 - ctx.edge_jitter * 0.5;
        let residual_mean = 1.0 - ctx.edge_jitter * JITTER_RESIDUAL_SCALE * 0.5;
        let shrink_bias = target_mean / residual_mean.max(1e-3);
        let primary: Polygon = (0..nv).map(|k| {
            let base = phase + TAU * (k as f32) / nv as f32;
            let wobble = (rng.next_f32() - 0.5) * (TAU / nv as f32) * 0.6;
            let ang = base + wobble;
            let nx = ang.cos() * EDGE_NOISE_FREQ;
            let ny = ang.sin() * EDGE_NOISE_FREQ;
            let noise = crate::noise::fbm(nx, ny, ctx.plate_salt, EDGE_NOISE_OCTAVES);
            let residual = 1.0 - ctx.edge_jitter * JITTER_RESIDUAL_SCALE * rng.next_f32();
            let radial_factor = shrink_bias * residual * (1.0 + EDGE_NOISE_AMP * noise);
            let lx = rx * radial_factor * ang.cos();
            let ly = ry * radial_factor * ang.sin();
            (ctx.center.0 + lx * cos_t - ly * sin_t,
             ctx.center.1 + lx * sin_t + ly * cos_t)
        }).collect();
        vec![primary]
    }
}
```

`EDGE_NOISE_*` constants + `JITTER_RESIDUAL_SCALE` + `lerp` move into the `shape` module (or stay in flatworld and become `pub(crate)`).

### 4.5 — flatworld::generate integration (v3.1a)

The plate loop becomes:

```rust
let registry = ShapeRegistry::engine_default();
// v3.1a default = Fixed(Ellipse) to guarantee byte-identical with v3.0.
// v3.1b will switch to DispatchMode::Weighted(engine_v3_1b_weights()).
let dispatcher = DispatchMode::Fixed(ShapeKind::Ellipse);

let plates = centers.into_iter().enumerate().map(|(id, (cx, cy))| {
    let rank = size_ranks.get(id).copied().unwrap_or(SizeRank::Medium);
    let plate_salt = (params.seed as u32).wrapping_mul(0x9E37_79B9) ^ (id as u32);
    let shape_seed = (params.seed as u32).wrapping_mul(0x27D4_EB2F)
                   ^ (id as u32).wrapping_mul(0x1656_67B1);

    let ctx = ShapeContext {
        depth: 0,
        center: (cx, cy),
        envelope: (pitch, pitch),
        size_rank: rank,
        seed: shape_seed,
        plate_salt,
        parent_path: Vec::new(),
        world_theme: None,
        edge_jitter: params.edge_jitter,
        vertex_count_range: (params.min_vertices, max_v),
    };

    let kind = dispatcher.select(&registry, &ctx, &mut rng);  // Fixed: no rng consumption
    let components = registry.get(kind).expect("registered").generate(&ctx, &mut rng);

    let speed = mrng.next_f32() * params.max_speed;
    let vdir  = mrng.next_f32() * TAU;
    let velocity = (speed * vdir.cos(), speed * vdir.sin());

    let zone_warp_salt =
        (params.seed as u32).wrapping_mul(0x85EB_CA6B) ^ (id as u32).wrapping_mul(0xC2B2_AE35);

    let mut plate = Plate {
        id, center: (cx, cy),
        components,
        velocity,
        zone_sites: Vec::new(),
        subzone_sites: Vec::new(),
        zone_warp_salt,
        size_rank: rank,
        shape_seed,
        shape_kind: kind,    // NEW v3.1a
    };
    // zone + subzone sampling unchanged from v3.0 — uses zrng stream
    // ...
    plate
}).collect();
```

`FlatParams` gains an optional override `pub plate_dispatch: Option<DispatchMode>` — `None` uses the default (`Fixed(Ellipse)` in v3.1a, `Weighted(...)` in v3.1b). Tests / debug callers can pin `Fixed(Polar)` etc.

### 4.6 — v3.1b algorithms

#### 4.6.1 — BezierSpine

Cubic Bézier `B(t) = (1-t)³P0 + 3(1-t)²t P1 + 3(1-t)t² P2 + t³P3`. Sample at `N = vertex_count/2` stations; at each station, lay perpendicular thickness `r(t)` from a piecewise-linear radius profile. Boundary = left edge `[P_i + r_i·N_i]` forward, right edge `[P_i - r_i·N_i]` backward → closed loop of `2N` vertices.

Templates (picked by `hash(ctx.seed) % 3`):
- **SCurve**: spine `[(-1,-0.5), (-0.3, 0.6), (0.3,-0.6), (1, 0.5)]`, radius `[0.25, 0.45, 0.35, 0.20]` (normalized; scaled by `envelope.x`).
- **Hook**: spine `[(-1,-0.6), (0.6,-0.6), (0.8, 0.3), (0.1, 0.9)]`, radius `[0.28, 0.42, 0.35, 0.45]`.
- **Boot** (Italy): spine `[(-0.6, 1.0), (0.0,-0.5), (0.5,-0.7), (0.8,-0.3)]`, radius `[0.3, 0.4, 0.4, 0.22]`.

Each station radius perturbed by `ctx.edge_jitter` × `next_f32()`. Result scaled to fit `envelope` (uniform scale = `min(envelope.x / spine_bbox.x, envelope.y / spine_bbox.y)`), rotated by `rng.next_f32() * TAU`, translated to `ctx.center`.

**Determinism:** all RNG from `Rng::for_stage(ctx.seed, b"bezier-spine")` so cross-plate RNG order doesn't shift if Bezier runs.

#### 4.6.2 — Polar / Superformula

Sample `θ ∈ [0, 2π]` at `N = vertex_count` steps. Radius from superformula:
```
r(θ) = ( |cos(m·θ/4)/a|^n2 + |sin(m·θ/4)/b|^n3 )^(-1/n1)
```
Templates (picked by `hash(ctx.seed) % 4`):
- **Pentagon**: m=5, a=b=1, n1=10, n2=10, n3=10 (5-sided rounded).
- **Cardioid**: bypass superformula; `r(θ) = a·(1 + cos(θ))`, scale to envelope.
- **Rose** (4-petal): `r(θ) = a · |cos(2θ)|` (use abs to avoid r<0); rare — weight≤0.10.
- **Oval**: m=2, n1=2, n2=2, n3=2 → near-ellipse, preserves backward feel.

Apply jitter (per-vertex multiplicative `1 + edge_jitter · (next_f32() - 0.5)`), scale, rotate, translate.

**Self-intersect guard:** after assembly, run a simple winding-number check; if non-simple (Rose with high jitter), retry with `edge_jitter * 0.5` (max 3 retries) → fallback to Oval.

#### 4.6.3 — Boolean / CSG

Build 2 sub-ellipses via simple `n=24` ellipsoid sampling (no fbm — clean geometry for CSG to operate on). Apply `geo-clipper` union / difference. Take outermost ring of result (largest area). Resample to `vertex_count` via arc-length interpolation.

Templates (picked by `hash(ctx.seed) % 4`):
- **Ring**: outer ellipse (envelope × 1.0) **MINUS** inner ellipse (envelope × 0.4 centered). Outer ring of result only (inner hole discarded — documented limitation; v3.3 hole support deferred).
- **EllipseUnion**: ellipse A (envelope × 0.7) ∪ ellipse B offset by `(envelope.x * 0.5, 0)`. Peanut shape.
- **EllipseDifference**: ellipse A ∖ ellipse B offset by `(envelope.x * 0.4, envelope.y * 0.2)`. Crescent / gulf.
- **WedgeCut**: ellipse A ∖ triangular wedge (3-vertex polygon spanning from centre to envelope edge). Inlet.

Apply final per-vertex jitter, rotate, translate.

**Failure mode:** geo-clipper can return empty / multi-component / degenerate polygon. Wrap:
```rust
fn safe_boolean(a: &Polygon, b: &Polygon, op: BooleanOp) -> Polygon {
    match clip(a, b, op) {
        Ok(result) if !result.is_empty() => largest_component(result),
        _ => a.clone(),  // fallback: return A unchanged
    }
}
```

#### 4.6.4 — DispatchMode::Weighted (v3.1b)

```rust
DispatchMode::Weighted(HashMap<SizeRank, HashMap<ShapeKind, f32>>)
```

`select` looks up `ctx.size_rank` → ShapeKind→weight table → samples via cumulative weight + `rng.next_f32()`. Weights must sum to 1.0 per rank (`debug_assert`). **Robustness:** if cumulative sum overshoots target due to f32 rounding, the loop falls through and returns the LAST listed kind (so a malformed table never panics — debug builds catch it via assert, release degrades gracefully).

v3.1b weight table (only 4 algos until v3.2):

| ShapeKind | Giant | Large | Medium | Small | Micro |
|-----------|------:|------:|-------:|------:|------:|
| Ellipse | 0.30 | 0.30 | 0.40 | 0.40 | 0.60 |
| BezierSpine | 0.35 | 0.40 | 0.30 | 0.20 | 0.10 |
| Polar | 0.10 | 0.10 | 0.20 | 0.30 | 0.25 |
| Boolean | 0.25 | 0.20 | 0.10 | 0.10 | 0.05 |
| **Total** | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Rationale matches §14 Q4 trend (flat for Giants, ellipse-heavy for Micros). Weights tunable post-visual-review.

`engine_v3_1b_weights() -> HashMap<...>` ships as a function for easy override.

### 4.7 — Schema additive change (v3.1a)

```rust
// flatworld.rs — Plate struct
#[derive(Debug, Clone)]
pub struct Plate {
    /* ... v3.0 fields unchanged ... */
    /// v3.1a: which algorithm generated this plate. Drives v4.X dispatcher,
    /// debug rendering, and future eval-per-algorithm metrics.
    pub shape_kind: crate::shape::ShapeKind,
}
```

`PlateData` in `world_map.rs` exporter (if it mirrors Plate) gains the same field for sidecar JSON. Default to `Ellipse` for legacy deserialization.

### 4.8 — Eval framework adaptation (v3.1b)

`scripts/climate_eval.py` — `lat_banding` metric currently scores by per-plate centroid count across lat bands. Elongated Bezier plates span 2-3 bands → centroid count drops → false regression.

**Change:** measure per-component AREA distribution. For each plate component, integrate area inside each lat band; score `lat_banding = 1 - chi_squared(distribution, earth_target_distribution)`. Per-component area is already O(N) on existing polygon code.

Other metrics (`continentality`, `dist`, `diversity`, `sanity`) are shape-agnostic; no change for v3.1b. New baseline lands at `eval/baselines/v5.3.json` after v3.1b ships.

---

## 5 — Acceptance criteria

### 5.1 — v3.1a (foundation, byte-identical)
- [ ] `crates/world-gen/src/shape/` module exists with `mod.rs`, `dispatch.rs`, `ellipse.rs`.
- [ ] `ShapeKind` enum has all 8 variants (4 v3.1+ usable, 4 reserved).
- [ ] `ShapeRegistry::engine_default()` registers exactly 1 generator (Ellipse).
- [ ] `DispatchMode::Fixed(k)` returns `k` without consuming RNG.
- [ ] `DispatchMode::Random` with single registered kind returns it without consuming RNG.
- [ ] `Plate::shape_kind` field present; defaults to `Ellipse` in `engine_default` dispatch.
- [ ] `flatworld::generate` with default `FlatParams` produces output **byte-identical** to v3.0 (commit f022cf82) at seeds 1, 7, 13, 42. Verify via `content_hash` comparison.
- [ ] All 208 existing lib tests + new shape tests pass.
- [ ] `cargo clippy --workspace` no NEW warnings (3 pre-existing OK).
- [ ] Eval composite at v5.2 baseline `eval/baselines/v5.2.json` reproduces exact mean 85.24 (byte-identical render → same eval).

### 5.2 — v3.1b (3 algorithms + Weighted dispatch)
- [ ] `shape/spine.rs`, `shape/polar.rs`, `shape/csg.rs` exist; 3 generators registered.
- [ ] `geo-clipper` crate dep added to `crates/world-gen/Cargo.toml`; `cargo tree` shows acceptable transitive footprint (≤5 new transitive crates).
- [ ] `DispatchMode::Weighted` variant + `engine_v3_1b_weights()` function; weights sum to 1.0 per rank (`debug_assert`).
- [ ] Default `flatworld::generate` dispatch flips from `Fixed(Ellipse)` to `Weighted(engine_v3_1b_weights())`.
- [ ] At seeds 7, 13, 42 — render PNG (`eval/compare-phase-a/v3.1/plates_s{7,13,42}.png`) shows ≥1 non-ellipse plate visible.
- [ ] 10+ new unit tests covering: each algorithm centre-inside, deterministic, area-within-target, simple polygon, Weighted sums-to-1, Random with multi-kind consumes RNG, Boolean fallback safety.
- [ ] `scripts/climate_eval.py` `lat_banding` updated to per-component area distribution; new baseline `eval/baselines/v5.3.json` reports adapted composite (no `±5` gate per PO directive — visual review approves).
- [ ] Polygon `is_simple` assertion passes for all generated v3.1b polygons across 100 random seeds.
- [ ] PO visual review of `eval/compare-phase-a/v3.1/` PNGs APPROVED before commit.

---

## 6 — Risks

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | RNG consumption order in dispatcher shifts state → byte-identical breaks | **HIGH** | `Fixed` mode is no-op; `Random` with `len==1` short-circuits without `next_u32()`. Default v3.1a = `Fixed(Ellipse)`. Snapshot test pins v3.0 content_hash. |
| R2 | EllipseGenerator extraction reorders RNG by one call → seed drift | **HIGH** | Side-by-side diff old `flatworld::generate` body vs `EllipseGenerator::generate`; preserve every `rng.next_*()` call in original order. Snapshot test catches it. |
| R3 | `Plate.shape_kind` field breaks downstream JSON deserialisers | **MED** | Field is additive; mark `#[serde(default)]` on deserialize; default impl returns `Ellipse`. |
| R4 | `geo-clipper` pulls heavy transitive deps | **MED** | Run `cargo tree` after add; if footprint > 5 transitives, switch to a leaner alternative (`geo-booleanop` or hand-rolled Sutherland-Hodgman for union-only). |
| R5 | Boolean ops produce degenerate / multi-component output | **MED** | `safe_boolean` wraps with fallback to operand A. `largest_component` picks biggest ring. `is_simple` post-check; retry-with-smaller-jitter then fallback. |
| R6 | Hole-in-polygon (Ring template) lost when discarding inner ring | LOW | Documented limitation. Result is a flat disk with no inland sea; v3.3 marching squares will properly support holes. |
| R7 | Polar Rose self-intersects under jitter | LOW | Use Rose sparingly (Polar weight ≤ 0.10 anywhere); winding-number post-check + retry-with-half-jitter → fallback to Oval. |
| R8 | Weighted dispatch produces unbalanced shape variety (one kind dominates) | MED | Visual review at seeds 7/13/42; tune weight table iteratively. PO approves before commit. |
| R9 | Eval `lat_banding` rewrite introduces unrelated metric shift | MED | Compute both old (centroid) and new (area-distribution) on v3.0 worlds; verify new metric agrees within 5% on the no-elongation baseline. |
| R10 | `geo-clipper` API mismatch (older crate uses i64 fixed-point not f32) | MED | Plan time spike: read crate docs first; wrap with f32↔fixed converter helper. Adds ~1h to v3.1b. |

---

## 7 — Out-of-scope

- Climate/hydrology re-tuning beyond eval-metric adaptation.
- World-map exporter changes beyond mirroring `shape_kind`.
- Render-pipeline changes (PNG output, fonts, colours).
- Documentation translation (any new doc may be English-only).

---

## 8 — Open questions

None. PO answered all 5 kickoff questions in CLARIFY (Session 60):
1. Build order: Hybrid (minimal dispatcher first).
2. Boolean dep: `geo-clipper` crate (full CSG).
3. Eval policy: tool not gate.
4. AMAW mode: opt-out, default v2.2.
5. Commit strategy: 2 separate commits (v3.1a, v3.1b).
