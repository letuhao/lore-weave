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
    blended_height_with_seam(subs, x, y).0
}

#[allow(dead_code)]
fn blended_height_with_owner(subs: &[SubAttr], x: f32, y: f32) -> (f32, usize) {
    let (h, i1, _, _) = blended_height_with_seam(subs, x, y);
    (h, i1)
}

/// Same as [`blended_height`] but also returns the **2-nearest sub-attr
/// indices** AND the **blend weight** for the nearest. W6 v2.1b biome render
/// uses this to blend biome COLORS at zone seams (not just heights), which
/// eliminates the previous 1-pixel sharp biome flip at every zone boundary.
///
/// Returns `(blended_height, i1, i2, w1)`:
///   - `i1`: index of the nearest sub-attr
///   - `i2`: index of the 2nd-nearest (== i1 if only 1 sub-attr exists)
///   - `w1`: weight for i1 in `[0.5, 1.0]` — 0.5 at the exact seam, 1.0
///     deep inside i1's cell
fn blended_height_with_seam(subs: &[SubAttr], x: f32, y: f32) -> (f32, usize, usize, f32) {
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
        return (h1, i1, i1, 1.0);
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
    (w1 * h1 + (1.0 - w1) * h2, i1, i2, w1)
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

/// Drainage thresholds **as fractions of the land cell count** — adaptive so
/// the river-network density is consistent across map resolutions (a 10× area
/// map yields ~10× drainage values; fixed absolute thresholds would saturate).
/// `OUTLET_FRAC` = fraction of total land cells an outlet's catchment must
/// reach to start a river network; `TRIB_FRAC` = same for an admitted
/// tributary. Tuned at the reference 1024×640 resolution where they were
/// ≈ 400 / 120 absolute (matching `land_count ≈ 327k`).
const OUTLET_FRAC: f32 = 0.0012;
const TRIB_FRAC: f32 = 0.00037;
/// Upper drainage value (as a fraction of land cells) for the river brush's
/// log-scale ramp — drainage at or above this maps to the widest, darkest
/// brush. Below `OUTLET_FRAC` maps to the thinnest/lightest.
const BRUSH_HI_FRAC: f32 = 0.024;
/// River / stream colours.
const STREAM_COLOR: [u8; 3] = [90, 140, 195];
const RIVER_COLOR: [u8; 3] = [42, 90, 165];

/// Drainage accumulation per land cell on a (depression-filled) eroded grid.
/// Each land cell has a D8 **receiver** = its strictly-lowest neighbour; if no
/// neighbour is lower, the receiver is any adjacent void cell (the sea). We
/// then walk land cells in **descending elevation** and propagate
/// `drainage[receiver] += drainage[self] + 1`, so a downstream cell carries
/// the count of every upstream contributor. Void cells stay 0. Returns
/// `(drainage, receiver)` so the river-network walker can re-use the topology.
fn compute_drainage(
    elev: &[f32],
    is_land: &[bool],
    w: usize,
    h: usize,
) -> (Vec<u32>, Vec<usize>) {
    let n = w * h;
    const OFF: [(isize, isize); 8] = [
        (-1, -1), (0, -1), (1, -1),
        (-1, 0),           (1, 0),
        (-1, 1),  (0, 1),  (1, 1),
    ];
    let nb_idx = |x: isize, y: isize| -> Option<usize> {
        if x < 0 || y < 0 || x >= w as isize || y >= h as isize {
            None
        } else {
            Some(y as usize * w + x as usize)
        }
    };
    let mut receiver = vec![usize::MAX; n];
    for y in 0..h {
        for x in 0..w {
            let i = y * w + x;
            if !is_land[i] {
                continue;
            }
            let mut best_neigh = usize::MAX;
            let mut best_e = elev[i];
            for &(dx, dy) in &OFF {
                if let Some(j) = nb_idx(x as isize + dx, y as isize + dy) {
                    if elev[j] < best_e {
                        best_e = elev[j];
                        best_neigh = j;
                    }
                }
            }
            if best_neigh == usize::MAX {
                // No strictly-lower neighbour — drain to any adjacent void.
                for &(dx, dy) in &OFF {
                    if let Some(j) = nb_idx(x as isize + dx, y as isize + dy) {
                        if !is_land[j] {
                            best_neigh = j;
                            break;
                        }
                    }
                }
            }
            receiver[i] = best_neigh;
        }
    }
    let mut order: Vec<u32> = (0..n as u32).filter(|&i| is_land[i as usize]).collect();
    order.sort_by(|&a, &b| {
        elev[b as usize]
            .partial_cmp(&elev[a as usize])
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let mut drainage = vec![0u32; n];
    for &i in &order {
        let i = i as usize;
        drainage[i] += 1;
        let r = receiver[i];
        if r != usize::MAX && is_land[r] {
            drainage[r] += drainage[i];
        }
    }
    (drainage, receiver)
}

/// Tree-walker that extracts the **river network** from the receiver tree:
/// start at every coastal outlet whose drainage ≥ `outlet_t`, then walk
/// upstream following the highest-drainage child (the mainstream). Other
/// children are admitted as tributaries only if their drainage ≥ `trib_t` —
/// smaller branches are pruned so the network is a clean tree (source →
/// confluence → outlet) instead of scribbles on every slope. Returns a mask
/// of land cells that belong to the network.
fn build_river_network(
    receiver: &[usize],
    drainage: &[u32],
    is_land: &[bool],
    outlet_t: u32,
    trib_t: u32,
) -> Vec<bool> {
    let n = receiver.len();
    // Inverse: for each downstream cell, list its upstream contributors.
    let mut children: Vec<Vec<u32>> = vec![Vec::new(); n];
    for i in 0..n {
        if !is_land[i] {
            continue;
        }
        let r = receiver[i];
        if r != usize::MAX && is_land[r] {
            children[r].push(i as u32);
        }
    }
    // Mainstream first: highest-drainage upstream contributor leads.
    for kids in children.iter_mut() {
        kids.sort_by(|&a, &b| drainage[b as usize].cmp(&drainage[a as usize]));
    }
    // Outlets: land cells whose receiver is sea (void / MAX).
    let outlets = (0..n).filter(|&i| {
        is_land[i] && {
            let r = receiver[i];
            r == usize::MAX || !is_land[r]
        } && drainage[i] >= outlet_t
    });

    let mut is_river = vec![false; n];
    let mut stack: Vec<u32> = Vec::new();
    for o in outlets {
        stack.push(o as u32);
    }
    while let Some(c) = stack.pop() {
        let ci = c as usize;
        is_river[ci] = true;
        let kids = &children[ci];
        if kids.is_empty() {
            continue;
        }
        // Mainstream = first child (highest drainage). Always extend it (it
        // carries this cell's flow upstream); the walk naturally terminates
        // when the mainstream tip has no children.
        stack.push(kids[0]);
        // Tributaries = the remaining children, admitted only if big enough.
        for &k in &kids[1..] {
            if drainage[k as usize] >= trib_t {
                stack.push(k);
            }
        }
    }
    is_river
}

/// Beach band width **as a fraction of the shorter map dimension** — so the
/// shoreline reads at the same relative width across resolutions (at 1024×640
/// this gives ≈ 22 px, matching the previous absolute constant).
const BEACH_FRAC: f32 = 0.034;
/// How far above `min_land` the shore lip sits (the bottom of the beach
/// taper, just above the void outlet). `pub(crate)` so the climate module
/// can derive its default `sea_level` from `flatworld::BASE_LEVEL +
/// SHORE_LEVEL_OFFSET` — keeping climate's threshold in sync with zonegen's
/// shoreline at compile time (MED-3 from /review-impl).
pub(crate) const SHORE_LEVEL_OFFSET: f32 = 0.02;

/// Multi-source BFS over a `w × h` 4-conn grid: starting from every cell with
/// `is_sea[i] == true`, returns the hop distance from each non-sea cell to
/// the nearest sea cell. Sea cells = 0; unreachable land = `u32::MAX`.
///
/// **B5 v2:** `is_sea` is the union of (void) + (any land cell whose post-
/// erosion elevation is below `sea_level`). In v2 the coast taper guarantees
/// land ≥ sea_level so this is identical to "void only"; the API is shaped
/// for v3 inland-lake support.
pub(crate) fn edge_dist_from_sea(is_sea: &[bool], w: usize, h: usize) -> Vec<u32> {
    let n = w * h;
    let mut dist = vec![u32::MAX; n];
    let mut frontier: Vec<u32> = Vec::new();
    for i in 0..n {
        if is_sea[i] {
            dist[i] = 0;
            frontier.push(i as u32);
        }
    }
    let mut d = 0u32;
    while !frontier.is_empty() {
        let mut next = Vec::new();
        for &c in &frontier {
            let i = c as usize;
            let (x, y) = (i % w, i / w);
            let mut try_neighbour = |j: usize| {
                if !is_sea[j] && dist[j] == u32::MAX {
                    dist[j] = d + 1;
                    next.push(j as u32);
                }
            };
            if x > 0 {
                try_neighbour(i - 1);
            }
            if x + 1 < w {
                try_neighbour(i + 1);
            }
            if y > 0 {
                try_neighbour(i - w);
            }
            if y + 1 < h {
                try_neighbour(i + w);
            }
        }
        frontier = next;
        d += 1;
    }
    dist
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
///
/// **Internally:** `compute_render_state` (terrain + erosion + coast +
///   drainage + caches) → `colorize_hypso` (palette pass) →
///   `apply_river_overlay` (river stamps). The B5 v2 biome render
///   ([`render_all_zones_biome`]) shares the same `compute_render_state` and
///   `apply_river_overlay`, only the colour pass differs.
pub fn render_all_zones_eroded(
    world: &FlatWorld,
    master_seed: u64,
    ratios: &ClassRatios,
    strength: ErosionStrength,
) -> Vec<u8> {
    let state = compute_render_state(world, master_seed, ratios, strength);
    let mut rgb = colorize_hypso(&state);
    apply_river_overlay(&mut rgb, &state);
    rgb
}

/// Full-map zone terrain rendered with **B5 v2 biome colours** instead of the
/// raw hypsometric ramp. Climate is the layered pipeline in [`crate::flat_climate`]:
///
/// - **Per zone (precomputed once):** Insolation → Circulation → Continentality
///   → Whittaker classification (8 biomes).
/// - **Per pixel:** the zone's biome is the default; an elevation-lapse override
///   flips tall pixels to Tundra / Ice (snow caps regardless of zone biome).
///
/// Reuses the same terrain + erosion + drainage + coast + river overlay as
/// [`render_all_zones_eroded`]; only the colour pass is different.
pub fn render_all_zones_biome(
    world: &FlatWorld,
    master_seed: u64,
    ratios: &ClassRatios,
    strength: ErosionStrength,
    climate: &crate::flat_climate::WorldClimateParams,
) -> Vec<u8> {
    let state = compute_render_state(world, master_seed, ratios, strength);
    let zone_climates = compute_zone_climates(world, climate, &state);
    let mut rgb = colorize_biome_with(&state, world, climate, &zone_climates);
    // W10 fix: climate-aware river overlay — Tundra / Ice zones get
    // FROZEN_RIVER instead of temperate stream/river blue.
    apply_river_overlay_biome(&mut rgb, &state, &zone_climates);
    rgb
}

/// Compute one [`crate::flat_climate::ZoneClimate`] per L1 zone of every
/// plate. Shared by `colorize_biome` and `apply_river_overlay_biome` so the
/// expensive per-zone climate computation runs exactly once per render.
fn compute_zone_climates(
    world: &FlatWorld,
    climate: &crate::flat_climate::WorldClimateParams,
    state: &RenderState,
) -> Vec<Vec<crate::flat_climate::ZoneClimate>> {
    use crate::flat_climate::compute_zone_climate;
    world
        .plates
        .iter()
        .map(|p| {
            (0..p.zone_sites.len())
                .map(|zi| compute_zone_climate(world, climate, p.id, zi, &state.edge_dist))
                .collect()
        })
        .collect()
}

/// Shared precompute for both render fns. Pure-procedural; no RNG (terrain
/// salts are derived in [`zone_salt`]). The returned [`RenderState`] carries
/// everything the colour passes + river overlay need.
fn compute_render_state(
    world: &FlatWorld,
    master_seed: u64,
    ratios: &ClassRatios,
    strength: ErosionStrength,
) -> RenderState {
    let w = world.width as usize;
    let h = world.height as usize;
    let n = w * h;

    let subattrs: Vec<Vec<SubAttr>> = (0..world.plates.len())
        .map(|pi| plate_subattrs(world, master_seed, ratios, pi))
        .collect();

    // MED-1 fix from /review-impl: the `plate_at: Vec<i16>` and `subattr_idx_at:
    // Vec<u16>` caches were chosen narrow to halve cache memory (2.5 MB vs 5 MB
    // at 1024×640). Guard against silent wrap if a hostile world exceeds the
    // type range. With default `FlatParams` we use 7 plates × ≤42 subzones —
    // multiple orders of magnitude under the limit.
    debug_assert!(
        world.plates.len() <= i16::MAX as usize,
        "plate count {} exceeds i16 cache range; widen plate_at or split rendering",
        world.plates.len()
    );
    debug_assert!(
        subattrs.iter().all(|s| s.len() <= u16::MAX as usize),
        "a plate has > 65535 subzones; widen subattr_idx_at or reduce subdivision"
    );

    // Rasterize blended terrain; track land mask + the lowest land value +
    // per-pixel (plate, 2 nearest subattr indices, seam weight) for beach/
    // biome use. W6 v2.1b cache: `subattr_idx_2_at` + `seam_w1_q` enable
    // smooth biome color blending at zone seams (no more 1-pixel sharp flip).
    let mut elev = vec![0f32; n];
    let mut is_land = vec![false; n];
    let mut plate_at = vec![-1i16; n];
    let mut subattr_idx_at = vec![0u16; n];
    let mut subattr_idx_2_at = vec![0u16; n];
    // Seam weight quantized to u8 (256 levels) to save memory; convert back to
    // f32 at colour-pass time. Range [128, 255] = w1 ∈ [0.5, 1.0].
    let mut seam_w1_q = vec![255u8; n];
    let mut min_land = f32::INFINITY;
    let mut land_count = 0usize;
    for py in 0..h {
        for px in 0..w {
            let x = px as f32 + 0.5;
            let y = py as f32 + 0.5;
            if let Some(p) = world.plates.iter().find(|p| p.contains(x, y)) {
                let (e, i1, i2, w1) = blended_height_with_seam(&subattrs[p.id], x, y);
                let i = py * w + px;
                elev[i] = e;
                is_land[i] = true;
                plate_at[i] = p.id as i16;
                subattr_idx_at[i] = i1 as u16;
                subattr_idx_2_at[i] = i2 as u16;
                // w1 ∈ [0.5, 1.0] → quant to [128, 255]
                seam_w1_q[i] = ((w1 - 0.5) * 2.0 * 254.0 + 128.0).clamp(128.0, 255.0) as u8;
                min_land = min_land.min(e);
                land_count += 1;
            }
        }
    }
    if land_count == 0 {
        return RenderState::empty(w, h, subattrs);
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
    let iter_scale = (land_count as f32 / 327_000.0).max(1.0);
    // Snapshot pre-erosion for drainage (macro gradients intact).
    let pre_erosion = elev.clone();
    erosion::apply_scaled(&mut elev, &neighbors, land_fraction, strength, None, iter_scale);

    let beach_band = (w.min(h) as f32 * BEACH_FRAC).round().max(2.0) as u32;
    let outlet_t = ((land_count as f32) * OUTLET_FRAC).round().max(20.0) as u32;
    let trib_t = ((land_count as f32) * TRIB_FRAC).round().max(8.0) as u32;
    let brush_hi = ((land_count as f32) * BRUSH_HI_FRAC).max((outlet_t * 2) as f32);

    // **v2 sea proxy**: void OR low-eroded land. In v2 the coast taper holds
    // every land pixel ≥ shore_level so this is structurally identical to
    // `!is_land`. The API is v3-lake-ready: when hydrology adds lakes, lake
    // pixels enter `is_sea` and continentality respects them without refactor.
    let shore_level = min_land + SHORE_LEVEL_OFFSET;
    let is_sea: Vec<bool> = (0..n)
        .map(|i| !is_land[i] || elev[i] < shore_level)
        .collect();
    let edge_dist = edge_dist_from_sea(&is_sea, w, h);

    // B3b-2 coast shaping (beach taper for plains/hills); now consumes the
    // cached (plate, subattr) instead of redoing the lookups.
    let mut is_beach = vec![false; n];
    let mut beach_t = vec![0f32; n];
    for py in 0..h {
        for px in 0..w {
            let i = py * w + px;
            if !is_land[i] || edge_dist[i] >= beach_band {
                continue;
            }
            let pid = plate_at[i];
            if pid < 0 {
                continue;
            }
            let subs = &subattrs[pid as usize];
            if subs.is_empty() {
                continue;
            }
            let class = subs[subattr_idx_at[i] as usize].class;
            if matches!(class, TerrainClass::Plains | TerrainClass::Hills) {
                let t = (edge_dist[i] as f32 / beach_band as f32).clamp(0.0, 1.0);
                let s = smoothstep01(t);
                elev[i] = shore_level + (elev[i] - shore_level) * s;
                is_beach[i] = true;
                beach_t[i] = t;
            }
        }
    }

    // Drainage on the pre-erosion macro field (gradients intact).
    let (drainage, receiver) = compute_drainage(&pre_erosion, &is_land, w, h);
    let in_network = build_river_network(&receiver, &drainage, &is_land, outlet_t, trib_t);

    // Land range over the (eroded + coast-tapered) elev.
    let (mut lo, mut hi) = (f32::INFINITY, f32::NEG_INFINITY);
    for i in 0..n {
        if is_land[i] {
            lo = lo.min(elev[i]);
            hi = hi.max(elev[i]);
        }
    }

    RenderState {
        w,
        h,
        elev,
        is_land,
        plate_at,
        subattr_idx_at,
        subattr_idx_2_at,
        seam_w1_q,
        edge_dist,
        drainage,
        in_network,
        is_beach,
        beach_t,
        lo,
        hi,
        outlet_t,
        brush_hi,
        subattrs,
    }
}

/// Shared per-render state. Computed once in [`compute_render_state`];
/// consumed by both colourize passes + the river overlay.
struct RenderState {
    w: usize,
    h: usize,
    elev: Vec<f32>,
    is_land: Vec<bool>,
    /// `-1` = void; else plate id.
    plate_at: Vec<i16>,
    /// Valid when `plate_at[i] >= 0`: index into `subattrs[plate_at[i]]` of the
    /// nearest sub-zone (the `i1` of the 2-nearest blend).
    subattr_idx_at: Vec<u16>,
    /// W6 v2.1b: index of the 2nd-nearest sub-attr (== subattr_idx_at[i] if
    /// only 1 sub-attr exists). Used to blend biome colors at seams.
    subattr_idx_2_at: Vec<u16>,
    /// W6 v2.1b: quantized seam weight for the nearest. 128 = 0.5 (seam mid),
    /// 255 = 1.0 (deep inside cell). Cell colour at pixel i = w × biome(i1) +
    /// (1-w) × biome(i2) where w = (seam_w1_q[i] - 128) / 254 + 0.5.
    seam_w1_q: Vec<u8>,
    /// Hop distance from each pixel to the nearest sea pixel (BFS).
    edge_dist: Vec<u32>,
    drainage: Vec<u32>,
    in_network: Vec<bool>,
    is_beach: Vec<bool>,
    beach_t: Vec<f32>,
    /// Land-only range of `elev` post-erosion + post-coast-taper.
    lo: f32,
    hi: f32,
    outlet_t: u32,
    brush_hi: f32,
    subattrs: Vec<Vec<SubAttr>>,
}

impl RenderState {
    fn empty(w: usize, h: usize, subattrs: Vec<Vec<SubAttr>>) -> Self {
        let n = w * h;
        RenderState {
            w,
            h,
            elev: vec![0.0; n],
            is_land: vec![false; n],
            plate_at: vec![-1; n],
            subattr_idx_at: vec![0; n],
            subattr_idx_2_at: vec![0; n],
            seam_w1_q: vec![255; n],
            edge_dist: vec![0; n],
            drainage: vec![0; n],
            in_network: vec![false; n],
            is_beach: vec![false; n],
            beach_t: vec![0.0; n],
            lo: 0.0,
            hi: 1.0,
            outlet_t: 0,
            brush_hi: 1.0,
            subattrs,
        }
    }
}

const VOID_COLOR: [u8; 3] = [12, 16, 28];
// W7 tuning (B5 v2.1a): wet sand pulled cooler/grayer to distinguish from
// the new reddish HotDesert biome `#D89060`. Old WET_SAND `#C4B284` lived
// in the same hue family as HotDesert — now visually unambiguous.
const WET_SAND: [u8; 3] = [180, 168, 154];
const DRY_SAND: [u8; 3] = [212, 200, 178];
/// W10 fix from B5 v2.1a: rivers in Tundra / Ice zones paint as frozen
/// (light blue-grey) rather than the default stream/river blue. Climate-
/// aware overlay; only applies on the biome render path.
const FROZEN_RIVER: [u8; 3] = [200, 213, 224];

fn beach_color(t: f32) -> [u8; 3] {
    [
        (WET_SAND[0] as f32 + (DRY_SAND[0] as f32 - WET_SAND[0] as f32) * t) as u8,
        (WET_SAND[1] as f32 + (DRY_SAND[1] as f32 - WET_SAND[1] as f32) * t) as u8,
        (WET_SAND[2] as f32 + (DRY_SAND[2] as f32 - WET_SAND[2] as f32) * t) as u8,
    ]
}

/// W4 fix from B5 v2.1a: blend beach sand INTO the biome colour by
/// `smoothstep(beach_t)` instead of replacing the biome colour with sand.
/// At `t = 0` (shore): full sand. At `t = 1` (inland edge): full biome.
/// Preserves the climate signal everywhere — small-plate worlds no longer
/// erase 65 %+ of their biome interior to sand.
///
/// The smoothstep curve eases the transition (sand-dominant near shore,
/// biome-dominant inland) rather than a hard linear lerp.
fn blend_beach_into_biome(biome: [u8; 3], beach_t: f32) -> [u8; 3] {
    let sand = beach_color(beach_t);
    let s = smoothstep01(beach_t.clamp(0.0, 1.0));
    [
        (sand[0] as f32 + (biome[0] as f32 - sand[0] as f32) * s) as u8,
        (sand[1] as f32 + (biome[1] as f32 - sand[1] as f32) * s) as u8,
        (sand[2] as f32 + (biome[2] as f32 - sand[2] as f32) * s) as u8,
    ]
}

/// Paint pixels with the hypsometric ramp (lowland → upland → snow). Void
/// stays slate; beach pixels paint sand by `beach_t`.
fn colorize_hypso(state: &RenderState) -> Vec<u8> {
    let n = state.w * state.h;
    let span = (state.hi - state.lo).max(1e-6);
    let mut rgb = vec![0u8; n * 3];
    for i in 0..n {
        let c = if !state.is_land[i] {
            VOID_COLOR
        } else if state.is_beach[i] {
            beach_color(state.beach_t[i])
        } else {
            let t = ((state.elev[i] - state.lo) / span).clamp(0.0, 1.0).powf(0.55);
            hypso_color(t)
        };
        rgb[i * 3] = c[0];
        rgb[i * 3 + 1] = c[1];
        rgb[i * 3 + 2] = c[2];
    }
    rgb
}

/// Paint pixels with their **biome** colour (B5 v2). Void stays slate; beach
/// pixels paint sand (the coast-band is shared with the hypso pass — beach is
/// purely a terrain feature, not a biome). Land non-beach pixels: look up the
/// zone's pre-computed [`crate::flat_climate::ZoneClimate`] via the
/// `subattr_idx_at` cache, then apply the per-pixel lapse override.
fn colorize_biome_with(
    state: &RenderState,
    world: &FlatWorld,
    climate: &crate::flat_climate::WorldClimateParams,
    zone_climates: &[Vec<crate::flat_climate::ZoneClimate>],
) -> Vec<u8> {
    use crate::flat_climate::pixel_biome;

    let n = state.w * state.h;

    // Cache each L1 zone's base_elevation (the lapse anchor).
    let zone_base: Vec<Vec<f32>> = world
        .plates
        .iter()
        .map(|p| {
            p.zone_sites
                .iter()
                .map(|&(sx, sy)| world.elevation_at(sx, sy))
                .collect()
        })
        .collect();

    let mut rgb = vec![0u8; n * 3];
    for i in 0..n {
        let c = if !state.is_land[i] {
            VOID_COLOR
        } else {
            // `is_land[i]` is true ⟺ `plate_at[i] >= 0` (both set together at
            // rasterize time). COSMETIC-2 fix: assert the invariant in dev
            // builds instead of silently falling back — a real bug shouldn't
            // hide behind a cosmetic VOID pixel.
            let pid = state.plate_at[i];
            debug_assert!(pid >= 0, "is_land[{i}] without plate_at[{i}] >= 0");
            let plate_id = pid as usize;
            let subs = &state.subattrs[plate_id];
            let sub_idx = state.subattr_idx_at[i] as usize;
            let l1 = subs[sub_idx].zone;
            let zc = &zone_climates[plate_id][l1];
            let base = zone_base[plate_id][l1];
            let biome = pixel_biome(zc, state.elev[i], base, climate);
            let biome_c = biome.color();
            // W6 v2.1b: seam-blend biome colors at zone boundaries (no more
            // 1-pixel sharp biome flip). Uses cached i1, i2, and seam weight.
            let i2 = state.subattr_idx_2_at[i] as usize;
            let blended_biome_c = if i2 != sub_idx && i2 < subs.len() {
                let l1_2 = subs[i2].zone;
                let zc_2 = &zone_climates[plate_id][l1_2];
                let base_2 = zone_base[plate_id][l1_2];
                let biome_2 = pixel_biome(zc_2, state.elev[i], base_2, climate);
                let biome_2_c = biome_2.color();
                let w1 = (state.seam_w1_q[i] as f32 - 128.0) / 254.0 + 0.5; // [0.5, 1.0]
                [
                    (biome_c[0] as f32 * w1 + biome_2_c[0] as f32 * (1.0 - w1)) as u8,
                    (biome_c[1] as f32 * w1 + biome_2_c[1] as f32 * (1.0 - w1)) as u8,
                    (biome_c[2] as f32 * w1 + biome_2_c[2] as f32 * (1.0 - w1)) as u8,
                ]
            } else {
                biome_c
            };
            // W9 deferred (v2.1b): elev modulation incompatible with current
            // eval framework. Future v2.1b-eval-rework would handle blended
            // pixels via fractional-contribution semantics.
            // W4 fix from B5 v2.1a: beach is now a TINT over biome, not a
            // replacement.
            if state.is_beach[i] {
                blend_beach_into_biome(blended_biome_c, state.beach_t[i])
            } else {
                blended_biome_c
            }
        };
        rgb[i * 3] = c[0];
        rgb[i * 3 + 1] = c[1];
        rgb[i * 3 + 2] = c[2];
    }
    rgb
}

/// Variable-width river stamps overlay. Painted in ASCENDING drainage so big
/// rivers dominate at confluences. **Hypso-mode**: stream/river blue colors
/// regardless of climate. For climate-aware coloring (frozen rivers on
/// Tundra/Ice) see [`apply_river_overlay_biome`].
fn apply_river_overlay(rgb: &mut [u8], state: &RenderState) {
    let n = state.w * state.h;
    let mut river_cells: Vec<(u32, u32)> = (0..n as u32)
        .filter(|&i| state.in_network[i as usize])
        .map(|i| (i, state.drainage[i as usize]))
        .collect();
    river_cells.sort_by_key(|&(_, d)| d);
    for (idx, d) in river_cells {
        let i = idx as usize;
        let (px, py) = (i % state.w, i / state.w);
        let (radius, color) = river_brush(d, state.outlet_t, state.brush_hi, state.w.min(state.h));
        stamp_disk(rgb, state.w, state.h, px, py, radius, color);
    }
}

/// Climate-aware river overlay for the biome render path (W10 fix from B5
/// v2.1a). Looks up the biome at each river cell via `subattr_idx_at +
/// zone_climates`; if it's Ice or Tundra → paint `FROZEN_RIVER` (light
/// blue-grey) instead of the stream/river blue. A cold river is now visually
/// distinct from a temperate one.
fn apply_river_overlay_biome(
    rgb: &mut [u8],
    state: &RenderState,
    zone_climates: &[Vec<crate::flat_climate::ZoneClimate>],
) {
    use crate::flat_climate::Biome;
    let n = state.w * state.h;
    let mut river_cells: Vec<(u32, u32)> = (0..n as u32)
        .filter(|&i| state.in_network[i as usize])
        .map(|i| (i, state.drainage[i as usize]))
        .collect();
    river_cells.sort_by_key(|&(_, d)| d);
    for (idx, d) in river_cells {
        let i = idx as usize;
        let (px, py) = (i % state.w, i / state.w);
        let (radius, default_color) =
            river_brush(d, state.outlet_t, state.brush_hi, state.w.min(state.h));
        // Look up zone biome at this river cell (river is always on land →
        // plate_at[i] >= 0 by construction; debug_assert mirrors colorize_biome).
        let pid = state.plate_at[i];
        debug_assert!(pid >= 0, "river on non-land at {i}");
        let plate_id = pid as usize;
        let subs = &state.subattrs[plate_id];
        let l1 = subs[state.subattr_idx_at[i] as usize].zone;
        let zone_biome = zone_climates[plate_id][l1].biome;
        let color = if matches!(zone_biome, Biome::Ice | Biome::Tundra) {
            FROZEN_RIVER
        } else {
            default_color
        };
        stamp_disk(rgb, state.w, state.h, px, py, radius, color);
    }
}

/// Map a cell's drainage to a (radius, colour) for the river brush. Log scale
/// on drainage so width grows from headwater to mainstem; the brush radius
/// also scales with the **map's short side** so rivers stay the same relative
/// thickness at any resolution. Colour lerps stream→river accordingly.
fn river_brush(drainage: u32, outlet_t: u32, brush_hi: f32, short_side: usize) -> (f32, [u8; 3]) {
    let d_lo = (outlet_t as f32).max(1.0);
    let d_hi = brush_hi.max(d_lo * 2.0);
    let t = ((drainage as f32).max(1.0).ln() - d_lo.ln()) / (d_hi.ln() - d_lo.ln());
    let t = t.clamp(0.0, 1.0);
    // Radius proportional to map short side (so a 10× area map gets ~√10× thick
    // rivers — they read at the same relative width).
    let scale = (short_side as f32 / 640.0).max(1.0);
    let radius = (0.7 + 3.0 * t) * scale;
    let color = [
        (STREAM_COLOR[0] as f32 + (RIVER_COLOR[0] as f32 - STREAM_COLOR[0] as f32) * t) as u8,
        (STREAM_COLOR[1] as f32 + (RIVER_COLOR[1] as f32 - STREAM_COLOR[1] as f32) * t) as u8,
        (STREAM_COLOR[2] as f32 + (RIVER_COLOR[2] as f32 - STREAM_COLOR[2] as f32) * t) as u8,
    ];
    (radius, color)
}

/// Paint a filled disc of `radius` at pixel `(px, py)` with `color` into the
/// RGB buffer (clipped to bounds).
fn stamp_disk(rgb: &mut [u8], w: usize, h: usize, px: usize, py: usize, radius: f32, color: [u8; 3]) {
    let r = radius.max(0.5);
    let r2 = r * r;
    let r_int = r.ceil() as isize;
    for dy in -r_int..=r_int {
        for dx in -r_int..=r_int {
            if (dx * dx + dy * dy) as f32 > r2 {
                continue;
            }
            let x = px as isize + dx;
            let y = py as isize + dy;
            if x < 0 || y < 0 || x >= w as isize || y >= h as isize {
                continue;
            }
            let k = (y as usize * w + x as usize) * 3;
            rgb[k] = color[0];
            rgb[k + 1] = color[1];
            rgb[k + 2] = color[2];
        }
    }
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
    fn drainage_accumulates_downstream_on_a_ramp() {
        // 5×1 land strip with a clean left→right downhill ramp; receiver of
        // every cell is its right neighbour. Drainage should grow monotonically
        // left→right: 1, 2, 3, 4, 5.
        let w = 5;
        let h = 1;
        let elev = vec![5.0f32, 4.0, 3.0, 2.0, 1.0];
        let is_land = vec![true; 5];
        let (d, _r) = compute_drainage(&elev, &is_land, w, h);
        assert_eq!(d, vec![1, 2, 3, 4, 5]);
    }

    #[test]
    fn river_network_is_a_tree_from_outlets() {
        // 4×3 grid where the rightmost column is sea (void). Land cells
        // (cols 0-2) slope rightward, so every land cell's receiver is its
        // right neighbour and the outlets are in column 2 (touching sea).
        let w = 4;
        let h = 3;
        let mut elev = vec![0f32; w * h];
        let mut is_land = vec![true; w * h];
        for y in 0..h {
            is_land[y * w + 3] = false;
            elev[y * w + 3] = -1.0;
            for x in 0..3 {
                elev[y * w + x] = 3.0 - x as f32;
            }
        }
        let (drainage, receiver) = compute_drainage(&elev, &is_land, w, h);
        let net = build_river_network(&receiver, &drainage, &is_land, 1, 1);
        // Every land cell should be in the network (small grid, outlet_t=1).
        for i in 0..w * h {
            if is_land[i] {
                assert!(net[i], "land cell {i} should be in network");
            }
        }
        // With outlet_t above the largest drainage, no outlet qualifies → empty.
        let big = drainage.iter().copied().max().unwrap() + 1;
        let empty = build_river_network(&receiver, &drainage, &is_land, big, 1);
        assert!(empty.iter().all(|&b| !b));
    }

    #[test]
    fn edge_distance_from_sea_is_zero_at_sea_and_grows_inward() {
        // 5×5 grid: a 3×3 land block centred, surrounded by sea (= void).
        // Distances: sea=0; 4-conn land sides = 1; centre = 2.
        let w = 5;
        let h = 5;
        let mut is_sea = vec![true; w * h];
        for y in 1..=3 {
            for x in 1..=3 {
                is_sea[y * w + x] = false; // land
            }
        }
        let d = edge_dist_from_sea(&is_sea, w, h);
        assert_eq!(d[0], 0, "corner is sea");
        assert_eq!(d[w + 1], 1, "land cell next to sea → 1");
        assert_eq!(d[2 * w + 2], 2, "interior cell → 2");
    }

    #[test]
    fn edge_dist_from_sea_respects_inland_water_cells() {
        // LOW-2 fix from /review-impl: the v3 "lake support" claim — `is_sea`
        // is shaped as `!is_land || elev < sea_level` so future lake cells
        // enter the BFS start set. This test injects a synthetic inland lake
        // into `is_sea` and confirms the BFS reaches it from surrounding land
        // (the v2 path is identical to void-only, so without this test the
        // generality is unproven).
        //
        // 7×7 all land, with a single lake cell at (3,3). The 4-conn-
        // adjacent land cells should all be distance 1.
        let w = 7;
        let h = 7;
        let mut is_sea = vec![false; w * h]; // all land
        let lake_idx = 3 * w + 3;
        is_sea[lake_idx] = true; // inland lake

        let d = edge_dist_from_sea(&is_sea, w, h);
        assert_eq!(d[lake_idx], 0, "lake cell distance is 0");
        // 4-conn neighbours of the lake → distance 1.
        assert_eq!(d[lake_idx - w], 1, "north of lake → 1");
        assert_eq!(d[lake_idx + w], 1, "south of lake → 1");
        assert_eq!(d[lake_idx - 1], 1, "west of lake → 1");
        assert_eq!(d[lake_idx + 1], 1, "east of lake → 1");
        // Corner (0, 0) — 6 steps away via Manhattan: 3 + 3 = 6.
        assert_eq!(d[0], 6, "corner far from inland lake → Manhattan dist");
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

    #[test]
    fn eroded_hypso_render_pins_a_content_hash() {
        // MED-5 fix from /review-impl: the determinism test only proves the
        // current impl is self-consistent — it does NOT prove the RenderState
        // refactor preserved the pre-refactor pixel output. Going forward,
        // this test pins a content hash of the hypso render so any FUTURE
        // change to the colour pass / pipeline ordering must be a deliberate
        // hash re-baseline rather than a silent drift.
        let p = FlatParams {
            width: 96,
            height: 64,
            seed: 7,
            ..Default::default()
        };
        let world = generate(&p);
        let rgb = render_all_zones_eroded(&world, p.seed, &ClassRatios::default(), ErosionStrength::Moderate);
        let hash = blake3::hash(&rgb);
        let actual = hash.to_hex().to_string();
        // Pinned 2026-05-23 (post-B5v2 RenderState refactor); rebaselined
        // 2026-05-23 (B5 v2.1a W1 stratified y-placement); rebaselined again
        // 2026-05-23 (B5 v2.1a W7 WET_SAND/DRY_SAND hue tuning affects beach
        // pixels in hypso too). Rebaseline only with intentional algorithm/
        // palette changes.
        let pinned = "996d2af581cc04f081db3068b900e896bfe997ebb41d77205c737ce27d286002";
        assert_eq!(
            actual.as_str(),
            pinned,
            "hypso render hash drifted; update pin or revert change. actual={actual}"
        );
    }

    #[test]
    fn biome_render_pins_a_content_hash() {
        // MED-1 fix from /review-impl: hypso has a hash pin but biome didn't.
        // Batch v2.1a changed biome semantics (W3 precip-gated Ice, W4 beach
        // tint, W7 hue, W10 frozen river) — without a hash pin a future
        // refactor could silently change biome output and only subjective
        // rating-comparison would catch it.
        use crate::flat_climate::WorldClimateParams;
        let p = FlatParams {
            width: 96,
            height: 64,
            seed: 7,
            ..Default::default()
        };
        let world = generate(&p);
        let climate = WorldClimateParams::default().scaled_for(96, 64, world.plates.len());
        let rgb = render_all_zones_biome(
            &world,
            p.seed,
            &ClassRatios::default(),
            ErosionStrength::Moderate,
            &climate,
        );
        let actual = blake3::hash(&rgb).to_hex().to_string();
        // Pinned 2026-05-23 (B5 v2.1a); rebaselined 2026-05-24 (B5 v2.1f
        // added DeciduousForest + Mediterranean biomes → classifier output
        // shifts on temperate zones); rebaselined 2026-05-24 (B5 v2.1c W6 +
        // v4 eval framework + W6 ship); rebaselined 2026-05-24 (B5 v2.1c
        // W2 noise overlay + W13 N=9 zone-avg coast_d → continentality
        // attenuation perturbed). Rebaseline only with intentional biome
        // algorithm / palette / pipeline changes.
        let pinned = "d0c3e17cd14b8ef83618a6bdffbf81dc8d6bf65616e1f93954e9a8fe517cd0ed";
        assert_eq!(
            actual.as_str(),
            pinned,
            "biome render hash drifted; update pin or revert change. actual={actual}"
        );
    }

    #[test]
    fn biome_render_is_world_sized_and_deterministic() {
        use crate::flat_climate::WorldClimateParams;
        let p = FlatParams {
            width: 96,
            height: 64,
            seed: 7,
            ..Default::default()
        };
        let world = generate(&p);
        let climate = WorldClimateParams::default().scaled_for(96, 64, world.plates.len());
        let a = render_all_zones_biome(
            &world,
            p.seed,
            &ClassRatios::default(),
            ErosionStrength::Moderate,
            &climate,
        );
        let b = render_all_zones_biome(
            &world,
            p.seed,
            &ClassRatios::default(),
            ErosionStrength::Moderate,
            &climate,
        );
        assert_eq!(a.len(), 96 * 64 * 3);
        assert_eq!(a, b, "biome render must be deterministic");
    }

    #[test]
    fn biome_render_paints_frozen_river_on_polar_zones() {
        // LOW-1 fix from /review-impl: `apply_river_overlay_biome` was only
        // visual-smoke-verified. Lock the semantic: among all river pixels of
        // a biome render that contains polar zones, at least SOME must paint
        // the FROZEN_RIVER color (proves the climate-aware branch fires).
        //
        // We use NorthOnly + seed 7 + the new defaults (12 plates) — polar
        // half is guaranteed to contain Tundra/Ice zones, and the river
        // network is dense enough that some rivers cross polar plates.
        use crate::flat_climate::WorldClimateParams;
        let p = FlatParams {
            width: 256,
            height: 192,
            seed: 7,
            ..Default::default()
        };
        let world = generate(&p);
        let climate = WorldClimateParams {
            hemisphere_layout: crate::flat_climate::HemisphereLayout::NorthOnly,
            ..WorldClimateParams::default()
        }
        .scaled_for(256, 192, world.plates.len());
        let rgb = render_all_zones_biome(
            &world,
            p.seed,
            &ClassRatios::default(),
            ErosionStrength::Moderate,
            &climate,
        );
        let mut found_frozen = false;
        for i in 0..rgb.len() / 3 {
            if [rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]] == FROZEN_RIVER {
                found_frozen = true;
                break;
            }
        }
        assert!(
            found_frozen,
            "biome render of a NorthOnly map should contain FROZEN_RIVER pixels"
        );
    }

    #[test]
    fn beach_tint_preserves_biome_signal_at_inland_edge() {
        // W4 fix: at beach_t = 1 (inland edge of beach band), the smoothstep
        // pushes the blend to ≥90% biome. Pure-sand replacement (v2 behavior)
        // would give a pixel indistinguishable from the wet-sand color
        // regardless of biome. This test locks the new tint semantic.
        let biome_dark_green = [15u8, 77, 26]; // TropicalRainforest
        let blended_inland = blend_beach_into_biome(biome_dark_green, 1.0);
        // At t=1, smoothstep(1)=1, so blend = biome × 1.0 + sand × 0 = biome.
        assert_eq!(blended_inland, biome_dark_green, "inland edge must be pure biome");

        // At t=0 (shore), smoothstep(0)=0, so blend = biome × 0 + sand × 1 = sand.
        let blended_shore = blend_beach_into_biome(biome_dark_green, 0.0);
        assert_eq!(blended_shore, WET_SAND, "shore must be pure wet sand");

        // At t=0.5, smoothstep(0.5)=0.5, so blend is halfway — must differ
        // from BOTH pure sand AND pure biome (proves it's actually blending).
        let blended_mid = blend_beach_into_biome(biome_dark_green, 0.5);
        assert_ne!(blended_mid, WET_SAND, "mid must not be pure sand");
        assert_ne!(blended_mid, biome_dark_green, "mid must not be pure biome");
    }

    #[test]
    fn biome_render_paints_recognisable_biome_colours() {
        // LOW-1 fix from /review-impl: the prior threshold (≥2 biomes) was
        // near-tautological. This version asserts ≥4 distinct biomes appear
        // on a lat-spanning world AND that `Biome::Ice` specifically appears
        // (locks the AC-4 lapse-on-peaks behavior — previously only verified
        // by manual visual smoke).
        use crate::flat_climate::{Biome, WorldClimateParams};
        let p = FlatParams {
            width: 256,
            height: 192,
            seed: 7,
            ..Default::default()
        };
        let world = generate(&p);
        let climate = WorldClimateParams::default().scaled_for(256, 192, world.plates.len());
        let rgb = render_all_zones_biome(
            &world,
            p.seed,
            &ClassRatios::default(),
            ErosionStrength::Moderate,
            &climate,
        );
        let biome_colors: std::collections::HashSet<[u8; 3]> = [
            Biome::Ice,
            Biome::Tundra,
            Biome::BorealForest,
            Biome::TemperateForest,
            Biome::TemperateGrassland,
            Biome::HotDesert,
            Biome::Savanna,
            Biome::TropicalRainforest,
        ]
        .iter()
        .map(|b| b.color())
        .collect();
        let found: std::collections::HashSet<[u8; 3]> = (0..rgb.len() / 3)
            .map(|i| [rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2]])
            .filter(|c| biome_colors.contains(c))
            .collect();
        assert!(
            found.len() >= 4,
            "biome render produced fewer than 4 biome colours: {found:?}"
        );
        // AC-4 lock: Ice must appear (snow caps on tectonically-uplifted
        // mountain zones). seed 7 has tectonic collisions producing mountain
        // class zones; some are at high lat → guaranteed Ice on peaks.
        assert!(
            found.contains(&Biome::Ice.color()),
            "biome render missing Ice — peak-lapse override not firing"
        );
    }
}
