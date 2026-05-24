# Phase A v3 + v4 — Full Plate/Zone/Sub-zone Shape Generation Roadmap

> **Status:** v3.0 SHIPPED (commit f022cf82) — multi-session (~95-130h, 15-25 sub-phases).
> **Last updated:** 2026-05-25 — expanded from v3.0-v3.3 to full v3+v4 per PO directive.
> **Companions:**
> - [`2026-05-25-world-map-v1-buildout.md`](2026-05-25-world-map-v1-buildout.md) (V1 spec, A-F phases)
> - Phase A v1 SHIPPED: `crates/world-gen/src/flatworld.rs` — 24/48 vertices, multi-octave fbm,
>   `Plate::zone_warp_salt` domain warp, eval composite **89.30** (was 89.56).
> - **Research base — read first**: [`../research/INDEX.md`](../research/INDEX.md) →
>   [Research 1](../research/2026-05-25-phase-a-research-1-procgen-algorithms.md) (10-algo catalog),
>   [Research 2](../research/2026-05-25-phase-a-research-2-shape-templates-sizing.md) (17-algo + Azgaar FMG + Pareto sizing),
>   [Research 3](../research/2026-05-25-phase-a-research-3-topology-game-algos.md) (12 topology-specific algos + 20 game industry refs + Bézier spine recommendation),
>   [Research 4](../research/2026-05-25-phase-a-research-4-slime-physarum.md) (PO's slime/Physarum/DLA + concave-hull hybrid).

---

## 0 — PO Directive (verbatim)

After Research 4 saved, PO requested expansion of the implementation roadmap:

> "ok, bây giờ update lại plan. tôi muốn implement toàn bộ thuật toán, chúng ta sẽ có logic tổng hợp, tùy vào LLM hoặc random để generate shape cho mỗi mảng kiến tạo, zone/sub zone khác nhau. như vậy bản đồ sẽ đa dạng và chất lượng hơn thay vì hiện tại chỉ có mỗi oval"

**Translation:** Update the plan. I want to implement ALL the algorithms. We'll have an **orchestrator (logic tổng hợp)** that — based on LLM or random — generates a shape for each plate, zone, sub-zone (each can be different). This way the map is more diverse and higher quality than the current oval-only.

## 1 — Goal

Replace the single anisotropic-ellipse plate generator with a **multi-algorithm shape generation system**:

1. **All 7-8 algorithms from research implemented** (Bézier spine, SDF capsule chain, Boolean polygon ops, polar/superformula, hand-authored stamps, slime/Physarum, marching squares on noise field, existing ellipse)
2. **Shape Orchestrator** (dispatcher) selects which algorithm per plate/zone/sub-zone:
   - **Random mode** (seeded weighted-random per ShapeKind)
   - **Fixed mode** (force one algorithm — for tests/debug)
   - **ByContext mode** (rules-based: e.g., polar plates → Cratonic, equatorial → Archipelago)
   - **LLM mode** (LLM picks ShapeKind given world theme + context)
3. **Apply at all 3 hierarchy levels**:
   - Plate (depth 0): main continent shape
   - Zone (depth 1): currently Voronoi cells, become templated polygons
   - Sub-zone (depth 2): currently Voronoi cells, become templated polygons
4. **Eval composite stays bounded** (±5 of v3.0 baseline 85.24)
5. **Determinism preserved** via cached LLM responses + seeded RNG

## 2 — Today's Status

v3.0 SHIPPED (commit f022cf82):
- Schema: `Plate.components: Vec<Polygon>` with `primary()` / `bounding_box()` helpers
- SizeRank enum (Giant/Large/Medium/Small/Micro), deterministic 12-plate distribution 1+2+3+4+2
- Anisotropic (rx, ry, theta_rot) ellipsoidal vertex generation only
- Eval baseline v5.2: mean composite 85.24
- 208/208 lib tests pass

**Gap:** every plate is still a perturbed ellipse. Zones/sub-zones are Voronoi cells of plate area — no templating, no shape variety per level.

## 3 — Algorithm Catalog (to implement)

All 8 algorithms from research, prioritised by impact-per-hour:

| # | Name | Research ref | Topology produced | Complexity | LOC |
|---|------|--------------|-------------------|------------|-----|
| **0** | **Ellipse + fbm** ✓ | v3.0 shipped | Oval/blob | 1 | 0 (have it) |
| 1 | **Bézier spine + variable thickness** | R3 §1.A1 + A8 | S, hook, sock, L, boot, arc, U | 3 | 120 |
| 2 | **Polar / superformula** | R3 §1.A7 | Star, pentagon, cardioid, rose, oval | 1 | 30 |
| 3 | **Boolean polygon ops** (CSG) | R3 §1.A6 | Ring, annulus, ellipse-minus-wedge, union | 3 | 80 + `geo-clipper` crate |
| 4 | **SDF capsule chain + smooth-min** | R3 §1.A2 | Y, T, +, X, branching, crab | 4 | 250 |
| 5 | **Marching squares on noise field** | R2 §A + R3 §1.A11 | Multi-component (archipelago), holes | 3 | 200 |
| 6 | **Slime / Physarum** (multi-agent walk + concave hull) | R4 entire | Unlimited emergent (branching, scattered, organic) | 4 | 310 |
| 7 | **Hand-authored stamps** (Diablo II school) | R3 §1.A10 | Whatever authored (Italy, Korea, Cuba presets) | 2 | 80 + N stamp JSONs |

**Total**: ~1070 LOC + 2 crate deps (`geo-clipper`, optional `spade` for Delaunay).

## 4 — Phase Roadmap (v3.1 → v4.5)

15-25 sub-phases across ~95-130 hours. Each phase is a shippable unit (commit + workflow gate).

### Tier 1 — Algorithm Implementation (plate-level only)

| Phase | Scope | Algos added | Hours | Risk |
|-------|-------|-------------|-------|------|
| **v3.1** | NEW `shape/` module + Bézier spine + Polar + Boolean (3 algos) | 1, 2, 3 | 12-15 | 2/5 |
| **v3.2** | SDF capsule chain + marching squares pipeline | 4, 5 | 14-18 | 3/5 |
| **v3.3** | Multi-component plates via marching squares (true archipelagos) | 5 (extension) | 6-8 | 4/5 |
| **v3.4** | Slime / Physarum algorithm + concave hull + simplification | 6 | 8-10 | 4/5 |
| **v3.5** | Hand-authored stamps library (10-20 stamps) | 7 | 8-12 (1h/stamp) | 2/5 |

**Tier 1 total**: 48-63 hours. End-state: 8 shape algorithms available, all callable at plate level only. Templates pickable via FlatParams.

### Tier 2 — Orchestrator (Dispatcher)

| Phase | Scope | Hours | Risk |
|-------|-------|-------|------|
| **v4.0** | `ShapeGenerator` trait + `ShapeKind` enum + `DispatchMode::{Random, Fixed, ByContext}` + wiring | 10-12 | 3/5 |

End-state: any plate generation goes through dispatcher; default `DispatchMode::Random` with seeded weighted-sample per SizeRank.

### Tier 3 — Apply at Zone + Sub-zone levels

| Phase | Scope | Hours | Risk |
|-------|-------|-------|------|
| **v4.1** | Templatize **zones** — Zone becomes `Polygon` instead of Voronoi cell. Climate/drainage adapted for templated zones | 14-18 | 5/5 |
| **v4.2** | Templatize **sub-zones** — SubZone becomes `Polygon`. Sub-zone climate / landscape diversity adapted | 10-14 | 4/5 |

**Tier 3 total**: 24-32 hours. Highest-risk phase — requires deep refactor of climate + drainage + render pipelines.

### Tier 4 — LLM-driven Dispatcher

| Phase | Scope | Hours | Risk |
|-------|-------|-------|------|
| **v4.3** | LLM client for shape selection. Prompt templates. Cache by (seed, context). | 10-12 | 3/5 |
| **v4.4** | LLM-authored stamp generation (LLM proposes new stamp polygons based on world theme) | 8-10 | 4/5 |

**Tier 4 total**: 18-22 hours. Pre-req: existing LLM infrastructure in `author.rs` / `naming.rs`.

### Tier 5 — Calibration + Eval

| Phase | Scope | Hours | Risk |
|-------|-------|-------|------|
| **v4.5** | Tune dispatcher weights. Update eval framework for wider topology variance. Per-rank quality assertions. | 10-15 | 2/5 |

**Tier 5 total**: 10-15 hours.

### Grand total

**95-130 hours across 15-25 sessions (3-6 months at 1 session/week).**

## 5 — Schema Evolution

### v3.0 (current)
```rust
pub struct Plate {
    pub id: usize,
    pub center: (f32, f32),
    pub components: Vec<Polygon>,
    pub velocity: (f32, f32),
    pub zone_sites: Vec<(f32, f32)>,         // Voronoi sites
    pub subzone_sites: Vec<Vec<(f32, f32)>>, // nested Voronoi sites
    pub zone_warp_salt: u32,
    pub size_rank: SizeRank,
    pub shape_seed: u32,
}
```

### v3.1+ — Add ShapeKind tag
```rust
pub struct Plate {
    /* ... v3.0 fields ... */
    pub shape_kind: ShapeKind,  // which algorithm was used
}

pub enum ShapeKind {
    Ellipse,           // v3.0 default
    BezierSpine { template: BezierTemplate },
    Polar { template: PolarTemplate },
    Boolean { template: BooleanTemplate },
    SdfCapsuleChain { template: CapsuleTemplate },
    MarchingNoise { template: NoiseTemplate },
    Slime { template: SlimeTemplate },
    Stamp { stamp_id: StampId },
}
```

### v4.1 — Zones become Polygon, not Voronoi
```rust
pub struct Zone {
    pub id: usize,
    pub plate_id: usize,
    pub center: (f32, f32),
    pub components: Vec<Polygon>,   // templated shape
    pub shape_kind: ShapeKind,
    pub size_rank: SizeRank,        // sub-rank within plate
    pub shape_seed: u32,
}

// Plate now holds Zones, not zone_sites
pub struct Plate {
    /* ... v3.1 fields ... */
    pub zones: Vec<Zone>,           // REPLACES zone_sites + subzone_sites
}
```

### v4.2 — Sub-zones become Polygon
```rust
pub struct Zone {
    /* ... v4.1 fields ... */
    pub subzones: Vec<SubZone>,    // REPLACES subzone_sites
}

pub struct SubZone {
    pub id: usize,
    pub zone_path: (usize, usize),  // (plate_id, zone_id)
    pub center: (f32, f32),
    pub components: Vec<Polygon>,
    pub shape_kind: ShapeKind,
    pub shape_seed: u32,
}
```

### Backward compat
Each tier preserves the *external* API:
- `Plate::contains(x, y)` works at all schema versions
- `Plate::zone_at(x, y)` iterates `zones` to find which zone contains the point
- `flat_climate.rs` / `hydrology.rs` use the helper API, not direct field access

## 6 — Shape Orchestrator Design

### Core trait
```rust
pub trait ShapeGenerator {
    fn kind(&self) -> ShapeKind;
    fn generate(&self, ctx: &ShapeContext, rng: &mut Rng) -> Vec<Polygon>;
    fn estimated_area(&self, ctx: &ShapeContext) -> f32;  // for calibration
}

pub struct ShapeContext {
    pub depth: u32,                  // 0=plate, 1=zone, 2=subzone
    pub center: (f32, f32),
    pub bbox: (f32, f32, f32, f32),  // bounding box from parent container
    pub size_rank: SizeRank,
    pub seed: u32,
    pub parent_path: Option<Vec<usize>>,  // [plate_id] or [plate_id, zone_id]
    pub world_theme: Option<&'static str>, // for LLM mode (e.g., "earth-like", "alien", "ice")
}
```

### Dispatcher modes
```rust
pub enum DispatchMode {
    /// Deterministic weighted random selection per ShapeKind.
    Random { weights: HashMap<ShapeKind, f32> },

    /// Force a single ShapeKind (for tests / debug).
    Fixed(ShapeKind),

    /// Rules-based — match ShapeContext against predicates,
    /// pick first matching ShapeKind, fallback to Ellipse.
    ByContext { rules: Vec<(ContextPredicate, ShapeKind)> },

    /// LLM-driven — call LLM with prompt template, parse ShapeKind from response.
    /// Caches by (seed, context_hash) so calls are deterministic across runs.
    Llm {
        client_name: &'static str,
        prompt_template: &'static str,
        cache: Arc<Mutex<LlmShapeCache>>,
    },

    /// Per-level mode — different mode per depth.
    /// e.g., LLM for plates, Random for zones, Fixed for sub-zones.
    PerDepth([Box<DispatchMode>; 3]),
}

pub trait ContextPredicate: Send + Sync {
    fn matches(&self, ctx: &ShapeContext) -> bool;
}
```

### Default per-rank weights (v4.0 starting point)

| ShapeKind | Giant | Large | Medium | Small | Micro |
|-----------|------:|------:|-------:|------:|------:|
| Ellipse | 0.10 | 0.15 | 0.20 | 0.20 | 0.30 |
| BezierSpine | 0.30 | 0.30 | 0.25 | 0.20 | 0.10 |
| Polar | 0.05 | 0.10 | 0.20 | 0.25 | 0.30 |
| Boolean | 0.10 | 0.15 | 0.10 | 0.05 | 0.05 |
| SdfCapsuleChain | 0.25 | 0.20 | 0.15 | 0.10 | 0.05 |
| MarchingNoise | 0.10 | 0.05 | 0.05 | 0.10 | 0.10 |
| Slime | 0.05 | 0.05 | 0.05 | 0.10 | 0.10 |
| Stamp | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 |
| **Total** | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |

Rationale:
- Giants favor branching / complex shapes (SdfCapsuleChain, BezierSpine — Eurasia-like)
- Mediums use full mix
- Micros favor simple shapes (Polar / Slime) — won't dominate visual
- Stamps reserved for Giants only (signature continents that look authored)

Weights are tunable; PO can iterate per visual preference.

## 7 — Per-level Application

### v4.0 — Plate level only (in-place upgrade)
```rust
// In flatworld::generate()
for plate_idx in 0..n_plates {
    let ctx = ShapeContext { depth: 0, ... };
    let kind = dispatcher.select(&ctx, &mut rng);
    let generator = registry.get(&kind);
    plate.components = generator.generate(&ctx, &mut rng);
    plate.shape_kind = kind;
}
```
No schema break vs v3.0 beyond adding `shape_kind` field.

### v4.1 — Zone level (HIGH refactor)
Replace `sample_zone_sites` (Voronoi) with shape generation per zone:
```rust
let zone_count = sample_count(plate.size_rank, &mut rng);
for z in 0..zone_count {
    let zone_center = sample_in_plate(&plate, &mut rng);
    let zone_size_rank = derive_zone_rank(plate.size_rank, zone_count);
    let zone_ctx = ShapeContext {
        depth: 1,
        center: zone_center,
        bbox: estimate_zone_bbox(&plate, zone_count),
        size_rank: zone_size_rank,
        ...
    };
    let kind = dispatcher.select(&zone_ctx, &mut rng);
    let generator = registry.get(&kind);
    let polys = generator.generate(&zone_ctx, &mut rng);
    plate.zones.push(Zone { components: polys, shape_kind: kind, ... });
}
```

Climate computation (`compute_zone_climate`) needs adapter:
- Currently uses `plate.zone_sites[zone_id]` for sampling
- New: uses `plate.zones[zone_id].center` and iterates `plate.zones[zone_id].components` for pixel ownership

Drainage / hydrology similarly adapts.

### v4.2 — Sub-zone level
Same pattern as v4.1 but recurses into each zone:
```rust
for zone in plate.zones.iter_mut() {
    let subzone_count = sample_subzone_count(zone.size_rank, &mut rng);
    for sz in 0..subzone_count {
        let sz_ctx = ShapeContext {
            depth: 2,
            parent_path: Some(vec![plate.id, zone.id]),
            ...
        };
        let kind = dispatcher.select(&sz_ctx, &mut rng);
        let polys = registry.get(&kind).generate(&sz_ctx, &mut rng);
        zone.subzones.push(SubZone { components: polys, shape_kind: kind, ... });
    }
}
```

## 8 — Determinism + Caching

### Seed propagation
- World seed → plate gen seed stream
- Per-plate `shape_seed` (already in schema since v3.0)
- Per-zone `shape_seed = hash(plate.shape_seed, zone_id)`
- Per-subzone `shape_seed = hash(zone.shape_seed, subzone_id)`

Each algorithm seeds its own RNG from `ShapeContext.seed`. No shared state between plates.

### LLM cache
```rust
pub struct LlmShapeCache {
    map: HashMap<(u64, u64), ShapeKind>,  // (seed, context_hash) → kind
    path: PathBuf,                          // cache file location
}

impl LlmShapeCache {
    pub fn lookup_or_call(&mut self, seed: u64, ctx: &ShapeContext, client: impl LlmClient) -> ShapeKind {
        let h = ctx.hash();
        if let Some(kind) = self.map.get(&(seed, h)) {
            return *kind;
        }
        let prompt = render_prompt(ctx);
        let response = client.complete(&prompt);
        let kind = parse_shape_kind(&response);
        self.map.insert((seed, h), kind);
        self.flush_to_disk();
        kind
    }
}
```

Cache file: `eval/llm_shape_cache.json` (committed to git for reproducibility). Same world seed always yields same shapes even on offline runs.

### Shape generation cache
Heavy algorithms (slime, marching-squares) cache output polygon:
```rust
pub struct ShapeCache {
    map: LruCache<u64, Vec<Polygon>>,  // ctx_hash → polygons
}
```
Avoids re-running 10k-agent slime sim per render call.

## 9 — Risks + Mitigations

| Risk | Phase | Severity | Mitigation |
|---|---|---|---|
| Schema refactor breaks downstream consumers (climate/drainage/render) | v4.1 | Critical | Compile-time errors guide migration; staged refactor with helper API stable across versions |
| Climate eval composite swings ±15-20pt per phase | v3.1-v3.5 | High | Per-phase calibration step; tune dispatcher weights to keep mean within ±5 of baseline; ship per-phase v5.X baselines |
| LLM non-determinism breaks reproducibility | v4.3 | Critical | Mandatory disk-cached LLM responses; cache file in git; offline mode falls back to ByContext rules |
| Heavy algorithms (slime, marching-squares) too slow at zone/sub-zone scale | v4.1-v4.2 | High | Per-rank algorithm restrictions (slime only for Small/Micro plates); polygon caching; rayon parallelism |
| Hash pin fragility (any algorithm change drifts hashes) | v3.1-v3.5 | Medium | Hash pins reset per major phase; v5.X baseline numbering matches roadmap |
| Stamp authoring is expensive (1h/stamp × 20 stamps) | v3.5 | Medium | Start with 5 high-value stamps (Italy, Korea, Cuba, Japan, Iceland); add more if PO requests |
| Polygon Boolean ops produce degenerate polygons (self-touching corners) | v3.1 | Medium | `geo-clipper` crate handles degeneracies; assertion `polygon.is_simple()` per generated shape |
| LLM cost (API calls) | v4.3 | Low | Cache-first; only call on cache miss; per-world seed = ~12-100 calls = <$1 typically |
| Concave hull self-intersection (Research 4) | v3.4 | Medium | Bentley-Ottmann post-pass; retry with different k_neighbors |
| Zone/sub-zone gaps (templated polygons don't tile parent) | v4.1-v4.2 | Medium | Two options: (a) accept gaps as "void/water" within plate, (b) clip to parent bbox + fill residual |

## 10 — Effort Estimate Summary

| Tier | Scope | Hours | Sessions (4h each) |
|------|-------|-------|--------------------|
| 0 | v3.0 ✓ shipped | 0 | 0 (done) |
| 1 | All 8 algorithms (plate-level) | 48-63 | 12-16 |
| 2 | Orchestrator (Dispatcher) | 10-12 | 3 |
| 3 | Zone + Sub-zone templating | 24-32 | 6-8 |
| 4 | LLM-driven dispatcher | 18-22 | 5-6 |
| 5 | Calibration + eval | 10-15 | 3-4 |
| **Total** | | **95-130 hours** | **29-37 sessions** |

At 1 session/week (the historical pace): **~7-9 months**. At 2 sessions/week: **~3.5-5 months**.

## 11 — Phase-by-Phase Acceptance Criteria

### v3.1 — First 3 algorithms (Bézier + Polar + Boolean)
- ✓ NEW `crates/world-gen/src/shape/` module with `mod.rs`, `spine.rs`, `polar.rs`, `csg.rs`
- ✓ `ShapeKind::{Ellipse, BezierSpine, Polar, Boolean}` enum
- ✓ Each algorithm has `generate(&ShapeContext, &mut Rng) -> Vec<Polygon>` impl
- ✓ Per-template parameter presets (3 BezierSpine templates: S-curve, Hook, Boot)
- ✓ 6 unit tests (centre-inside, deterministic, area-within-target, simple-polygon)
- ✓ Eval composite within 85.24 ± 5 (allow modest regression while templates are coarse)
- ✓ Visual render at seeds 7, 13, 42 — at least 1 plate per render shows non-ellipse shape

### v3.2 — SDF capsule chain + marching squares
- ✓ NEW `shape/sdf.rs`, `shape/raster.rs` modules
- ✓ `ShapeKind::SdfCapsuleChain` with `template: CapsuleTemplate { joints, radii, smin_k }`
- ✓ `ShapeKind::MarchingNoise` for noise-field plates
- ✓ Raster→polygon pipeline (256×256 SDF grid, marching squares, Chaikin smoothing)
- ✓ 4 templates: Y-branch, Z-zigzag, Crab-radial, Worm-chain
- ✓ Eval composite within 85.24 ± 5

### v3.3 — Multi-component (true archipelagos)
- ✓ Each plate can have N>1 polygon components from single algorithm output
- ✓ `flat_climate.rs` correctly attributes climate per-component
- ✓ At least one render shows visible multi-component plate (Indonesia-style)

### v3.4 — Slime / Physarum
- ✓ NEW `shape/slime.rs` with multi-agent walk + concave hull
- ✓ `ShapeKind::Slime { template: SlimeTemplate { n_agents, energy, persistence } }`
- ✓ Quality filter rejects + re-seeds degenerate output (`area < threshold`)
- ✓ 2 templates: SlimeBlob (low persistence), SlimeBranch (high persistence)

### v3.5 — Stamps library
- ✓ NEW `shape/stamps/` directory with N stamp JSONs (start with Italy, Korea, Cuba, Japan, Iceland)
- ✓ `ShapeKind::Stamp { id: StampId }` loads from disk
- ✓ Stamp loader normalizes to ShapeContext (translate, rotate, scale)
- ✓ Per-stamp tests verify load + render

### v4.0 — Dispatcher
- ✓ NEW `shape/dispatcher.rs` with `ShapeGenerator` trait + `ShapeRegistry`
- ✓ `DispatchMode::{Random, Fixed, ByContext, Llm, PerDepth}` impls
- ✓ Default per-rank Random weights (table §6)
- ✓ Plates generated via dispatcher; default mode = Random
- ✓ FlatParams exposes `dispatch_mode: DispatchMode`

### v4.1 — Templatize zones
- ✓ Schema: `Zone` struct with `components: Vec<Polygon>` replaces `zone_sites`
- ✓ All call sites in `flat_climate.rs`, `hydrology.rs`, `zonegen.rs` migrated
- ✓ Dispatcher invoked per zone at depth=1
- ✓ Zone shapes visible in render (zone outlines differ per algorithm)

### v4.2 — Templatize sub-zones
- ✓ Schema: `SubZone` struct with `components` replaces `subzone_sites`
- ✓ Climate / landscape diversity adapted for templated sub-zones
- ✓ Multiple shape kinds visible per zone in render

### v4.3 — LLM dispatcher
- ✓ NEW `shape/llm_dispatch.rs` with `LlmShapeCache`
- ✓ Prompt template renders ShapeContext into natural language
- ✓ Cache file at `eval/llm_shape_cache.json` (committed to git)
- ✓ Offline fallback to ByContext rules when cache miss + LLM unavailable

### v4.4 — LLM-authored stamps
- ✓ Tool: `cargo run --bin author-stamp -- --theme "italian boot"` writes new stamp JSON via LLM
- ✓ LLM-generated stamps load same as hand-authored

### v4.5 — Calibration + eval
- ✓ Per-rank quality assertions (e.g., Giant must have area > X)
- ✓ Eval framework recognises new ShapeKinds (lat_banding tolerates wider topology)
- ✓ v5.3 baseline locked

## 12 — Files Layout (target end-state)

```
crates/world-gen/src/
├── flatworld.rs           # Plate gen orchestration (slimmer over time)
├── shape/                  # NEW module — all shape algorithms + dispatcher
│   ├── mod.rs              # ShapeKind, ShapeContext, ShapeGenerator trait, registry
│   ├── ellipse.rs          # v3.0 algorithm extracted as ShapeGenerator
│   ├── spine.rs            # v3.1 Bézier spine + variable thickness
│   ├── polar.rs            # v3.1 superformula / rose / cardioid
│   ├── csg.rs              # v3.1 Boolean polygon ops (geo-clipper wrapper)
│   ├── sdf.rs              # v3.2 SDF capsule chain + smooth-min
│   ├── raster.rs           # v3.2 marching squares pipeline (shared)
│   ├── slime.rs            # v3.4 multi-agent walk + concave hull
│   ├── stamps/
│   │   ├── mod.rs          # Stamp loader
│   │   ├── italy.json      # v3.5 hand-authored
│   │   ├── korea.json
│   │   └── ...             # 10-20 stamps total
│   ├── dispatcher.rs       # v4.0 DispatchMode + ShapeRegistry
│   ├── llm_dispatch.rs     # v4.3 LLM client + cache
│   └── concave_hull.rs     # Moreira-Santos algorithm (used by slime)
├── flat_climate.rs         # adapter for templated zones in v4.1+
├── hydrology.rs            # adapter for templated zones in v4.1+
├── zonegen.rs              # render pipeline + hash pins per phase
├── world_map.rs            # PlateData/ZoneData export schema updates
└── ...
```

## 13 — Out-of-V3/V4-Scope (deferred to V5+)

- True plate-tectonic simulation (rigid body motion, collision dynamics) — V5 if requested
- Hydraulic erosion as post-process (carving fjords from existing heightmaps) — Phase B+
- Wave Function Collapse on tile grid (Townscaper-style) — alternative architecture, V5
- Time dynamics (plates drift, continents merge over time) — V6+
- Spherical world support (currently flat 1024×640 only) — separate track

## 14 — Open Questions for PO

To finalise the plan before v3.1 implementation starts:

1. **LLM client choice**: do we use existing `author.rs` / `naming.rs` LLM integration, or set up dedicated shape-dispatcher LLM client? (Probably reuse.)
2. **LLM cost**: at 12 plates × 5 zones × 3 sub-zones = 180 LLM calls per world. Is that within budget? (Cache makes repeat-runs free.)
3. **Stamp authoring**: should v3.5 stamps be hand-drawn polygons (PO authors in SVG/JSON) or LLM-generated? Or both?
4. **Per-rank weight philosophy**: should Giants ALWAYS be elongated (Eurasia-like) or have variety? Current proposal: weighted toward elongation but allows other.
5. **Per-rank stamps**: should stamps only apply to certain SizeRanks (e.g., Italy only for Medium)?
6. **Eval acceptance**: are we OK with eval composite swinging widely (e.g., 75-95) during v3.1-v3.5 phases, with calibration in v4.5? Or strict ±5 of baseline per phase?
7. **Visual review cadence**: render + compare at end of each phase (v3.1, v3.2, ...) or only at tier boundaries?

## 15 — References

- All algorithm details: [`../research/INDEX.md`](../research/INDEX.md) and the 4 research files
- v3.0 implementation: `crates/world-gen/src/flatworld.rs` (commit f022cf82)
- Eval framework: `scripts/climate_eval.py` (v5.2 baseline at `eval/baselines/v5.2.json`)
- AMAW workflow: `agentic-workflow/WORKFLOW.md`

---

**Status:** PLAN — pending PO greenlight on §14 open questions before v3.1 implementation kickoff.
