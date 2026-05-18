//! Stage 2 — heightmap.
//!
//! A global continuous heightmap *function*, [`height_at`], sampled at each
//! cell centre (Path B — replaced the Azgaar-style radial blob seeds, whose
//! `amp·falloff^r` growth made every mountain a concentric "bullseye"):
//! - a low-frequency fBm **continent base**;
//! - **ridged-multifractal** mountain ranges — sharp linear ridgelines, not
//!   radial cones — gated by a low-frequency **belt mask** (ranges cluster)
//!   and a **landness gate** (ranges rise on continental crust);
//! - mid-frequency fBm **hills**;
//! - **domain warping** so nothing is grid-aligned;
//! - the optional Inland continental **dome**.
//!
//! Then a coastline-profile radial falloff (`apply_falloff` — shapes *where*
//! land is), **hydraulic erosion** ([`crate::erosion`] — carves valleys and
//! drainage networks into the raw heightmap, Path B v2), normalize to `u16`,
//! a connectivity-aware sea level, and structural land-coherence enforcement.
//!
//! Land coherence (acceptance criterion #5) is enforced structurally:
//! - non-Archipelago — `enforce_coherence` submerges every land component
//!   except the largest, so one dominant continent always remains;
//! - Archipelago — the radial mask confines land to 5 fixed, well-separated
//!   island discs (`ARCH_ISLANDS` / `ARCH_RADIUS`); the mask is exactly 0
//!   between discs, so the islands are always separate connected components.

use crate::creative_seed::{CoastlineProfile, ErosionStrength};
use crate::erosion;
use crate::noise::{fbm, ridged_fbm};
use crate::rng::sub_seed;

/// Archipelago island disc centres — pairwise separation ≥ 0.353, so with
/// `ARCH_RADIUS = 0.15` (disc span 0.30) the discs never touch.
const ARCH_ISLANDS: [(f32, f32); 5] = [
    (0.25, 0.25),
    (0.75, 0.25),
    (0.25, 0.75),
    (0.75, 0.75),
    (0.50, 0.50),
];
/// Archipelago island disc radius. `2 * ARCH_RADIUS < min island separation`,
/// so the radial mask is exactly 0 in the sea bands between islands.
const ARCH_RADIUS: f32 = 0.15;

// --- heightmap tuning (Path B) ----------------------------------------------

/// Domain-warp frequency / amplitude / octaves — bends ridges and coastlines
/// off the noise lattice so nothing reads as grid-aligned.
const WARP_FREQ: f32 = 2.2;
const WARP_AMP: f32 = 0.09;
const WARP_OCTAVES: u32 = 3;
/// Continent base — low frequency: the broad landmass.
const CONT_FREQ: f32 = 1.7;
const CONT_OCTAVES: u32 = 4;
/// Mountain ranges — ridged multifractal.
const MTN_FREQ: f32 = 4.5;
const MTN_OCTAVES: u32 = 5;
/// Mountain-belt mask — low frequency: *where* ranges cluster.
const BELT_FREQ: f32 = 1.9;
const BELT_OCTAVES: u32 = 3;
/// Hills — mid frequency: rolling terrain between ranges.
const HILL_FREQ: f32 = 7.5;
const HILL_OCTAVES: u32 = 4;

/// Component weights in the height sum.
const CONT_WEIGHT: f32 = 1.00;
const MTN_WEIGHT: f32 = 1.35;
const HILL_WEIGHT: f32 = 0.15;

/// Distinct noise-field salts so the components are decorrelated.
const SALT_WARP_X: u32 = 0x7A1C_9E11;
const SALT_WARP_Y: u32 = 0x31B5_22F7;
const SALT_CONT: u32 = 0x9D4E_0C53;
const SALT_MTN: u32 = 0xC0FF_EE42;
const SALT_BELT: u32 = 0x1357_9BDF;
const SALT_HILL: u32 = 0x2468_ACE0;

/// Per-cell elevations + the chosen sea level.
pub struct Terrain {
    /// `elevation[i]` for cell `i`, `0..=65535`.
    pub elevation: Vec<u16>,
    /// Elevation threshold; `< sea_level` ⇒ water.
    pub sea_level: u16,
}

/// Build the heightmap for the given mesh.
pub fn build(
    seed: u64,
    profile: CoastlineProfile,
    erosion_strength: ErosionStrength,
    centers: &[(f32, f32)],
    neighbors: &[Vec<u32>],
) -> Terrain {
    let count = centers.len();
    // The heightmap is a pure function of position + a u32 noise seed — Path B
    // dropped the blob RNG stream, so no `Rng` is threaded through this stage.
    let s = sub_seed(seed, b"terrain-height");
    let nseed = (s ^ (s >> 32)) as u32;

    let mut elev: Vec<f32> = centers
        .iter()
        .map(|&(x, y)| height_at(x, y, profile, nseed))
        .collect();

    // Coastline-profile radial falloff — shapes *where* land is.
    apply_falloff(profile, centers, &mut elev);

    // Hydraulic erosion (Path B v2) — carve valleys / drainage networks into
    // the raw heightmap, on the f32 field before it is quantized to u16.
    // Skipped for Archipelago: that profile's defining invariant is 5 fixed
    // island discs (see `apply_falloff` / `enforce_coherence`), and incision
    // carving a strait would dissect one. Erosion shapes coherent landmasses.
    if !profile.is_archipelago() {
        erosion::apply(&mut elev, neighbors, profile.land_fraction(), erosion_strength);
    }

    // Normalize to [0,1], then to u16.
    let mut lo = f32::INFINITY;
    let mut hi = f32::NEG_INFINITY;
    for &e in &elev {
        lo = lo.min(e);
        hi = hi.max(e);
    }
    let span = (hi - lo).max(1e-6);
    let mut elevation = vec![0u16; count];
    for (i, &e) in elev.iter().enumerate() {
        let n = ((e - lo) / span).clamp(0.0, 1.0);
        // n in [0,1] ⇒ n*65535 in [0,65535] ⇒ fits u16 after round.
        elevation[i] = (n * 65535.0).round() as u16;
    }

    let sea_level = choose_sea_level(profile, &elevation, neighbors);
    enforce_coherence(profile, &mut elevation, neighbors, sea_level);

    Terrain {
        elevation,
        sea_level,
    }
}

/// The Path B heightmap — a pure function of position. A low-frequency fBm
/// continent, ridged-multifractal mountain ranges gated by a belt mask and a
/// landness gate, mid-frequency hills, all domain-warped, plus the optional
/// Inland continental dome. Always `≥ 0` (the normalize + `apply_falloff`
/// multiply both assume a non-negative field).
fn height_at(x: f32, y: f32, profile: CoastlineProfile, seed: u32) -> f32 {
    // Domain warp — displace the sample point with low-frequency fBm.
    let wx = x + WARP_AMP * fbm(x * WARP_FREQ, y * WARP_FREQ, seed ^ SALT_WARP_X, WARP_OCTAVES);
    let wy = y + WARP_AMP * fbm(x * WARP_FREQ, y * WARP_FREQ, seed ^ SALT_WARP_Y, WARP_OCTAVES);

    // Continent base — the broad landmass, fBm mapped to ~[0,1].
    let continent =
        0.5 + 0.5 * fbm(wx * CONT_FREQ, wy * CONT_FREQ, seed ^ SALT_CONT, CONT_OCTAVES);

    // Hills — mid-frequency rolling terrain, signed (raises and lowers).
    let hills = fbm(wx * HILL_FREQ, wy * HILL_FREQ, seed ^ SALT_HILL, HILL_OCTAVES);

    // Mountain-belt mask — a soft low-frequency gate so ranges cluster into
    // belts rather than blanketing the whole map.
    let belt_raw = 0.5 + 0.5 * fbm(x * BELT_FREQ, y * BELT_FREQ, seed ^ SALT_BELT, BELT_OCTAVES);
    let belt = smoothstep(0.46, 0.72, belt_raw);

    // Ridged ranges — sharp linear ridgelines (the bullseye-killer).
    let ridges = ridged_fbm(wx * MTN_FREQ, wy * MTN_FREQ, seed ^ SALT_MTN, MTN_OCTAVES);

    // Landness gate — ranges rise on continental crust, fade over deep ocean.
    let landness = smoothstep(0.32, 0.52, continent);

    // Inland continental dome — a broad radial bias so the high-land Inland
    // profile forms one coherent mass (`base_amplitude` is 0 for the rest).
    let dome = profile.base_amplitude() * dome_bias(x, y);

    let height = CONT_WEIGHT * continent
        + HILL_WEIGHT * hills
        + MTN_WEIGHT * belt * ridges * landness
        + dome;
    height.max(0.0)
}

/// Broad radial dome — 1 at the map centre, falling to 0 by the rim — the
/// Inland profile's coherent-landmass bias.
fn dome_bias(x: f32, y: f32) -> f32 {
    let r = dist(x, y, 0.5, 0.5) / 0.92;
    (1.0 - r * r).max(0.0)
}

/// Hermite smoothstep — 0 at/below `e0`, 1 at/above `e1`, smooth between.
fn smoothstep(e0: f32, e1: f32, x: f32) -> f32 {
    let t = ((x - e0) / (e1 - e0)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

/// Multiply each cell's elevation by a coastline-profile radial mask.
fn apply_falloff(profile: CoastlineProfile, centers: &[(f32, f32)], elev: &mut [f32]) {
    for (i, &(x, y)) in centers.iter().enumerate() {
        let mask = match profile {
            CoastlineProfile::Island => {
                let d = dist(x, y, 0.5, 0.5);
                (1.0 - (d / 0.55) * (d / 0.55)).max(0.0)
            }
            CoastlineProfile::Peninsula => {
                // Open on the bottom edge; falloff on the other three.
                let edge = x.min(1.0 - x).min(1.0 - y);
                edge_ramp(edge, 0.30)
            }
            CoastlineProfile::Coastal => {
                // Falloff on the right edge only.
                edge_ramp(1.0 - x, 0.22)
            }
            CoastlineProfile::Inland => {
                // Mild uniform mask — little forced sea.
                let edge = x.min(1.0 - x).min(y).min(1.0 - y);
                0.85 + 0.15 * edge_ramp(edge, 0.12)
            }
            CoastlineProfile::Archipelago => {
                // max over island discs; exactly 0 in the sea bands between.
                let mut best = 0.0f32;
                for &(cx, cy) in &ARCH_ISLANDS {
                    let d = dist(x, y, cx, cy);
                    let m = 1.0 - (d / ARCH_RADIUS) * (d / ARCH_RADIUS);
                    best = best.max(m.max(0.0));
                }
                best
            }
        };
        elev[i] *= mask;
    }
}

/// 0 at the edge, ramping linearly to 1 by `width` inland.
fn edge_ramp(edge_dist: f32, width: f32) -> f32 {
    (edge_dist / width).clamp(0.0, 1.0)
}

/// Euclidean distance between two points.
fn dist(x: f32, y: f32, cx: f32, cy: f32) -> f32 {
    ((x - cx) * (x - cx) + (y - cy) * (y - cy)).sqrt()
}

/// Choose the sea level. Archipelago keeps the percentile pick (its 5-island
/// structure already defines coherence); every other profile uses a
/// connectivity-aware binary search so the largest land component lands near
/// the target fraction.
fn choose_sea_level(profile: CoastlineProfile, elevation: &[u16], neighbors: &[Vec<u32>]) -> u16 {
    if profile.is_archipelago() {
        return pick_sea_level(elevation, profile.land_fraction());
    }
    let target = (profile.land_fraction() * elevation.len() as f32) as usize;
    // `largest_land_component` is monotone non-increasing in sea_level (any
    // component of a smaller land set is connected in the larger set, so its
    // size cannot exceed the larger set's max component). Binary-search the
    // highest sea_level whose largest component still meets `target`.
    let (mut lo, mut hi) = (8192u32, 57344u32);
    while lo < hi {
        let mid = lo + (hi - lo).div_ceil(2);
        if largest_land_component(elevation, neighbors, mid as u16) >= target {
            lo = mid;
        } else {
            hi = mid - 1;
        }
    }
    // If even sea_level 8192 cannot form a component that large, the search
    // floors at 8192 — the largest achievable continent (best-effort).
    lo as u16
}

/// Size of the largest connected component of land cells at `sea_level`.
fn largest_land_component(elevation: &[u16], neighbors: &[Vec<u32>], sea_level: u16) -> usize {
    let n = elevation.len();
    let mut seen = vec![false; n];
    let mut largest = 0usize;
    for start in 0..n {
        if seen[start] || elevation[start] < sea_level {
            continue;
        }
        let mut size = 0usize;
        let mut stack = vec![start];
        seen[start] = true;
        while let Some(c) = stack.pop() {
            size += 1;
            for &nb in &neighbors[c] {
                let nb = nb as usize;
                if !seen[nb] && elevation[nb] >= sea_level {
                    seen[nb] = true;
                    stack.push(nb);
                }
            }
        }
        largest = largest.max(size);
    }
    largest
}

/// Pick the sea level so roughly `land_fraction` of cells are land — the
/// `(1 - land_fraction)` percentile of the sorted elevation list. Clamped
/// to GEO_001's sane `[8192, 57344]` band. (Archipelago path of
/// `choose_sea_level`.)
fn pick_sea_level(elevation: &[u16], land_fraction: f32) -> u16 {
    let mut sorted: Vec<u16> = elevation.to_vec();
    sorted.sort_unstable();
    // Degenerate tiny meshes — guard the indexing below (the Phase 1
    // pipeline never produces these, but `build` is `pub`).
    if sorted.len() < 2 {
        return sorted.first().copied().unwrap_or(0).clamp(8192, 57344);
    }
    // sea cells are the lowest (1 - land_fraction) portion.
    // value is in [0, len], non-negative ⇒ cast to usize is safe.
    let sea_count = ((1.0 - land_fraction) * sorted.len() as f32).round() as usize;
    let idx = sea_count.clamp(1, sorted.len() - 1);
    sorted[idx].clamp(8192, 57344)
}

/// Enforce land coherence (acceptance criterion #5). For non-Archipelago
/// profiles, submerge every land component except the largest so exactly one
/// continent survives. Archipelago is already structurally fragmented (the
/// radial mask separates the island discs) and is left untouched.
fn enforce_coherence(
    profile: CoastlineProfile,
    elevation: &mut [u16],
    neighbors: &[Vec<u32>],
    sea_level: u16,
) {
    if profile.is_archipelago() {
        return;
    }
    let comps = land_components(elevation, neighbors, sea_level);
    if comps.len() <= 1 {
        return;
    }
    // Largest component; ties resolve to the lower index (strict `>`).
    let mut largest = 0usize;
    for ci in 1..comps.len() {
        if comps[ci].len() > comps[largest].len() {
            largest = ci;
        }
    }
    // Submerge non-largest components: compress their elevation into
    // [0, sea_level) so they read as a natural underwater shelf rather than
    // a flat patch. u64 math keeps the product well clear of overflow.
    let ceil = u64::from(sea_level.saturating_sub(1));
    for (ci, comp) in comps.iter().enumerate() {
        if ci == largest {
            continue;
        }
        for &cell in comp {
            elevation[cell] = (u64::from(elevation[cell]) * ceil / 65535) as u16;
        }
    }
}

/// Connected components of land cells (`elevation >= sea_level`) over the
/// `neighbors` graph. Deterministic: ascending start-cell sweep, DFS over
/// the (sorted) neighbour lists.
fn land_components(elevation: &[u16], neighbors: &[Vec<u32>], sea_level: u16) -> Vec<Vec<usize>> {
    let n = elevation.len();
    let mut seen = vec![false; n];
    let mut comps: Vec<Vec<usize>> = Vec::new();
    for start in 0..n {
        if seen[start] || elevation[start] < sea_level {
            continue;
        }
        let mut comp = Vec::new();
        let mut stack = vec![start];
        seen[start] = true;
        while let Some(c) = stack.pop() {
            comp.push(c);
            for &nb in &neighbors[c] {
                let nb = nb as usize;
                if !seen[nb] && elevation[nb] >= sea_level {
                    seen[nb] = true;
                    stack.push(nb);
                }
            }
        }
        comps.push(comp);
    }
    comps
}

#[cfg(test)]
mod tests {
    use super::*;

    const PROFILES: [CoastlineProfile; 5] = [
        CoastlineProfile::Island,
        CoastlineProfile::Peninsula,
        CoastlineProfile::Coastal,
        CoastlineProfile::Inland,
        CoastlineProfile::Archipelago,
    ];

    #[test]
    fn height_at_is_deterministic() {
        for i in 0..500 {
            let (x, y) = (i as f32 * 0.0017, 1.0 - i as f32 * 0.0019);
            let a = height_at(x, y, CoastlineProfile::Coastal, 12345);
            let b = height_at(x, y, CoastlineProfile::Coastal, 12345);
            assert_eq!(a.to_bits(), b.to_bits(), "height_at not reproducible");
        }
    }

    #[test]
    fn height_at_is_non_negative_and_finite() {
        for profile in PROFILES {
            for i in 0..60 {
                for j in 0..60 {
                    let h = height_at(i as f32 / 60.0, j as f32 / 60.0, profile, 99);
                    assert!(h.is_finite() && h >= 0.0, "height_at({profile:?}) = {h}");
                }
            }
        }
    }

    #[test]
    fn height_at_varies_across_space() {
        let first = height_at(0.2, 0.3, CoastlineProfile::Coastal, 7);
        let differs = (1..400).any(|i| {
            let p = i as f32 * 0.0025;
            (height_at(p, 1.0 - p, CoastlineProfile::Coastal, 7) - first).abs() > 1e-3
        });
        assert!(differs, "height_at produced a constant field");
    }
}
