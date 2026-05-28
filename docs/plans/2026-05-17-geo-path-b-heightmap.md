# Plan — GEO Path B: heightmap rework

**Date:** 2026-05-17 · **Task size:** L (model change + substantial `terrain.rs`
rewrite) · **Branch:** geo-generator-amaw · **Mode:** default v2.2.

## Problem

`terrain::grow_blob` grows each mountain as a BFS with `amp · falloff^r` — a
perfect radial gradient. N blobs → N concentric "bullseye" cones; no ridgelines,
no valleys, no ranges. Path A's render disguises it but cannot fix it — the
defect is in the *model*. This is the actual quality lever.

## Design — a global continuous heightmap function

Replace the blob seeds with `height_at(x, y)` — a pure function of position,
sampled at each cell centre:

1. **Continent base** — low-frequency fBm. The broad landmass.
2. **Mountain ranges** — **ridged-multifractal noise** (`offset − |noise|`,
   squared, multifractal-weighted). Ridged noise crests track the *zero
   crossings* of the noise → sharp linear **ridgelines**, not radial cones.
   This is the bullseye-killer.
3. **Mountain-belt mask** — a low-frequency smoothstep field gating *where*
   ranges rise, so mountains cluster into belts, not blanket the map.
4. **Landness gate** — ranges fade out over deep ocean (mountains rise on
   continental crust, not mid-abyss).
5. **Hills** — mid-frequency fBm, small amplitude — rolling terrain between
   ranges.
6. **Domain warp** — warp `(x,y)` before sampling so ridges curve and branch.

`height_at` is a pure function of position ⇒ a sample-able **global field** —
the property that makes chunking/streaming tractable later (discussed with PO).

### Kept unchanged

`apply_falloff` (coastline-profile masks — Island/Peninsula/Coastal/Inland/
Archipelago still shape *where* land is), the Inland continental dome (folded
into `height_at` via `CoastlineProfile::base_amplitude`), `choose_sea_level`
(connectivity-aware), `enforce_coherence`, u16 normalization, and the entire
downstream pipeline (climate, hydrology, biome, political…) — they consume
elevation, they do not care how it is made.

### Removed

`grow_blob`, `nearest_cell` (blob seeding), `erode` (the blob-banding blur — the
noise heightmap has no concentric banding to wash out). No RNG stream is needed
in `terrain::build` any more — noise is a pure function of position + seed.

## Files

- `crates/world-gen/src/noise.rs` — add `ridged_fbm` (ridged multifractal).
- `crates/world-gen/src/terrain.rs` — rewrite `build`; new `height_at` + a local
  `smoothstep`; remove `grow_blob` / `nearest_cell` / `erode`; keep
  `apply_falloff` / `edge_ramp` / `dist` / `choose_sea_level` /
  `largest_land_component` / `pick_sea_level` / `enforce_coherence` /
  `land_components`.
- `crates/world-gen/src/creative_seed.rs` — refresh the `base_amplitude` doc
  (its "a blob-only heightmap cannot…" rationale is now stale).
- `crates/world-gen/src/biome.rs` / `climate.rs` — **only if** verification
  shows the new elevation distribution breaks a threshold. Verify first.

## Determinism

`content_hash` **changes** — every seed now yields a different, better world.
Expected: an intentional algorithm change. The determinism *invariant* (same
seed + binary → byte-identical) holds — the noise is pure; the determinism test
(two runs identical) still passes. `noise.rs` thus joins the deterministic
model (it was render-only before).

## Verification

- Determinism: `generate` byte-identical across two runs / two processes.
- The `tests/structure.rs` suite stays green — watch especially
  `land_fraction_near_target`, `land_coherence_per_profile`,
  `biome_patch_coherence`, `route_kinds_are_generated` (MountainPass needs
  mountains). Retune `biome.rs` / `climate.rs` thresholds if the new
  distribution breaks an assumption.
- `cargo clippy` clean.
- Regenerate PNGs (Path A relief render) — the terrain should now show
  ridge-and-valley ranges, not bullseye cones. Tune `height_at` constants by
  eye; PO visual sign-off.

## Out of scope (Path B v2)

Hydraulic erosion (carved valleys, dendritic drainage networks). The ridged
ranges are the big quality jump; erosion is realism polish — decided after this.
Mesh resolution stays at the current per-`WorldScale` cell counts (the separate
scale/streaming axis).
