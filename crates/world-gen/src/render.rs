//! Land/sea raster export.
//!
//! Rasterizes a [`WorldMap`] by nearest-cell-centre lookup — which *is* the
//! Voronoi diagram — so no cell polygon is needed. Rendering is a CLI side
//! output: it is not part of the `WorldMap` value or its `content_hash`, so
//! an approximate nearest-neighbour is fine here.

use image::{Rgb, RgbImage};

use crate::biome::BiomeKind;
use crate::world_map::WorldMap;

/// Rasterize `map` to `width × height`: each pixel takes the colour of its
/// nearest cell centre — which *is* the Voronoi diagram.
fn rasterize<F: Fn(usize) -> Rgb<u8>>(
    map: &WorldMap,
    width: u32,
    height: u32,
    color: F,
) -> RgbImage {
    let index = SpatialIndex::build(map);
    let mut img = RgbImage::new(width, height);
    for py in 0..height {
        for px in 0..width {
            let x = (px as f32 + 0.5) / width as f32;
            let y = (py as f32 + 0.5) / height as f32;
            let cell = index.nearest(map, x, y);
            // Image y grows downward; flip so map y=0 is the image bottom.
            img.put_pixel(px, height - 1 - py, color(cell));
        }
    }
    img
}

/// Render a land/sea (elevation-shaded) image of `map`.
pub fn land_sea_image(map: &WorldMap, width: u32, height: u32) -> RgbImage {
    rasterize(map, width, height, |cell| shade(map, cell))
}

/// Render a biome-coloured image of `map` (Phase 2).
pub fn biome_image(map: &WorldMap, width: u32, height: u32) -> RgbImage {
    rasterize(map, width, height, |cell| biome_color(map.biome[cell]))
}

/// Colour for each `BiomeKind`.
fn biome_color(b: BiomeKind) -> Rgb<u8> {
    match b {
        BiomeKind::Ocean => Rgb([30, 60, 130]),
        BiomeKind::Lake => Rgb([60, 110, 190]),
        BiomeKind::River => Rgb([90, 150, 210]),
        BiomeKind::Coast => Rgb([200, 190, 130]),
        BiomeKind::Beach => Rgb([235, 220, 160]),
        BiomeKind::Plain => Rgb([130, 190, 90]),
        BiomeKind::Forest => Rgb([50, 120, 55]),
        BiomeKind::Jungle => Rgb([25, 95, 40]),
        BiomeKind::Marsh => Rgb([95, 120, 70]),
        BiomeKind::Mountain => Rgb([140, 135, 130]),
        BiomeKind::Hill => Rgb([120, 140, 80]),
        BiomeKind::Desert => Rgb([220, 200, 130]),
        BiomeKind::Tundra => Rgb([170, 160, 150]),
        BiomeKind::Glacier => Rgb([240, 245, 250]),
    }
}

/// A uniform bucket grid over cell centres for fast nearest-centre lookup.
struct SpatialIndex {
    side: usize,
    buckets: Vec<Vec<u32>>,
}

impl SpatialIndex {
    fn build(map: &WorldMap) -> Self {
        let side = (map.cells.len() as f32).sqrt().round().max(1.0) as usize;
        let mut buckets = vec![Vec::new(); side * side];
        for (i, c) in map.cells.iter().enumerate() {
            let b = bucket_of(c.center.0, c.center.1, side);
            buckets[b].push(i as u32);
        }
        SpatialIndex { side, buckets }
    }

    /// Nearest cell index to normalized `(x,y)`; widening ring search with a
    /// distance-correct stop — only stops once no unsearched bucket can hold
    /// a closer centre than the current best.
    fn nearest(&self, map: &WorldMap, x: f32, y: f32) -> usize {
        let side = self.side as isize;
        let gx = ((x * self.side as f32) as isize).clamp(0, side - 1);
        let gy = ((y * self.side as f32) as isize).clamp(0, side - 1);
        let mut best = 0usize;
        let mut best_d = f32::INFINITY;
        let mut radius = 1isize;
        while radius <= side {
            for by in (gy - radius).max(0)..=(gy + radius).min(side - 1) {
                for bx in (gx - radius).max(0)..=(gx + radius).min(side - 1) {
                    for &ci in &self.buckets[(by * side + bx) as usize] {
                        let c = &map.cells[ci as usize];
                        let d = (c.center.0 - x) * (c.center.0 - x)
                            + (c.center.1 - y) * (c.center.1 - y);
                        if d < best_d {
                            best_d = d;
                            best = ci as usize;
                        }
                    }
                }
            }
            // Every cell in a not-yet-searched bucket is at least
            // (radius-1)/side away from the pixel. Stop once the best hit is
            // provably no farther than that (compare squared distances).
            if best_d.is_finite() {
                let covered = (radius - 1) as f32 / self.side as f32;
                if covered * covered >= best_d {
                    break;
                }
            }
            radius += 1;
        }
        best
    }
}

/// Bucket index for a normalized point on a `side × side` grid.
fn bucket_of(x: f32, y: f32, side: usize) -> usize {
    let cx = ((x * side as f32) as usize).min(side - 1);
    let cy = ((y * side as f32) as usize).min(side - 1);
    cy * side + cx
}

/// Colour a cell: blue ramp for water (deeper = darker), green→brown→white
/// ramp for land (higher = lighter).
fn shade(map: &WorldMap, cell: usize) -> Rgb<u8> {
    let e = map.cells[cell].elevation;
    if e < map.sea_level {
        let depth = f32::from(map.sea_level - e) / f32::from(map.sea_level.max(1));
        let blue = (200.0 - 120.0 * depth).clamp(60.0, 200.0);
        Rgb([20, 60, blue as u8])
    } else {
        let span = f32::from((65535 - map.sea_level).max(1));
        let t = (f32::from(e - map.sea_level) / span).clamp(0.0, 1.0);
        land_ramp(t)
    }
}

/// Land colour ramp: `t=0` coastal green, `t=0.5` brown, `t=1` snow white.
fn land_ramp(t: f32) -> Rgb<u8> {
    if t < 0.5 {
        let k = t / 0.5;
        Rgb([
            (70.0 + 100.0 * k) as u8,
            (130.0 - 20.0 * k) as u8,
            (60.0 + 10.0 * k) as u8,
        ])
    } else {
        let k = (t - 0.5) / 0.5;
        Rgb([
            (170.0 + 85.0 * k) as u8,
            (110.0 + 145.0 * k) as u8,
            (70.0 + 185.0 * k) as u8,
        ])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::creative_seed::{CoastlineProfile, CreativeSeed};
    use crate::generate;

    fn island_map() -> WorldMap {
        let cs = CreativeSeed {
            coastline_profile: CoastlineProfile::Island,
            ..CreativeSeed::default()
        };
        generate(2026, &cs)
    }

    #[test]
    fn image_has_requested_dimensions() {
        let img = land_sea_image(&island_map(), 128, 96);
        assert_eq!(img.width(), 128);
        assert_eq!(img.height(), 96);
    }

    #[test]
    fn island_render_shows_both_land_and_water() {
        let img = land_sea_image(&island_map(), 160, 160);
        let mut water = 0u32;
        let mut land = 0u32;
        for px in img.pixels() {
            // Water shading keeps blue dominant over green; land never does.
            if px.0[2] > px.0[1] {
                water += 1;
            } else {
                land += 1;
            }
        }
        assert!(water > 0, "island map rendered no water");
        assert!(land > 0, "island map rendered no land");
    }

    #[test]
    fn land_ramp_is_total_over_unit_range() {
        // Exercises every `as u8` cast in the ramp; must not panic / wrap.
        for i in 0..=1000 {
            let _ = land_ramp(i as f32 / 1000.0);
        }
        // out-of-range inputs are clamped by `shade`, but the ramp itself
        // must still be total.
        let _ = land_ramp(-0.3);
        let _ = land_ramp(1.7);
    }

    #[test]
    fn biome_image_has_requested_dimensions() {
        let img = biome_image(&island_map(), 100, 80);
        assert_eq!(img.width(), 100);
        assert_eq!(img.height(), 80);
    }

    #[test]
    fn biome_image_is_not_uniform() {
        // A real island map has ocean + several land biomes ⇒ >1 colour.
        let img = biome_image(&island_map(), 128, 128);
        let first = *img.get_pixel(0, 0);
        assert!(
            img.pixels().any(|p| *p != first),
            "biome image rendered a single flat colour"
        );
    }
}
