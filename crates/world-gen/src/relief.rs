//! Render-time relief engine — a continuous per-pixel elevation field with
//! hillshade, the basis for every PNG render mode.
//!
//! Not part of `WorldMap` / `content_hash` (see [`crate::render`]), so it
//! freely re-triangulates the mesh and layers procedural detail on top. Still
//! deterministic: the detail and domain-warp noise is seeded from
//! `WorldMap.seed`, so a rendered PNG reproduces byte-for-byte.
//!
//! Pipeline ([`ReliefField::build`]):
//! 1. re-triangulate the cell centres (`delaunator`);
//! 2. barycentric-rasterize cell elevations → a continuous base buffer;
//! 3. domain-warp that buffer with low-frequency fBm — bends the heightmap's
//!    concentric blob rings into irregular shapes;
//! 4. add modulated fBm detail — the mid/high-frequency texture the coarse
//!    mesh cannot hold;
//! 5. hillshade the result — the gradient relighting that renders it as
//!    rugged 3-D terrain.

use delaunator::{Point, triangulate};

use crate::noise::{fbm, lerp};
use crate::world_map::WorldMap;

/// Domain-warp frequency (cycles across the map) + octave count. Tuned to
/// vary *within* a blob (a blob spans ≈ 1/5 of the map) so the warp bends
/// each radial mountain into an irregular massif, not just shifts it whole.
const WARP_FREQ: f32 = 5.5;
const WARP_OCTAVES: u32 = 3;
/// Detail-noise frequency + octave count — higher, for the mid/high-frequency
/// texture the coarse mesh structurally cannot hold.
const DETAIL_FREQ: f32 = 12.0;
const DETAIL_OCTAVES: u32 = 5;

/// Distinct noise-field salts so warp-x, warp-y and detail are decorrelated.
const SALT_WARP_X: u32 = 0x5F35_61A1;
const SALT_WARP_Y: u32 = 0xBC27_90B2;
const SALT_DETAIL: u32 = 0x1D83_C4C3;

/// Cartographic style — switches palette, coastline treatment and hillshade
/// contrast. The relief *engine* is identical for both.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RenderStyle {
    /// Google-terrain-layer look: hypsometric tint, strong NW hillshade, a
    /// natural fractal coastline.
    Realistic,
    /// Fantasy-atlas look: muted parchment palette, a smooth coastline with an
    /// ink outline, soft low-contrast relief.
    Atlas,
}

/// Per-style tuning. The engine reads these; *only* these differ by style.
struct StyleParams {
    /// Detail-noise amplitude, in normalized elevation units.
    detail_amp: f32,
    /// Domain-warp amplitude, in model `[0,1]` units.
    warp_amp: f32,
    /// Hillshade vertical exaggeration (multiplied by image width).
    relief_strength: f32,
    /// Hillshade ambient floor — the darkest an unlit slope goes.
    ambient: f32,
    /// `true` → coastline follows base+detail (fractal); `false` → base only.
    fractal_coast: bool,
}

impl RenderStyle {
    fn params(self) -> StyleParams {
        match self {
            RenderStyle::Realistic => StyleParams {
                detail_amp: 0.055,
                warp_amp: 0.058,
                relief_strength: 0.30,
                ambient: 0.42,
                fractal_coast: true,
            },
            RenderStyle::Atlas => StyleParams {
                detail_amp: 0.030,
                warp_amp: 0.046,
                relief_strength: 0.16,
                ambient: 0.66,
                fractal_coast: false,
            },
        }
    }
}

/// A rendered relief field — a continuous per-pixel elevation buffer plus the
/// hillshade derived from it. All buffers are row-major in image order: row 0
/// is the top of the image (model `y = 1`).
pub struct ReliefField {
    pub width: u32,
    pub height: u32,
    /// Combined base + detail elevation, normalized to roughly `[0,1]`.
    pub elev: Vec<f32>,
    /// Per-pixel land/water flag (style-dependent coastline). `true` = water.
    pub water: Vec<bool>,
    /// Per-pixel hillshade multiplier in `[ambient, 1]`.
    pub shade: Vec<f32>,
    /// Sea level, in the same normalized space as `elev`.
    pub sea: f32,
}

impl ReliefField {
    /// Build the relief field for `map` at `width × height` in the given style.
    pub fn build(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> ReliefField {
        let p = style.params();
        let w = width as usize;
        let h = height as usize;
        let n = w * h;
        let sea = f32::from(map.sea_level) / 65535.0;
        // fold the u64 world seed into the u32 the noise hash takes.
        let seed = (map.seed ^ (map.seed >> 32)) as u32;

        // 1+2 — triangulate the cell centres, barycentric-rasterize elevation.
        let base_raw = rasterize_base(map, width, height);

        // 3+4 — domain warp (resample base_raw) + modulated fBm detail.
        let mut elev = vec![0.0f32; n];
        let mut water = vec![false; n];
        for py in 0..h {
            for px in 0..w {
                let i = py * w + px;
                // model coords (y up) — noise sampled here is resolution-stable.
                let mx = (px as f32 + 0.5) / width as f32;
                let my = 1.0 - (py as f32 + 0.5) / height as f32;

                // domain warp: a model-space displacement, applied in pixels
                // (model +y is image −y, hence the sign on the y term).
                let wx = p.warp_amp * fbm(mx * WARP_FREQ, my * WARP_FREQ, seed ^ SALT_WARP_X, WARP_OCTAVES);
                let wy = p.warp_amp * fbm(mx * WARP_FREQ, my * WARP_FREQ, seed ^ SALT_WARP_Y, WARP_OCTAVES);
                let base = sample_bilinear(
                    &base_raw,
                    w,
                    h,
                    px as f32 + 0.5 + wx * width as f32,
                    py as f32 + 0.5 - wy * height as f32,
                );

                // detail amplitude: ~0 in open ocean, gentle on plains, full
                // on highlands — keeps the open sea smooth and mountains rugged.
                let land_t = (base - sea) / (1.0 - sea).max(1e-3);
                let m = smoothstep(-0.15, 0.02, land_t) * (0.30 + 0.70 * land_t.clamp(0.0, 1.0));
                let detail = p.detail_amp
                    * m
                    * fbm(mx * DETAIL_FREQ, my * DETAIL_FREQ, seed ^ SALT_DETAIL, DETAIL_OCTAVES);

                let combined = base + detail;
                elev[i] = combined;
                // fractal coast tests the detailed surface; smooth coast the base.
                water[i] = if p.fractal_coast { combined < sea } else { base < sea };
            }
        }

        // 5 — hillshade from the combined elevation.
        let shade = hillshade(&elev, width, height, p.relief_strength, p.ambient);

        ReliefField { width, height, elev, water, shade, sea }
    }
}

/// Triangulate the cell centres and barycentric-rasterize their elevations
/// into a `width × height` buffer (normalized, image order). The mesh's
/// perimeter ring puts the convex hull on the unit square, so every pixel is
/// covered; [`backfill`] is insurance against a degenerate sliver.
fn rasterize_base(map: &WorldMap, width: u32, height: u32) -> Vec<f32> {
    let w = width as usize;
    let h = height as usize;
    let mut buf = vec![f32::NAN; w * h];

    let pts: Vec<Point> = map
        .cells
        .iter()
        .map(|c| Point {
            x: f64::from(c.center.0),
            y: f64::from(c.center.1),
        })
        .collect();
    let tri = triangulate(&pts);

    for t in tri.triangles.chunks_exact(3) {
        let pos = [
            cell_px(map, t[0], width, height),
            cell_px(map, t[1], width, height),
            cell_px(map, t[2], width, height),
        ];
        let elev = [
            norm_elev(map, t[0]),
            norm_elev(map, t[1]),
            norm_elev(map, t[2]),
        ];
        rasterize_triangle(&mut buf, w, h, pos, elev);
    }

    backfill(&mut buf, map, width, height);
    // Barycentric interpolation is piecewise-linear, so its gradient — and
    // hence a raw hillshade — is faceted per triangle. Blur the base by ~one
    // triangle edge (≈ width / √cells) to lift it to a smooth field; the fBm
    // detail added later restores the fine texture the blur removes.
    let facet = width as f32 / (map.cells.len() as f32).sqrt();
    let radius = (facet * 0.5).round().max(1.0) as usize;
    box_blur(&mut buf, w, h, radius, 2);
    buf
}

/// In-place separable box blur — `passes` repeats of a radius-`r` box, a cheap
/// Gaussian approximation. Two passes lift a piecewise-linear field to `C²`,
/// enough that the hillshade gradient is smooth rather than faceted.
fn box_blur(buf: &mut [f32], w: usize, h: usize, r: usize, passes: u32) {
    if r == 0 {
        return;
    }
    let mut tmp = vec![0.0f32; buf.len()];
    for _ in 0..passes {
        for y in 0..h {
            let row = y * w;
            for x in 0..w {
                let lo = x.saturating_sub(r);
                let hi = (x + r).min(w - 1);
                let sum: f32 = buf[row + lo..=row + hi].iter().sum();
                tmp[row + x] = sum / (hi - lo + 1) as f32;
            }
        }
        for x in 0..w {
            for y in 0..h {
                let lo = y.saturating_sub(r);
                let hi = (y + r).min(h - 1);
                let mut sum = 0.0;
                for k in lo..=hi {
                    sum += tmp[k * w + x];
                }
                buf[y * w + x] = sum / (hi - lo + 1) as f32;
            }
        }
    }
}

/// Cell centre → pixel coordinates, with the model-y → image-y flip.
fn cell_px(map: &WorldMap, cell: usize, width: u32, height: u32) -> (f32, f32) {
    let (cx, cy) = map.cells[cell].center;
    (cx * width as f32, (1.0 - cy) * height as f32)
}

/// Normalized elevation of a cell in `[0,1]`.
fn norm_elev(map: &WorldMap, cell: usize) -> f32 {
    f32::from(map.cells[cell].elevation) / 65535.0
}

/// Barycentric-fill one triangle's interpolated elevation into `buf`.
fn rasterize_triangle(buf: &mut [f32], w: usize, h: usize, pos: [(f32, f32); 3], elev: [f32; 3]) {
    let (ax, ay) = pos[0];
    let (bx, by) = pos[1];
    let (cx, cy) = pos[2];

    // canonical barycentric denominator (== twice the signed triangle area).
    let det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
    if det.abs() < 1e-9 {
        return; // degenerate sliver — `backfill` covers any pixel it owned.
    }
    let inv = 1.0 / det;

    let min_x = ax.min(bx).min(cx).floor().max(0.0) as usize;
    let max_x = (ax.max(bx).max(cx).ceil().max(0.0) as usize).min(w - 1);
    let min_y = ay.min(by).min(cy).floor().max(0.0) as usize;
    let max_y = (ay.max(by).max(cy).ceil().max(0.0) as usize).min(h - 1);

    for py in min_y..=max_y {
        for px in min_x..=max_x {
            let sx = px as f32 + 0.5;
            let sy = py as f32 + 0.5;
            let wa = ((by - cy) * (sx - cx) + (cx - bx) * (sy - cy)) * inv;
            let wb = ((cy - ay) * (sx - cx) + (ax - cx) * (sy - cy)) * inv;
            let wc = 1.0 - wa - wb;
            // a small tolerance so a pixel exactly on a shared edge is kept.
            if wa >= -1e-4 && wb >= -1e-4 && wc >= -1e-4 {
                buf[py * w + px] = wa * elev[0] + wb * elev[1] + wc * elev[2];
            }
        }
    }
}

/// Replace any pixel left `NaN` (no triangle covered it — only possible at a
/// degenerate sliver) with the nearest cell's elevation, so the buffer is
/// total. In practice this touches nothing.
fn backfill(buf: &mut [f32], map: &WorldMap, width: u32, height: u32) {
    let w = width as usize;
    for py in 0..height as usize {
        for px in 0..w {
            let i = py * w + px;
            if !buf[i].is_nan() {
                continue;
            }
            let mx = (px as f32 + 0.5) / width as f32;
            let my = 1.0 - (py as f32 + 0.5) / height as f32;
            let mut best = 0usize;
            let mut best_d = f32::INFINITY;
            for (ci, c) in map.cells.iter().enumerate() {
                let d = (c.center.0 - mx).powi(2) + (c.center.1 - my).powi(2);
                if d < best_d {
                    best_d = d;
                    best = ci;
                }
            }
            buf[i] = norm_elev(map, best);
        }
    }
}

/// Bilinearly sample `buf` at fractional pixel coords, clamped to the buffer.
fn sample_bilinear(buf: &[f32], w: usize, h: usize, fx: f32, fy: f32) -> f32 {
    let cx = fx.clamp(0.0, w as f32 - 1.0);
    let cy = fy.clamp(0.0, h as f32 - 1.0);
    let x0 = cx.floor() as usize;
    let y0 = cy.floor() as usize;
    let x1 = (x0 + 1).min(w - 1);
    let y1 = (y0 + 1).min(h - 1);
    let tx = cx - x0 as f32;
    let ty = cy - y0 as f32;
    let top = lerp(buf[y0 * w + x0], buf[y0 * w + x1], tx);
    let bot = lerp(buf[y1 * w + x0], buf[y1 * w + x1], tx);
    lerp(top, bot, ty)
}

/// NW-lit hillshade from a normalized elevation buffer. `strength` is a
/// vertical exaggeration (scaled by width so the look is resolution-stable);
/// `ambient` is the dark floor. Returns a per-pixel multiplier in `[ambient,1]`.
fn hillshade(elev: &[f32], width: u32, height: u32, strength: f32, ambient: f32) -> Vec<f32> {
    let w = width as usize;
    let h = height as usize;
    let exagg = strength * width as f32;
    // sun: NW, ~45° elevation. Image space — x right, y down, light from
    // upper-left so NW-facing slopes are bright.
    let light = normalize3(-1.0, -1.0, 1.4);
    let mut shade = vec![0.0f32; w * h];
    for py in 0..h {
        for px in 0..w {
            let xm = px.saturating_sub(1);
            let xp = (px + 1).min(w - 1);
            let ym = py.saturating_sub(1);
            let yp = (py + 1).min(h - 1);
            let dzdx = (elev[py * w + xp] - elev[py * w + xm]) * 0.5;
            let dzdy = (elev[yp * w + px] - elev[ym * w + px]) * 0.5;
            // normal of the exaggerated height surface, then Lambert term.
            let normal = normalize3(-dzdx * exagg, -dzdy * exagg, 1.0);
            let d = (normal.0 * light.0 + normal.1 * light.1 + normal.2 * light.2).max(0.0);
            shade[py * w + px] = ambient + (1.0 - ambient) * d;
        }
    }
    shade
}

/// Normalize a 3-vector; a (near-)zero vector falls back to `+z`.
fn normalize3(x: f32, y: f32, z: f32) -> (f32, f32, f32) {
    let len = (x * x + y * y + z * z).sqrt();
    if len < 1e-12 {
        (0.0, 0.0, 1.0)
    } else {
        (x / len, y / len, z / len)
    }
}

/// Hermite smoothstep — `0` at/below `e0`, `1` at/above `e1`, smooth between.
fn smoothstep(e0: f32, e1: f32, x: f32) -> f32 {
    let t = ((x - e0) / (e1 - e0)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::creative_seed::CreativeSeed;
    use crate::generate;

    fn sample_map() -> WorldMap {
        generate(2026, &CreativeSeed::default())
    }

    #[test]
    fn field_has_pixel_dimensions() {
        let f = ReliefField::build(&sample_map(), 64, 48, RenderStyle::Realistic);
        assert_eq!(f.elev.len(), 64 * 48);
        assert_eq!(f.shade.len(), 64 * 48);
        assert_eq!(f.water.len(), 64 * 48);
    }

    #[test]
    fn elev_is_all_finite() {
        // the `backfill` pass guarantees no NaN survives rasterization.
        let f = ReliefField::build(&sample_map(), 80, 80, RenderStyle::Realistic);
        assert!(
            f.elev.iter().all(|e| e.is_finite()),
            "relief elevation has non-finite values"
        );
    }

    #[test]
    fn shade_is_in_unit_range() {
        let f = ReliefField::build(&sample_map(), 80, 80, RenderStyle::Realistic);
        assert!(
            f.shade.iter().all(|&s| (0.0..=1.0).contains(&s)),
            "hillshade factor escaped [0,1]"
        );
    }

    #[test]
    fn interpolation_stays_in_a_sane_band() {
        // barycentric interpolation is bounded by the mesh elevation range
        // ([0,1]); detail is small ⇒ the field cannot wander far outside it.
        let f = ReliefField::build(&sample_map(), 80, 80, RenderStyle::Realistic);
        assert!(
            f.elev.iter().all(|&e| (-0.25..=1.25).contains(&e)),
            "relief elevation escaped a sane band"
        );
    }

    #[test]
    fn build_is_deterministic() {
        let m = sample_map();
        let a = ReliefField::build(&m, 96, 96, RenderStyle::Atlas);
        let b = ReliefField::build(&m, 96, 96, RenderStyle::Atlas);
        assert!(
            a.elev.iter().zip(&b.elev).all(|(x, y)| x.to_bits() == y.to_bits()),
            "relief elevation is not reproducible"
        );
        assert!(
            a.shade.iter().zip(&b.shade).all(|(x, y)| x.to_bits() == y.to_bits()),
            "relief hillshade is not reproducible"
        );
        assert_eq!(a.water, b.water, "relief water mask is not reproducible");
    }

    #[test]
    fn styles_produce_different_relief() {
        let m = sample_map();
        let r = ReliefField::build(&m, 96, 96, RenderStyle::Realistic);
        let a = ReliefField::build(&m, 96, 96, RenderStyle::Atlas);
        assert!(
            r.shade.iter().zip(&a.shade).any(|(x, y)| x.to_bits() != y.to_bits()),
            "realistic and atlas produced an identical hillshade"
        );
    }

    #[test]
    fn field_has_both_land_and_water() {
        let f = ReliefField::build(&sample_map(), 128, 128, RenderStyle::Realistic);
        assert!(f.water.iter().any(|&w| w), "relief field has no water pixels");
        assert!(f.water.iter().any(|&w| !w), "relief field has no land pixels");
    }
}
