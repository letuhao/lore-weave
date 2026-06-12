# Spec — 3D world export (glTF globe + 16-bit heightmap)

> **Task size: XL.** Add two export formats to the world-gen CLI so the (already
> 3D-sphere) world can be opened/used in external 3D engines (Blender, Godot,
> Unity): a **16-bit equirectangular heightmap PNG** and a **glTF 2.0 `.glb`
> displaced globe mesh with an embedded biome texture**. Session 100 cont.
> Branch: world-gen-climate-arc (or a fresh export branch).

## 0 — Why

The world MODEL has been a real 3D sphere (3D Voronoi mesh + u16 elevation +
plate tectonics + the climate arc) since the world-tier redesign, but it has only
ever been RENDERED to 2D images. There is no way to view/use it as true 3D. These
two exports bridge that: a heightmap for engine terrain pipelines, and a
self-contained `.glb` you can open and immediately see the 3D planet.

## 1 — Reused primitives (no reinvention)

- `relief::ReliefField::build(map, w, h, RenderStyle::Realistic, Projection::Equirectangular)`
  → per-pixel `elev: Vec<f32>` (normalized ~[0,1]) + `water: Vec<bool>` + `sea: f32`.
- `render::biome_image(map, w, h, Projection::Equirectangular, …)` → equirect biome
  RGB image (the embedded `.glb` texture).
- `projection::Projection::{back_project, equirectangular}` — UV ↔ sphere mapping.
- `image` crate 0.25 (`Luma<u16>` for the heightmap PNG; PNG encode for the texture).
- `serde_json` (already a dep) for the glTF JSON chunk. **No new dependency** — the
  `.glb` container + JSON are hand-rolled (glTF 2.0 is fully specified).

## 2 — Heightmap export

`export::heightmap_png(map, width) -> Vec<u8>` (PNG bytes):
- `height = width / 2` (equirect 2:1). Build a `ReliefField` at `width × height`.
- Pixel value = `(elev.clamp(0,1) * 65535).round() as u16`, written as a 16-bit
  grayscale (`Luma16`) PNG. Row 0 = north (matches `ReliefField` image order).
- CLI: `--heightmap-png <path>` + `--heightmap-width <u32>` (default 2048).
- Document: values are normalized relief elevation (sea level = `map.sea_level/65535`),
  not metres; the engine rescales.

## 3 — glTF `.glb` globe mesh

`export::glb_globe(map, grid_w, grid_h, exaggeration, tex_width) -> Vec<u8>`:

**Mesh (lat/lon UV-sphere grid):** `(grid_w+1) × (grid_h+1)` vertices. For vertex
`(i,j)`: `u = i/grid_w`, `v = j/grid_h`; sphere direction `dir = back_project((u,v))`.
- Sample elevation `e` from a `ReliefField` built at the grid resolution (bilinear,
  u-wrapped). Ocean (`water` / `e < sea`) clamps to `sea` so the sea is a smooth
  sphere and continents rise above it: `r = BASE + max(e, sea) * exaggeration`.
- `position = dir * r`. `BASE = 1.0`; `exaggeration` default `0.06` (planets need
  vertical exaggeration to read; knob `--exaggeration`).
- **Seam:** duplicate the `u=1` column (UV=1.0) so the texture wraps without a gap.
  **Poles:** top/bottom rows collapse to the pole point (degenerate tris accepted).
- **TEXCOORD_0** = `(u, v)` per vertex → indexes the equirect biome texture.
- **Normals:** finite-difference from grid neighbours (proper terrain shading), not
  the radial direction. Normalized.
- **Indices:** 2 triangles per quad, u32, CCW outward.

**Embedded texture:** `biome_image(map, tex_width, tex_width/2, Equirectangular)` →
PNG bytes → a glTF `image` (via a `bufferView`, `mimeType: image/png`) → `sampler`
(wrap U = REPEAT, wrap V = CLAMP) → `texture` → `material.pbrMetallicRoughness
.baseColorTexture` (metallic 0, roughness 1). CLI: `--glb <path>` + `--glb-grid <u32>`
(default 512 → 512×256) + `--glb-texture <u32>` (default 2048) + `--exaggeration <f32>`.

**GLB container (hand-rolled):** 12-byte header (`glTF`, version 2, total len) +
JSON chunk (padded to 4 with `0x20`) + BIN chunk (padded to 4 with `0x00`). BIN
buffer packs: positions f32×3, normals f32×3, texcoords f32×2, indices u32, then the
texture PNG bytes — each as its own `bufferView` with correct `byteOffset`/`byteLength`
and 4-byte alignment. Accessors carry `min`/`max` for POSITION (glTF-required).

## 4 — Files + tests

**Touch:** new `crates/world-gen/src/export.rs` (heightmap + glb + a tiny GLB writer);
`lib.rs` (`pub mod export;`); `main.rs` (CLI flags + wiring). No `content_hash` change
(exports are render-side, like the PNGs — not hashed).

**Tests (`export.rs`):**
- `heightmap_png_is_16bit_and_sized` — decode the bytes, assert `Luma16`, `w×h = width×width/2`.
- `glb_has_valid_container` — magic `glTF`, version 2, declared length == bytes.len(),
  2 chunks (JSON + BIN), JSON parses, chunk lengths 4-aligned.
- `glb_mesh_counts_are_consistent` — accessor counts: positions == normals == texcoords
  == `(grid_w+1)*(grid_h+1)`; index count == `grid_w*grid_h*6`; POSITION accessor has
  min/max.
- `glb_embeds_a_png_texture` — the image bufferView's bytes start with the PNG magic
  `\x89PNG`; material references baseColorTexture.
- `export_is_deterministic` — same seed+params → byte-identical heightmap + glb.
- `ocean_is_clamped_to_sea_level` — a known ocean vertex radius == `BASE + sea*exag`
  (within eps); a known land peak radius > that.

**VERIFY:** lib green; clippy-clean; generate a real `.glb` + heightmap from a seed-7
world and **open the `.glb`** (load via a glTF validator / headless check that it
parses) — evidence the container is valid; eyeball the heightmap PNG.

## 5 — Out of scope

Per-region flat heightmap tiles; OBJ/USD; LOD; 3D rivers/roads as geometry; animated
or textured normal maps; a built-in 3D viewer (export only).
