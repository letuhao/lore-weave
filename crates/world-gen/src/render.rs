//! Land/sea raster export.
//!
//! Rasterizes a [`WorldMap`] by nearest-cell-centre lookup — which *is* the
//! Voronoi diagram — so no cell polygon is needed. Rendering is a CLI side
//! output: it is not part of the `WorldMap` value or its `content_hash`, so
//! an approximate nearest-neighbour is fine here.

use image::{Rgb, RgbImage};

use crate::biome::BiomeKind;
use crate::world_map::{RouteKind, SettlementRole, WorldMap};

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

/// Render a political map (Phase 3): cells tinted by state, with routes drawn
/// as lines and settlements as dots.
pub fn political_image(map: &WorldMap, width: u32, height: u32) -> RgbImage {
    let mut img = rasterize(map, width, height, |cell| political_cell_color(map, cell));
    for r in &map.routes {
        draw_line(&mut img, map, r.from_cell, r.to_cell, route_color(r.kind));
    }
    for s in &map.settlements {
        draw_dot(
            &mut img,
            map,
            s.cell,
            1 + u32::from(s.population_tier),
            settlement_color(s.role),
        );
    }
    img
}

/// Base cell colour for the political map — water blue, else tinted by state.
fn political_cell_color(map: &WorldMap, cell: usize) -> Rgb<u8> {
    let pid = map.province_of[cell];
    if pid == u32::MAX {
        return Rgb([40, 70, 120]); // water
    }
    state_color(map.provinces[pid as usize].state)
}

/// A distinct tint per state id.
fn state_color(id: u32) -> Rgb<u8> {
    const PALETTE: [[u8; 3]; 12] = [
        [200, 120, 120],
        [120, 170, 200],
        [170, 200, 120],
        [200, 180, 110],
        [160, 130, 190],
        [120, 200, 170],
        [210, 150, 170],
        [150, 160, 120],
        [190, 160, 200],
        [130, 190, 140],
        [200, 200, 140],
        [170, 140, 130],
    ];
    Rgb(PALETTE[(id as usize) % PALETTE.len()])
}

fn route_color(k: RouteKind) -> Rgb<u8> {
    match k {
        RouteKind::Road => Rgb([40, 30, 20]),
        RouteKind::Trail => Rgb([120, 90, 50]),
        RouteKind::RiverNavigation => Rgb([90, 160, 220]),
        RouteKind::SeaLane => Rgb([225, 225, 255]),
        RouteKind::MountainPass => Rgb([220, 80, 60]),
    }
}

fn settlement_color(r: SettlementRole) -> Rgb<u8> {
    match r {
        SettlementRole::Capital => Rgb([255, 40, 40]),
        SettlementRole::City => Rgb([255, 205, 40]),
        SettlementRole::Town => Rgb([255, 255, 255]),
        SettlementRole::Village => Rgb([205, 205, 205]),
        SettlementRole::Hamlet => Rgb([150, 150, 150]),
        SettlementRole::Fortress => Rgb([130, 50, 130]),
    }
}

/// Pixel coordinate of a cell centre (with the map-y → image-y flip).
fn cell_px(map: &WorldMap, cell: u32, w: i32, h: i32) -> (i32, i32) {
    let (x, y) = map.cells[cell as usize].center;
    let px = ((x * w as f32) as i32).clamp(0, w - 1);
    let py = ((h - 1) - (y * h as f32) as i32).clamp(0, h - 1);
    (px, py)
}

/// Bresenham line between two cell centres.
fn draw_line(img: &mut RgbImage, map: &WorldMap, a: u32, b: u32, color: Rgb<u8>) {
    let (w, h) = (img.width() as i32, img.height() as i32);
    let (mut x0, mut y0) = cell_px(map, a, w, h);
    let (x1, y1) = cell_px(map, b, w, h);
    let dx = (x1 - x0).abs();
    let dy = -(y1 - y0).abs();
    let sx = if x0 < x1 { 1 } else { -1 };
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut err = dx + dy;
    loop {
        img.put_pixel(x0 as u32, y0 as u32, color);
        if x0 == x1 && y0 == y1 {
            break;
        }
        let e2 = 2 * err;
        if e2 >= dy {
            err += dy;
            x0 += sx;
        }
        if e2 <= dx {
            err += dx;
            y0 += sy;
        }
    }
}

/// Filled square dot at a cell centre.
fn draw_dot(img: &mut RgbImage, map: &WorldMap, cell: u32, radius: u32, color: Rgb<u8>) {
    let (w, h) = (img.width() as i32, img.height() as i32);
    let (cx, cy) = cell_px(map, cell, w, h);
    let r = radius as i32;
    for dy in -r..=r {
        for dx in -r..=r {
            let (px, py) = (cx + dx, cy + dy);
            if px >= 0 && py >= 0 && px < w && py < h {
                img.put_pixel(px as u32, py as u32, color);
            }
        }
    }
}

/// Render the political map as an SVG string (Phase 4 vector export):
/// land cells as state-tinted `<rect>`s, routes as `<line>`s, settlements as
/// `<circle>`s. Water cells are omitted — the ocean background shows through.
pub fn political_svg(map: &WorldMap, size: u32) -> String {
    let s = size as f32;
    let grid = (map.cells.len() as f32).sqrt().max(1.0);
    let cell = (s / grid * 1.5).max(1.0); // slight overlap avoids seams
    let mut svg = String::with_capacity(map.cells.len() * 80);
    svg.push_str(&format!(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{size}\" height=\"{size}\" \
         viewBox=\"0 0 {size} {size}\">\n"
    ));
    svg.push_str(&format!(
        "<rect width=\"{size}\" height=\"{size}\" fill=\"#284878\"/>\n"
    ));
    for (i, c) in map.cells.iter().enumerate() {
        let pid = map.province_of[i];
        if pid == u32::MAX {
            continue; // water — ocean background shows through
        }
        let (px, py) = svg_px(c.center, s);
        svg.push_str(&format!(
            "<rect x=\"{:.1}\" y=\"{:.1}\" width=\"{cell:.1}\" height=\"{cell:.1}\" fill=\"{}\"/>\n",
            px - cell / 2.0,
            py - cell / 2.0,
            hex(state_color(map.provinces[pid as usize].state)),
        ));
    }
    for r in &map.routes {
        let (ax, ay) = svg_px(map.cells[r.from_cell as usize].center, s);
        let (bx, by) = svg_px(map.cells[r.to_cell as usize].center, s);
        svg.push_str(&format!(
            "<line x1=\"{ax:.1}\" y1=\"{ay:.1}\" x2=\"{bx:.1}\" y2=\"{by:.1}\" \
             stroke=\"{}\" stroke-width=\"1.5\"/>\n",
            hex(route_color(r.kind)),
        ));
    }
    for st in &map.settlements {
        let (px, py) = svg_px(map.cells[st.cell as usize].center, s);
        svg.push_str(&format!(
            "<circle cx=\"{px:.1}\" cy=\"{py:.1}\" r=\"{:.1}\" fill=\"{}\"/>\n",
            2.0 + f32::from(st.population_tier),
            hex(settlement_color(st.role)),
        ));
    }
    svg.push_str("</svg>\n");
    svg
}

/// Cell centre → SVG pixel (map y=0 is the bottom; SVG y grows downward).
fn svg_px(center: (f32, f32), s: f32) -> (f32, f32) {
    (center.0 * s, s - center.1 * s)
}

/// `Rgb` → `#rrggbb`.
fn hex(c: Rgb<u8>) -> String {
    format!("#{:02x}{:02x}{:02x}", c.0[0], c.0[1], c.0[2])
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

    #[test]
    fn political_image_dimensions_and_not_uniform() {
        let map = generate(3, &CreativeSeed::default());
        let img = political_image(&map, 200, 150);
        assert_eq!(img.width(), 200);
        assert_eq!(img.height(), 150);
        // ocean + ≥1 state tint + route/settlement marks ⇒ >1 colour.
        let first = *img.get_pixel(0, 0);
        assert!(
            img.pixels().any(|p| *p != first),
            "political image rendered a single flat colour"
        );
    }

    #[test]
    fn political_svg_is_well_formed() {
        let map = generate(3, &CreativeSeed::default());
        let svg = political_svg(&map, 256);
        assert!(svg.starts_with("<svg"), "SVG must start with <svg");
        assert!(
            svg.trim_end().ends_with("</svg>"),
            "SVG must end with </svg>"
        );
        assert!(svg.contains("<rect"), "SVG must contain land-cell rects");
        assert!(svg.contains("<line"), "SVG must contain route lines");
        assert!(svg.contains("<circle"), "SVG must contain settlement circles");
    }
}
