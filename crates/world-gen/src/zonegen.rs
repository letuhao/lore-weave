//! Per-zone **local** terrain generator — NEW code that inherits the proven
//! primitive layer ([`crate::noise`]) but drops all world-framing. A zone is a
//! local patch of one plate; it has **no sea level, no ocean, no coastline
//! mask** of its own. Its macro context — is this mountain or plain? — comes
//! from the anchor `base_elevation` (computed at the plate/zone level), not
//! from the generator inventing its own sea.
//!
//! First cut (single zone): classify a zone, then synthesize relief on top of
//! its anchor floor. Erosion + seam-stitching with neighbours come later
//! (deferred, bottom-up — see the region-tree data-architecture doc).

use crate::creative_seed::ErosionStrength;
use crate::erosion;
use crate::flatworld::{FlatWorld, BASE_LEVEL};
use crate::noise::{fbm_3d, ridged_fbm_3d};
use crate::rng::{sub_seed, Rng};

/// Coarse terrain class for a zone. Decided by `classify`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TerrainClass {
    Plains,
    Hills,
    Plateau,
    Mountains,
}

impl TerrainClass {
    pub fn name(self) -> &'static str {
        match self {
            TerrainClass::Plains => "plains",
            TerrainClass::Hills => "hills",
            TerrainClass::Plateau => "plateau",
            TerrainClass::Mountains => "mountains",
        }
    }
}

/// Relative likelihoods of the non-tectonic classes (mountains are forced by
/// the tectonic floor, not rolled). Need not sum to 1.
#[derive(Debug, Clone)]
pub struct ClassRatios {
    pub plains: f32,
    pub hills: f32,
    pub plateau: f32,
}

impl Default for ClassRatios {
    fn default() -> Self {
        Self {
            plains: 0.55,
            hills: 0.30,
            plateau: 0.15,
        }
    }
}

/// `base_elevation` above which a zone is treated as tectonically uplifted →
/// **Mountains** regardless of the random roll (the "combine" rule).
const MOUNTAIN_FLOOR: f32 = BASE_LEVEL + 0.08;

/// Combine rule: a clearly-uplifted zone (collision belt) is Mountains; an
/// un-uplifted zone rolls a flat-ish class by `ratios`.
pub fn classify(base_elev: f32, ratios: &ClassRatios, rng: &mut Rng) -> TerrainClass {
    if base_elev >= MOUNTAIN_FLOOR {
        return TerrainClass::Mountains;
    }
    let total = (ratios.plains + ratios.hills + ratios.plateau).max(1e-6);
    let r = rng.next_f32() * total;
    if r < ratios.plains {
        TerrainClass::Plains
    } else if r < ratios.plains + ratios.hills {
        TerrainClass::Hills
    } else {
        TerrainClass::Plateau
    }
}

/// Frequency of the broad intra-zone "swell" (large-scale tilt). Low so it
/// gives one gentle gradient across a ~150 px zone.
const SWELL_FREQ: f32 = 0.006;
/// Frequency of the domain-warp field.
const WARP_FREQ: f32 = 0.012;

/// Domain warp: offset the sample point by a low-frequency fBm vector, so
/// downstream noise (ridges, hills) bends organically off the lattice. `amp`
/// is the max offset in world pixels (0 ⇒ no warp). Ported from the sphere
/// pipeline's `warp_point`, applied in the local 2D zone frame.
fn warp(x: f32, y: f32, salt: u32, amp: f32) -> (f32, f32) {
    let wx = fbm_3d(x * WARP_FREQ, y * WARP_FREQ, 0.0, salt ^ 0xA1, 3);
    let wy = fbm_3d(x * WARP_FREQ, y * WARP_FREQ, 0.0, salt ^ 0xB2, 3);
    (x + amp * wx, y + amp * wy)
}

/// Local relief at world point `(x, y)` for a zone of `class`, on top of its
/// anchor `base_elev`. Pure noise primitives — no sea, no mask. `salt`
/// decorrelates this zone's field from every other.
///
/// Each class is built from layered octaves on top of a **broad low-frequency
/// swell** (the macro slope within the zone, so it reads directionally rather
/// than as a flat sheet). Hills and mountains are **domain-warped** so ridges
/// and valleys bend organically off the noise lattice (ported from the sphere
/// pipeline's warp, applied locally). Plains stay near-flat; mountains carry
/// warped ridged-multifractal ranges.
pub fn zone_height(x: f32, y: f32, class: TerrainClass, base_elev: f32, salt: u32) -> f32 {
    // fbm sampled at an (optionally warped) point + frequency; signed ≈[-1,1].
    let fbm = |px: f32, py: f32, freq: f32, oct: u32, s: u32| {
        fbm_3d(px * freq, py * freq, 0.0, salt ^ s, oct)
    };
    // Broad swell shared by the flatter classes — a gentle large-scale tilt.
    let swell = |amp: f32, s: u32| amp * fbm(x, y, SWELL_FREQ, 2, s);

    match class {
        // Near-flat lowland: a broad swell + a faint fine texture only.
        TerrainClass::Plains => base_elev + swell(0.018, 0x11) + 0.008 * fbm(x, y, 0.024, 2, 0x12),
        // Rolling hills: warped mid-frequency multi-octave fbm over a swell.
        TerrainClass::Hills => {
            let (wx, wy) = warp(x, y, salt, 14.0);
            base_elev + swell(0.045, 0x21) + 0.13 * (0.5 + 0.5 * fbm(wx, wy, 0.020, 4, 0x22))
        }
        // Tableland: raised, mostly-flat top with a broad uneven dome + light
        // surface texture (steep edges come later via seam handling).
        TerrainClass::Plateau => {
            base_elev + 0.17 + swell(0.05, 0x31) + 0.022 * fbm(x, y, 0.030, 3, 0x32)
        }
        // Mountains: a foothill underlay + warped ridged-multifractal ranges.
        TerrainClass::Mountains => {
            let (wx, wy) = warp(x, y, salt, 20.0);
            let foothills = 0.08 * (0.5 + 0.5 * fbm(x, y, 0.012, 3, 0x41));
            let ranges = ridged_fbm_3d(wx * 0.028, wy * 0.028, 0.0, salt ^ 0x44, 5);
            base_elev + foothills + 0.48 * ranges
        }
    }
}

/// Deterministic per-zone noise salt from the master seed + the zone's
/// file/folder path (`[plate_id, zone_id]`), matching the data architecture.
pub fn zone_salt(master: u64, path: &[u32]) -> u32 {
    let bytes: Vec<u8> = path.iter().flat_map(|p| p.to_le_bytes()).collect();
    sub_seed(master, &bytes) as u32
}

/// Width (px) of the seam-blend band: within this much of equal distance to
/// two sub-zone sites, their height fields crossfade. Wider ⇒ softer seams.
const BLEND_WIDTH: f32 = 22.0;

/// One sub-zone's terrain inputs, flattened for blending.
#[derive(Clone, Copy)]
struct SubAttr {
    site: (f32, f32),
    zone: usize,
    class: TerrainClass,
    base: f32,
    salt: u32,
}

/// Flatten every sub-zone of a plate into a blend-ready attribute list. Class +
/// base are inherited from the L1 zone; each sub-zone gets its own path salt.
fn plate_subattrs(
    world: &FlatWorld,
    master_seed: u64,
    ratios: &ClassRatios,
    plate_id: usize,
) -> Vec<SubAttr> {
    let plate = &world.plates[plate_id];
    let mut out = Vec::new();
    for (zi, subs) in plate.subzone_sites.iter().enumerate() {
        let (class, base) = zone_attrs(world, master_seed, plate_id, zi, ratios);
        for (l2, &site) in subs.iter().enumerate() {
            let salt = zone_salt(master_seed, &[plate_id as u32, zi as u32, l2 as u32]);
            out.push(SubAttr { site, zone: zi, class, base, salt });
        }
    }
    out
}

/// Seam-stitched terrain at `(x, y)` from a list of sub-zone attributes: a
/// **smooth-Voronoi 2-nearest blend**. Deep inside a cell → that cell's field;
/// near the boundary between the two nearest sites → a crossfade, so the height
/// (and the class/base it carries) is continuous across the seam. `subs` should
/// be the candidates to blend among (a whole plate, or one L1 zone).
fn blended_height(subs: &[SubAttr], x: f32, y: f32) -> f32 {
    let mut d1 = f32::INFINITY;
    let mut d2 = f32::INFINITY;
    let mut i1 = 0usize;
    let mut i2 = 0usize;
    for (i, s) in subs.iter().enumerate() {
        let d = (x - s.site.0) * (x - s.site.0) + (y - s.site.1) * (y - s.site.1);
        if d < d1 {
            d2 = d1;
            i2 = i1;
            d1 = d;
            i1 = i;
        } else if d < d2 {
            d2 = d;
            i2 = i;
        }
    }
    let a = subs[i1];
    let h1 = zone_height(x, y, a.class, a.base, a.salt);
    if !d2.is_finite() || subs.len() < 2 {
        return h1;
    }
    let b = subs[i2];
    let h2 = zone_height(x, y, b.class, b.base, b.salt);
    // Typed seam: the blend width depends on the class pair (B3b). A narrow
    // band → a sharp escarpment; a wide band → a graded foothill ramp.
    let width = seam_width(a.class, b.class);
    // Blend by the gap between the two nearest *distances* (not squared), so the
    // band has consistent pixel width regardless of cell size.
    let gap = d2.sqrt() - d1.sqrt();
    let t = (gap / width).clamp(0.0, 1.0);
    let w1 = 0.5 + 0.5 * smoothstep01(t); // 0.5 at the seam → 1.0 deep in cell 1
    w1 * h1 + (1.0 - w1) * h2
}

/// Blend-band width (px) for a seam between two classes — the "type" of the
/// boundary. Symmetric in its arguments.
/// - **Escarpment** (plateau ⨯ lowland) → narrow → a sharp inland cliff/step.
/// - **Foothills / piedmont** (mountains ⨯ lowland) → wide → a graded ramp.
/// - everything else (same class, or already-rugged pairs) → the default
///   smooth width.
fn seam_width(a: TerrainClass, b: TerrainClass) -> f32 {
    use TerrainClass::{Hills, Mountains, Plains, Plateau};
    let lowland = |c| matches!(c, Plains | Hills);
    match (a, b) {
        (Plateau, x) | (x, Plateau) if lowland(x) => 6.0,
        (Mountains, x) | (x, Mountains) if lowland(x) => 46.0,
        _ => BLEND_WIDTH,
    }
}

/// `smoothstep` on a value already in `[0,1]`.
fn smoothstep01(t: f32) -> f32 {
    t * t * (3.0 - 2.0 * t)
}

/// L1-zone attributes (class + anchor floor) — set at the **zone** level and
/// shared by its sub-zones (per the top-down inheritance in the data
/// architecture). The per-sub-zone noise salt is derived separately at the
/// pixel level so sub-zones vary in relief while inheriting class + base.
fn zone_attrs(
    world: &FlatWorld,
    master_seed: u64,
    plate_id: usize,
    zone_id: usize,
    ratios: &ClassRatios,
) -> (TerrainClass, f32) {
    let (sx, sy) = world.plates[plate_id].zone_sites[zone_id];
    let base = world.elevation_at(sx, sy);
    let mut crng = Rng::for_stage(master_seed, b"zone-class");
    for _ in 0..(plate_id * 97 + zone_id * 13) {
        crng.next_u32();
    }
    let class = classify(base, ratios, &mut crng);
    (class, base)
}

/// Render **every** zone of the whole map into one image, on a single global
/// height scale, with a hypsometric ramp (lowland green → upland tan/brown →
/// peaks white; void = deep slate). Overlapping plate footprints are owned by
/// the lowest-id plate (stable; overlaps are thin). This is the review render
/// for the full zone terrain.
pub fn render_all_zones(
    world: &FlatWorld,
    master_seed: u64,
    ratios: &ClassRatios,
    outline: bool,
) -> Vec<u8> {
    const VOID: [u8; 3] = [12, 16, 28];
    let w = world.width as usize;
    let h = world.height as usize;

    // Precompute the blend-ready sub-zone attributes per plate once.
    let subattrs: Vec<Vec<SubAttr>> = (0..world.plates.len())
        .map(|pi| plate_subattrs(world, master_seed, ratios, pi))
        .collect();

    // Pass 1: seam-stitched heights (B3 blend) + per-pixel sub-zone owner id
    // (only needed when drawing outlines) + range.
    let mut heights = vec![f32::NAN; w * h];
    let mut owner = vec![-1i64; w * h]; // pid*1_000_000 + l1*1000 + l2; -1 = void
    let (mut lo, mut hi) = (f32::INFINITY, f32::NEG_INFINITY);
    for py in 0..h {
        for px in 0..w {
            let x = px as f32 + 0.5;
            let y = py as f32 + 0.5;
            if let Some(p) = world.plates.iter().find(|p| p.contains(x, y)) {
                let e = blended_height(&subattrs[p.id], x, y);
                let i = py * w + px;
                heights[i] = e;
                if outline {
                    let (l1, l2) = p.subzone_at(x, y).unwrap_or((0, 0));
                    owner[i] = (p.id as i64) * 1_000_000 + (l1 as i64) * 1000 + l2 as i64;
                }
                lo = lo.min(e);
                hi = hi.max(e);
            }
        }
    }
    let span = (hi - lo).max(1e-6);

    // Pass 2: hypsometric colour by normalized height; optional thin dark
    // outline on sub-zone boundaries (structure view).
    const OUTLINE: [u8; 3] = [22, 28, 38];
    let mut rgb = vec![0u8; w * h * 3];
    for py in 0..h {
        for px in 0..w {
            let i = py * w + px;
            let c = if heights[i].is_nan() {
                VOID
            } else {
                let on_edge = outline && {
                    let right = if px + 1 < w { owner[i + 1] } else { owner[i] };
                    let down = if py + 1 < h { owner[i + w] } else { owner[i] };
                    owner[i] != right || owner[i] != down
                };
                if on_edge {
                    OUTLINE
                } else {
                    // Gamma < 1 spreads the cramped low end (plains/hills/
                    // plateau all sit far below the tall mountains) so the
                    // flatter classes are visually distinguishable.
                    let t = ((heights[i] - lo) / span).clamp(0.0, 1.0).powf(0.55);
                    hypso_color(t)
                }
            };
            rgb[i * 3] = c[0];
            rgb[i * 3 + 1] = c[1];
            rgb[i * 3 + 2] = c[2];
        }
    }
    rgb
}

/// 4-connectivity neighbour lists for a `w × h` grid (the adjacency
/// `erosion::apply` expects). Cell index = `y * w + x`.
fn grid_neighbors_4(w: usize, h: usize) -> Vec<Vec<u32>> {
    let mut nb = vec![Vec::with_capacity(4); w * h];
    for y in 0..h {
        for x in 0..w {
            let i = y * w + x;
            if x > 0 {
                nb[i].push((i - 1) as u32);
            }
            if x + 1 < w {
                nb[i].push((i + 1) as u32);
            }
            if y > 0 {
                nb[i].push((i - w) as u32);
            }
            if y + 1 < h {
                nb[i].push((i + w) as u32);
            }
        }
    }
    nb
}

/// Full-map zone terrain **with local hydraulic erosion** (B2): rasterize the
/// seam-stitched terrain to a grid, treat the void between plates as the
/// drainage outlet (set below all land), and run [`erosion::apply`] so sloped
/// land (mountains, foothills) carves dendritic valleys while flat plains stay
/// flat. Reuses the proven stream-power erosion — no world-framing (the void,
/// not an invented sea level, is the outlet). Hypsometric colour, void slate.
pub fn render_all_zones_eroded(
    world: &FlatWorld,
    master_seed: u64,
    ratios: &ClassRatios,
    strength: ErosionStrength,
) -> Vec<u8> {
    const VOID: [u8; 3] = [12, 16, 28];
    let w = world.width as usize;
    let h = world.height as usize;
    let n = w * h;

    let subattrs: Vec<Vec<SubAttr>> = (0..world.plates.len())
        .map(|pi| plate_subattrs(world, master_seed, ratios, pi))
        .collect();

    // Rasterize blended terrain; track land mask + the lowest land value.
    let mut elev = vec![0f32; n];
    let mut is_land = vec![false; n];
    let mut min_land = f32::INFINITY;
    let mut land_count = 0usize;
    for py in 0..h {
        for px in 0..w {
            let x = px as f32 + 0.5;
            let y = py as f32 + 0.5;
            if let Some(p) = world.plates.iter().find(|p| p.contains(x, y)) {
                let e = blended_height(&subattrs[p.id], x, y);
                let i = py * w + px;
                elev[i] = e;
                is_land[i] = true;
                min_land = min_land.min(e);
                land_count += 1;
            }
        }
    }
    if land_count == 0 {
        return vec![VOID[0]; n * 3]; // degenerate: all void
    }

    // Void = the drainage outlet: set it strictly below all land so the
    // `(1 - land_fraction)` percentile waterline lands exactly on the void.
    let sentinel = min_land - 0.05;
    for i in 0..n {
        if !is_land[i] {
            elev[i] = sentinel;
        }
    }
    let land_fraction = land_count as f32 / n as f32;
    let neighbors = grid_neighbors_4(w, h);
    erosion::apply(&mut elev, &neighbors, land_fraction, strength, None);

    // Re-range over land only (erosion may have lowered peaks/filled pits).
    let (mut lo, mut hi) = (f32::INFINITY, f32::NEG_INFINITY);
    for i in 0..n {
        if is_land[i] {
            lo = lo.min(elev[i]);
            hi = hi.max(elev[i]);
        }
    }
    let span = (hi - lo).max(1e-6);

    let mut rgb = vec![0u8; n * 3];
    for i in 0..n {
        let c = if is_land[i] {
            let t = ((elev[i] - lo) / span).clamp(0.0, 1.0).powf(0.55);
            hypso_color(t)
        } else {
            VOID
        };
        rgb[i * 3] = c[0];
        rgb[i * 3 + 1] = c[1];
        rgb[i * 3 + 2] = c[2];
    }
    rgb
}

/// Hypsometric ramp `t ∈ [0,1]`: lowland green → upland tan → brown → snow.
fn hypso_color(t: f32) -> [u8; 3] {
    const STOPS: [(f32, [f32; 3]); 5] = [
        (0.00, [56.0, 110.0, 60.0]),   // lowland green
        (0.35, [120.0, 150.0, 78.0]),  // dry green/tan
        (0.60, [140.0, 120.0, 82.0]),  // tan
        (0.82, [110.0, 86.0, 66.0]),   // brown
        (1.00, [242.0, 242.0, 245.0]), // snow
    ];
    let t = t.clamp(0.0, 1.0);
    let mut out = STOPS[STOPS.len() - 1].1;
    for win in STOPS.windows(2) {
        let (t0, c0) = win[0];
        let (t1, c1) = win[1];
        if t <= t1 {
            let k = ((t - t0) / (t1 - t0)).clamp(0.0, 1.0);
            out = [
                c0[0] + (c1[0] - c0[0]) * k,
                c0[1] + (c1[1] - c0[1]) * k,
                c0[2] + (c1[2] - c0[2]) * k,
            ];
            break;
        }
    }
    [out[0] as u8, out[1] as u8, out[2] as u8]
}

/// Result of generating one zone: the class chosen and its anchor floor (for
/// reporting), plus the rendered grayscale buffer.
pub struct ZoneRender {
    pub class: TerrainClass,
    pub base_elevation: f32,
    pub min_height: f32,
    pub max_height: f32,
    pub rgb: Vec<u8>,
}

/// Render a **single** zone's local terrain into a world-sized grayscale buffer
/// (the zone painted in place, everything else near-black void). Auto-scales
/// the zone's own height range to the grey ramp so the relief is legible.
pub fn render_zone(
    world: &FlatWorld,
    plate_id: usize,
    zone_id: usize,
    master_seed: u64,
    ratios: &ClassRatios,
) -> ZoneRender {
    const VOID: [u8; 3] = [10, 10, 14];
    let plate = &world.plates[plate_id];
    let (class, base_elev) = zone_attrs(world, master_seed, plate_id, zone_id, ratios);
    // Blend among THIS zone's sub-zones only (single-zone view; the L1 edge is
    // the zone's boundary → void, no neighbour to stitch to here).
    let zone_subs: Vec<SubAttr> = plate_subattrs(world, master_seed, ratios, plate_id)
        .into_iter()
        .filter(|s| s.zone == zone_id)
        .collect();

    let w = world.width as usize;
    let h = world.height as usize;

    // First pass: seam-stitched heights over the zone's pixels + range.
    let mut heights = vec![f32::NAN; w * h];
    let (mut lo, mut hi) = (f32::INFINITY, f32::NEG_INFINITY);
    for py in 0..h {
        for px in 0..w {
            let x = px as f32 + 0.5;
            let y = py as f32 + 0.5;
            if plate.contains(x, y) && plate.zone_at(x, y) == Some(zone_id) {
                let e = blended_height(&zone_subs, x, y);
                heights[py * w + px] = e;
                lo = lo.min(e);
                hi = hi.max(e);
            }
        }
    }
    let span = (hi - lo).max(1e-6);

    // Second pass: grayscale ramp inside the zone, void elsewhere.
    let mut rgb = vec![0u8; w * h * 3];
    for i in 0..w * h {
        let c = if heights[i].is_nan() {
            VOID
        } else {
            let g = (40.0 + 215.0 * ((heights[i] - lo) / span)).round() as u8;
            [g, g, g]
        };
        rgb[i * 3] = c[0];
        rgb[i * 3 + 1] = c[1];
        rgb[i * 3 + 2] = c[2];
    }

    ZoneRender {
        class,
        base_elevation: base_elev,
        min_height: if lo.is_finite() { lo } else { base_elev },
        max_height: if hi.is_finite() { hi } else { base_elev },
        rgb,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::{generate, FlatParams};

    #[test]
    fn uplifted_zone_is_mountains() {
        let mut rng = Rng::for_stage(1, b"t");
        // Well above the mountain floor → forced Mountains regardless of roll.
        assert_eq!(
            classify(BASE_LEVEL + 0.4, &ClassRatios::default(), &mut rng),
            TerrainClass::Mountains
        );
    }

    #[test]
    fn flat_zone_rolls_a_flat_class() {
        let mut rng = Rng::for_stage(2, b"t");
        for _ in 0..50 {
            let c = classify(BASE_LEVEL, &ClassRatios::default(), &mut rng);
            assert!(
                matches!(
                    c,
                    TerrainClass::Plains | TerrainClass::Hills | TerrainClass::Plateau
                ),
                "flat zone must not be Mountains"
            );
        }
    }

    #[test]
    fn mountains_have_more_relief_than_plains() {
        let salt = 0xABCD;
        let sample = |class| {
            let (mut lo, mut hi) = (f32::INFINITY, f32::NEG_INFINITY);
            for k in 0..400 {
                let x = (k % 20) as f32 * 8.0;
                let y = (k / 20) as f32 * 8.0;
                let e = zone_height(x, y, class, 0.35, salt);
                lo = lo.min(e);
                hi = hi.max(e);
            }
            hi - lo
        };
        assert!(sample(TerrainClass::Mountains) > sample(TerrainClass::Plains));
    }

    #[test]
    fn render_is_world_sized_and_deterministic() {
        let p = FlatParams {
            width: 128,
            height: 96,
            seed: 13,
            ..Default::default()
        };
        let world = generate(&p);
        let a = render_zone(&world, 0, 0, p.seed, &ClassRatios::default());
        let b = render_zone(&world, 0, 0, p.seed, &ClassRatios::default());
        assert_eq!(a.rgb.len(), 128 * 96 * 3);
        assert_eq!(a.rgb, b.rgb, "render must be deterministic");
    }

    #[test]
    fn blend_makes_a_seam_continuous() {
        // Two adjacent sub-zones with very different bases (plains so relief ≈
        // base). Without blending, crossing the boundary at x≈50 jumps ~0.55;
        // with the blend the height changes gradually, no single big step.
        let subs = [
            SubAttr { site: (0.0, 0.0), zone: 0, class: TerrainClass::Plains, base: 0.35, salt: 1 },
            SubAttr { site: (100.0, 0.0), zone: 1, class: TerrainClass::Plains, base: 0.90, salt: 2 },
        ];
        let mut prev = blended_height(&subs, 0.0, 0.0);
        let mut max_step = 0.0f32;
        for k in 1..=100 {
            let x = k as f32;
            let cur = blended_height(&subs, x, 0.0);
            max_step = max_step.max((cur - prev).abs());
            prev = cur;
        }
        assert!(
            max_step < 0.05,
            "seam not continuous: max per-pixel step {max_step} (expected < 0.05)"
        );
    }

    #[test]
    fn eroded_render_is_world_sized_and_deterministic() {
        let p = FlatParams {
            width: 96,
            height: 64,
            seed: 50,
            ..Default::default()
        };
        let world = generate(&p);
        let a = render_all_zones_eroded(&world, p.seed, &ClassRatios::default(), ErosionStrength::Moderate);
        let b = render_all_zones_eroded(&world, p.seed, &ClassRatios::default(), ErosionStrength::Moderate);
        assert_eq!(a.len(), 96 * 64 * 3);
        assert_eq!(a, b, "eroded render must be deterministic");
    }

    #[test]
    fn full_map_render_is_world_sized_and_deterministic() {
        let p = FlatParams {
            width: 96,
            height: 64,
            seed: 13,
            ..Default::default()
        };
        let world = generate(&p);
        let a = render_all_zones(&world, p.seed, &ClassRatios::default(), false);
        let b = render_all_zones(&world, p.seed, &ClassRatios::default(), false);
        assert_eq!(a.len(), 96 * 64 * 3);
        assert_eq!(a, b, "full-map render must be deterministic");
    }
}
