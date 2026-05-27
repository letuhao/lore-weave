# Spec — Flatworld v3.5 Coastline Fractalize (Mandelbrot Hausdorff)

> **Status:** DRAFT — kickoff 2026-05-28.
> **Parent roadmap:** [`../plans/2026-05-25-phase-a-v3-roadmap.md`](../plans/2026-05-25-phase-a-v3-roadmap.md) §4 Tier 1 v3.5.
> **Scope redirect:** PO replaced original v3.5 ("Stamps library") with **Coastline Fractalize** during v3.4 POST-REVIEW (`docs/specs/2026-05-27-flatworld-v3-4-slime-physarum.md` Round 3). Stamps deferred to v3.6+.
> **Predecessor:** [`2026-05-27-flatworld-v3-4-slime-physarum.md`](2026-05-27-flatworld-v3-4-slime-physarum.md) (v3.4 shipped 53766c2f).
> **Mode:** v2.2 human-in-loop. Branch `geo-generator-amaw`.
> **Size:** L (files=5, logic=4, side_effects=1). Estimated 4-6h.

---

## 1 — Problem

After v3.4 every plate generator (Ellipse, Bezier, Polar, Boolean, SDF,
MarchingNoise, Slime) produces decent shapes but with **smooth polygonal
coasts** — straight line segments between vertices. Real coastlines have
**self-similar detail at all scales** (Mandelbrot 1967, "How long is the
coast of Britain?"; Hausdorff dimension ≈ 1.25 for actual coastlines vs
1.0 for smooth curves).

v3.5 ships a **universal post-process** that applies fractal noise to
every plate polygon (regardless of generator), bringing coasts closer to
the Hausdorff-1.25 ideal.

---

## 2 — PO decisions (CLARIFY 2026-05-28)

1. **POST vertex-count fit** — Each generator's output is first clamped
   to `ctx.vertex_count_range` (24-48 typical), THEN fractalize explodes
   vertex count via midpoint displacement. Final polygon has high
   fidelity but exceeds the input range — this is the design choice.
2. **Decay-per-iteration** — Standard midpoint displacement: offset
   amplitude multiplies by `0.5^iter` so each recursion halves. Classic
   self-similar fractal, predictable, controlled.
3. **Per-template config** — FlatParams flag `fractalize_satellites: bool`
   (default true). PO can override per-render to compare visual.

---

## 3 — Goals

### 3.1 — `shape/coastline.rs` NEW module (~150 LOC)

Public API:

```rust
pub struct FractalizeConfig {
    /// 0.0 = no fractalize; 1.0 = max chaos. Calibrated so 0.5 produces
    /// recognisable but not overpowering coast detail.
    pub roughness: f32,
    /// Midpoint displacement iterations (0-5). Each iteration roughly
    /// doubles vertex count.
    pub iterations: usize,
    /// Perlin frequency scale for the final warp pass (cycles per envelope).
    /// Default 8.0 = 8 fine wiggles per plate diameter.
    pub perlin_freq: f32,
    /// Apply to satellite components (multi-comp plates)? Default true.
    pub apply_to_satellites: bool,
}

impl Default for FractalizeConfig {
    fn default() -> Self {
        Self {
            roughness: 0.35,         // moderate default
            iterations: 3,           // 8× vertex count
            perlin_freq: 8.0,
            apply_to_satellites: true,
        }
    }
}

/// Apply hybrid midpoint-displacement + Perlin-warp fractalize to a
/// polygon. Output has roughly `input_len × 2^iterations` vertices plus
/// the per-vertex Perlin warp.
pub fn fractalize_polygon(
    poly: &Polygon,
    config: &FractalizeConfig,
    noise_salt: u32,
    rng: &mut Rng,
) -> Polygon;
```

### 3.2 — Algorithm

```
fn fractalize_polygon(poly, config, noise_salt, rng):
    // Stage A: midpoint displacement
    current = poly.clone()
    base_amp = config.roughness * avg_edge_length(poly)
    for iter in 0..config.iterations:
        amp = base_amp * 0.5^iter           // decay per PO #2
        next = Vec::with_capacity(current.len() × 2)
        for i in 0..current.len():
            p = current[i]
            q = current[(i+1) % current.len()]
            next.push(p)
            // Midpoint + perpendicular offset
            edge_dx = q.0 - p.0
            edge_dy = q.1 - p.1
            edge_len = sqrt(edge_dx² + edge_dy²)
            mid = ((p.0+q.0)/2, (p.1+q.1)/2)
            // Perpendicular unit (rotated 90° CCW): (-dy, dx)/edge_len
            perp = (-edge_dy / edge_len, edge_dx / edge_len)
            // Gaussian-ish offset: (rng - 0.5) × 2 × amp ∈ [-amp, +amp]
            offset = (rng.next_f32() - 0.5) * 2.0 * amp
            mid_displaced = (mid.0 + perp.0 * offset, mid.1 + perp.1 * offset)
            next.push(mid_displaced)
        current = next

    // Stage B: Perlin/fbm warp (universal micro-detail)
    bbox = compute_bbox(current)
    bbox_diag = bbox_diagonal(bbox)
    warp_amp = config.roughness * bbox_diag * 0.01
    for i in 0..current.len():
        p = current[i]
        n_x = fbm(p.0 * config.perlin_freq / bbox_diag, p.1 * config.perlin_freq / bbox_diag, noise_salt, 3)
        n_y = fbm(p.0 * config.perlin_freq / bbox_diag, p.1 * config.perlin_freq / bbox_diag, noise_salt ^ 0xCAFE, 3)
        current[i] = (p.0 + n_x * warp_amp, p.1 + n_y * warp_amp)

    current
```

### 3.3 — Integration

`flatworld::generate` wraps each generator call:

```rust
let mut result = generator.generate(&ctx, &mut plate_rng);
if params.coastline.enabled {
    let rng = &mut Rng::for_stage(plate_seed as u64, b"coastline");
    let salt = ctx.plate_salt.wrapping_add(0xC047_5712);
    let primary = std::mem::take(&mut result.polygons[0]);
    result.polygons[0] = fractalize_polygon(&primary, &params.coastline, salt, rng);
    if params.coastline.apply_to_satellites {
        for i in 1..result.polygons.len() {
            let sat = std::mem::take(&mut result.polygons[i]);
            result.polygons[i] = fractalize_polygon(&sat, &params.coastline, salt.wrapping_add(i as u32), rng);
        }
    }
}
```

### 3.4 — FlatParams config

```rust
pub struct FlatParams {
    /* ... existing fields ... */
    pub coastline: CoastlineParams,
}

pub struct CoastlineParams {
    pub enabled: bool,                   // default true
    pub roughness: f32,                  // default 0.35
    pub iterations: usize,               // default 3
    pub perlin_freq: f32,                // default 8.0
    pub apply_to_satellites: bool,       // default true
}
```

### 3.5 — CLI extension

`examples/flatworld.rs` adds:
- `--coastline-roughness <0..1>` (override default 0.35)
- `--coastline-iter <0..5>` (override default 3)
- `--no-coastline` (set enabled=false for v3.4 comparison)

### 3.6 — Test adaptation

`flatworld::tests::phase_a_defaults_use_high_vertex_count` currently
asserts plate primary vertex count ≤ max_vertices (48). With fractalize
post-process at iterations=3, vertex count grows ~8× → 192-384 vertices.
**The test must relax**: assert vertex count is in `[min_vertices, MAX_HARD_CAP]`
where MAX_HARD_CAP = max_vertices × 16 ≈ 768. Or split into "pre-fractalize"
and "post-fractalize" assertions.

---

## 4 — Non-goals

- LLM-driven roughness (defer to v4.4)
- Self-intersection avoidance (midpoint displacement at moderate roughness
  doesn't self-intersect under typical configs; if visible at high
  roughness, add Bentley-Ottmann check in v4)
- Adaptive iterations (auto-tune from input polygon size) — fixed 3 default
- Stamps (deferred to v3.6 or later per PO redirect)

---

## 5 — Acceptance criteria

- [ ] NEW `crates/world-gen/src/shape/coastline.rs` ~150 LOC + ~100 LOC tests
- [ ] `fractalize_polygon` deterministic for `(input, config, salt, rng)`
- [ ] `CoastlineParams` + `FractalizeConfig` in FlatParams
- [ ] `flatworld::generate` invokes fractalize per plate when enabled
- [ ] CLI flags `--coastline-roughness/--coastline-iter/--no-coastline` work
- [ ] `phase_a_defaults_use_high_vertex_count` test adapted for post-fractalize vertex count
- [ ] `cargo test --lib -p world-gen` passes (≥291 tests, +2 for coastline)
- [ ] `cargo clippy --all-features` no new warnings
- [ ] NEW `coastline_increases_vertex_count_predictably` test
- [ ] NEW `coastline_disabled_byte_identical_to_v3_4` test (verify roundtrip)
- [ ] Render: 5 default seeds + 4 comparison renders (roughness 0.0/0.35/0.7/1.0 at seed 42)
- [ ] `eval/baselines/v5.8.json` committed
- [ ] PO visual review of fractalize ON vs OFF + roughness sweep

---

## 6 — Risks + mitigations

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | Vertex count explodes → slow render | Medium | Cap iterations at 5; default 3 keeps polygons under ~400 vertices |
| 2 | Self-intersection at high roughness (offset > edge_len/2) | High | Per-iteration amplitude decay (0.5^iter) keeps later iterations from over-displacing already-displaced points |
| 3 | Hash pin tests drift again | Expected | Rebase v5.5 → v5.6 with v3.5 rationale |
| 4 | Climate eval regresses further (coast detail = more lat-band mixing) | Expected | Per PO directive §14 Q6: tool not gate. v4.5 calibration handles |
| 5 | `phase_a_defaults_use_high_vertex_count` test break | Expected | Spec §3.6 adaptation: assert vertex count ≤ max_vertices × 16 |
| 6 | Per-vertex Perlin warp at low roughness over-smooths | Low | warp_amp scales linearly with roughness; at roughness=0 no warp |

---

## 7 — Implementation order (TDD)

1. `shape/coastline.rs` skeleton + `FractalizeConfig` + `fractalize_polygon` signature
2. Midpoint displacement core + 2 unit tests (vertex count grows, deterministic)
3. Perlin warp final pass + 1 test (warp amplitude scales with roughness)
4. `CoastlineParams` in `FlatParams` + default value
5. `flatworld::generate` integration + 1 integration test
6. CLI flags in `examples/flatworld.rs`
7. Update vertex-count regression test for post-fractalize counts
8. Hash pin rebase after render

---

## 8 — File LOC budget

| File | New LOC | Test LOC | Total |
|------|--------:|---------:|------:|
| `shape/coastline.rs` | 150 | 100 | 250 |
| `shape/mod.rs` | +3 | 0 | 3 |
| `flatworld.rs` | +30 | +25 | 55 |
| `examples/flatworld.rs` | +20 | 0 | 20 |
| `zonegen.rs` | +6 | 0 | 6 |
| **Total** | **~210** | **~125** | **~335** |

---

## 9 — References
- Mandelbrot 1967 — "How long is the coast of Britain? Statistical self-similarity and fractional dimension" Science 156:636
- Hausdorff dimension calculation for fractal coastlines: H = 1 + log2(2 × roughness)
- Predecessor v3.4 spec: `docs/specs/2026-05-27-flatworld-v3-4-slime-physarum.md`
- Existing `crate::noise::fbm` for Perlin warp lookup
