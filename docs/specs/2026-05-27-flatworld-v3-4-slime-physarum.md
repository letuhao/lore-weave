# Spec — Flatworld v3.4 Slime / Physarum + Concave Hull

> **Status:** DRAFT — kickoff 2026-05-27.
> **Parent roadmap:** [`../plans/2026-05-25-phase-a-v3-roadmap.md`](../plans/2026-05-25-phase-a-v3-roadmap.md) §4 Tier 1 v3.4.
> **Predecessor:** [`2026-05-27-flatworld-v3-3-multi-component.md`](2026-05-27-flatworld-v3-3-multi-component.md) (v3.3 shipped 2cf71cf1).
> **Research base:** [`../research/2026-05-25-phase-a-research-4-slime-physarum.md`](../research/2026-05-25-phase-a-research-4-slime-physarum.md).
> **Mode:** v2.2 human-in-loop. Branch `geo-generator-amaw`.
> **Size:** L (files=5, logic=5, side_effects=1). Estimated 8-10h.

---

## 1 — Problem

`ShapeKind::Slime` has been reserved in the enum since v3.1a but never
implemented. v3.4 ships it as the **first emergent algorithm** in the
generator family — multi-agent random walk + concave hull, modelled on
biological slime molds (research §1) and DBM lightning physics.

PO opted for **maximal thoroughness** at CLARIFY (per user memory):
- Hybrid multi-comp tunability per template (Blob single, Branch eligible)
- Aggressive 6-8 agents × 8000 steps (high detail, ~80-200ms per plate)
- Hybrid α-shape primary + Moreira-Santos fallback (most robust)

---

## 2 — Goals

### 2.1 — `SlimeBlob` template (single-component)
- `n_agents = 6`, `persistence = 0.30`, `energy = 8000`
- Low persistence ⇒ agents cloud-expand from `ctx.center` like a blob
- Single connected concave hull (multi-comp filtered → primary only)
- Visual: organic blob with crinkly coast, no separated islands

### 2.2 — `SlimeBranch` template (multi-comp eligible)
- `n_agents = 8`, `persistence = 0.85`, `energy = 8000`
- High persistence ⇒ agents shoot off in straight tendrils
- Multi-comp eligible: when agents diverge into spatially-separate
  clusters, α-shape naturally emits multiple polygons (≥ 1% bbox)
- Visual: peninsular / Indonesia-style tendrils, occasional broken arm

### 2.3 — Algorithm pipeline (per agent template)

```
1. Spawn N agents at ctx.center with random initial headings
2. Each agent walks ~energy steps. Each step:
   - dtheta = (rng - 0.5) × (1 - persistence) × TAU
   - heading += dtheta
   - pos += (cos(heading), sin(heading)) × step_size
   - clamp pos to bounds (= ctx.envelope × 1.4 half-extents around center)
3. Collect all visited positions → point cloud (~48k-64k points)
4. Subsample to ~1500-2000 anchor points (every K-th, K=energy×N/2000) for hull-tractable
5. α-shape primary: Delaunay triangulate, accept triangles with circumradius < alpha;
   boundary = unshared edges; stitch into polygon rings
6. If α-shape produced 0 rings OR self-intersecting → Moreira-Santos fallback (k=8)
7. Per ring: Chaikin × 1 pass + DP simplify (eps = 0.5% bbox diagonal)
8. Apply multi-comp filter (template-specific):
   - SlimeBlob: keep largest only (drop all satellites)
   - SlimeBranch: primary + satellites ≥ 1% bbox
9. Quality filter: if total area < `target_area × 0.25`, reject + reseed
   with rng_advance(salt + retry_count) up to 3 retries
```

### 2.4 — Concave hull algorithms

**α-shape (primary):** uses `delaunator::triangulate(&[Point])` (already a dep
from `mesh.rs`). For each triangle, compute circumradius:

```
R = (a * b * c) / (4 * area_triangle)
```

Accept triangles with `R < alpha` (tunable; default `alpha = avg_point_spacing × 2.5`).
Boundary edges = edges adjacent to exactly 1 accepted triangle. Stitch
edges into closed polygons via shared endpoint walk.

**Moreira-Santos (fallback):** standard k-nearest. Start at rightmost
point, walk clockwise via k=8 nearest non-visited neighbors, pick the
candidate that maximizes right-turn angle. Reject candidates that
create self-intersection (Bentley-Ottmann O(N log N) check). Repeat
until back to start.

### 2.5 — Dispatcher integration
- `ShapeRegistry::engine_default()` adds `SlimeGenerator` (7 kinds total)
- NEW `engine_v3_4_weights()` restores Slime weights per roadmap §14 Q4:
  G=0.05, L=0.05, M=0.05, S=0.10, μ=0.10 (Small/Micro favored — slime is
  best at small organic shapes per research §4)
- `flatworld::generate` default flips from `engine_v3_2_weights()` → `engine_v3_4_weights()`
- `engine_v3_2_weights` retained as `pub` for reproducibility

### 2.6 — Quality filter (per roadmap §11 v3.4)
After steps 1-7, if `total_polygon_area < target_area × 0.25` (degenerate
output — agents all clustered at center or walked off-bounds), reject +
re-seed with salt incremented by retry counter, up to 3 retries. If all
retries fail, fall back to `EllipseGenerator` output (honest downgrade
via `effective_kind = Ellipse`).

---

## 3 — Non-goals
- LLM-driven slime parameters (deferred to v4.4 per PO)
- Per-agent food/pheromone trails (research §6 advanced variants;
  Physarum simulation is overkill for v3.4 — pure random walk suffices)
- Adaptive `alpha` (auto-tune per point cloud) — fixed formula at v3.4
- Multi-component primary clusters (cluster-then-hull) — α-shape natural
  multi-output suffices
- New crate deps — reuse `delaunator` already in tree

---

## 4 — Design

### 4.1 — Module layout

```
crates/world-gen/src/shape/
├── mod.rs            # extend: pub mod slime; pub use slime::{SlimeGenerator, SlimeTemplate};
├── dispatch.rs       # extend: engine_v3_4_weights(); engine_default registers Slime
├── slime.rs          # NEW — multi-agent walk + α-shape + Moreira-Santos + filters
└── ... (unchanged: csg, ellipse, polar, raster, sdf, spine)
```

### 4.2 — Public types

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub enum SlimeTemplate {
    Blob,    // single-component, low persistence
    Branch,  // multi-comp eligible, high persistence
}

impl SlimeTemplate {
    pub fn n_agents(self) -> usize {
        match self { Self::Blob => 6, Self::Branch => 8 }
    }
    pub fn persistence(self) -> f32 {
        match self { Self::Blob => 0.30, Self::Branch => 0.85 }
    }
    pub fn energy(self) -> usize { 8000 }
    pub fn keeps_satellites(self) -> bool {
        matches!(self, Self::Branch)
    }
}

pub struct SlimeGenerator;
impl ShapeGenerator for SlimeGenerator {
    fn kind(&self) -> ShapeKind { ShapeKind::Slime }
    fn generate(&self, ctx: &ShapeContext, _caller: &mut Rng) -> ShapeResult {
        // ... pipeline (§2.3)
    }
}
```

### 4.3 — RNG order discipline
- Internal RNG via `Rng::for_stage(ctx.seed as u64, b"slime")`
- Quality-filter retries use `Rng::for_stage(ctx.seed as u64 ^ retry_count, b"slime")`
- Per-agent walk consumes 1 `next_f32()` per step × N agents × energy = up to 64k draws
- α-shape & Moreira-Santos consume 0 RNG (deterministic algorithms on point cloud)

### 4.4 — Visual fallback
If quality filter exhausts all retries: emit `ShapeResult` with
`polygons = EllipseGenerator.generate(ctx, &mut internal_rng).polygons`
and `effective_kind = ShapeKind::Ellipse` (honest reporting per v3.1c
pattern).

---

## 5 — Acceptance criteria

- [ ] NEW `crates/world-gen/src/shape/slime.rs` ~500 LOC + ~250 LOC tests
- [ ] `SlimeGenerator` implements `ShapeGenerator`
- [ ] `SlimeTemplate::{Blob, Branch}` enum exported
- [ ] `ShapeRegistry::engine_default()` registers 7 generators
- [ ] `engine_v3_4_weights()` restores Slime weights (G=0.05/L=0.05/M=0.05/S=0.10/μ=0.10)
- [ ] `flatworld::generate` default uses v3.4 weights
- [ ] `engine_v3_2_weights` retained as `pub` for reproducibility
- [ ] α-shape primary + Moreira-Santos fallback both implemented + tested
- [ ] Quality filter rejects + reseeds degenerate output; falls back to Ellipse after 3 retries
- [ ] Multi-comp tunable per template (Blob single, Branch multi-eligible)
- [ ] `cargo test --lib -p world-gen` passes (target ≥285 tests, +4 new for slime)
- [ ] `cargo clippy --all-features` clean (≤3 pre-existing warnings tolerated)
- [ ] NEW `v3_4_slime_default_contains_center` regression test (Fixed(Slime) at ≥1 of 5 seeds yields plate with `contains(center)`)
- [ ] Render: 4 PNGs in `eval/compare-v3-4/`: seed 42 plates+biome × {Blob, Branch} via `--force-template`
- [ ] `eval/baselines/v5.7.json` committed
- [ ] PO visual review of 4 PNG samples

---

## 6 — Risks + mitigations

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | α-shape produces multiple disconnected components for SlimeBlob (intended single) | Medium | Multi-comp filter keeps primary only; satellites dropped silently |
| 2 | Moreira-Santos self-intersection at high density | High | Bentley-Ottmann check + reject candidate + try next k-nearest |
| 3 | Quality filter never converges (3 retries all degenerate) | Medium | Fall back to Ellipse w/ effective_kind=Ellipse — honest reporting |
| 4 | Slime CPU cost exceeds budget at full 8000-step × 8-agent | High | Subsample anchors before Delaunay (~1500 pts max); per-plate ~100ms cap with rayon parallelism deferred |
| 5 | RNG order shift breaks hash pins | Expected | Hash pins rebase to v5.5; per-phase ritual |
| 6 | Slime tendrils escape envelope and break climate ownership | Medium | Bounds clamp during walk (envelope × 1.4); polygon stays in plate bbox |
| 7 | Deterministic α-shape requires stable Delaunator output | Low | `delaunator` is deterministic given identical input point order; preserve sort order across runs |

---

## 7 — Implementation order (TDD)

1. `slime.rs` scaffold + `SlimeTemplate` + `SlimeGenerator` struct + module wire-up
2. Multi-agent walk + 3 unit tests (deterministic, bounds-respected, agent-count-honored)
3. Delaunay-based α-shape + 3 tests (single component, multi component, circle smoke)
4. Moreira-Santos fallback + 2 tests (single component, self-intersection avoid)
5. Quality filter + Ellipse fallback + 1 test (degenerate input → Ellipse)
6. Dispatcher integration (`engine_v3_4_weights`, register Slime) + 2 tests
7. `flatworld::generate` default flip + acceptance test
8. CLI `--force-template <blob|branch>` for QC renders
9. Hash pin rebase (after render)
10. Render 5 default seeds + 4 force-slime samples + v5.7 baseline

---

## 8 — File LOC budget

| File | New LOC | Test LOC | Total |
|------|--------:|---------:|------:|
| `shape/slime.rs` | 500 | 250 | 750 |
| `shape/dispatch.rs` | +60 | +20 | 80 |
| `shape/mod.rs` | +5 | 0 | 5 |
| `flatworld.rs` | +25 | +20 | 45 |
| `examples/flatworld.rs` | +12 | 0 | 12 |
| **Total** | **~600** | **~290** | **~890** |

---

## 9 — References
- Research §3 algorithm sketch: `docs/research/2026-05-25-phase-a-research-4-slime-physarum.md`
- Moreira-Santos paper: <https://repositorium.sdum.uminho.pt/bitstream/1822/6429/1/ConcaveHull_ACM_MYS.pdf>
- `delaunator` crate: <https://docs.rs/delaunator/1.0.2/delaunator/>
- Predecessor v3.3 spec: `docs/specs/2026-05-27-flatworld-v3-3-multi-component.md`
