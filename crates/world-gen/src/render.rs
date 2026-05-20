//! Raster + SVG map export.
//!
//! Rendering is a CLI side output: it is *not* part of the `WorldMap` value or
//! its `content_hash`. Categorical maps (biome / political / culture) place
//! pixels by nearest-cell-centre lookup — which *is* the Voronoi diagram —
//! then composite a hillshade from [`crate::relief`] over the flat fill. The
//! hypsometric [`relief_image`] renders the relief field directly.

use image::{Rgb, RgbImage};

use crate::biome::BiomeKind;
use crate::relief::{ReliefField, RenderStyle};
use crate::world_map::{RouteKind, SettlementRole, WorldMap};

/// Internal supersampling factor. Every raster `*_image` renders at `SS×` the
/// requested size, then box-downsamples — anti-aliasing coastlines, the
/// hillshade and the Voronoi cell edges, and letting the fBm detail sample
/// finer. Rendering is an offline one-shot, so the ~`SS²` cost is fine.
const SS: u32 = 2;

/// Render `inner` at `SS×` the requested size, then box-downsample back. The
/// public render entry points are thin wrappers over this.
fn supersampled(width: u32, height: u32, inner: impl Fn(u32, u32) -> RgbImage) -> RgbImage {
    downsample(&inner(width * SS, height * SS), SS)
}

/// Box-downsample `src` by an integer `factor`: each output pixel is the mean
/// of its `factor × factor` source block. Deterministic.
fn downsample(src: &RgbImage, factor: u32) -> RgbImage {
    let (dw, dh) = (src.width() / factor, src.height() / factor);
    let area = factor * factor;
    let mut out = RgbImage::new(dw, dh);
    for dy in 0..dh {
        for dx in 0..dw {
            let (mut r, mut g, mut b) = (0u32, 0u32, 0u32);
            for fy in 0..factor {
                for fx in 0..factor {
                    let p = src.get_pixel(dx * factor + fx, dy * factor + fy);
                    r += u32::from(p[0]);
                    g += u32::from(p[1]);
                    b += u32::from(p[2]);
                }
            }
            out.put_pixel(dx, dy, Rgb([(r / area) as u8, (g / area) as u8, (b / area) as u8]));
        }
    }
    out
}

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

/// Render a hypsometric relief image — the showcase terrain render. Continuous
/// barycentric-interpolated elevation, fBm detail, NW hillshade; palette and
/// coastline treatment per `style`. Supersampled (see [`supersampled`]).
pub fn relief_image(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> RgbImage {
    supersampled(width, height, |w, h| relief_image_inner(map, w, h, style))
}

fn relief_image_inner(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style);
    let mut img = RgbImage::new(width, height);
    for py in 0..height {
        for px in 0..width {
            let i = (py * width + px) as usize;
            let base = if relief.water[i] {
                water_color(relief.elev[i], relief.sea, style)
            } else {
                land_color(relief.elev[i], relief.sea, style)
            };
            img.put_pixel(px, py, shade_rgb(base, relief.shade[i]));
        }
    }
    if style == RenderStyle::Atlas {
        draw_coast_outline(&mut img, &relief);
    }
    img
}

/// Render a biome-coloured image of `map`, hillshaded by the relief field.
pub fn biome_image(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> RgbImage {
    supersampled(width, height, |w, h| biome_image_inner(map, w, h, style))
}

fn biome_image_inner(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style);
    let mut img = rasterize(map, width, height, |cell| biome_color(map.biome[cell]));
    apply_shade(&mut img, &relief);
    img
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

/// Render a culture-region image of `map` — each land cell tinted by its
/// culture id, hillshaded by the relief field; water cells are ocean-blue.
pub fn culture_image(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> RgbImage {
    supersampled(width, height, |w, h| culture_image_inner(map, w, h, style))
}

fn culture_image_inner(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style);
    let mut img = rasterize(map, width, height, |cell| {
        let cid = map.culture_of[cell];
        if cid == u32::MAX {
            Rgb([40, 70, 120]) // water
        } else {
            culture_color(cid)
        }
    });
    apply_shade(&mut img, &relief);
    img
}

/// A distinct tint per culture id (`culture_count` is clamped to 1..=16).
fn culture_color(id: u32) -> Rgb<u8> {
    const PALETTE: [[u8; 3]; 16] = [
        [210, 100, 100],
        [100, 160, 210],
        [160, 200, 100],
        [210, 180, 90],
        [150, 120, 200],
        [100, 200, 170],
        [220, 140, 170],
        [140, 170, 110],
        [190, 150, 210],
        [120, 190, 130],
        [210, 200, 120],
        [170, 130, 120],
        [120, 140, 200],
        [200, 170, 140],
        [150, 200, 200],
        [180, 110, 150],
    ];
    Rgb(PALETTE[(id as usize) % PALETTE.len()])
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
            // B2 sphere migration: bucket by the (u, v) equirectangular
            // projection of the 3D centre.
            let (cu, cv) = crate::project_uv(c.center);
            let b = bucket_of(cu, cv, side);
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
                        // B2 sphere migration: nearest-cell query for the
                        // raster image uses the (u, v) equirectangular
                        // projection of the cell's 3D centre.
                        let c = &map.cells[ci as usize];
                        let (cu, cv) = crate::project_uv(c.center);
                        let d = (cu - x) * (cu - x) + (cv - y) * (cv - y);
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

/// Multiply every pixel of `img` by the relief hillshade — turns a flat
/// categorical map (biome / political / culture) into a relief-shaded one.
/// `img` and `relief` must share dimensions.
fn apply_shade(img: &mut RgbImage, relief: &ReliefField) {
    debug_assert_eq!(
        (img.width(), img.height()),
        (relief.width, relief.height),
        "apply_shade: image and relief field must share dimensions"
    );
    for py in 0..img.height() {
        for px in 0..img.width() {
            let s = relief.shade[(py * relief.width + px) as usize];
            let p = img.get_pixel_mut(px, py);
            *p = shade_rgb(*p, s);
        }
    }
}

/// Scale an `Rgb` by a `[0,1]` shade factor.
fn shade_rgb(c: Rgb<u8>, s: f32) -> Rgb<u8> {
    let ch = |v: u8| (f32::from(v) * s).round().clamp(0.0, 255.0) as u8;
    Rgb([ch(c.0[0]), ch(c.0[1]), ch(c.0[2])])
}

/// Linear-interpolate a colour through an ascending `(stop, rgb)` ramp.
fn ramp(stops: &[(f32, [u8; 3])], t: f32) -> Rgb<u8> {
    let t = t.clamp(stops[0].0, stops[stops.len() - 1].0);
    for pair in stops.windows(2) {
        let (t0, c0) = pair[0];
        let (t1, c1) = pair[1];
        if t <= t1 {
            let k = if t1 > t0 { (t - t0) / (t1 - t0) } else { 0.0 };
            return Rgb([
                lerp_u8(c0[0], c1[0], k),
                lerp_u8(c0[1], c1[1], k),
                lerp_u8(c0[2], c1[2], k),
            ]);
        }
    }
    Rgb(stops[stops.len() - 1].1)
}

/// Linear interpolation between two `u8` channel values.
fn lerp_u8(a: u8, b: u8, t: f32) -> u8 {
    (f32::from(a) + (f32::from(b) - f32::from(a)) * t.clamp(0.0, 1.0))
        .round()
        .clamp(0.0, 255.0) as u8
}

/// Hypsometric land colour by normalized height above sea level. Land stops
/// keep blue off the dominant channel so a water test can be `b > r && b > g`.
fn land_color(elev: f32, sea: f32, style: RenderStyle) -> Rgb<u8> {
    let t = ((elev - sea) / (1.0 - sea).max(1e-3)).clamp(0.0, 1.0);
    match style {
        RenderStyle::Realistic => ramp(
            &[
                (0.00, [78, 126, 68]),   // coastal lowland green
                (0.10, [100, 146, 78]),  // plains
                (0.24, [132, 154, 90]),  // dry grassland
                (0.42, [160, 150, 100]), // foothills / steppe
                (0.60, [150, 120, 84]),  // upland tan
                (0.76, [126, 112, 104]), // bare rock
                (0.90, [172, 168, 162]), // high rock
                (1.00, [255, 255, 255]), // snow cap
            ],
            t,
        ),
        RenderStyle::Atlas => ramp(
            &[
                (0.00, [208, 202, 170]),
                (0.30, [196, 184, 146]),
                (0.60, [178, 160, 132]),
                (0.85, [162, 152, 138]),
                (1.00, [200, 199, 197]),
            ],
            t,
        ),
    }
}

/// Water colour by normalized depth below sea level.
fn water_color(elev: f32, sea: f32, style: RenderStyle) -> Rgb<u8> {
    let d = ((sea - elev) / sea.max(1e-3)).clamp(0.0, 1.0);
    match style {
        RenderStyle::Realistic => ramp(
            &[
                (0.00, [128, 182, 200]), // bright coastal shallows
                (0.12, [86, 144, 184]),  // shelf
                (0.45, [44, 94, 148]),   // open water
                (1.00, [16, 38, 84]),    // deep ocean
            ],
            d,
        ),
        RenderStyle::Atlas => ramp(&[(0.00, [182, 196, 202]), (1.00, [138, 160, 180])], d),
    }
}

/// Atlas style: stroke an ink line wherever a land pixel touches water. The
/// line is stamped `SS` pixels thick so it survives the supersample
/// downsample as a crisp outline rather than a faint ~quarter-strength edge.
fn draw_coast_outline(img: &mut RgbImage, relief: &ReliefField) {
    const INK: Rgb<u8> = Rgb([66, 56, 48]);
    let (w, h) = (relief.width, relief.height);
    let is_water = |px: u32, py: u32| relief.water[(py * w + px) as usize];
    for py in 0..h {
        for px in 0..w {
            if is_water(px, py) {
                continue;
            }
            let coast = (px > 0 && is_water(px - 1, py))
                || (px + 1 < w && is_water(px + 1, py))
                || (py > 0 && is_water(px, py - 1))
                || (py + 1 < h && is_water(px, py + 1));
            if coast {
                for oy in 0..SS {
                    for ox in 0..SS {
                        let (sx, sy) = (px + ox, py + oy);
                        if sx < w && sy < h {
                            img.put_pixel(sx, sy, INK);
                        }
                    }
                }
            }
        }
    }
}

/// Render a political map (Phase 3): cells tinted by state and hillshaded,
/// with routes drawn as lines and settlements as dots.
pub fn political_image(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> RgbImage {
    supersampled(width, height, |w, h| political_image_inner(map, w, h, style))
}

fn political_image_inner(map: &WorldMap, width: u32, height: u32, style: RenderStyle) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style);
    let mut img = rasterize(map, width, height, |cell| political_cell_color(map, cell));
    apply_shade(&mut img, &relief);
    for r in &map.routes {
        // Trace the route's actual cell path, not a straight endpoint line.
        let color = route_color(r.kind);
        for seg in r.path.windows(2) {
            draw_line(&mut img, map, seg[0], seg[1], color);
        }
    }
    for s in &map.settlements {
        // Rendering at SS× — scale the dot radius so it survives downsampling.
        draw_dot(
            &mut img,
            map,
            s.cell,
            SS * (1 + u32::from(s.population_tier)),
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

/// Pixel coordinate of a cell centre via equirectangular projection.
/// `(u, v)` from `project_uv` already has `v = 0` at the top (north pole) —
/// matches raster row=0 at top, so no flip is needed.
fn cell_px(map: &WorldMap, cell: u32, w: i32, h: i32) -> (i32, i32) {
    let (u, v) = crate::project_uv(map.cells[cell as usize].center);
    let px = ((u * w as f32) as i32).clamp(0, w - 1);
    let py = ((v * h as f32) as i32).clamp(0, h - 1);
    (px, py)
}

/// Bresenham line between two cell centres, stamped `SS` pixels thick so it
/// stays solid through the supersample downsample.
fn draw_line(img: &mut RgbImage, map: &WorldMap, a: u32, b: u32, color: Rgb<u8>) {
    let (w, h) = (img.width() as i32, img.height() as i32);
    let (mut x0, mut y0) = cell_px(map, a, w, h);
    let (x1, y1) = cell_px(map, b, w, h);
    let dx = (x1 - x0).abs();
    let dy = -(y1 - y0).abs();
    let sx = if x0 < x1 { 1 } else { -1 };
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut err = dx + dy;
    let t = SS as i32;
    loop {
        for oy in 0..t {
            for ox in 0..t {
                let (px, py) = (x0 + ox, y0 + oy);
                if px >= 0 && py >= 0 && px < w && py < h {
                    img.put_pixel(px as u32, py as u32, color);
                }
            }
        }
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
/// land cells as state-tinted `<polygon>`s, routes as `<polyline>`s,
/// settlements as `<circle>`s. Water cells are omitted — the ocean background
/// shows through.
pub fn political_svg(map: &WorldMap, size: u32) -> String {
    let s = size as f32;
    let mut svg = String::with_capacity(map.cells.len() * 120);
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
        // The cell's true Voronoi polygon, state-tinted.
        let pts: Vec<String> = c
            .vertex_polygon
            .iter()
            .map(|&v| {
                let (px, py) = svg_px(v, s);
                format!("{px:.1},{py:.1}")
            })
            .collect();
        svg.push_str(&format!(
            "<polygon points=\"{}\" fill=\"{}\"/>\n",
            pts.join(" "),
            hex(state_color(map.provinces[pid as usize].state)),
        ));
    }
    for r in &map.routes {
        // A polyline tracing the route's actual cell path over the terrain.
        let pts: Vec<String> = r
            .path
            .iter()
            .map(|&c| {
                let (px, py) = svg_px(map.cells[c as usize].center, s);
                format!("{px:.1},{py:.1}")
            })
            .collect();
        svg.push_str(&format!(
            "<polyline points=\"{}\" fill=\"none\" stroke=\"{}\" stroke-width=\"1.5\"/>\n",
            pts.join(" "),
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
    // Feature-name labels — only features the `naming` step has named emit a
    // `<text>`; a freshly-generated (unnamed) map produces no labels.
    for st in &map.settlements {
        if st.name.is_empty() {
            continue;
        }
        let (px, py) = svg_px(map.cells[st.cell as usize].center, s);
        svg.push_str(&svg_text(&st.name, px, py - 4.0, 11.0, "#1a1a1a"));
    }
    for state in &map.states {
        if state.name.is_empty() {
            continue;
        }
        // The realm name sits at the state's centroid, not its capital — the
        // capital cell already carries the capital settlement's own label.
        let (px, py) = state_centroid_px(map, state.id, s);
        svg.push_str(&svg_text(&state.name, px, py, 16.0, "#3a2a14"));
    }
    for mr in &map.mountain_ranges {
        if mr.name.is_empty() {
            continue;
        }
        let (px, py) = centroid_px(map, &mr.cells, s);
        svg.push_str(&svg_text(&mr.name, px, py, 12.0, "#4a3a2a"));
    }
    for rv in &map.rivers {
        if rv.name.is_empty() {
            continue;
        }
        let (px, py) = centroid_px(map, &rv.cells, s);
        svg.push_str(&svg_text(&rv.name, px, py, 11.0, "#1e4a6e"));
    }
    for wb in &map.water_bodies {
        if wb.name.is_empty() {
            continue;
        }
        let (px, py) = centroid_px(map, &wb.cells, s);
        svg.push_str(&svg_text(&wb.name, px, py, 13.0, "#cfe2ee"));
    }
    svg.push_str("</svg>\n");
    svg
}

/// SVG pixel coordinates for a feature's label — the cell-centroid, snapped to
/// the member cell nearest it. Snapping keeps the label *on* the feature even
/// when the raw centroid falls outside it (a sea rings the land, so its
/// centroid lands on the continent).
fn centroid_px(map: &WorldMap, cells: &[u32], s: f32) -> (f32, f32) {
    if cells.is_empty() {
        return (0.0, 0.0);
    }
    // B2 sphere migration: project each 3D cell centre to (u, v) for the
    // SVG centroid pick. The (u, v) projection is equirectangular.
    let (mut sx, mut sy) = (0.0f32, 0.0f32);
    for &c in cells {
        let (x, y) = crate::project_uv(map.cells[c as usize].center);
        sx += x;
        sy += y;
    }
    let n = cells.len() as f32;
    let (cx, cy) = (sx / n, sy / n);
    let mut best = cells[0];
    let mut best_d = f32::INFINITY;
    for &c in cells {
        let (x, y) = crate::project_uv(map.cells[c as usize].center);
        let d = (x - cx) * (x - cx) + (y - cy) * (y - cy);
        if d < best_d {
            best_d = d;
            best = c;
        }
    }
    svg_px(map.cells[best as usize].center, s)
}

/// SVG pixel coordinates for a realm's label — the state's land cells, their
/// centroid snapped to a member cell by [`centroid_px`].
fn state_centroid_px(map: &WorldMap, state_id: u32, s: f32) -> (f32, f32) {
    let cells: Vec<u32> = map
        .province_of
        .iter()
        .enumerate()
        .filter(|&(_, &pid)| pid != u32::MAX && map.provinces[pid as usize].state == state_id)
        .map(|(c, _)| c as u32)
        .collect();
    centroid_px(map, &cells, s)
}

/// One SVG `<text>` label, centred at `(px, py)`.
fn svg_text(label: &str, px: f32, py: f32, size: f32, fill: &str) -> String {
    format!(
        "<text x=\"{px:.1}\" y=\"{py:.1}\" font-size=\"{size:.0}\" fill=\"{fill}\" \
         text-anchor=\"middle\" font-family=\"serif\">{}</text>\n",
        xml_escape(label)
    )
}

/// Escape the five XML metacharacters so an LLM-authored name is safe inside
/// SVG text content. `&` is replaced first so the other escapes are not
/// double-escaped.
fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// Cell centre (3D unit-sphere) → SVG pixel via equirectangular projection.
/// `(u, v)` from `project_uv` has `v = 0` at the north pole (top of canvas),
/// matching SVG's y-down convention — **no flip needed**.
fn svg_px(center: [f32; 3], s: f32) -> (f32, f32) {
    let (u, v) = crate::project_uv(center);
    (u * s, v * s)
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

    /// A pixel is "water" iff blue is its strictly dominant channel — true for
    /// every water ramp colour and false for every land ramp colour, in both
    /// styles, and stable under the uniform per-pixel hillshade scaling.
    fn is_blue(p: &Rgb<u8>) -> bool {
        p.0[2] > p.0[0] && p.0[2] > p.0[1]
    }

    #[test]
    fn relief_image_has_requested_dimensions() {
        let img = relief_image(&island_map(), 128, 96, RenderStyle::Realistic);
        assert_eq!(img.width(), 128);
        assert_eq!(img.height(), 96);
    }

    #[test]
    fn relief_image_shows_land_and_water() {
        let img = relief_image(&island_map(), 160, 160, RenderStyle::Realistic);
        assert!(img.pixels().any(is_blue), "relief render shows no water");
        assert!(img.pixels().any(|p| !is_blue(p)), "relief render shows no land");
    }

    #[test]
    fn relief_image_styles_differ() {
        let map = generate(3, &CreativeSeed::default());
        let r = relief_image(&map, 128, 128, RenderStyle::Realistic);
        let a = relief_image(&map, 128, 128, RenderStyle::Atlas);
        assert!(
            r.pixels().zip(a.pixels()).any(|(x, y)| x != y),
            "realistic and atlas relief renders are identical"
        );
    }

    #[test]
    fn relief_image_is_deterministic() {
        let map = generate(5, &CreativeSeed::default());
        let a = relief_image(&map, 100, 100, RenderStyle::Realistic);
        let b = relief_image(&map, 100, 100, RenderStyle::Realistic);
        assert_eq!(a.as_raw(), b.as_raw(), "relief render is not deterministic");
    }

    #[test]
    fn land_and_water_colors_are_total() {
        // exercises every `as u8` cast in the ramps for both styles.
        for style in [RenderStyle::Realistic, RenderStyle::Atlas] {
            for i in 0..=1000 {
                let e = i as f32 / 1000.0;
                let _ = land_color(e, 0.4, style);
                let _ = water_color(e, 0.4, style);
            }
            // out-of-range inputs must clamp, not panic.
            let _ = land_color(-0.5, 0.4, style);
            let _ = land_color(1.9, 0.4, style);
            let _ = water_color(-0.5, 0.4, style);
        }
    }

    #[test]
    fn downsample_averages_each_block() {
        // a 4×4 source → 2×2; the top-left 2×2 block averages to 100.
        let mut src = RgbImage::new(4, 4);
        for (x, y, v) in [(0, 0, 0u8), (1, 0, 100), (0, 1, 200), (1, 1, 100)] {
            src.put_pixel(x, y, Rgb([v, v, v]));
        }
        let out = downsample(&src, 2);
        assert_eq!((out.width(), out.height()), (2, 2));
        // (0 + 100 + 200 + 100) / 4 == 100
        assert_eq!(out.get_pixel(0, 0), &Rgb([100, 100, 100]));
    }

    #[test]
    fn biome_image_has_requested_dimensions() {
        let img = biome_image(&island_map(), 100, 80, RenderStyle::Realistic);
        assert_eq!(img.width(), 100);
        assert_eq!(img.height(), 80);
    }

    #[test]
    fn biome_image_is_not_uniform() {
        // A real island map has ocean + several land biomes ⇒ >1 colour.
        let img = biome_image(&island_map(), 128, 128, RenderStyle::Realistic);
        let first = *img.get_pixel(0, 0);
        assert!(
            img.pixels().any(|p| *p != first),
            "biome image rendered a single flat colour"
        );
    }

    #[test]
    fn political_image_dimensions_and_not_uniform() {
        let map = generate(3, &CreativeSeed::default());
        let img = political_image(&map, 200, 150, RenderStyle::Realistic);
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
        assert!(svg.contains("<rect"), "SVG must contain the background rect");
        assert!(svg.contains("<polyline"), "SVG must contain route polylines");
        assert!(svg.contains("<circle"), "SVG must contain settlement circles");
    }

    #[test]
    fn named_map_svg_has_text_labels() {
        let mut map = generate(3, &CreativeSeed::default());
        // a freshly generated map is unnamed → no <text> labels.
        assert!(
            !political_svg(&map, 256).contains("<text"),
            "an unnamed map must emit no labels"
        );
        // name a settlement, a state, and a mountain range — each distinct
        // label code path must render.
        map.settlements[0].name = "Testburg".to_string();
        map.states[0].name = "Testrealm".to_string();
        if let Some(mr) = map.mountain_ranges.first_mut() {
            mr.name = "Testpeaks".to_string();
        }
        let svg = political_svg(&map, 256);
        assert!(svg.contains("<text"), "a named map must emit <text> labels");
        assert!(svg.contains("Testburg"), "the settlement label must be in the SVG");
        assert!(svg.contains("Testrealm"), "the state label must be in the SVG");
        if !map.mountain_ranges.is_empty() {
            assert!(svg.contains("Testpeaks"), "the range label must be in the SVG");
        }
    }

    #[test]
    fn xml_escape_neutralizes_metacharacters() {
        let escaped = xml_escape("A & B <tag> \"q\" it's");
        assert!(!escaped.contains('<') && !escaped.contains('>'));
        assert!(!escaped.contains('\''), "a raw apostrophe must be escaped");
        assert!(escaped.contains("&amp;"));
        assert!(escaped.contains("&lt;"));
        assert!(escaped.contains("&quot;"));
        assert!(escaped.contains("&apos;"));
    }
}
