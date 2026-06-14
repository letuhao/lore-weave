//! Raster + SVG map export.
//!
//! Rendering is a CLI side output: it is *not* part of the `WorldMap` value or
//! its `content_hash`. Categorical maps (biome / political / culture) place
//! pixels by nearest-cell-centre lookup — which *is* the Voronoi diagram —
//! then composite a hillshade from [`crate::relief`] over the flat fill. The
//! hypsometric [`relief_image`] renders the relief field directly.

use image::{Rgb, RgbImage};

use crate::biome::BiomeKind;
use crate::params::RenderTheme;
use crate::projection::Projection;
use crate::relief::{ReliefField, RenderStyle};
use crate::world_map::{RouteKind, SettlementRole, WorldMap};

/// Wrap an `[u8;3]` theme colour as an `image::Rgb`.
fn rgb(c: [u8; 3]) -> Rgb<u8> {
    Rgb(c)
}

/// Render `inner` at `ss×` the requested size, then box-downsample back —
/// anti-aliasing coastlines, the hillshade and the Voronoi cell edges, and
/// letting the fBm detail sample finer. The public render entry points are thin
/// wrappers over this. `ss` is [`RenderTheme::supersample`].
fn supersampled(width: u32, height: u32, ss: u32, inner: impl Fn(u32, u32) -> RgbImage) -> RgbImage {
    downsample(&inner(width * ss, height * ss), ss)
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
/// nearest cell centre — which *is* the Voronoi diagram. Pixels outside the
/// projected world (the Orthographic disc exterior) take [`BACKGROUND`].
///
/// `(u, v)` has `v = 0` at the north pole (top), matching raster row 0 — so
/// no image-y flip is needed (Stage B sphere migration).
fn rasterize<F: Fn(usize) -> Rgb<u8>>(
    map: &WorldMap,
    width: u32,
    height: u32,
    proj: Projection,
    bg: Rgb<u8>,
    color: F,
) -> RgbImage {
    let index = SpatialIndex::build(map, proj);
    let mut img = RgbImage::new(width, height);
    for py in 0..height {
        for px in 0..width {
            let x = (px as f32 + 0.5) / width as f32;
            let y = (py as f32 + 0.5) / height as f32;
            // Outside the projected world (Orthographic disc exterior) → bg.
            if proj.back_project((x, y)).is_none() {
                img.put_pixel(px, py, bg);
                continue;
            }
            let cell = index.nearest(map, x, y);
            img.put_pixel(px, py, color(cell));
        }
    }
    img
}

/// Render a hypsometric relief image — the showcase terrain render. Continuous
/// barycentric-interpolated elevation, fBm detail, NW hillshade; palette and
/// coastline treatment per `style`. Supersampled (see [`supersampled`]).
pub fn relief_image(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    supersampled(width, height, theme.supersample, |w, h| {
        relief_image_inner(map, w, h, style, proj, theme)
    })
}

fn relief_image_inner(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style, proj);
    let mut img = RgbImage::new(width, height);
    for py in 0..height {
        for px in 0..width {
            let i = (py * width + px) as usize;
            if !relief.visible[i] {
                img.put_pixel(px, py, rgb(theme.background));
                continue;
            }
            let base = if relief.water[i] {
                water_color(relief.elev[i], relief.sea, style, theme)
            } else {
                land_color(relief.elev[i], relief.sea, style, theme)
            };
            img.put_pixel(px, py, shade_rgb(base, relief.shade[i]));
        }
    }
    if style == RenderStyle::Atlas {
        draw_coast_outline(&mut img, &relief, theme.supersample, rgb(theme.coast_ink));
    }
    img
}

/// Render a biome-coloured image of `map`, hillshaded by the relief field.
pub fn biome_image(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    supersampled(width, height, theme.supersample, |w, h| {
        biome_image_inner(map, w, h, style, proj, theme)
    })
}

fn biome_image_inner(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style, proj);
    let mut img = rasterize(map, width, height, proj, rgb(theme.background), |cell| {
        biome_color(map.biome[cell], theme)
    });
    apply_shade(&mut img, &relief);
    img
}

/// Colour for each `BiomeKind` (theme table, indexed by `tag`).
fn biome_color(b: BiomeKind, theme: &RenderTheme) -> Rgb<u8> {
    rgb(theme.biome[b.tag() as usize])
}

/// Render a culture-region image of `map` — each land cell tinted by its
/// culture id, hillshaded by the relief field; water cells are ocean-blue.
pub fn culture_image(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    supersampled(width, height, theme.supersample, |w, h| {
        culture_image_inner(map, w, h, style, proj, theme)
    })
}

fn culture_image_inner(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style, proj);
    let mut img = rasterize(map, width, height, proj, rgb(theme.background), |cell| {
        let cid = map.culture_of[cell];
        if cid == u32::MAX {
            rgb(theme.water_flat)
        } else {
            culture_color(cid, theme)
        }
    });
    apply_shade(&mut img, &relief);
    img
}

/// Render a tectonic-plate image (Phase 2): cells tinted by plate id —
/// continental plates warm, oceanic plates cool — boundary cells overdrawn by
/// their `BoundaryKind` colour, hillshaded by the relief field. In `Profile`
/// `TerrainMode` (no plates) this falls back to the biome image.
pub fn plate_image(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    if map.plates.is_empty() {
        return biome_image(map, width, height, style, proj, theme);
    }
    supersampled(width, height, theme.supersample, |w, h| {
        plate_image_inner(map, w, h, style, proj, theme)
    })
}

fn plate_image_inner(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style, proj);
    // Per-cell boundary kind: the kind of the (cell plate, lowest differing
    // neighbour plate) pair — mirrors `plates::boundary_field`'s seeding so
    // the outline matches the orogeny.
    let boundary_kind = cell_boundary_kinds(map);
    let mut img = rasterize(map, width, height, proj, rgb(theme.background), |cell| {
        let pid = map.plate_of[cell];
        if pid == u32::MAX {
            return rgb(theme.water_flat);
        }
        match boundary_kind[cell] {
            Some(bk) => boundary_color(bk, theme),
            None => plate_color(map.plates[pid as usize].kind, pid, theme),
        }
    });
    apply_shade(&mut img, &relief);
    img
}

/// Per-cell `Some(BoundaryKind)` for boundary cells (a neighbour on a
/// different plate), else `None`. The pair kind comes from `map.plate_boundaries`.
fn cell_boundary_kinds(map: &WorldMap) -> Vec<Option<crate::world_map::BoundaryKind>> {
    use std::collections::BTreeMap;
    let mut pair_kind: BTreeMap<(u32, u32), crate::world_map::BoundaryKind> = BTreeMap::new();
    for b in &map.plate_boundaries {
        pair_kind.insert((b.plate_a, b.plate_b), b.kind);
    }
    (0..map.cells.len())
        .map(|c| {
            let pa = map.plate_of[c];
            if pa == u32::MAX {
                return None;
            }
            let mut other: Option<u32> = None;
            for &nb in &map.neighbors[c] {
                let pb = map.plate_of[nb as usize];
                if pb != pa {
                    other = Some(other.map_or(pb, |o| o.min(pb)));
                }
            }
            other.map(|pb| {
                let key = if pa < pb { (pa, pb) } else { (pb, pa) };
                pair_kind
                    .get(&key)
                    .copied()
                    .unwrap_or(crate::world_map::BoundaryKind::Interior)
            })
        })
        .collect()
}

/// Warm tint for continental plates, cool for oceanic; varied per id. The base
/// tints are theme params; the per-id jitter (so adjacent same-kind plates read
/// apart) is fixed render math.
fn plate_color(kind: crate::world_map::PlateKind, id: u32, theme: &RenderTheme) -> Rgb<u8> {
    use crate::world_map::PlateKind;
    let j = ((id.wrapping_mul(2654435761)) >> 24) as i32 % 40 - 20;
    let clamp = |v: i32| v.clamp(0, 255) as u8;
    let base = match kind {
        PlateKind::Continental => theme.plate_continental,
        PlateKind::Oceanic => theme.plate_oceanic,
    };
    let (r, g, b) = (base[0] as i32, base[1] as i32, base[2] as i32);
    match kind {
        PlateKind::Continental => Rgb([clamp(r + j), clamp(g + j), clamp(b + j / 2)]),
        PlateKind::Oceanic => Rgb([clamp(r + j / 2), clamp(g + j), clamp(b + j)]),
    }
}

/// Outline colour per boundary kind (theme table, by enum order).
fn boundary_color(k: crate::world_map::BoundaryKind, theme: &RenderTheme) -> Rgb<u8> {
    use crate::world_map::BoundaryKind as B;
    let i = match k {
        B::FoldMountain => 0,
        B::Subduction => 1,
        B::IslandArc => 2,
        B::Ridge => 3,
        B::Rift => 4,
        B::Fault => 5,
        B::Interior => 6,
    };
    rgb(theme.boundary[i])
}

/// 3-tier geometric-hierarchy choropleth (C-1b): each land cell is filled with
/// its **region** colour; a cell on a **continent** boundary (a neighbour in a
/// different continent — including the ocean, i.e. the coastline) is drawn
/// near-black, and a cell on a **subcontinent** boundary dark-grey. All three
/// levels read in one image. Ocean cells are blue. Falls back to
/// [`biome_image`] for a land-less world (no hierarchy to show).
pub fn region_image(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    if map.continents.is_empty() {
        return biome_image(map, width, height, style, proj, theme);
    }
    supersampled(width, height, theme.supersample, |w, h| {
        region_image_inner(map, w, h, style, proj, theme)
    })
}

fn region_image_inner(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style, proj);
    let water = rgb(theme.water_flat);
    let continent_border = rgb(theme.tier1_border);
    let subcontinent_border = rgb(theme.tier2_border);
    let mut img = rasterize(map, width, height, proj, rgb(theme.background), |cell| {
        let cont = map.continent_of[cell];
        if cont == u32::MAX {
            return water;
        }
        let sub = map.subcontinent_of[cell];
        let mut continent_edge = false;
        let mut subcontinent_edge = false;
        for &nb in &map.neighbors[cell] {
            let nb = nb as usize;
            if map.continent_of[nb] != cont {
                continent_edge = true;
            } else if map.subcontinent_of[nb] != sub {
                subcontinent_edge = true;
            }
        }
        if continent_edge {
            continent_border
        } else if subcontinent_edge {
            subcontinent_border
        } else {
            id_color(map.region_of[cell], theme)
        }
    });
    apply_shade(&mut img, &relief);
    img
}

/// A well-separated tint per id — a golden-ratio hue rotation at fixed
/// saturation/value, so adjacent ids read apart. Used to colour both geometric
/// regions (`region_image`) and political provinces (`realm_image`).
fn id_color(id: u32, theme: &RenderTheme) -> Rgb<u8> {
    let hue = (id as f32 * 0.618_034).fract();
    hsv_to_rgb(hue, theme.choropleth_sat, theme.choropleth_val)
}

/// `h, s, v` each in `[0, 1]` → 8-bit RGB.
fn hsv_to_rgb(h: f32, s: f32, v: f32) -> Rgb<u8> {
    let i = (h * 6.0).floor();
    let f = h * 6.0 - i;
    let p = v * (1.0 - s);
    let q = v * (1.0 - f * s);
    let t = v * (1.0 - (1.0 - f) * s);
    let (r, g, b) = match (i as i32).rem_euclid(6) {
        0 => (v, t, p),
        1 => (q, v, p),
        2 => (p, v, t),
        3 => (p, q, v),
        4 => (t, p, v),
        _ => (v, p, q),
    };
    let c = |x: f32| (x * 255.0).round().clamp(0.0, 255.0) as u8;
    Rgb([c(r), c(g), c(b)])
}

/// Political-tier choropleth (C-2b): each land cell is filled with its
/// **province** colour; a cell on a **realm** boundary (a neighbour in a
/// different realm — including the ocean) is drawn near-black, and a cell on a
/// **state** boundary dark-grey. So the province ⊆ state ⊆ realm nesting reads
/// in one image. Ocean cells are blue. Falls back to [`biome_image`] for a
/// world with no political tiers (no land).
pub fn realm_image(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    if map.realms.is_empty() {
        return biome_image(map, width, height, style, proj, theme);
    }
    supersampled(width, height, theme.supersample, |w, h| {
        realm_image_inner(map, w, h, style, proj, theme)
    })
}

fn realm_image_inner(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style, proj);
    let water = rgb(theme.water_flat);
    let realm_border = rgb(theme.tier1_border);
    let state_border = rgb(theme.tier2_border);
    // Map a cell to its (state, realm); `u32::MAX` for water / unassigned.
    let state_of = |c: usize| -> u32 {
        let p = map.province_of[c];
        if p == u32::MAX {
            u32::MAX
        } else {
            map.provinces[p as usize].state
        }
    };
    let realm_of = |c: usize| -> u32 {
        let s = state_of(c);
        if s == u32::MAX {
            u32::MAX
        } else {
            map.states[s as usize].realm
        }
    };
    let mut img = rasterize(map, width, height, proj, rgb(theme.background), |cell| {
        let prov = map.province_of[cell];
        if prov == u32::MAX {
            return water;
        }
        let realm = realm_of(cell);
        let state = state_of(cell);
        let mut realm_edge = false;
        let mut state_edge = false;
        for &nb in &map.neighbors[cell] {
            let nb = nb as usize;
            if realm_of(nb) != realm {
                realm_edge = true;
            } else if state_of(nb) != state {
                state_edge = true;
            }
        }
        if realm_edge {
            realm_border
        } else if state_edge {
            state_border
        } else {
            id_color(prov, theme)
        }
    });
    apply_shade(&mut img, &relief);
    img
}

/// A distinct tint per culture id (theme palette, cycled).
fn culture_color(id: u32, theme: &RenderTheme) -> Rgb<u8> {
    rgb(theme.culture[(id as usize) % theme.culture.len()])
}

/// A uniform bucket grid over the **projected** cell centres `(u, v) ∈ [0,1]²`
/// for fast nearest-centre lookup. Projection-aware (Stage B-2): only cells
/// the projection makes *visible* are indexed (the Orthographic far side is
/// excluded), and the `u` axis **wraps** under Equirectangular so the nearest
/// search has no antimeridian seam.
pub(crate) struct SpatialIndex {
    side: usize,
    buckets: Vec<Vec<u32>>,
    proj: Projection,
    /// Whether the `u` axis wraps (Equirectangular longitude seam).
    wrap_u: bool,
}

impl SpatialIndex {
    pub(crate) fn build(map: &WorldMap, proj: Projection) -> Self {
        let side = (map.cells.len() as f32).sqrt().round().max(1.0) as usize;
        let mut buckets = vec![Vec::new(); side * side];
        for (i, c) in map.cells.iter().enumerate() {
            // Only index cells the projection makes visible.
            if let Some((cu, cv)) = proj.project(c.center) {
                let b = bucket_of(cu, cv, side);
                buckets[b].push(i as u32);
            }
        }
        let wrap_u = matches!(proj, Projection::Equirectangular);
        SpatialIndex {
            side,
            buckets,
            proj,
            wrap_u,
        }
    }

    /// Nearest *visible* cell to the canvas point `(x, y) ∈ [0,1]²`, measured
    /// in projected `(u, v)` distance (with `u`-wrap under Equirectangular).
    /// Widening-ring search with a distance-correct stop.
    pub(crate) fn nearest(&self, map: &WorldMap, x: f32, y: f32) -> usize {
        let side = self.side as isize;
        let gx = ((x * self.side as f32) as isize).clamp(0, side - 1);
        let gy = ((y * self.side as f32) as isize).clamp(0, side - 1);
        let mut best = 0usize;
        let mut best_d = f32::INFINITY;
        let mut radius = 0isize;
        while radius <= side {
            for by in (gy - radius).max(0)..=(gy + radius).min(side - 1) {
                for dbx in -radius..=radius {
                    // `u`-wrap: bucket column wraps modulo `side` under
                    // Equirectangular; otherwise clamp to the grid.
                    let bx = if self.wrap_u {
                        (gx + dbx).rem_euclid(side)
                    } else {
                        let v = gx + dbx;
                        if v < 0 || v >= side {
                            continue;
                        }
                        v
                    };
                    for &ci in &self.buckets[(by * side + bx) as usize] {
                        let c = &map.cells[ci as usize];
                        let (cu, cv) = self
                            .proj
                            .project(c.center)
                            .expect("indexed cells are visible");
                        let du = if self.wrap_u {
                            let d = (cu - x).abs();
                            d.min(1.0 - d)
                        } else {
                            cu - x
                        };
                        let dv = cv - y;
                        let d = du * du + dv * dv;
                        if d < best_d {
                            best_d = d;
                            best = ci as usize;
                        }
                    }
                }
            }
            // Every cell in a not-yet-searched ring is at least `radius/side`
            // away from the pixel's bucket. Stop once the best hit is provably
            // no farther (compare squared distances). `radius` starts at 0 so
            // the home bucket is searched before any stop test.
            if best_d.is_finite() {
                let covered = radius as f32 / self.side as f32;
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
            let i = (py * relief.width + px) as usize;
            // Don't shade background pixels (Orthographic disc exterior) — they
            // are not part of the lit globe surface.
            if !relief.visible[i] {
                continue;
            }
            let s = relief.shade[i];
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

/// Linear-interpolate a colour through an ascending `(stop, rgb)` ramp. Stops
/// SHOULD be ascending; a non-ascending theme yields odd-but-deterministic
/// colours (GIGO), never a panic — the clamp below is order-tolerant
/// (`f32::clamp` would otherwise panic when `min > max`).
fn ramp(stops: &[(f32, [u8; 3])], t: f32) -> Rgb<u8> {
    let (a, b) = (stops[0].0, stops[stops.len() - 1].0);
    let t = t.max(a.min(b)).min(a.max(b));
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
fn land_color(elev: f32, sea: f32, style: RenderStyle, theme: &RenderTheme) -> Rgb<u8> {
    let t = ((elev - sea) / (1.0 - sea).max(1e-3)).clamp(0.0, 1.0);
    match style {
        RenderStyle::Realistic => ramp(&theme.land_realistic, t),
        RenderStyle::Atlas => ramp(&theme.land_atlas, t),
    }
}

/// Water colour by normalized depth below sea level.
fn water_color(elev: f32, sea: f32, style: RenderStyle, theme: &RenderTheme) -> Rgb<u8> {
    let d = ((sea - elev) / sea.max(1e-3)).clamp(0.0, 1.0);
    match style {
        RenderStyle::Realistic => ramp(&theme.water_realistic, d),
        RenderStyle::Atlas => ramp(&theme.water_atlas, d),
    }
}

/// Atlas style: stroke an ink line wherever a land pixel touches water. The
/// line is stamped `SS` pixels thick so it survives the supersample
/// downsample as a crisp outline rather than a faint ~quarter-strength edge.
fn draw_coast_outline(img: &mut RgbImage, relief: &ReliefField, ss: u32, ink: Rgb<u8>) {
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
                for oy in 0..ss {
                    for ox in 0..ss {
                        let (sx, sy) = (px + ox, py + oy);
                        if sx < w && sy < h {
                            img.put_pixel(sx, sy, ink);
                        }
                    }
                }
            }
        }
    }
}

/// Render a political map (Phase 3): cells tinted by state and hillshaded,
/// with routes drawn as lines and settlements as dots.
pub fn political_image(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    supersampled(width, height, theme.supersample, |w, h| {
        political_image_inner(map, w, h, style, proj, theme)
    })
}

fn political_image_inner(
    map: &WorldMap,
    width: u32,
    height: u32,
    style: RenderStyle,
    proj: Projection,
    theme: &RenderTheme,
) -> RgbImage {
    let relief = ReliefField::build(map, width, height, style, proj);
    let mut img = rasterize(map, width, height, proj, rgb(theme.background), |cell| {
        political_cell_color(map, cell, theme)
    });
    apply_shade(&mut img, &relief);
    for r in &map.routes {
        // Trace the route's actual cell path, not a straight endpoint line.
        let color = route_color(r.kind, theme);
        for seg in r.path.windows(2) {
            draw_line(&mut img, map, seg[0], seg[1], color, proj, theme.supersample);
        }
    }
    for s in &map.settlements {
        // Rendering at SS× — scale the dot radius so it survives downsampling.
        draw_dot(
            &mut img,
            map,
            s.cell,
            theme.supersample * (1 + u32::from(s.population_tier)),
            settlement_color(s.role, theme),
            proj,
        );
    }
    img
}

/// Base cell colour for the political map — water blue, else tinted by state.
fn political_cell_color(map: &WorldMap, cell: usize, theme: &RenderTheme) -> Rgb<u8> {
    let pid = map.province_of[cell];
    if pid == u32::MAX {
        return rgb(theme.water_flat);
    }
    state_color(map.provinces[pid as usize].state, theme)
}

/// A distinct tint per state id (theme palette, cycled).
fn state_color(id: u32, theme: &RenderTheme) -> Rgb<u8> {
    rgb(theme.state[(id as usize) % theme.state.len()])
}

fn route_color(k: RouteKind, theme: &RenderTheme) -> Rgb<u8> {
    let i = match k {
        RouteKind::Road => 0,
        RouteKind::Trail => 1,
        RouteKind::RiverNavigation => 2,
        RouteKind::SeaLane => 3,
        RouteKind::MountainPass => 4,
    };
    rgb(theme.route[i])
}

fn settlement_color(r: SettlementRole, theme: &RenderTheme) -> Rgb<u8> {
    let i = match r {
        SettlementRole::Capital => 0,
        SettlementRole::City => 1,
        SettlementRole::Town => 2,
        SettlementRole::Village => 3,
        SettlementRole::Hamlet => 4,
        SettlementRole::Fortress => 5,
    };
    rgb(theme.settlement[i])
}

/// Pixel coordinate of a cell centre under `proj`. `None` when the cell is on
/// the hidden hemisphere (Orthographic far side). `(u, v)` has `v = 0` at the
/// top (north pole) — matches raster row 0 at top, so no flip is needed.
fn cell_px(map: &WorldMap, cell: u32, w: i32, h: i32, proj: Projection) -> Option<(i32, i32)> {
    let (u, v) = proj.project(map.cells[cell as usize].center)?;
    let px = ((u * w as f32) as i32).clamp(0, w - 1);
    let py = ((v * h as f32) as i32).clamp(0, h - 1);
    Some((px, py))
}

/// Bresenham line between two cell centres, stamped `SS` pixels thick so it
/// stays solid through the supersample downsample. Skipped if either endpoint
/// is on the hidden hemisphere (Orthographic). Endpoints whose projected `u`
/// straddle the antimeridian seam would draw a long wrong line; such segments
/// are skipped when the pixel gap exceeds half the canvas width.
fn draw_line(img: &mut RgbImage, map: &WorldMap, a: u32, b: u32, color: Rgb<u8>, proj: Projection, ss: u32) {
    let (w, h) = (img.width() as i32, img.height() as i32);
    let (Some((mut x0, mut y0)), Some((x1, y1))) =
        (cell_px(map, a, w, h, proj), cell_px(map, b, w, h, proj))
    else {
        return; // a hidden endpoint — skip this segment
    };
    // Antimeridian seam guard (Equirectangular): a route segment whose
    // endpoints sit on opposite sides of the lon=±π seam would otherwise be
    // drawn as a long horizontal streak across the whole map.
    if matches!(proj, Projection::Equirectangular) && (x1 - x0).abs() > w / 2 {
        return;
    }
    let dx = (x1 - x0).abs();
    let dy = -(y1 - y0).abs();
    let sx = if x0 < x1 { 1 } else { -1 };
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut err = dx + dy;
    let t = ss as i32;
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

/// Filled square dot at a cell centre. Skipped for a hidden-hemisphere cell.
fn draw_dot(img: &mut RgbImage, map: &WorldMap, cell: u32, radius: u32, color: Rgb<u8>, proj: Projection) {
    let (w, h) = (img.width() as i32, img.height() as i32);
    let Some((cx, cy)) = cell_px(map, cell, w, h, proj) else {
        return;
    };
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
pub fn political_svg(map: &WorldMap, size: u32, theme: &RenderTheme) -> String {
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
            hex(state_color(map.provinces[pid as usize].state, theme)),
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
            hex(route_color(r.kind, theme)),
        ));
    }
    for st in &map.settlements {
        let (px, py) = svg_px(map.cells[st.cell as usize].center, s);
        svg.push_str(&format!(
            "<circle cx=\"{px:.1}\" cy=\"{py:.1}\" r=\"{:.1}\" fill=\"{}\"/>\n",
            2.0 + f32::from(st.population_tier),
            hex(settlement_color(st.role, theme)),
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
        let (x, y) = crate::projection::equirectangular(map.cells[c as usize].center);
        sx += x;
        sy += y;
    }
    let n = cells.len() as f32;
    let (cx, cy) = (sx / n, sy / n);
    let mut best = cells[0];
    let mut best_d = f32::INFINITY;
    for &c in cells {
        let (x, y) = crate::projection::equirectangular(map.cells[c as usize].center);
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
    let (u, v) = crate::projection::equirectangular(center);
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

    /// The default background, for the orthographic-corner tests (was a const).
    const BACKGROUND: Rgb<u8> = Rgb([12, 14, 18]);

    // P8b: the render fns now take a `&RenderTheme`. These default-theme
    // wrappers shadow the `use super::*` glob (local items outrank glob imports),
    // so the existing tests below — and the pinned-hash baseline — exercise the
    // default theme without threading it through every call site by hand.
    fn dt() -> RenderTheme {
        RenderTheme::default()
    }
    fn relief_image(m: &WorldMap, w: u32, h: u32, s: RenderStyle, p: Projection) -> RgbImage {
        super::relief_image(m, w, h, s, p, &dt())
    }
    fn biome_image(m: &WorldMap, w: u32, h: u32, s: RenderStyle, p: Projection) -> RgbImage {
        super::biome_image(m, w, h, s, p, &dt())
    }
    fn culture_image(m: &WorldMap, w: u32, h: u32, s: RenderStyle, p: Projection) -> RgbImage {
        super::culture_image(m, w, h, s, p, &dt())
    }
    fn plate_image(m: &WorldMap, w: u32, h: u32, s: RenderStyle, p: Projection) -> RgbImage {
        super::plate_image(m, w, h, s, p, &dt())
    }
    fn region_image(m: &WorldMap, w: u32, h: u32, s: RenderStyle, p: Projection) -> RgbImage {
        super::region_image(m, w, h, s, p, &dt())
    }
    fn realm_image(m: &WorldMap, w: u32, h: u32, s: RenderStyle, p: Projection) -> RgbImage {
        super::realm_image(m, w, h, s, p, &dt())
    }
    fn political_image(m: &WorldMap, w: u32, h: u32, s: RenderStyle, p: Projection) -> RgbImage {
        super::political_image(m, w, h, s, p, &dt())
    }
    fn political_svg(m: &WorldMap, size: u32) -> String {
        super::political_svg(m, size, &dt())
    }
    fn land_color(elev: f32, sea: f32, style: RenderStyle) -> Rgb<u8> {
        super::land_color(elev, sea, style, &dt())
    }
    fn water_color(elev: f32, sea: f32, style: RenderStyle) -> Rgb<u8> {
        super::water_color(elev, sea, style, &dt())
    }

    /// **Render-palette byte-identical pin** (P8b safety net). The sphere render
    /// is not part of `content_hash` and had no test guarding its output, so the
    /// RenderTheme parameterization (moving palettes/ramps into params) could
    /// silently shift a colour. This pins the blake3 of seed-7 renders (every
    /// map mode, both styles where they differ) at a fixed 80×40 — a default
    /// `RenderTheme` must reproduce them byte-for-byte. Re-captured at **elevation
    /// S5** (coupled uplift⇄erosion, 2026-06-14): S5 changed default land
    /// elevation, so every relief-derived render shifts (expected).
    #[test]
    fn render_output_is_byte_identical_baseline() {
        let m = generate(7, &CreativeSeed::default());
        let p = crate::projection::Projection::Equirectangular;
        let hh = |img: &RgbImage| blake3::hash(img.as_raw()).to_hex().to_string();
        let r = RenderStyle::Realistic;
        let a = RenderStyle::Atlas;
        let cases: [(&str, RgbImage, &str); 8] = [
            ("relief/realistic", relief_image(&m, 80, 40, r, p), "dc650c17012997fd492734ab9b8a7c3a4e5a98b76b3241e299806f7abab7e4d2"),
            ("relief/atlas", relief_image(&m, 80, 40, a, p), "33188d32aa79dac60fc625cf2340d530f8e9a7111824c1f13bb85df8b9e212e3"),
            ("biome", biome_image(&m, 80, 40, r, p), "2c208a98b9aa880b18264d3127b0e22df30a9b2372bdd667de849f1ee534dc0f"),
            ("culture", culture_image(&m, 80, 40, r, p), "37173cea3e02e0c5656c6e17d3bfae7d58c6bdae096109ccbd4b2c36b29814b8"),
            ("plate", plate_image(&m, 80, 40, r, p), "cca4c24940919ed89b886b4caf26e5092230da58679092d581bc613725542aac"),
            ("region", region_image(&m, 80, 40, r, p), "dcff6323ae495070261148770cf43a80512fd5c48c829d9ae1cedce02e47c8c7"),
            ("realm", realm_image(&m, 80, 40, r, p), "dcff6323ae495070261148770cf43a80512fd5c48c829d9ae1cedce02e47c8c7"),
            ("political", political_image(&m, 80, 40, r, p), "a1c1b01528d03c929d929ac577674c80bb5369e9a474adb0fd4aaec7fdc4772b"),
        ];
        for (name, img, want) in &cases {
            assert_eq!(&hh(img), want, "render output drifted for {name}");
        }
    }

    /// **A non-default RenderTheme changes the render** (P8b) — recolour the
    /// biome palette and the biome image must differ. Proves the theme is wired
    /// (the byte-identical pin above proves the *default* is unchanged).
    #[test]
    fn render_theme_recolours_the_output() {
        let m = generate(7, &CreativeSeed::default());
        let p = Projection::Equirectangular;
        let base = super::biome_image(&m, 80, 40, RenderStyle::Realistic, p, &dt());
        let mut theme = dt();
        theme.biome[BiomeKind::Jungle.tag() as usize] = [255, 0, 255]; // magenta jungle
        let recolored = super::biome_image(&m, 80, 40, RenderStyle::Realistic, p, &theme);
        assert_ne!(base.as_raw(), recolored.as_raw(), "recolouring a biome must change the render");
    }

    /// **A pathological (descending) ramp must not panic** (P8b, review-impl #1)
    /// — `ramp`'s clamp is order-tolerant, so a config with land/water stops out
    /// of order renders odd colours but never panics (`f32::clamp(min>max)` would).
    #[test]
    fn descending_ramp_does_not_panic() {
        let m = generate(7, &CreativeSeed::default());
        let p = Projection::Equirectangular;
        let mut theme = dt();
        // Reverse the stop positions so they descend (0..1 → 1..0).
        let n = theme.land_realistic.len();
        for k in 0..n {
            theme.land_realistic[k].0 = 1.0 - theme.land_realistic[k].0;
        }
        theme.land_realistic.reverse(); // keep array form; positions now descend
        theme.water_realistic[0].0 = 1.0;
        theme.water_realistic[3].0 = 0.0;
        // Must not panic.
        let _ = super::relief_image(&m, 80, 40, RenderStyle::Realistic, p, &theme);
    }

    /// A non-default supersample changes anti-aliasing → a different render.
    #[test]
    fn render_theme_supersample_changes_the_output() {
        let m = generate(7, &CreativeSeed::default());
        let p = Projection::Equirectangular;
        let base = super::relief_image(&m, 80, 40, RenderStyle::Realistic, p, &dt());
        let theme = RenderTheme { supersample: 1, ..dt() };
        let ss1 = super::relief_image(&m, 80, 40, RenderStyle::Realistic, p, &theme);
        assert_ne!(base.as_raw(), ss1.as_raw(), "changing supersample must change the render");
    }

    #[test]
    fn relief_image_has_requested_dimensions() {
        let img = relief_image(&island_map(), 128, 96, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!(img.width(), 128);
        assert_eq!(img.height(), 96);
    }

    #[test]
    fn relief_image_shows_land_and_water() {
        let img = relief_image(&island_map(), 160, 160, RenderStyle::Realistic, Projection::Equirectangular);
        assert!(img.pixels().any(is_blue), "relief render shows no water");
        assert!(img.pixels().any(|p| !is_blue(p)), "relief render shows no land");
    }

    #[test]
    fn relief_image_styles_differ() {
        let map = generate(3, &CreativeSeed::default());
        let r = relief_image(&map, 128, 128, RenderStyle::Realistic, Projection::Equirectangular);
        let a = relief_image(&map, 128, 128, RenderStyle::Atlas, Projection::Equirectangular);
        assert!(
            r.pixels().zip(a.pixels()).any(|(x, y)| x != y),
            "realistic and atlas relief renders are identical"
        );
    }

    #[test]
    fn relief_image_is_deterministic() {
        let map = generate(5, &CreativeSeed::default());
        let a = relief_image(&map, 100, 100, RenderStyle::Realistic, Projection::Equirectangular);
        let b = relief_image(&map, 100, 100, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!(a.as_raw(), b.as_raw(), "relief render is not deterministic");
    }

    fn ortho() -> Projection {
        Projection::Orthographic {
            camera: [1.0, 0.0, 0.0],
        }
    }

    #[test]
    fn orthographic_relief_corners_are_background() {
        // The disc is inscribed in the square, so the four corners fall
        // outside it and must be the background colour.
        let img = relief_image(&island_map(), 128, 128, RenderStyle::Realistic, ortho());
        let (w, h) = (img.width(), img.height());
        for &(x, y) in &[(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)] {
            assert_eq!(
                img.get_pixel(x, y),
                &BACKGROUND,
                "orthographic corner ({x},{y}) is not the background colour"
            );
        }
        // The disc centre must NOT be background (it's the visible globe).
        assert_ne!(img.get_pixel(w / 2, h / 2), &BACKGROUND);
    }

    #[test]
    fn orthographic_relief_shows_land_and_water() {
        let img = relief_image(&island_map(), 160, 160, RenderStyle::Realistic, ortho());
        assert!(img.pixels().any(is_blue), "orthographic relief shows no water");
        assert!(
            img.pixels().any(|p| !is_blue(p) && p != &BACKGROUND),
            "orthographic relief shows no land"
        );
    }

    #[test]
    fn orthographic_render_is_deterministic() {
        let map = generate(5, &CreativeSeed::default());
        let a = relief_image(&map, 96, 96, RenderStyle::Realistic, ortho());
        let b = relief_image(&map, 96, 96, RenderStyle::Realistic, ortho());
        assert_eq!(a.as_raw(), b.as_raw(), "orthographic render is not deterministic");
    }

    #[test]
    fn orthographic_and_equirectangular_differ() {
        let map = generate(3, &CreativeSeed::default());
        let e = relief_image(&map, 128, 128, RenderStyle::Realistic, Projection::Equirectangular);
        let o = relief_image(&map, 128, 128, RenderStyle::Realistic, ortho());
        assert!(
            e.pixels().zip(o.pixels()).any(|(x, y)| x != y),
            "the two projections produced identical images"
        );
    }

    #[test]
    fn orthographic_biome_corners_are_background() {
        let img = biome_image(&island_map(), 100, 100, RenderStyle::Realistic, ortho());
        assert_eq!(img.get_pixel(0, 0), &BACKGROUND);
        assert_ne!(img.get_pixel(50, 50), &BACKGROUND);
    }

    #[test]
    fn plate_image_renders_and_is_not_uniform() {
        // Default (Tectonic) map → plate layer present → distinct plate tints.
        let map = generate(7, &CreativeSeed::default());
        assert!(!map.plates.is_empty(), "tectonic map must expose plates");
        let img = plate_image(&map, 160, 160, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!((img.width(), img.height()), (160, 160));
        let first = *img.get_pixel(0, 0);
        assert!(
            img.pixels().any(|p| *p != first),
            "plate image rendered a single flat colour"
        );
    }

    #[test]
    fn plate_image_falls_back_to_biome_in_profile_mode() {
        // Profile mode → no plates → plate_image == biome_image.
        let cs = CreativeSeed {
            terrain_mode: crate::TerrainMode::Profile,
            ..CreativeSeed::default()
        };
        let map = generate(7, &cs);
        assert!(map.plates.is_empty());
        let plate = plate_image(&map, 96, 96, RenderStyle::Realistic, Projection::Equirectangular);
        let biome = biome_image(&map, 96, 96, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!(plate.as_raw(), biome.as_raw(), "profile-mode plate_image must equal biome_image");
    }

    #[test]
    fn region_image_renders_and_is_not_uniform() {
        // Default (Tectonic) map has land ⇒ a multi-region choropleth.
        let map = generate(7, &CreativeSeed::default());
        assert!(!map.continents.is_empty(), "default map must have land");
        let img = region_image(&map, 160, 160, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!((img.width(), img.height()), (160, 160));
        let first = *img.get_pixel(0, 0);
        assert!(
            img.pixels().any(|p| *p != first),
            "region image rendered a single flat colour"
        );
    }

    #[test]
    fn region_image_falls_back_to_biome_when_landless() {
        // No land ⇒ no hierarchy ⇒ region_image == biome_image. Forcing a
        // land-less map deterministically is awkward, so assert the documented
        // fallback contract directly on an emptied-hierarchy clone.
        let mut map = generate(7, &CreativeSeed::default());
        map.continents.clear();
        let region = region_image(&map, 96, 96, RenderStyle::Realistic, Projection::Equirectangular);
        let biome = biome_image(&map, 96, 96, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!(region.as_raw(), biome.as_raw(), "land-less region_image must equal biome_image");
    }

    #[test]
    fn hsv_to_rgb_covers_all_sextants_without_panic() {
        for i in 0..=600 {
            let _ = hsv_to_rgb(i as f32 / 600.0, 0.55, 0.85);
        }
        // saturation / value extremes must clamp, not panic.
        let _ = hsv_to_rgb(0.0, 0.0, 0.0);
        let _ = hsv_to_rgb(1.0, 1.0, 1.0);
    }

    #[test]
    fn realm_image_renders_and_is_not_uniform() {
        // Default map has political tiers ⇒ a multi-province choropleth.
        let map = generate(7, &CreativeSeed::default());
        assert!(!map.realms.is_empty(), "default map must have realms");
        let img = realm_image(&map, 160, 160, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!((img.width(), img.height()), (160, 160));
        let first = *img.get_pixel(0, 0);
        assert!(
            img.pixels().any(|p| *p != first),
            "realm image rendered a single flat colour"
        );
    }

    #[test]
    fn realm_image_falls_back_to_biome_when_landless() {
        // No political tiers ⇒ realm_image == biome_image.
        let mut map = generate(7, &CreativeSeed::default());
        map.realms.clear();
        let realm = realm_image(&map, 96, 96, RenderStyle::Realistic, Projection::Equirectangular);
        let biome = biome_image(&map, 96, 96, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!(realm.as_raw(), biome.as_raw(), "land-less realm_image must equal biome_image");
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
        let img = biome_image(&island_map(), 100, 80, RenderStyle::Realistic, Projection::Equirectangular);
        assert_eq!(img.width(), 100);
        assert_eq!(img.height(), 80);
    }

    #[test]
    fn biome_image_is_not_uniform() {
        // A real island map has ocean + several land biomes ⇒ >1 colour.
        let img = biome_image(&island_map(), 128, 128, RenderStyle::Realistic, Projection::Equirectangular);
        let first = *img.get_pixel(0, 0);
        assert!(
            img.pixels().any(|p| *p != first),
            "biome image rendered a single flat colour"
        );
    }

    #[test]
    fn political_image_dimensions_and_not_uniform() {
        let map = generate(3, &CreativeSeed::default());
        let img = political_image(&map, 200, 150, RenderStyle::Realistic, Projection::Equirectangular);
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
