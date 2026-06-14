//! 3D world export — a glTF 2.0 `.glb` displaced globe mesh and a 16-bit
//! equirectangular heightmap PNG.
//!
//! The world model has been a real 3D sphere (3D Voronoi mesh + `u16` elevation)
//! since the world-tier redesign, but it had only ever been rendered to 2D
//! images. These exports bridge it to external 3D engines (Blender, Godot,
//! Unity): a heightmap for terrain pipelines, and a self-contained `.glb` you can
//! open and immediately see the 3D planet (continents displaced above a smooth
//! sea, painted with an embedded equirectangular biome texture).
//!
//! Both reuse existing primitives: [`ReliefField`] for the per-pixel elevation,
//! [`crate::render::biome_image`] for the embedded texture, and
//! [`Projection`] for the UV↔sphere mapping. The `.glb` container + glTF JSON are
//! hand-rolled (glTF 2.0 is fully specified) so no new dependency is needed.

use std::io::Cursor;

use image::{DynamicImage, ImageBuffer, ImageFormat, Luma};
use serde_json::json;

use crate::params::RenderTheme;
use crate::projection::Projection;
use crate::relief::{ReliefField, RenderStyle};
use crate::render::{biome_image, plate_image, realm_image, region_image};
use crate::world_map::WorldMap;

/// Base radius of the exported globe (sea level sits near this; land rises above
/// it by the exaggerated elevation).
const BASE_RADIUS: f32 = 1.0;

/// Which map layer paints the exported globe's embedded texture. The geometry
/// (elevation displacement) is identical across modes — only the surface colour
/// changes, so a `Region`/`Realm`/`Plate` globe shows the *structural hierarchy*
/// (continents → subcontinents → regions, or the political tiers, or the
/// tectonic plates) draped over the real 3D terrain, instead of biome colour.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColorMode {
    /// Biome / climate colour (the default).
    Biome,
    /// Region choropleth — continent/subcontinent/region boundaries.
    Region,
    /// Political-tier choropleth — province fill + realm/state outlines.
    Realm,
    /// Tectonic plates — continental/oceanic tint + plate boundaries.
    Plate,
}

impl ColorMode {
    /// Render the equirectangular texture for this colour mode.
    fn texture(self, map: &WorldMap, w: u32, h: u32, theme: &RenderTheme) -> image::RgbImage {
        let (st, pr) = (RenderStyle::Realistic, Projection::Equirectangular);
        match self {
            ColorMode::Biome => biome_image(map, w, h, st, pr, theme),
            ColorMode::Region => region_image(map, w, h, st, pr, theme),
            ColorMode::Realm => realm_image(map, w, h, st, pr, theme),
            ColorMode::Plate => plate_image(map, w, h, st, pr, theme),
        }
    }
}

// ── Heightmap ───────────────────────────────────────────────────────────────

/// Encode a **16-bit grayscale equirectangular heightmap** PNG of `map`.
///
/// `width × (width/2)` (the equirect 2:1 aspect). Pixel value = the normalized
/// relief elevation `∈ [0,1]` scaled to `0..=65535`; row 0 is north. Sea level is
/// `map.sea_level / 65535` in the same normalized space — the engine rescales to
/// metres as it likes.
pub fn heightmap_png(map: &WorldMap, width: u32) -> Vec<u8> {
    let width = width.max(2);
    let height = (width / 2).max(1);
    let relief = ReliefField::build(
        map,
        width,
        height,
        RenderStyle::Realistic,
        Projection::Equirectangular,
    );
    let mut img: ImageBuffer<Luma<u16>, Vec<u16>> = ImageBuffer::new(width, height);
    for (i, px) in img.pixels_mut().enumerate() {
        let e = relief.elev[i].clamp(0.0, 1.0);
        *px = Luma([(e * 65535.0).round() as u16]);
    }
    encode_png(DynamicImage::ImageLuma16(img))
}

fn encode_png(img: DynamicImage) -> Vec<u8> {
    let mut bytes = Vec::new();
    img.write_to(&mut Cursor::new(&mut bytes), ImageFormat::Png)
        .expect("in-memory PNG encode never fails");
    bytes
}

// ── glTF .glb globe ───────────────────────────────────────────────────────────

/// Build a glTF 2.0 binary (`.glb`) of `map` as a displaced globe mesh with an
/// embedded equirectangular biome texture.
///
/// - A lat/lon UV-sphere vertex grid `(grid_w+1) × (grid_h+1)` (the `u=1` seam
///   column is duplicated so the texture wraps without a gap; the poles collapse).
/// - Each vertex is displaced radially by `BASE + max(elev, sea) · exaggeration`,
///   so the ocean is a smooth sphere at sea level and continents rise above it.
/// - Smooth per-vertex normals (accumulated face normals) for terrain shading;
///   `TEXCOORD_0 = (u, v)` indexes the embedded biome PNG.
#[allow(clippy::too_many_arguments)]
pub fn glb_globe(
    map: &WorldMap,
    grid_w: u32,
    grid_h: u32,
    exaggeration: f32,
    tex_width: u32,
    color: ColorMode,
    theme: &RenderTheme,
) -> Vec<u8> {
    let grid_w = grid_w.max(2);
    let grid_h = grid_h.max(2);
    let cols = grid_w + 1; // +1 duplicated seam column
    let rows = grid_h + 1;
    let nverts = (cols * rows) as usize;

    // Sample elevation from a relief field at the grid resolution.
    let relief = ReliefField::build(
        map,
        grid_w,
        grid_h,
        RenderStyle::Realistic,
        Projection::Equirectangular,
    );

    let mut positions: Vec<[f32; 3]> = Vec::with_capacity(nverts);
    let mut texcoords: Vec<[f32; 2]> = Vec::with_capacity(nverts);
    for j in 0..rows {
        let v = j as f32 / grid_h as f32;
        // Wrap/clamp the sample pixel: the seam column (i==grid_w) reuses column
        // 0; the bottom row (j==grid_h) reuses the last pixel row.
        let py = (j.min(grid_h - 1)) as usize;
        for i in 0..cols {
            let u = i as f32 / grid_w as f32;
            let dir = Projection::Equirectangular
                .back_project((u, v))
                .unwrap_or([0.0, 0.0, 1.0]);
            let px = (i % grid_w) as usize;
            let ridx = py * grid_w as usize + px;
            let e = relief.elev[ridx];
            let h = if relief.water[ridx] {
                relief.sea
            } else {
                e.max(relief.sea)
            };
            let r = BASE_RADIUS + h * exaggeration;
            positions.push([dir[0] * r, dir[1] * r, dir[2] * r]);
            texcoords.push([u, v]);
        }
    }

    // Indices — 2 triangles per quad, CCW seen from outside.
    let idx = |i: u32, j: u32| j * cols + i;
    let mut indices: Vec<u32> = Vec::with_capacity((grid_w * grid_h * 6) as usize);
    for j in 0..grid_h {
        for i in 0..grid_w {
            let v00 = idx(i, j);
            let v10 = idx(i + 1, j);
            let v01 = idx(i, j + 1);
            let v11 = idx(i + 1, j + 1);
            indices.extend_from_slice(&[v00, v01, v11, v00, v11, v10]);
        }
    }

    let normals = smooth_normals(&positions, &indices);

    let tex_width = tex_width.max(2);
    let tex_png = encode_png(DynamicImage::ImageRgb8(color.texture(
        map,
        tex_width,
        (tex_width / 2).max(1),
        theme,
    )));

    assemble_glb(&positions, &normals, &texcoords, &indices, &tex_png)
}

/// Smooth per-vertex normals = normalized sum of incident face normals. Robust
/// to the seam/pole degeneracy (a zero-area face contributes a zero vector).
fn smooth_normals(positions: &[[f32; 3]], indices: &[u32]) -> Vec<[f32; 3]> {
    let mut normals = vec![[0.0f32; 3]; positions.len()];
    for tri in indices.chunks_exact(3) {
        let (a, b, c) = (tri[0] as usize, tri[1] as usize, tri[2] as usize);
        let (pa, pb, pc) = (positions[a], positions[b], positions[c]);
        let e1 = sub(pb, pa);
        let e2 = sub(pc, pa);
        let n = cross(e1, e2);
        for &v in &[a, b, c] {
            normals[v] = add(normals[v], n);
        }
    }
    for (v, n) in normals.iter_mut().enumerate() {
        let len = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt();
        if len > 1e-9 {
            n[0] /= len;
            n[1] /= len;
            n[2] /= len;
        } else {
            // Degenerate (pole) vertex — fall back to the radial outward
            // direction (the normalized position), correct at BOTH poles.
            let p = positions[v];
            let pl = (p[0] * p[0] + p[1] * p[1] + p[2] * p[2]).sqrt().max(1e-9);
            *n = [p[0] / pl, p[1] / pl, p[2] / pl];
        }
    }
    normals
}

fn sub(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}
fn add(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
}
fn cross(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

/// Accumulates a 4-byte-aligned binary buffer and records each region as a glTF
/// `bufferView`.
struct BinBuffer {
    bytes: Vec<u8>,
    views: Vec<serde_json::Value>,
}

impl BinBuffer {
    fn new() -> Self {
        BinBuffer {
            bytes: Vec::new(),
            views: Vec::new(),
        }
    }

    /// Append a region, 4-byte aligned, and return its `bufferView` index.
    /// `target` is the glTF buffer target (34962 ARRAY_BUFFER, 34963
    /// ELEMENT_ARRAY_BUFFER) or `None` (e.g. the embedded image).
    fn push(&mut self, data: &[u8], target: Option<u32>) -> usize {
        while self.bytes.len() % 4 != 0 {
            self.bytes.push(0);
        }
        let offset = self.bytes.len();
        self.bytes.extend_from_slice(data);
        let mut view = json!({
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": data.len(),
        });
        if let Some(t) = target {
            view["target"] = json!(t);
        }
        let index = self.views.len();
        self.views.push(view);
        index
    }
}

fn f32x3_le(v: &[[f32; 3]]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 12);
    for p in v {
        for c in p {
            b.extend_from_slice(&c.to_le_bytes());
        }
    }
    b
}
fn f32x2_le(v: &[[f32; 2]]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 8);
    for p in v {
        for c in p {
            b.extend_from_slice(&c.to_le_bytes());
        }
    }
    b
}
fn u32_le(v: &[u32]) -> Vec<u8> {
    let mut b = Vec::with_capacity(v.len() * 4);
    for &x in v {
        b.extend_from_slice(&x.to_le_bytes());
    }
    b
}

/// Per-component `[min, max]` over a list of 3-vectors — glTF requires these on
/// the POSITION accessor.
fn bounds3(v: &[[f32; 3]]) -> ([f32; 3], [f32; 3]) {
    let mut lo = [f32::INFINITY; 3];
    let mut hi = [f32::NEG_INFINITY; 3];
    for p in v {
        for k in 0..3 {
            lo[k] = lo[k].min(p[k]);
            hi[k] = hi[k].max(p[k]);
        }
    }
    (lo, hi)
}

/// Assemble the final `.glb` (12-byte header + JSON chunk + BIN chunk).
fn assemble_glb(
    positions: &[[f32; 3]],
    normals: &[[f32; 3]],
    texcoords: &[[f32; 2]],
    indices: &[u32],
    tex_png: &[u8],
) -> Vec<u8> {
    let mut bin = BinBuffer::new();
    let bv_pos = bin.push(&f32x3_le(positions), Some(34962));
    let bv_nrm = bin.push(&f32x3_le(normals), Some(34962));
    let bv_uv = bin.push(&f32x2_le(texcoords), Some(34962));
    let bv_idx = bin.push(&u32_le(indices), Some(34963));
    let bv_img = bin.push(tex_png, None);

    let (pmin, pmax) = bounds3(positions);
    let accessors = json!([
        { "bufferView": bv_pos, "componentType": 5126, "count": positions.len(),
          "type": "VEC3", "min": pmin, "max": pmax },
        { "bufferView": bv_nrm, "componentType": 5126, "count": normals.len(), "type": "VEC3" },
        { "bufferView": bv_uv, "componentType": 5126, "count": texcoords.len(), "type": "VEC2" },
        { "bufferView": bv_idx, "componentType": 5125, "count": indices.len(), "type": "SCALAR" },
    ]);

    let gltf = json!({
        "asset": { "version": "2.0", "generator": "lore-weave world-gen export" },
        "scene": 0,
        "scenes": [ { "nodes": [0] } ],
        "nodes": [ { "mesh": 0, "name": "world" } ],
        "meshes": [ {
            "name": "globe",
            "primitives": [ {
                "attributes": { "POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2 },
                "indices": 3,
                "material": 0,
                "mode": 4
            } ]
        } ],
        "materials": [ {
            "name": "biome",
            "pbrMetallicRoughness": {
                "baseColorTexture": { "index": 0 },
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0
            }
        } ],
        "textures": [ { "sampler": 0, "source": 0 } ],
        "images": [ { "bufferView": bv_img, "mimeType": "image/png" } ],
        "samplers": [ { "wrapS": 10497, "wrapT": 33071 } ],
        "accessors": accessors,
        "bufferViews": bin.views,
        "buffers": [ { "byteLength": bin.bytes.len() } ],
    });

    let mut json_chunk = serde_json::to_vec(&gltf).expect("glTF JSON serialize");
    while json_chunk.len() % 4 != 0 {
        json_chunk.push(b' '); // pad JSON with spaces
    }
    let mut bin_chunk = bin.bytes;
    while bin_chunk.len() % 4 != 0 {
        bin_chunk.push(0); // pad BIN with zeros
    }

    let total = 12 + 8 + json_chunk.len() + 8 + bin_chunk.len();
    let mut glb = Vec::with_capacity(total);
    glb.extend_from_slice(&0x4654_6C67u32.to_le_bytes()); // "glTF" (g,l,T,F)
    glb.extend_from_slice(&2u32.to_le_bytes()); // version
    glb.extend_from_slice(&(total as u32).to_le_bytes());
    // JSON chunk
    glb.extend_from_slice(&(json_chunk.len() as u32).to_le_bytes());
    glb.extend_from_slice(&0x4E4F_534Au32.to_le_bytes()); // "JSON"
    glb.extend_from_slice(&json_chunk);
    // BIN chunk
    glb.extend_from_slice(&(bin_chunk.len() as u32).to_le_bytes());
    glb.extend_from_slice(&0x004E_4942u32.to_le_bytes()); // "BIN\0"
    glb.extend_from_slice(&bin_chunk);
    glb
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::creative_seed::{CreativeSeed, WorldScale};

    // P8b: `glb_globe` now takes a `&RenderTheme`. This default-theme wrapper
    // shadows the `use super::*` glob so the existing tests need no change.
    fn glb_globe(
        map: &WorldMap,
        grid_w: u32,
        grid_h: u32,
        exaggeration: f32,
        tex_width: u32,
        color: ColorMode,
    ) -> Vec<u8> {
        super::glb_globe(map, grid_w, grid_h, exaggeration, tex_width, color, &RenderTheme::default())
    }

    fn tiny_world() -> WorldMap {
        let cs = CreativeSeed {
            world_scale: WorldScale::Pocket,
            ..CreativeSeed::default()
        };
        crate::generate(7, &cs)
    }

    fn read_u32(b: &[u8], off: usize) -> u32 {
        u32::from_le_bytes([b[off], b[off + 1], b[off + 2], b[off + 3]])
    }

    #[test]
    fn heightmap_png_is_16bit_and_sized() {
        let map = tiny_world();
        let bytes = heightmap_png(&map, 128);
        let img = image::load_from_memory(&bytes).expect("decode heightmap");
        assert_eq!((img.width(), img.height()), (128, 64), "equirect 2:1");
        assert!(
            matches!(img, DynamicImage::ImageLuma16(_)),
            "heightmap must be 16-bit grayscale, got {:?}",
            img.color()
        );
    }

    #[test]
    fn glb_has_valid_container() {
        let map = tiny_world();
        let glb = glb_globe(&map, 16, 8, 0.06, 64, ColorMode::Biome);
        assert_eq!(&glb[0..4], b"glTF", "magic");
        assert_eq!(read_u32(&glb, 4), 2, "version 2");
        assert_eq!(read_u32(&glb, 8) as usize, glb.len(), "declared total length");
        // JSON chunk
        let json_len = read_u32(&glb, 12) as usize;
        assert_eq!(&glb[16..20], b"JSON");
        assert_eq!(json_len % 4, 0, "JSON chunk 4-aligned");
        let json_bytes = &glb[20..20 + json_len];
        let v: serde_json::Value = serde_json::from_slice(json_bytes).expect("JSON parses");
        assert_eq!(v["asset"]["version"], "2.0");
        // BIN chunk header follows
        let bin_off = 20 + json_len;
        let bin_len = read_u32(&glb, bin_off) as usize;
        assert_eq!(&glb[bin_off + 4..bin_off + 8], b"BIN\0");
        assert_eq!(bin_len % 4, 0, "BIN chunk 4-aligned");
        assert_eq!(bin_off + 8 + bin_len, glb.len(), "BIN chunk spans to EOF");
    }

    #[test]
    fn glb_mesh_counts_are_consistent() {
        let map = tiny_world();
        let (gw, gh) = (16u32, 8u32);
        let glb = glb_globe(&map, gw, gh, 0.06, 64, ColorMode::Biome);
        let json_len = read_u32(&glb, 12) as usize;
        let v: serde_json::Value = serde_json::from_slice(&glb[20..20 + json_len]).unwrap();
        let acc = &v["accessors"];
        let nverts = ((gw + 1) * (gh + 1)) as u64;
        assert_eq!(acc[0]["count"].as_u64().unwrap(), nverts, "POSITION count");
        assert_eq!(acc[1]["count"].as_u64().unwrap(), nverts, "NORMAL count");
        assert_eq!(acc[2]["count"].as_u64().unwrap(), nverts, "TEXCOORD_0 count");
        assert_eq!(acc[3]["count"].as_u64().unwrap(), (gw * gh * 6) as u64, "index count");
        assert!(acc[0]["min"].is_array() && acc[0]["max"].is_array(), "POSITION min/max present");
    }

    #[test]
    fn glb_embeds_a_png_texture() {
        let map = tiny_world();
        let glb = glb_globe(&map, 16, 8, 0.06, 64, ColorMode::Biome);
        let json_len = read_u32(&glb, 12) as usize;
        let v: serde_json::Value = serde_json::from_slice(&glb[20..20 + json_len]).unwrap();
        assert_eq!(v["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"], 0);
        assert_eq!(v["images"][0]["mimeType"], "image/png");
        // The image's bufferView bytes start with the PNG magic.
        let img_bv = v["images"][0]["bufferView"].as_u64().unwrap() as usize;
        let bv = &v["bufferViews"][img_bv];
        let bin_off = 20 + json_len + 8; // past JSON chunk + BIN chunk header
        let off = bin_off + bv["byteOffset"].as_u64().unwrap() as usize;
        assert_eq!(&glb[off..off + 4], b"\x89PNG", "embedded image is a PNG");
    }

    #[test]
    fn glb_normals_point_outward() {
        // Guards against an inside-out globe: the triangle winding must make the
        // smooth normals point outward (positive dot with the radial position).
        let map = tiny_world();
        let (gw, gh) = (32u32, 16u32);
        let glb = glb_globe(&map, gw, gh, 0.06, 64, ColorMode::Biome);
        let json_len = read_u32(&glb, 12) as usize;
        let v: serde_json::Value = serde_json::from_slice(&glb[20..20 + json_len]).unwrap();
        let bin_off = 20 + json_len + 8;
        let read_vec3 = |acc_i: usize, k: usize| -> [f32; 3] {
            let bv = v["accessors"][acc_i]["bufferView"].as_u64().unwrap() as usize;
            let off = bin_off
                + v["bufferViews"][bv]["byteOffset"].as_u64().unwrap() as usize
                + k * 12;
            [
                f32::from_le_bytes([glb[off], glb[off + 1], glb[off + 2], glb[off + 3]]),
                f32::from_le_bytes([glb[off + 4], glb[off + 5], glb[off + 6], glb[off + 7]]),
                f32::from_le_bytes([glb[off + 8], glb[off + 9], glb[off + 10], glb[off + 11]]),
            ]
        };
        let count = v["accessors"][1]["count"].as_u64().unwrap() as usize;
        let mut outward = 0usize;
        for k in 0..count {
            let p = read_vec3(0, k); // POSITION
            let n = read_vec3(1, k); // NORMAL
            if p[0] * n[0] + p[1] * n[1] + p[2] * n[2] > 0.0 {
                outward += 1;
            }
        }
        // The vast majority must face outward (a handful of steep-relief cells can
        // tilt past horizontal, but an inside-out winding would flip ~all of them).
        assert!(
            outward * 100 >= count * 95,
            "only {outward}/{count} vertex normals face outward — winding likely inverted"
        );
    }

    #[test]
    fn export_is_deterministic() {
        let map = tiny_world();
        assert_eq!(heightmap_png(&map, 128), heightmap_png(&map, 128));
        assert_eq!(glb_globe(&map, 16, 8, 0.06, 64, ColorMode::Biome), glb_globe(&map, 16, 8, 0.06, 64, ColorMode::Biome));
    }

    #[test]
    fn glb_color_mode_changes_only_the_texture_not_the_mesh() {
        // A Region-coloured globe must have an identical mesh (same displaced
        // geometry) to the Biome one, but a different embedded texture — so the
        // structural hierarchy is draped over the SAME terrain.
        let cs = CreativeSeed {
            world_scale: WorldScale::Continent,
            ..CreativeSeed::default()
        };
        let map = crate::generate(7, &cs);
        let biome = glb_globe(&map, 32, 16, 0.06, 128, ColorMode::Biome);
        let region = glb_globe(&map, 32, 16, 0.06, 128, ColorMode::Region);
        assert_ne!(biome, region, "region texture must differ from biome");

        // The POSITION bytes (the mesh) must be byte-identical across modes.
        let pos_bytes = |glb: &[u8]| -> Vec<u8> {
            let json_len = read_u32(glb, 12) as usize;
            let v: serde_json::Value = serde_json::from_slice(&glb[20..20 + json_len]).unwrap();
            let bin_off = 20 + json_len + 8;
            let bv = v["accessors"][0]["bufferView"].as_u64().unwrap() as usize;
            let off = bin_off + v["bufferViews"][bv]["byteOffset"].as_u64().unwrap() as usize;
            let len = v["bufferViews"][bv]["byteLength"].as_u64().unwrap() as usize;
            glb[off..off + len].to_vec()
        };
        assert_eq!(
            pos_bytes(&biome),
            pos_bytes(&region),
            "mesh geometry must be identical across colour modes"
        );
    }

    #[test]
    fn ocean_is_clamped_to_sea_radius_and_land_rises() {
        // A Continent world at a finer grid so land is clearly present.
        let cs = CreativeSeed {
            world_scale: WorldScale::Continent,
            ..CreativeSeed::default()
        };
        let map = crate::generate(7, &cs);
        let (gw, gh, exag) = (64u32, 32u32, 0.06f32);
        let relief =
            ReliefField::build(&map, gw, gh, RenderStyle::Realistic, Projection::Equirectangular);
        let sea_r = BASE_RADIUS + relief.sea * exag;
        let glb = glb_globe(&map, gw, gh, exag, 64, ColorMode::Biome);
        // Pull POSITION bytes back and verify every vertex radius ≥ sea radius
        // (ocean clamped to sea, land above) and at least one rises above it.
        let json_len = read_u32(&glb, 12) as usize;
        let v: serde_json::Value = serde_json::from_slice(&glb[20..20 + json_len]).unwrap();
        let bin_off = 20 + json_len + 8;
        let pos_bv = v["accessors"][0]["bufferView"].as_u64().unwrap() as usize;
        let off = bin_off + v["bufferViews"][pos_bv]["byteOffset"].as_u64().unwrap() as usize;
        let count = v["accessors"][0]["count"].as_u64().unwrap() as usize;
        let mut any_above = false;
        for k in 0..count {
            let base = off + k * 12;
            let x = f32::from_le_bytes([glb[base], glb[base + 1], glb[base + 2], glb[base + 3]]);
            let y = f32::from_le_bytes([glb[base + 4], glb[base + 5], glb[base + 6], glb[base + 7]]);
            let z = f32::from_le_bytes([glb[base + 8], glb[base + 9], glb[base + 10], glb[base + 11]]);
            let r = (x * x + y * y + z * z).sqrt();
            assert!(r >= sea_r - 1e-4, "vertex radius {r} below sea radius {sea_r}");
            if r > sea_r + 1e-4 {
                any_above = true;
            }
        }
        assert!(any_above, "no land rose above sea level");
    }
}
