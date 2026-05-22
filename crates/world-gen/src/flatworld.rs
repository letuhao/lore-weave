//! Flat-world generator — a NEW, top-down hierarchical sketch, kept fully
//! separate from the sphere/`terrain.rs` pipeline.
//!
//! **Level 0 (this file): tectonic plates as polygons on a flat rectangle.**
//! A `width × height` rectangle holds `n` randomly-generated polygons (the
//! tectonic plates). They may overlap or sit far apart; the uncovered space
//! between them is the **void** (`hư vô`). No elevation yet — everything is
//! flat; this is purely the macro plate layout that later levels build on.
//!
//! Everything is deterministic (seeded [`Rng`]) and parameter-driven, so the
//! layout can be steered or pinned.

use crate::rng::Rng;
use serde::Serialize;
use std::f32::consts::TAU;

/// Inputs for [`generate`]. All fields are intervenable; [`Default`] gives the
/// reference layout (7 plates).
#[derive(Debug, Clone)]
pub struct FlatParams {
    /// Rectangle size in pixels.
    pub width: u32,
    pub height: u32,
    /// Number of plates (tectonic blocks). Reference value: 7.
    pub plate_count: usize,
    /// Master seed — same seed ⇒ same layout.
    pub seed: u64,
    /// Vertices per plate polygon, inclusive range. More verts ⇒ rounder.
    pub min_vertices: usize,
    pub max_vertices: usize,
    /// Plate "radius" as a fraction of the centre **pitch**
    /// (`sqrt(area / plate_count)`), inclusive range. Tying radius to the pitch
    /// (not the frame) keeps overlaps scale-invariant: ~`0.5` ⇒ neighbours just
    /// touch; a little above `0.5` ⇒ thin collision seams; well above ⇒ plates
    /// stack (avoid). Smaller ⇒ more void.
    pub min_radius_frac: f32,
    pub max_radius_frac: f32,
    /// Per-vertex radial jitter `0..1` — 0 = regular polygon, 1 = very ragged.
    pub edge_jitter: f32,
    /// Max plate drift speed (arbitrary units). Each plate gets a random
    /// direction + a speed in `0..max_speed`. Collisions = convergent drift.
    pub max_speed: f32,
    /// How much a unit of convergence raises the overlap elevation. Higher ⇒
    /// taller collision mountains. (`càng va mạnh càng nhô cao`.)
    pub collision_gain: f32,
    /// Minimum centre-to-centre spacing as a fraction of the ideal grid pitch
    /// `sqrt(area / plate_count)`. Higher ⇒ centres spread out ⇒ plates meet
    /// at thin boundary seams instead of stacking on top of each other (real
    /// plates tile the surface; they don't fully overlap). `0` = no constraint.
    pub separation: f32,
    /// Zones per plate, inclusive range — each plate is subdivided into a random
    /// count in `[min_zones, max_zones]` via an interior Voronoi partition.
    pub min_zones: usize,
    pub max_zones: usize,
}

impl Default for FlatParams {
    fn default() -> Self {
        Self {
            width: 1024,
            height: 640,
            plate_count: 7,
            seed: 1,
            min_vertices: 6,
            max_vertices: 11,
            // Radius as a fraction of the centre pitch: just over 0.5 so
            // adjacent plates overlap in a thin seam (the boundary), not a
            // full stack — Earth-like. With `separation` ≈ 0.9 the closest
            // pairs collide thinly; farther pairs leave void.
            min_radius_frac: 0.50,
            max_radius_frac: 0.66,
            edge_jitter: 0.35,
            max_speed: 1.0,
            collision_gain: 0.35,
            separation: 0.90,
            min_zones: 3,
            max_zones: 7,
        }
    }
}

/// Plate base elevation (the "unchanged" height of land that isn't colliding).
/// Collisions add on top; void sits below. Named here as the obvious next
/// intervention point for the elevation pass.
pub const BASE_LEVEL: f32 = 0.35;
/// Elevation of the void (uncovered space between plates).
pub const VOID_LEVEL: f32 = 0.0;

/// One tectonic plate: a simple (non-self-intersecting) polygon in pixel
/// coordinates, ordered counter-clockwise around its centre.
#[derive(Debug, Clone)]
pub struct Plate {
    pub id: usize,
    pub center: (f32, f32),
    pub vertices: Vec<(f32, f32)>,
    /// Drift velocity (pixels-per-tick, arbitrary). Drives collision strength.
    pub velocity: (f32, f32),
    /// Voronoi sites for the plate's interior zones — [`Plate::zone_at`] assigns
    /// each interior point to its nearest site. `zone_sites.len()` = zone count.
    pub zone_sites: Vec<(f32, f32)>,
}

impl Plate {
    /// Point-in-polygon (ray-casting). Coordinates in the same pixel space as
    /// [`Plate::vertices`].
    pub fn contains(&self, x: f32, y: f32) -> bool {
        let v = &self.vertices;
        let mut inside = false;
        let mut j = v.len() - 1;
        for i in 0..v.len() {
            let (xi, yi) = v[i];
            let (xj, yj) = v[j];
            // Does the horizontal ray at `y` cross edge (j → i)?
            if (yi > y) != (yj > y) {
                let t = (y - yi) / (yj - yi);
                if x < xi + t * (xj - xi) {
                    inside = !inside;
                }
            }
            j = i;
        }
        inside
    }

    /// Index of the interior zone containing `(x, y)` — the nearest Voronoi
    /// site. `None` if the plate has no zones. (Does not check `contains`; the
    /// caller passes interior points.)
    pub fn zone_at(&self, x: f32, y: f32) -> Option<usize> {
        let mut best = None;
        let mut best_d = f32::INFINITY;
        for (i, &(sx, sy)) in self.zone_sites.iter().enumerate() {
            let d = (x - sx) * (x - sx) + (y - sy) * (y - sy);
            if d < best_d {
                best_d = d;
                best = Some(i);
            }
        }
        best
    }
}

/// A generated flat world: the rectangle + its plates. The void is implicit
/// (any point covered by zero plates).
#[derive(Debug, Clone)]
pub struct FlatWorld {
    pub width: u32,
    pub height: u32,
    pub plates: Vec<Plate>,
    /// Carried from [`FlatParams`] so [`FlatWorld::elevation_at`] is self-contained.
    pub collision_gain: f32,
}

impl FlatWorld {
    /// All plates covering a point (empty ⇒ void). Overlap ⇒ length ≥ 2.
    pub fn plates_at(&self, x: f32, y: f32) -> Vec<usize> {
        self.plates
            .iter()
            .filter(|p| p.contains(x, y))
            .map(|p| p.id)
            .collect()
    }

    /// Elevation at a point, by the plate-tectonic principle:
    /// - **void** (no plate) → [`VOID_LEVEL`];
    /// - a single plate, or non-converging plates → [`BASE_LEVEL`] (unchanged);
    /// - **overlapping, converging** plates → `BASE_LEVEL` + uplift summed over
    ///   every colliding pair, scaled by `collision_gain` (harder convergence
    ///   ⇒ higher).
    pub fn elevation_at(&self, x: f32, y: f32) -> f32 {
        let hits: Vec<&Plate> = self.plates.iter().filter(|p| p.contains(x, y)).collect();
        if hits.is_empty() {
            return VOID_LEVEL;
        }
        let mut e = BASE_LEVEL;
        for i in 0..hits.len() {
            for j in (i + 1)..hits.len() {
                e += collision_strength(hits[i], hits[j]) * self.collision_gain;
            }
        }
        e
    }
}

/// Convergence between two plates: the rate at which they close along the line
/// joining their centres. Positive ⇒ converging (uplift); ≤ 0 ⇒ diverging or
/// sliding (no uplift here — that's a rift/fault, deferred).
pub fn collision_strength(a: &Plate, b: &Plate) -> f32 {
    let dx = b.center.0 - a.center.0;
    let dy = b.center.1 - a.center.1;
    let len = (dx * dx + dy * dy).sqrt();
    if len < 1e-6 {
        return 0.0;
    }
    let (nx, ny) = (dx / len, dy / len);
    // Relative velocity of A with respect to B, projected onto A→B: if A drives
    // toward B (and/or B toward A), the projection is positive = closing.
    let vrx = a.velocity.0 - b.velocity.0;
    let vry = a.velocity.1 - b.velocity.1;
    (vrx * nx + vry * ny).max(0.0)
}

/// Generate the flat plate layout from `params`. Deterministic in `seed`.
pub fn generate(params: &FlatParams) -> FlatWorld {
    let mut rng = Rng::for_stage(params.seed, b"flatworld-plates");
    // Separate stream for motion, so adding velocities doesn't perturb the
    // polygon layout produced by the plate stream.
    let mut mrng = Rng::for_stage(params.seed, b"flatworld-motion");
    // Separate stream for interior zones — independent of layout + motion.
    let mut zrng = Rng::for_stage(params.seed, b"flatworld-zones");
    let w = params.width as f32;
    let h = params.height as f32;
    let max_v = params.max_vertices.max(params.min_vertices);

    // Spread the centres (min-separation rejection sampling) so plates meet at
    // thin seams instead of stacking. `min_sep` is `separation` × the ideal
    // grid pitch for `plate_count` blobs over the rectangle.
    let pitch = (w * h / params.plate_count.max(1) as f32).sqrt();
    let min_sep = params.separation * pitch;
    let centers = place_centers(&mut rng, w, h, params.plate_count, min_sep);

    let max_zones = params.max_zones.max(params.min_zones).max(1);

    let plates = centers
        .into_iter()
        .enumerate()
        .map(|(id, (cx, cy))| {
            let radius =
                pitch * lerp(params.min_radius_frac, params.max_radius_frac, rng.next_f32());

            let nv = params.min_vertices
                + (rng.next_f32() * (max_v - params.min_vertices + 1) as f32) as usize;
            let nv = nv.clamp(3, max_v.max(3));

            // Even angular spokes + small per-spoke angular wobble keep the
            // ring ordered (simple polygon), while radial jitter makes the
            // outline ragged rather than a clean circle.
            let phase = rng.next_f32() * TAU;
            let vertices = (0..nv)
                .map(|k| {
                    let base = phase + TAU * (k as f32 + 0.0) / nv as f32;
                    let wobble = (rng.next_f32() - 0.5) * (TAU / nv as f32) * 0.6;
                    let ang = base + wobble;
                    let r = radius * (1.0 - params.edge_jitter * rng.next_f32());
                    (cx + r * ang.cos(), cy + r * ang.sin())
                })
                .collect();

            let speed = mrng.next_f32() * params.max_speed;
            let vdir = mrng.next_f32() * TAU;
            let velocity = (speed * vdir.cos(), speed * vdir.sin());

            let mut plate = Plate {
                id,
                center: (cx, cy),
                vertices,
                velocity,
                zone_sites: Vec::new(),
            };
            let zone_count = params.min_zones
                + (zrng.next_f32() * (max_zones - params.min_zones + 1) as f32) as usize;
            plate.zone_sites = sample_zone_sites(&plate, zone_count.max(1), &mut zrng);
            plate
        })
        .collect();

    FlatWorld {
        width: params.width,
        height: params.height,
        plates,
        collision_gain: params.collision_gain,
    }
}

fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// Place `n` plate centres in the rectangle, rejecting any that fall within
/// `min_sep` of an already-placed centre (so plates spread out). Relaxes the
/// constraint if it can't place all centres (keeps generation total).
fn place_centers(rng: &mut Rng, w: f32, h: f32, n: usize, min_sep: f32) -> Vec<(f32, f32)> {
    let mut pts: Vec<(f32, f32)> = Vec::with_capacity(n);
    let min_sep2 = min_sep * min_sep;
    let cap = n * 40;
    let mut tries = 0;
    while pts.len() < n && tries < cap {
        let c = (rng.next_f32() * w, rng.next_f32() * h);
        if pts
            .iter()
            .all(|&(x, y)| (c.0 - x) * (c.0 - x) + (c.1 - y) * (c.1 - y) >= min_sep2)
        {
            pts.push(c);
        }
        tries += 1;
    }
    // Fill any remainder unconstrained (dense layouts may not fit n spread
    // centres) so the plate count is always honoured.
    while pts.len() < n {
        pts.push((rng.next_f32() * w, rng.next_f32() * h));
    }
    pts
}

/// Rejection-sample `count` Voronoi sites inside a plate polygon (uniform over
/// its bounding box, kept if inside). Falls back to the centre if the polygon
/// is too thin to hit.
fn sample_zone_sites(plate: &Plate, count: usize, rng: &mut Rng) -> Vec<(f32, f32)> {
    let (mut minx, mut miny) = (f32::INFINITY, f32::INFINITY);
    let (mut maxx, mut maxy) = (f32::NEG_INFINITY, f32::NEG_INFINITY);
    for &(x, y) in &plate.vertices {
        minx = minx.min(x);
        miny = miny.min(y);
        maxx = maxx.max(x);
        maxy = maxy.max(y);
    }
    let mut sites = Vec::with_capacity(count);
    let cap = count * 60;
    let mut tries = 0;
    while sites.len() < count && tries < cap {
        let x = lerp(minx, maxx, rng.next_f32());
        let y = lerp(miny, maxy, rng.next_f32());
        if plate.contains(x, y) {
            sites.push((x, y));
        }
        tries += 1;
    }
    if sites.is_empty() {
        sites.push(plate.center);
    }
    sites
}

/// Render the flat world to an RGB byte buffer (`width * height * 3`, row-major
/// from the top-left). Void = near-black; each plate gets a distinct hue;
/// overlaps blend (averaged) so intersecting plates read as a seam.
pub fn render_rgb(world: &FlatWorld) -> Vec<u8> {
    const VOID: [u8; 3] = [10, 10, 14];
    let palette: Vec<[u8; 3]> = (0..world.plates.len())
        .map(|i| plate_color(i, world.plates.len()))
        .collect();

    let w = world.width as usize;
    let h = world.height as usize;
    let mut buf = vec![0u8; w * h * 3];
    for py in 0..h {
        for px in 0..w {
            // Sample at the pixel centre.
            let x = px as f32 + 0.5;
            let y = py as f32 + 0.5;
            let hits = world.plates_at(x, y);
            let color = if hits.is_empty() {
                VOID
            } else {
                let mut acc = [0u32; 3];
                for &id in &hits {
                    let c = palette[id];
                    acc[0] += c[0] as u32;
                    acc[1] += c[1] as u32;
                    acc[2] += c[2] as u32;
                }
                let n = hits.len() as u32;
                [
                    (acc[0] / n) as u8,
                    (acc[1] / n) as u8,
                    (acc[2] / n) as u8,
                ]
            };
            let o = (py * w + px) * 3;
            buf[o] = color[0];
            buf[o + 1] = color[1];
            buf[o + 2] = color[2];
        }
    }
    buf
}

/// Render the elevation field to a grayscale RGB buffer on a **fixed** scale
/// (`[0,1]` → `[0,255]`, clamped): void = black, plate base = a constant grey
/// (`BASE_LEVEL`), collision belts brighter the harder the convergence — and
/// **comparable across seeds** (the same grey always means the same height).
/// Returns `(buffer, max_elevation)`; `max_elevation > 1.0` means the tallest
/// collision is clipping to white (lower `collision_gain` to bring it on-scale).
pub fn render_height_rgb(world: &FlatWorld) -> (Vec<u8>, f32) {
    let w = world.width as usize;
    let h = world.height as usize;

    let mut buf = vec![0u8; w * h * 3];
    let mut max_e = VOID_LEVEL;
    for py in 0..h {
        for px in 0..w {
            let e = world.elevation_at(px as f32 + 0.5, py as f32 + 0.5);
            if e > max_e {
                max_e = e;
            }
            let g = (e.clamp(0.0, 1.0) * 255.0).round() as u8;
            let o = (py * w + px) * 3;
            buf[o] = g;
            buf[o + 1] = g;
            buf[o + 2] = g;
        }
    }
    (buf, max_e)
}

/// Render the interior-zone subdivision: void = near-black; each plate keeps
/// its hue, and its zones are distinguished by stepped brightness/saturation
/// so the partition inside every plate is legible. In an overlap, the
/// lowest-id plate's zones are shown (stable choice — overlaps are thin now).
pub fn render_zones_rgb(world: &FlatWorld) -> Vec<u8> {
    const VOID: [u8; 3] = [10, 10, 14];
    let n = world.plates.len();
    let w = world.width as usize;
    let h = world.height as usize;
    let mut buf = vec![0u8; w * h * 3];
    for py in 0..h {
        for px in 0..w {
            let x = px as f32 + 0.5;
            let y = py as f32 + 0.5;
            // First (lowest-id) plate covering the point owns the pixel.
            let color = match world.plates.iter().find(|p| p.contains(x, y)) {
                None => VOID,
                Some(p) => {
                    let z = p.zone_at(x, y).unwrap_or(0);
                    zone_color(p.id, n, z, p.zone_sites.len().max(1))
                }
            };
            let o = (py * w + px) * 3;
            buf[o] = color[0];
            buf[o + 1] = color[1];
            buf[o + 2] = color[2];
        }
    }
    buf
}

/// Colour for zone `z` of `n_zones` inside plate `plate_id` (of `n_plates`):
/// the plate's base hue, stepped in brightness + alternating saturation so
/// adjacent zones read as distinct patches.
fn zone_color(plate_id: usize, n_plates: usize, z: usize, n_zones: usize) -> [u8; 3] {
    let hue = (plate_id as f32 / n_plates.max(1) as f32) * 360.0;
    let t = if n_zones > 1 {
        z as f32 / (n_zones - 1) as f32
    } else {
        0.5
    };
    let val = 0.5 + 0.45 * t;
    let sat = if z % 2 == 0 { 0.7 } else { 0.45 };
    hsv_to_rgb(hue, sat, val)
}

/// Distinct, evenly-spread hue per plate (simple HSV→RGB at full S/V).
fn plate_color(i: usize, n: usize) -> [u8; 3] {
    let hue = (i as f32 / n.max(1) as f32) * 360.0;
    hsv_to_rgb(hue, 0.62, 0.92)
}

fn hsv_to_rgb(h: f32, s: f32, v: f32) -> [u8; 3] {
    let c = v * s;
    let hp = h / 60.0;
    let x = c * (1.0 - (hp % 2.0 - 1.0).abs());
    let (r, g, b) = match hp as u32 {
        0 => (c, x, 0.0),
        1 => (x, c, 0.0),
        2 => (0.0, c, x),
        3 => (0.0, x, c),
        4 => (x, 0.0, c),
        _ => (c, 0.0, x),
    };
    let m = v - c;
    [
        ((r + m) * 255.0).round() as u8,
        ((g + m) * 255.0).round() as u8,
        ((b + m) * 255.0).round() as u8,
    ]
}

// ── Data export — the "anchor" for per-zone terrain generation ─────────────
//
// Mirrors the LOCKED region-tree schema at the levels built so far (plate =
// depth 0, zone = depth 1), with file/folder `path` ids. This is the data a
// future per-zone geo generator reads: each zone carries its anchor floor
// (`base_elevation`), and the partition is reproducible from the plate
// boundary + zone `site`s (Voronoi by nearest site).

/// Top-level export document.
#[derive(Debug, Clone, Serialize)]
pub struct WorldData {
    pub width: u32,
    pub height: u32,
    pub seed: u64,
    pub plate_count: usize,
    pub base_level: f32,
    pub void_level: f32,
    pub collision_gain: f32,
    pub plates: Vec<PlateData>,
}

/// A plate (region depth 0).
#[derive(Debug, Clone, Serialize)]
pub struct PlateData {
    /// File/folder path: `[plate_id]`.
    pub path: Vec<u32>,
    pub center: [f32; 2],
    /// Drift velocity — drives collision strength at boundaries.
    pub velocity: [f32; 2],
    /// Polygon outline (world pixels).
    pub boundary: Vec<[f32; 2]>,
    pub zones: Vec<ZoneData>,
}

/// A zone (region depth 1) — a Voronoi cell inside its plate.
#[derive(Debug, Clone, Serialize)]
pub struct ZoneData {
    /// File/folder path: `[plate_id, zone_id]`.
    pub path: Vec<u32>,
    /// Voronoi site (also the partition key — the cell is the points nearest it).
    pub site: [f32; 2],
    /// Anchor floor sampled at the site: `BASE_LEVEL` + any collision uplift.
    /// This is the elevation a per-zone generator builds its relief on top of.
    pub base_elevation: f32,
}

/// Build the export document from a generated world. `seed` is recorded for
/// reproducibility (the world doesn't carry it).
pub fn export(world: &FlatWorld, seed: u64) -> WorldData {
    let plates = world
        .plates
        .iter()
        .map(|p| PlateData {
            path: vec![p.id as u32],
            center: [p.center.0, p.center.1],
            velocity: [p.velocity.0, p.velocity.1],
            boundary: p.vertices.iter().map(|&(x, y)| [x, y]).collect(),
            zones: p
                .zone_sites
                .iter()
                .enumerate()
                .map(|(z, &(sx, sy))| ZoneData {
                    path: vec![p.id as u32, z as u32],
                    site: [sx, sy],
                    base_elevation: world.elevation_at(sx, sy),
                })
                .collect(),
        })
        .collect();

    WorldData {
        width: world.width,
        height: world.height,
        seed,
        plate_count: world.plates.len(),
        base_level: BASE_LEVEL,
        void_level: VOID_LEVEL,
        collision_gain: world.collision_gain,
        plates,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_the_requested_plate_count() {
        let p = FlatParams {
            plate_count: 7,
            ..Default::default()
        };
        let world = generate(&p);
        assert_eq!(world.plates.len(), 7);
        for plate in &world.plates {
            assert!(plate.vertices.len() >= 3, "polygon needs ≥3 vertices");
        }
    }

    #[test]
    fn is_deterministic_in_seed() {
        let p = FlatParams::default();
        let a = generate(&p);
        let b = generate(&p);
        for (pa, pb) in a.plates.iter().zip(&b.plates) {
            assert_eq!(pa.vertices.len(), pb.vertices.len());
            for (va, vb) in pa.vertices.iter().zip(&pb.vertices) {
                assert_eq!(va.0.to_bits(), vb.0.to_bits());
                assert_eq!(va.1.to_bits(), vb.1.to_bits());
            }
        }
    }

    #[test]
    fn distinct_seeds_differ() {
        let a = generate(&FlatParams { seed: 1, ..Default::default() });
        let b = generate(&FlatParams { seed: 2, ..Default::default() });
        let same = a
            .plates
            .iter()
            .zip(&b.plates)
            .all(|(pa, pb)| pa.center == pb.center);
        assert!(!same, "different seeds should give a different layout");
    }

    #[test]
    fn center_of_a_plate_is_inside_it() {
        let world = generate(&FlatParams::default());
        for plate in &world.plates {
            assert!(
                plate.contains(plate.center.0, plate.center.1),
                "plate {} should contain its own centre",
                plate.id
            );
        }
    }

    #[test]
    fn render_buffer_has_the_right_size() {
        let p = FlatParams {
            width: 64,
            height: 48,
            ..Default::default()
        };
        let world = generate(&p);
        assert_eq!(render_rgb(&world).len(), 64 * 48 * 3);
    }

    /// Axis-aligned square plate centred at `c` with half-size `r` and a given
    /// velocity — handy for constructing exact collision geometry.
    fn square(id: usize, c: (f32, f32), r: f32, velocity: (f32, f32)) -> Plate {
        Plate {
            id,
            center: c,
            vertices: vec![
                (c.0 - r, c.1 - r),
                (c.0 + r, c.1 - r),
                (c.0 + r, c.1 + r),
                (c.0 - r, c.1 + r),
            ],
            velocity,
            zone_sites: vec![c],
        }
    }

    #[test]
    fn void_is_lowest_single_plate_is_base() {
        let world = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![square(0, (50.0, 50.0), 20.0, (1.0, 0.0))],
            collision_gain: 1.0,
        };
        // Inside the lone plate → unchanged base (no collision).
        assert_eq!(world.elevation_at(50.0, 50.0), BASE_LEVEL);
        // Outside → void.
        assert_eq!(world.elevation_at(5.0, 5.0), VOID_LEVEL);
    }

    #[test]
    fn converging_overlap_rises_above_base() {
        // Two plates side by side, overlapping in the middle, driving together.
        let a = square(0, (40.0, 50.0), 25.0, (2.0, 0.0)); // moves +x (toward b)
        let b = square(1, (60.0, 50.0), 25.0, (-2.0, 0.0)); // moves -x (toward a)
        let world = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![a, b],
            collision_gain: 0.1,
        };
        // Overlap band around x=50 is covered by both → uplift.
        assert!(world.elevation_at(50.0, 50.0) > BASE_LEVEL);
        // A's exclusive interior (x≈20) is single-plate → base.
        assert_eq!(world.elevation_at(20.0, 50.0), BASE_LEVEL);
    }

    #[test]
    fn harder_convergence_is_higher() {
        let gentle = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![
                square(0, (40.0, 50.0), 25.0, (0.5, 0.0)),
                square(1, (60.0, 50.0), 25.0, (-0.5, 0.0)),
            ],
            collision_gain: 0.1,
        };
        let violent = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![
                square(0, (40.0, 50.0), 25.0, (3.0, 0.0)),
                square(1, (60.0, 50.0), 25.0, (-3.0, 0.0)),
            ],
            collision_gain: 0.1,
        };
        assert!(violent.elevation_at(50.0, 50.0) > gentle.elevation_at(50.0, 50.0));
    }

    #[test]
    fn diverging_overlap_stays_at_base() {
        // Overlapping but moving apart → no uplift (collision_strength = 0).
        let a = square(0, (40.0, 50.0), 25.0, (-2.0, 0.0)); // moves away from b
        let b = square(1, (60.0, 50.0), 25.0, (2.0, 0.0)); // moves away from a
        let world = FlatWorld {
            width: 100,
            height: 100,
            plates: vec![a, b],
            collision_gain: 1.0,
        };
        assert_eq!(world.elevation_at(50.0, 50.0), BASE_LEVEL);
    }

    #[test]
    fn each_plate_is_subdivided_into_zones() {
        let p = FlatParams {
            min_zones: 4,
            max_zones: 4,
            ..Default::default()
        };
        let world = generate(&p);
        for plate in &world.plates {
            assert_eq!(plate.zone_sites.len(), 4, "plate {} zone count", plate.id);
            // Every interior site resolves to a valid zone index.
            for &(sx, sy) in &plate.zone_sites {
                let z = plate.zone_at(sx, sy).expect("site has a zone");
                assert!(z < plate.zone_sites.len());
            }
        }
    }

    #[test]
    fn separation_reduces_overlap() {
        // With strong separation, fewer pixels are covered by 2+ plates than
        // with none — plates meet at seams rather than stacking.
        let spread = generate(&FlatParams { separation: 1.1, seed: 9, ..Default::default() });
        let stacked = generate(&FlatParams { separation: 0.0, seed: 9, ..Default::default() });
        let overlap = |wld: &FlatWorld| {
            let mut n = 0u32;
            for py in (0..wld.height).step_by(4) {
                for px in (0..wld.width).step_by(4) {
                    if wld.plates_at(px as f32 + 0.5, py as f32 + 0.5).len() >= 2 {
                        n += 1;
                    }
                }
            }
            n
        };
        assert!(
            overlap(&spread) < overlap(&stacked),
            "separation should reduce overlap: spread={} stacked={}",
            overlap(&spread),
            overlap(&stacked)
        );
    }

    #[test]
    fn export_mirrors_the_tree_with_paths_and_anchors() {
        let p = FlatParams {
            plate_count: 5,
            min_zones: 3,
            max_zones: 3,
            seed: 42,
            ..Default::default()
        };
        let world = generate(&p);
        let data = export(&world, p.seed);
        assert_eq!(data.seed, 42);
        assert_eq!(data.plates.len(), 5);
        for (pi, plate) in data.plates.iter().enumerate() {
            assert_eq!(plate.path, vec![pi as u32]);
            assert_eq!(plate.zones.len(), 3);
            for (zi, zone) in plate.zones.iter().enumerate() {
                assert_eq!(zone.path, vec![pi as u32, zi as u32]);
                // Anchor floor is at least the plate base (collisions only add).
                assert!(zone.base_elevation >= BASE_LEVEL - 1e-6);
            }
        }
        // Serializes cleanly.
        let json = serde_json::to_string(&data).expect("serialize");
        assert!(json.contains("\"base_elevation\""));
    }

    #[test]
    fn void_exists_with_tiny_plates() {
        // Tiny plates ⇒ lots of uncovered void.
        let p = FlatParams {
            width: 200,
            height: 200,
            plate_count: 3,
            min_radius_frac: 0.04,
            max_radius_frac: 0.06,
            ..Default::default()
        };
        let world = generate(&p);
        let mut void = 0;
        for py in 0..200 {
            for px in 0..200 {
                if world.plates_at(px as f32 + 0.5, py as f32 + 0.5).is_empty() {
                    void += 1;
                }
            }
        }
        assert!(void > 0, "small plates should leave void between them");
    }
}
