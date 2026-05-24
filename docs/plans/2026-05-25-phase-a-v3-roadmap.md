# Phase A v3 — Plate Shape & Size Diversity Roadmap

> **Status:** v3.0 SHIPPED (commit f022cf82) — multi-session (~12-16h, 4 sub-phases).
> **Companions:**
> - [`2026-05-25-world-map-v1-buildout.md`](2026-05-25-world-map-v1-buildout.md) (V1 spec, A-F phases)
> - Phase A v1 SHIPPED: `crates/world-gen/src/flatworld.rs` — 24/48 vertices, multi-octave fbm,
>   `Plate::zone_warp_salt` domain warp, eval composite **89.30** (was 89.56).
> - **Research base — read first**: [`../research/INDEX.md`](../research/INDEX.md) →
>   [Research 1](../research/2026-05-25-phase-a-research-1-procgen-algorithms.md) (10-algo catalog),
>   [Research 2](../research/2026-05-25-phase-a-research-2-shape-templates-sizing.md) (17-algo + Azgaar FMG + Pareto sizing),
>   [Research 3](../research/2026-05-25-phase-a-research-3-topology-game-algos.md) (12 topology-specific algos + 20 game industry refs + Bézier spine recommendation for S/sock/hook/L).
>
> **PO directive (2026-05-25):** "current plates are still rounded, equal-sized.
> Real continents have very diverse sizes. Need more edges and more complex shapes.
> Should use different TEMPLATES, not one formula. Combine multiple algorithms."

---

## 1 — Goal

Replace single-formula noise-perturbed-disk generation with a **template dispatcher**
that produces plates with:

1. **Diverse sizes** (Pareto-distributed; up to ~120× ratio largest:smallest, matching Earth's continent distribution)
2. **Diverse shapes** (7-template taxonomy: CratonicCore / RiftedContinent / PeninsularBlock / IslandArc / Archipelago / MicroBlock / FjordCoast)
3. **Multi-component plates** (one plate = main continent + 0-N satellite islands, supporting Indonesia-style archipelagos)
4. **Eval composite stable** (within ±2pt of baseline 89.30)

PO chose: **schema refactor in v3.0 as foundation** + **full 4-phase roadmap**.

---

## 2 — 4-Phase Roadmap

| Phase | Scope | Hours | Risk | Schema impact |
|---|---|---|---|---|
| **v3.0** | Schema refactor (`Plate.components`) + Pareto sizing + anisotropy + Earth-stat calibration | 2-3 | 3/5 | YES — breaks `Plate.vertices` |
| **v3.1** | NEW `plate_shape.rs` + 3-template dispatcher (Cratonic + Peninsular + Fjord) + size-rank assignment | 3-4 | 2/5 | additive |
| **v3.2** | Add 4 more templates (Rifted + IslandArc + Archipelago + MicroBlock) | 3-4 | 2/5 | additive |
| **v3.3** | Multi-component generation via marching-squares (true archipelagos) | 4-6 | 4/5 | uses Plate.components from v3.0 |

Total: ~12-16h across 4 sessions.

---

## 3 — Phase A v3.0 — Foundation (THIS SESSION)

### 3.0 Acceptance criteria
- `Plate.components: Vec<Polygon>` with `type Polygon = Vec<(f32, f32)>` (was `Plate.vertices: Vec<(f32, f32)>`)
- `Plate::contains(x, y)` returns true if any component contains the point
- All call sites updated (`render_rgb`, `plates_at`, `elevation_at`, `world_map` export, `flat_climate`, `hydrology`, `zonegen`)
- Size diversity via Pareto draw + size-rank pre-assignment (1 giant + 2 large + 3 medium + 4 small + 2 micro for 12 plates)
- Anisotropy: `(rx, ry, rotation)` instead of scalar radius
- E[area] calibrated to current ±5% (preserves climate eval composite)
- Hash pins rebased
- Climate eval mean composite within 89.30 ± 2
- All 208 lib tests pass (with updated test fixtures for new schema)

### 3.1 Schema refactor

Current:
```rust
pub struct Plate {
    pub id: usize,
    pub center: (f32, f32),
    pub vertices: Vec<(f32, f32)>,
    pub velocity: (f32, f32),
    pub zone_sites: Vec<(f32, f32)>,
    pub subzone_sites: Vec<Vec<(f32, f32)>>,
    pub zone_warp_salt: u32,
}
```

New:
```rust
pub type Polygon = Vec<(f32, f32)>;

pub struct Plate {
    pub id: usize,
    pub center: (f32, f32),
    pub components: Vec<Polygon>,   // [0] = primary; [1..] = satellite islands
    pub velocity: (f32, f32),
    pub zone_sites: Vec<(f32, f32)>,     // sampled across union of components
    pub subzone_sites: Vec<Vec<(f32, f32)>>,
    pub zone_warp_salt: u32,
    pub size_rank: SizeRank,             // for downstream template logic + render scaling
    pub shape_seed: u32,                 // for future template determinism (v3.1)
}

pub enum SizeRank {
    Giant, Large, Medium, Small, Micro,
}
```

`Plate::contains(x, y)` iterates all components (point-in-polygon for each).
`Plate::primary()` returns `&components[0]` for convenience.
`Plate::bounding_box()` returns AABB across all components.

In v3.0, every plate is generated with exactly 1 component (no archipelago yet — that's v3.3).
The schema is forward-compatible.

### 3.2 Pareto sizing

Current:
```rust
let radius = pitch * lerp(min_radius_frac, max_radius_frac, rng.next_f32());
// uniform in [0.50, 0.66] × pitch, ratio max/min = 1.32×
```

New:
```rust
// Deterministic size-rank assignment for `plate_count` plates
let ranks = assign_size_ranks(plate_count, seed);
// 12 plates → [Giant, Large, Large, Medium, Medium, Medium, Small, Small, Small, Small, Micro, Micro]

for (id, rank) in ranks.iter().enumerate() {
    let (r_min, r_max) = rank.radius_band();  // Giant: 1.6-2.4 × pitch; Micro: 0.2-0.4 × pitch
    let r = lerp(r_min, r_max, rng.next_f32()) * pitch;
    // Calibrated so E[area across all ranks] matches old E[area] within 5%
}
```

Size-rank → radius band mapping (in pitch units):

| Rank | Count (of 12) | r_min | r_max | Earth analog |
|---|---|---|---|---|
| Giant | 1 | 1.6 | 2.4 | Eurasia |
| Large | 2 | 1.0 | 1.4 | Africa, N. America |
| Medium | 3 | 0.6 | 0.9 | Australia, Antarctica, Greenland |
| Small | 4 | 0.35 | 0.55 | Madagascar, Borneo |
| Micro | 2 | 0.2 | 0.35 | Iceland, Hispaniola |

E[area] of the new distribution: weighted sum of `π × E[r²]` per rank, calibrated to match
old `π × 0.34 × pitch²` ≈ 1.07 × pitch² average plate area. Calibration target: ±5% of old mean.

### 3.3 Anisotropy

Current:
```rust
let r = radius * shrink_bias * residual * (1.0 + EDGE_NOISE_AMP * noise);
let (vx, vy) = (cx + r * ang.cos(), cy + r * ang.sin());
```

New:
```rust
// Anisotropic radii — also Pareto-sampled per plate
let aspect = pareto_sample(rng, alpha=2.5, x_min=1.0, x_max=3.0);
let theta_rot = rng.next_f32() * TAU;
let rx = r * aspect.sqrt();
let ry = r / aspect.sqrt();

// Vertex computation in plate-local frame (cos·rx, sin·ry), then rotate
let (cu, su) = (ang.cos(), ang.sin());
let local = (rx * cu * (1.0 + ...noise...), ry * su * (1.0 + ...noise...));
let (vx, vy) = (cx + local.0 * theta_rot.cos() - local.1 * theta_rot.sin(),
                cy + local.0 * theta_rot.sin() + local.1 * theta_rot.cos());
```

Aspect distribution: most plates 1.0-1.5 (slight elongation); some 2.0-3.0 (Italy/Chile-like).

### 3.4 Files touched (v3.0)

1. **flatworld.rs** — Plate struct, generate, contains, plates_at, elevation_at, render_rgb, render_zones_rgb, export, tests
2. **world_map.rs** — export schema may need PlateData.boundary → boundaries change
3. **zonegen.rs** — render_all_zones_biome iterates plate.vertices (or .contains); update + hash pin rebase
4. **flat_climate.rs** — orographic test fixture; per-plate vertex iteration if any
5. **hydrology.rs** — any plate.vertices usage
6. **render.rs** — sphere render unaffected (different pipeline)
7. **examples/flatworld.rs** — debug flags

### 3.5 Backward-compat helpers

To keep diff manageable, add `Plate::vertices()` returning `&self.components[0]` (deprecated, primary-only)
so call sites that semantically want "the polygon" can be migrated incrementally.

---

## 4 — Phase A v3.1 — Template Dispatcher (NEXT SESSION)

### 4.1 New module: `crates/world-gen/src/plate_shape.rs`

```rust
pub enum PlateTemplate {
    CratonicCore,    // Catmull-Rom + midpoint disp (low H≈0.5)
    PeninsularBlock, // Convex hull + L-system finger + midpoint
    FjordCoast,      // Catmull-Rom + midpoint (high H≈0.8)
    // v3.2 adds: RiftedContinent, IslandArc, Archipelago, MicroBlock
}

pub fn build(
    template: PlateTemplate,
    center: (f32, f32),
    rx: f32, ry: f32, theta: f32,
    size_rank: SizeRank,
    rng: &mut Rng,
    salt: u32,
) -> Vec<Polygon> {  // returns 1+ polygons (multi-component capable from start)
    match template {
        CratonicCore => build_cratonic(...),
        PeninsularBlock => build_peninsular(...),
        FjordCoast => build_fjord(...),
    }
}
```

### 4.2 Template selection

```rust
fn assign_templates(ranks: &[SizeRank], seed: u64) -> Vec<PlateTemplate> {
    // Deterministic per-rank distribution:
    // Giant + Large → CratonicCore or RiftedContinent
    // Medium → PeninsularBlock or FjordCoast
    // Small + Micro → IslandArc or Archipelago or MicroBlock
}
```

### 4.3 Acceptance criteria
- 3 templates render visibly different shapes
- Each template's output area matches expected band (verify via assertion)
- Climate eval composite within ±2 of v3.0 baseline

---

## 5 — Phase A v3.2 — Full Template Set

Add the 4 remaining templates: RiftedContinent, IslandArc, Archipelago, MicroBlock.

Each follows the v3.1 pattern. Specific algorithms per §6 of research report.

---

## 6 — Phase A v3.3 — Multi-component generation

Implement true marching-squares per-plate raster generation for Archipelago + IslandArc templates.
Now `Plate.components.len() > 1` for these templates.

Add `flat_climate.rs` adapter to handle climate per-component (or unified per-plate).
Add `hydrology.rs` adapter for drainage across components (or per-component).

Acceptance: Indonesia/Aegean-style outputs visible. Eval composite within ±3 of v3.2 baseline.

---

## 7 — Risks

| Risk | Mitigation |
|---|---|
| Schema refactor breaks many call sites silently | Compile-time safety in Rust; explicit `vertices()` accessor for backward compat during migration |
| E[area] shifts under Pareto → climate eval crashes | Calibrate Pareto α/x_min/x_max so E[area] matches old within 5%; verify via climate eval before/after |
| Hash pins drift on every iteration | Accept rebases per iteration; document v3.0/v3.1/v3.2/v3.3 in pin comments |
| Multi-component plates confuse Voronoi zones (v3.3) | Zones span union of components; sub-zone sampling may need adjustment |
| Determinism breaks in template dispatch (different RNG order) | Use per-plate `shape_seed: u32` instead of shared RNG state; each template runs with isolated stream |

---

## 8 — References

- [Azgaar FMG heightmap-generator.js](https://github.com/Azgaar/Fantasy-Map-Generator/blob/master/modules/heightmap-generator.js) — the canonical template-based plate generator
- Bird 2003 plate catalog ([G3 DOI](https://doi.org/10.1029/2001GC000252)) — size distribution
- [Sornette & Pisarenko 2003](https://doi.org/10.1029/2002GL015043) — Pareto α≈0.25 for plate areas
- [Quilez SDF 2D primitives](https://iquilezles.org/articles/distfunctions2d/) — SDF composition (v3.3 marching squares input)
- [Fournier-Fussell-Carpenter 1982](https://dl.acm.org/doi/10.1145/358523.358553) — midpoint displacement (used in Cratonic + Fjord templates)
- [Catmull-Rom spline](https://en.wikipedia.org/wiki/Centripetal_Catmull%E2%80%93Rom_spline) — Cratonic / Madagascar template base
- [Marching squares (Bourke 1987)](http://paulbourke.net/geometry/polygonise/) — Archipelago + IslandArc template extraction (v3.3)
- [`geo-booleanop` crate](https://crates.io/crates/geo-booleanop) — Boolean polygon ops if needed for stamp composition

---

## 9 — Out-of-V3-scope

- True hydraulic erosion as post-process (Phase B+ when hillshade lands)
- Plate tectonic SIMULATION (rigid body motion, collision dynamics) — Track 2, V2+
- Reaction-diffusion or other "no-template" emergence approaches
- L-system grammar tuning beyond simple finger off PeninsularBlock
