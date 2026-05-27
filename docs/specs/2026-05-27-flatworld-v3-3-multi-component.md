# Spec — Flatworld v3.3 Multi-Component Plates (True Archipelagos)

> **Status:** DRAFT — kickoff 2026-05-27.
> **Parent roadmap:** [`../plans/2026-05-25-phase-a-v3-roadmap.md`](../plans/2026-05-25-phase-a-v3-roadmap.md) §4 Tier 1 row v3.3.
> **Predecessor:** [`2026-05-26-flatworld-v3-2-sdf-marching.md`](2026-05-26-flatworld-v3-2-sdf-marching.md) (v3.2 shipped 250ebf57).
> **Mode:** v2.2 human-in-loop. Branch `geo-generator-amaw`.
> **Size class:** L (files=5, logic=4, side_effects=1).
> **Estimated effort:** 6-8 hours.

---

## 1 — Problem

`Plate.components: Vec<Polygon>` exists since v3.0 schema refactor, but every
generator from v3.0 → v3.2 returns exactly one polygon. The schema slot was
"reserved for v3.3". MarchingNoise in particular rasterizes a noise field
that NATURALLY produces multiple contour rings (an archipelago of small
islands offshore from a main continent), but `raster::field_to_polygon`
explicitly drops everything except the largest by area via `largest_ring()`.

v3.3 unlocks this: when a generator's pipeline produces multiple disjoint
polygons that all clear an area threshold, keep them all in
`Plate.components`. The visual result: Indonesia-style island chains,
Philippine-archipelago-style scatter, Hawai'i-style trails. Per roadmap §11
v3.3, at least one render must show a visibly multi-component plate.

---

## 2 — Goals

### 2.1 — Hybrid component schema (per PO decision 1)

- `Plate.components[0]` = **primary** continent. Owns `zone_sites` /
  `subzone_sites` (Voronoi seeds). Climate computed per-zone as today.
- `Plate.components[1..N]` = **satellites**. Visual-only polygons. **No**
  separate Voronoi zones; they inherit climate from the primary by
  proximity-weighted lookup.
- `Plate.center` stays at the primary's centroid (unchanged).
- `Plate.bounding_box()` returns the union bbox across ALL components
  (already implemented — iterates `self.components`).
- `Plate::contains` already iterates ALL components (works as-is).

### 2.2 — Generators with multi-component output (per PO decision 2)

| Generator | Multi-comp eligible? | Source |
|-----------|----------------------|--------|
| `EllipseGenerator` | No | Inherent single ellipse. |
| `BezierSpineGenerator` | No | Single spine sweep. |
| `PolarGenerator` | No | Single closed curve. |
| `BooleanGenerator` | **Yes** | `geo-clipper` union/diff can produce disjoint polygons. |
| `SdfCapsuleChainGenerator` | **Yes** | When `smin_k` is small relative to capsule spacing, contour splits at unbridged gaps. |
| `MarchingNoiseGenerator` | **Yes** | Noise field naturally produces multi-component archipelagos. |

The 3 eligible generators get a shared "multi-component finalize" pass
that filters rings by area threshold and emits all surviving polygons.

### 2.3 — Multi-component filter (per PO decision 3)

```rust
fn finalize_multi_component(
    rings: Vec<Polygon>,
    bbox: (f32, f32, f32, f32),
    min_area_frac: f32,        // 0.01 = 1% of bbox area per PO
) -> Vec<Polygon> {
    let bbox_area = (bbox.2 - bbox.0) * (bbox.3 - bbox.1);
    let threshold = bbox_area * min_area_frac;
    let mut keep: Vec<Polygon> = rings
        .into_iter()
        .filter(|p| signed_area(p).abs() >= threshold)
        .collect();
    // Sort by descending area so [0] is the primary.
    keep.sort_by(|a, b| {
        signed_area(b).abs().partial_cmp(&signed_area(a).abs()).unwrap()
    });
    keep
}
```

No max-count cap per PO directive — the noise / SDF / Boolean field
decides how many components survive the area filter.

### 2.4 — Climate adaptation for satellites

Satellites must NOT crash `flat_climate` code that iterates `plate.zone_sites`.
Two changes:

1. `Plate::zone_at(x, y)` returns the nearest zone among `zone_sites` IFF
   `(x, y)` is inside `components[0]` (primary). For points inside satellite
   components, returns the nearest zone site in the primary, weighted by
   geometric proximity. This means satellites inherit climate based on the
   "closest" primary zone.
2. Climate metrics (continentality, lat_banding, sanity) — eval framework
   processes pixels by biome ownership. With multi-component plates, a
   pixel can be on a satellite. Since the satellite shares the primary's
   biome assignment, no eval code change is needed at v3.3. v4.5 calibration
   may revisit if satellites need their own metrics.

### 2.5 — Hydrology adaptation

Drainage (`hydrology.rs`) operates on the rendered heightmap. With satellites
adding new land pixels, drainage produces new local rivers automatically.
No code change expected — the hydrology pipeline reads pixels, not plate
structure.

### 2.6 — Render

`render_rgb` / `render_zones_rgb` / `render_all_zones_biome` all already
iterate over plate polygons via point-in-polygon checks. They automatically
handle multi-component plates without modification.

---

## 3 — Non-goals

- **Per-component zone Voronoi** — deferred to v4.1 (zone templating)
  per roadmap. Satellites are visual-only at v3.3.
- **Per-component LLM naming** — deferred to v4.4 (LLM-authored content).
- **Schema break** — `Plate.components` already exists; v3.3 just fills the
  reserve slot.
- **Land area calibration drift correction** — satellites add area;
  eval composite may rise or fall, accepted per PO directive §14 Q6
  ("eval is a tool, not a gate").
- **Hole-in-polygon** — Boolean ring template still single-ring outer; v4 may
  add holes.

---

## 4 — Design

### 4.1 — `raster.rs` — lift "largest only" restriction

Change `field_to_polygon` signature to return `Vec<Polygon>` instead of
`Polygon`. Three call sites:

```rust
// Before (v3.2):
let poly = field_to_polygon(field, bbox, 0.0, 256, 2, 0.005, &mut rng, ctx.center, Some(range));
ShapeResult::single_kind(vec![poly], ShapeKind::MarchingNoise)

// After (v3.3):
let polys = field_to_polygon(field, bbox, 0.0, 256, 2, 0.005, &mut rng, ctx.center, Some(range), 0.01);
ShapeResult::single_kind(polys, ShapeKind::MarchingNoise)
```

The new `min_area_frac` param (last arg) controls the satellite filter.
Internally the pipeline keeps all rings ≥ threshold, sorted by descending area.

Inside `field_to_polygon`:
- Step 3 `stitch_rings` already returns `Vec<Polygon>` — no change needed.
- Step 4 `largest_ring` replaced with `finalize_multi_component`.
- Steps 4-7 (Chaikin, DP, fit, centroid-align, CCW) applied to **each**
  surviving ring. Centroid-align uses `target_center` for primary, and
  each satellite's own centroid as its anchor.

### 4.2 — `sdf.rs` — accept multi-component output

`SdfCapsuleChainGenerator::generate` calls the new `field_to_polygon`. Same
0.01 area threshold. SDF templates with tight `smin_k` (Z-zigzag = 0.10,
Worm-chain = 0.08) may occasionally fragment; templates with high
`smin_k` (Y-branch = 0.15, Crab = 0.20) stay single-component in
practice.

### 4.3 — `csg.rs` — Boolean multi-component

`BooleanGenerator` already uses `geo-clipper`. The Difference / Intersection
templates can yield `MultiPolygon` (disjoint pieces). Currently
the code takes only the largest piece via `bezier_largest_polygon`. Lift to
emit all pieces ≥ area threshold.

### 4.4 — `flatworld.rs` — store multi-component, single shape_kind

```rust
let result = generator.generate(&ctx, &mut rng);
let plate = Plate {
    /* ... */
    components: result.polygons,      // can be N >= 1 now
    shape_kind: result.effective_kind, // SINGLE kind for all components
    /* ... */
};
```

No schema change. `result.polygons` was always `Vec<Polygon>`; v3.3 simply
allows `len > 1`.

### 4.5 — `flat_climate.rs` — handle satellite pixel ownership

The `plate_owner_at(world, x, y)` function does point-in-polygon over all
plates' all components. Already works.

The `zone_at(x, y) -> Option<usize>` on a `Plate` does Voronoi lookup against
`zone_sites`. For a point inside a satellite (where zone_sites isn't tuned),
the lookup still returns a nearest-site result. The climate then inherits
from that primary zone. This is the intended behavior per §2.4.

No code change in `flat_climate.rs` expected (the climate iterates over
pixels, and pixel ownership already routes through `plate_owner_at`).

---

## 5 — RNG order discipline

No new RNG consumption introduced. The new area-filter is deterministic
sort + filter on existing polygon data. Stitching order was already
deterministic via `BTreeMap`.

For multi-component generators, the per-satellite centroid alignment may
consume 0 RNG (each satellite's polygon is positioned by where its
contour lies in the noise/SDF/Boolean field; only the primary's
`target_center` alignment was conditional).

---

## 6 — Acceptance criteria (per roadmap §11 v3.3 + this spec)

- [ ] `raster::field_to_polygon` signature returns `Vec<Polygon>` with new
  `min_area_frac: f32` parameter.
- [ ] `MarchingNoiseGenerator`, `SdfCapsuleChainGenerator`,
  `BooleanGenerator` all use `min_area_frac = 0.01`.
- [ ] `Plate.components.len()` can be > 1 in default render output.
- [ ] All 278 v3.2 tests still pass; +3-5 new tests for multi-component
  handling.
- [ ] `Plate::contains` correctly reports inside-any-component (existing
  behaviour, regression test).
- [ ] `Plate::zone_at` for satellite point returns nearest-primary-zone
  (new test).
- [ ] `cargo clippy --all-features` no new warnings.
- [ ] At least 1 plate per default render seed (13/42/108/256/512) has
  `components.len() > 1`.
- [ ] Render artifacts: 10 PNGs in `eval/compare-v3-3/` (5 seeds ×
  {plates, biome}).
- [ ] Eval baseline `eval/baselines/v5.6.json` committed; v5.5 untouched.
- [ ] PO visual review approves at least one Indonesia-style visible
  multi-component plate.

---

## 7 — Risks + mitigations

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| 1 | Heavy fragmentation: noise field at certain seeds produces 20+ tiny islands → render clutter | Medium | min_area_frac=0.01 (1%) is restrictive enough. Empirical check at seeds 13/42/108/256/512. |
| 2 | Climate `plate_owner_at` ambiguity when two plates' satellites overlap | Low | Existing winner-by-first-encounter logic; new satellites add to the same overlap stack. |
| 3 | Hydrology produces too many "tiny rivers" on micro-islands | Low | Hydrology operates on pixel heightmap; micro-islands naturally generate small features (this is realistic, not a bug). |
| 4 | Hash pins drift again | Expected | Already a per-phase rebase ritual; rebase v5.4 → v5.6 with v3.3 rationale. |
| 5 | Boolean multi-component breaks geo-clipper assumption (it returns MultiPolygon but our code expected Polygon) | Medium | Inspect csg.rs `bezier_largest_polygon` usage. Replace with multi-piece collection + area filter. |
| 6 | SDF multi-component triggers when not intended (template degeneracy) | Low | Templates tuned for single-component output; only Z-zigzag / Worm-chain at high-jitter seeds may fragment. Visual review catches. |
| 7 | Eval composite swing | Expected | Per PO §14 Q6: tool not gate. v5.6 baseline locks at whatever lands. |

---

## 8 — Implementation order (TDD)

1. `raster::field_to_polygon` signature change — return `Vec<Polygon>` with new param. Internal pipeline modified.
2. `raster::finalize_multi_component` new helper + 2 unit tests.
3. Update 3 callers (MarchingNoise, SDF, Boolean) to pass 0.01 threshold + accept Vec output.
4. New test in `raster.rs`: noise field with two distant inside-regions produces 2 polygons.
5. New test in `flatworld.rs`: default seed has ≥1 plate with `components.len() > 1`.
6. Update hash pins after fresh eval baseline.
7. Render 5 seeds, regen v5.6 baseline, visual review.

---

## 9 — Files touched estimate

| File | Change | LOC delta |
|------|--------|-----------|
| `crates/world-gen/src/shape/raster.rs` | API change + finalize helper + tests | +80 |
| `crates/world-gen/src/shape/sdf.rs` | Caller update | +5 |
| `crates/world-gen/src/shape/csg.rs` | Multi-piece collection + filter | +30 |
| `crates/world-gen/src/flatworld.rs` | Multi-component acceptance test | +20 |
| `crates/world-gen/src/zonegen.rs` | Hash pins rebase | +6 |
| **Total** | | ~140 LOC |

---

## 10 — Approval

PO sign-off required on:
- [ ] Acceptance criteria §6
- [ ] Risk #5 (Boolean MultiPolygon handling)
- [ ] Estimated 6-8h schedule alignment with roadmap

After approval → DESIGN-phase plan, then BUILD.

---

## 11 — References

- v3.3 acceptance row: `docs/plans/2026-05-25-phase-a-v3-roadmap.md` §11 v3.3
- Predecessor spec: `docs/specs/2026-05-26-flatworld-v3-2-sdf-marching.md`
- `Plate.components: Vec<Polygon>` schema (since v3.0): `crates/world-gen/src/flatworld.rs:253`
- `geo-clipper` crate for Boolean multi-piece: <https://docs.rs/geo-clipper>
