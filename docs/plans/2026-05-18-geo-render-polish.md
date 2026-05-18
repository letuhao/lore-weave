# GEO — Render polish

> **Status:** DESIGN → BUILD. Task size **L** (relief.rs + render.rs + tests +
> this plan). Render-only — **no `WorldMap` / `content_hash` change**.
> Default v2.2 workflow, human-in-loop. CLARIFY sign-off (2 PO questions):
> scope = relief engine + palette & coastline · supersample 2× approved.

## 1 — Problem

The relief renderer masks model-scale detail — erosion valleys, Path B ridges,
orographic relief are all built into `WorldMap` but barely read in the PNG.
Two concrete causes, found reading `relief.rs`:

1. **The de-facet blur eats it.** `rasterize_base` barycentric-interpolates
   cell-*centre* elevations → piecewise-linear → faceted → it `box_blur`s with
   radius ≈ ½ cell, 2 passes (≈ a full-cell-wide blur). A 1–2-cell-wide carved
   valley loses much of its depth before it is drawn.
2. **The detail noise is louder than the model.** The fBm detail overlay is
   amplitude 0.055 (Realistic); erosion's mean elevation change is ~0.034
   (normalized). The noise is *bigger* than the signal — and it is modulated
   *up* on highlands, exactly where erosion carved. The eye sees noise.

`ReliefField` feeds the hillshade for every render mode, so one fix improves
relief / biome / political / culture renders together.

## 2 — Design

### A. Supersampling 2× (`render.rs`)

Each public `*_image` fn renders at `SS·width × SS·height` (`SS = 2`), then
box-downsamples to `width × height`. Anti-aliases coastlines and the hillshade,
and lets the detail noise be sampled finer. `ReliefField::build` is unchanged —
it is simply called with the hi-res dimensions; relief.rs unit tests (which
call `build` directly) are unaffected.

- New `downsample(img: &RgbImage, factor: u32) -> RgbImage` — each output pixel
  is the mean of its `factor × factor` source block. Deterministic.
- Public fns become thin wrappers: `relief_image` = `downsample(render at
  SS×, SS)`; the existing body moves to a private hi-res renderer.
- `draw_coast_outline` runs at hi-res → the downsample anti-aliases it.

### B. Complementary detail noise (`relief.rs`)

The detail fBm should **fill** where the model is smooth and **recede** where
the model already has relief — the opposite of today's highland boost. The
`build` loop is restructured into two passes:

1. warp + sample the base → a `base` buffer (per pixel);
2. measure *local base relief* as a **high-pass** of the base — `base_lo =
   box_blur(base, ≈1 cell)`, then `local_relief = |base − base_lo|`. This is
   O(W·H) (a windowed max−min per pixel would be O(W·H·window²) — too slow at
   2× res); it is ~0 on flat ground and high over carved valleys / ridges;
3. per pixel: `detail_weight = 1 − smoothstep(lo, hi, local_relief)` (a pure,
   unit-testable helper); `elev = base + detail_amp · ocean_gate ·
   detail_weight · fbm(…)` — full detail on genuinely flat ground, suppressed
   over model structure.

`detail_amp` is also lowered so detail is a supporting texture, not the
headline. Net: the model's own carved structure reads; detail only dresses the
coarse-mesh flats.

### C. De-facet blur — gentler (`relief.rs`)

With detail no longer drowning the model and supersampling providing AA, the
`box_blur` de-facet radius is reduced (from `facet·0.5`) so more cell-scale
relief survives. Final radius tuned at VERIFY against the relief PNG.

### D. Hillshade concavity term (`relief.rs`)

Add an ambient-occlusion-style darkening of concave-up valley floors — the
most direct way to surface erosion. The concavity measure reuses the signed
high-pass from §B: `hp = base − base_lo` is negative in valley floors
(a Laplacian-of-Gaussian-style proxy at valley scale, computed on the **base**
buffer so fBm detail does not register as curvature). `shade = lambert ·
occlusion`, where `occlusion = 1 − k·smoothstep(0, OCC_RELIEF, −hp)` with
`k < 1` ⇒ `shade ∈ [0,1]`.

### E. Palette & coastline (`render.rs`)

Retune `land_color` / `water_color` hypsometric ramps per style for clearer
elevation legibility (more distinct bands so relief reads), and a soft coastal
shallows band in `water_color`. Subjective — tuned at VERIFY.

### Determinism

Every step is deterministic: `SS` supersample + box `downsample` are fixed
arithmetic; detail noise is sampled in model coordinates (resolution-stable);
the Laplacian reads the `elev` buffer. A rendered PNG stays byte-reproducible.

## 3 — Files

| # | File | Change |
|---|------|--------|
| 1 | `crates/world-gen/src/render.rs` | `SS` const, supersample wrappers + `downsample`, palette/water retune |
| 2 | `crates/world-gen/src/relief.rs` | two-pass build (complementary detail), de-facet tuning, hillshade concavity term |
| 3 | tests | inline in render.rs + relief.rs |
| 4 | `docs/plans/2026-05-18-geo-render-polish.md` | this plan |

## 4 — Acceptance criteria

1. Every `*_image` fn returns exactly `width × height` (supersampling is
   internal and invisible to callers).
2. Rendering is deterministic — same `(map, dims, style)` → byte-identical
   image (existing `build_is_deterministic` + a render-level determinism check).
3. `downsample` averages each `SS×SS` block correctly (unit test on a known
   pattern).
4. Detail is complementary — the modulation function returns less detail for a
   high-local-relief input than a flat one (unit test).
5. Hillshade with the concavity term stays in `[0,1]` (`shade_is_in_unit_range`
   still holds).
6. Existing relief/render tests stay green.
7. VERIFY (visual): erosion valleys / Path B ridges read clearly in the relief
   PNG vs. the pre-polish render; coastlines anti-aliased; palette legible.

## 5 — Build order

1. `render.rs` — `SS` + `downsample` + wrap the four `*_image` fns.
2. `relief.rs` — two-pass build with complementary detail modulation.
3. `relief.rs` — hillshade concavity term; reduce de-facet blur.
4. `render.rs` — palette / water-shallows retune.
5. VERIFY — `cargo test` + `clippy`; render before/after PNGs across styles +
   erosion strengths, tune the de-facet radius, detail amp, concavity `k`, and
   palette stops against the result.
