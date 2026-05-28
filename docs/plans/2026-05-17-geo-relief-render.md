# Plan — GEO relief render (Path A: render-only quality lift)

**Date:** 2026-05-17 · **Task size:** L (5 source files + tests, CLI-surface change) ·
**Branch:** geo-generator-amaw · **Mode:** default v2.2 (not /amaw — render-only, no
content-hash / API / DB impact).

## Problem

The generated PNGs look like a procedural toy. Root causes diagnosed in the
discussion:

1. **Flat-shaded Voronoi cells** — `render::rasterize` is nearest-cell, so every
   pixel in a cell is one flat colour → crystalline mosaic.
2. **No relief** — `shade` colours by elevation height only; no hillshade, so
   mountains are flat grey blobs.
3. **Bullseye terrain** — `terrain::grow_blob` lays perfect radial gradients;
   biome thresholds turn them into concentric rings. A *model* defect (Path B),
   but render-time **domain warping** can substantially disguise it.
4. **No mid-frequency detail** — the heightmap has 2 frequency bands (blobs +
   1-cell noise). The 8 k-cell mesh structurally cannot hold more.

Path A fixes 1, 2, partly 3, and 4 *at render time only*. The renderer is
explicitly **not** part of `WorldMap` / `content_hash` (see `render.rs` header),
so there is zero determinism risk to the model.

## Design — one engine, four render modes

A continuous per-pixel elevation buffer; every render mode is a function of it.

Pipeline per render call (`ReliefField::build`):

1. **Re-triangulate** the cell centres at render time (`delaunator`, already a
   dep). The cell set includes the perimeter ring at the exact map edges, so the
   triangulation tiles the whole unit square — every pixel lands in a triangle.
2. **Rasterize** each triangle, barycentric-interpolating its 3 corner
   elevations → `base_raw[w·h]` (normalized `f32`). Kills the flat mosaic.
3. **Domain warp** — resample `base_raw` at `(px,py)` displaced by low-frequency
   fBm. Wobbles the concentric blob rings into irregular shapes → disguises the
   bullseye. Render-only; `base_raw` stays untouched.
4. **fBm detail** — seeded multi-octave gradient noise, modulated (≈0 in open
   ocean, full in highlands) → `elev = warped_base + detail`.
5. **Hillshade** — gradient of `elev`, surface normal, NW sun dot product →
   `shade[w·h]`. The linchpin: detail noise is near-invisible as colour; the
   hillshade reacting to its micro-slopes is what renders rugged relief.
6. Each mode composites `base_colour · shade`.

### Key decisions

- **Barycentric over a render-time re-triangulation**, not IDW — correct
  piecewise-linear interpolation, continuous across cell edges, no model change.
- **Hand-rolled Perlin-style gradient noise** (`noise.rs`), not the `noise`
  crate — zero new deps, full determinism control, matches the crate's
  hand-rolled RNG. Seeded from `WorldMap.seed`.
- Noise sampled in **model `[0,1]²` coords** → `--png-size` changes sampling
  fineness, not the world. Same terrain at any output resolution.
- **SVG export unchanged** — vector political export; hillshade is raster.
- `land_sea_image` is **replaced** by `relief_image` (its only consumers are the
  crate's own CLI + tests; `publish = false`, no external API).

### `--style` switches palette + coastline + contrast only (engine identical)

| | realistic | atlas |
|---|---|---|
| land palette | green → tan → umber → grey → snow | muted cream → tan → brown → grey |
| coastline | natural fractal edge (`warped_base + detail` crossing) | smooth (`warped_base` crossing) + thin ink outline |
| hillshade | strong contrast | soft, low-contrast |

## Files

- **NEW** `crates/world-gen/src/noise.rs` — gradient noise + fBm + tests.
- **NEW** `crates/world-gen/src/relief.rs` — `ReliefField` engine, `RenderStyle`
  enum + tests.
- `crates/world-gen/src/render.rs` — `relief_image` (hypsometric); hillshade
  composited into biome/political/culture; old `shade`/`land_ramp`/
  `land_sea_image` removed.
- `crates/world-gen/src/lib.rs` — `pub mod noise; pub mod relief;`, re-export
  `RenderStyle`.
- `crates/world-gen/src/main.rs` — `--style realistic|atlas` (default
  realistic), `--relief-png <path>`, `StyleArg` mirror enum.

## Verification

- `noise`: deterministic (same args → identical bits), gradient noise = 0 at
  lattice points, fBm non-constant + bounded.
- `relief`: `elev`/`shade` length = `w·h`, no NaN, `shade ∈ [0,1]`,
  deterministic, realistic ≠ atlas.
- `render`: `relief_image` dimensions, shows land+water, styles differ,
  byte-identical for same `(seed, style, size)`.
- Existing 68 tests stay green; `cargo clippy` clean.
- Generate before/after PNGs (continent + island, both styles) for visual sign-off.

## Out of scope (follow-ups)

- Tapered river curves on the relief map.
- Marching-squares coastline curve-fitting (atlas uses interpolated-mesh coast +
  ink outline for now).
- Path B — fixing the bullseye in the *model* (fBm heightmap + erosion).
- Satellite-style photo-texture splatting.
