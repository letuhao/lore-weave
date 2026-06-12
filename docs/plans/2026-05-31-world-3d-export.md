# PLAN — 3D world export (glTF + heightmap)

> XL. Spec: [`docs/specs/2026-05-31-world-3d-export.md`](../specs/2026-05-31-world-3d-export.md).

## Build order (crates/world-gen/src/export.rs — new)

1. **GLB writer helpers** (private): `GlbBuilder` accumulating a binary buffer with
   4-byte-aligned `bufferView`s; emits the final `.glb` (header + JSON chunk + BIN
   chunk). JSON built with `serde_json::json!`.
2. **`heightmap_png(map, width) -> Vec<u8>`**: `ReliefField` (equirect) → `Luma16`
   PNG via `image`.
3. **`glb_globe(map, grid_w, grid_h, exaggeration, tex_width) -> Vec<u8>`**:
   - lat/lon vertex grid (+1 seam column duplicated); `dir = back_project((u,v))`.
   - elevation via a grid-res `ReliefField` (bilinear, u-wrap); `r = 1 + max(e,sea)*exag`.
   - positions, finite-difference normals, texcoords `(u,v)`, u32 indices (2 tri/quad).
   - embed `biome_image` PNG bytes as glTF image→sampler→texture→material.
   - assemble GLB.
4. **lib.rs**: `pub mod export;`.
5. **main.rs**: flags `--heightmap-png`/`--heightmap-width` (2048),
   `--glb`/`--glb-grid` (512)/`--glb-texture` (2048)/`--exaggeration` (0.06); wire after
   `generate`.

## Tests (per spec §4)

16-bit heightmap size; GLB container valid (magic/version/len/2 chunks/4-align/JSON
parses); mesh accessor counts consistent + POSITION min/max; embedded PNG magic +
material baseColorTexture; determinism (byte-identical); ocean clamped to sea radius.

## VERIFY

lib green; clippy clean; generate seed-7 `.glb` + heightmap; validate the `.glb` parses
(headless glTF parse / `gltf` reader one-off or python `pygltflib`/struct check);
eyeball heightmap. No content_hash impact.
