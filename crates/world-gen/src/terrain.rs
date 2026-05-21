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

use crate::creative_seed::{CoastlineProfile, CreativeSeed, TerrainMode};
use crate::erosion;
use crate::noise::{fbm_3d, ridged_fbm_3d};
use crate::plates::{self, Plates};
use crate::rng::sub_seed;

/// Archipelago island disc **centres on the unit sphere** — 5 mutually
/// distant points: a top-pentagon on a 45°-latitude circle. Pairwise
/// great-circle separation ≥ 1.26 rad (72° / nearest-neighbour); with
/// `ARCH_RADIUS = 0.30` (∼17°) the discs never touch.
const ARCH_ISLANDS: [[f32; 3]; 5] = [
    // cos(72° k) · sin(45°), sin(72° k) · sin(45°), cos(45°) for k=0..4
    [0.707_106_77, 0.0, 0.707_106_77],
    [0.218_508, 0.672_498_5, 0.707_106_77],
    [-0.572_061_4, 0.415_626_9, 0.707_106_77],
    [-0.572_061_4, -0.415_626_9, 0.707_106_77],
    [0.218_508, -0.672_498_5, 0.707_106_77],
];
/// Archipelago island disc radius — great-circle angle in radians (~17°).
/// `2 * ARCH_RADIUS < min island great-circle separation`, so the radial mask
/// is exactly 0 in the sea bands between islands.
const ARCH_RADIUS: f32 = 0.30;

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
/// 3D domain warp needs a third salt for the z-component (sphere migration).
const SALT_WARP_Z: u32 = 0x5C8B_3D04;
const SALT_CONT: u32 = 0x9D4E_0C53;
const SALT_MTN: u32 = 0xC0FF_EE42;
const SALT_BELT: u32 = 0x1357_9BDF;
const SALT_HILL: u32 = 0x2468_ACE0;

// --- tectonic relief tuning (Phase 2) ---------------------------------------

/// `Tectonic`-mode relief weights, layered on the plate base (continental 1.0
/// / oceanic 0.0) + orogeny uplift. Tuned for *lively, varied* continents
/// (the plate model owns the macro; this is the life): a strong low-freq
/// continental variation to fractal-ize coasts + roll interiors, real ranges
/// across the interior, and only a faint abyssal ripple in the deep ocean.
const TEC_CONT_WEIGHT: f32 = 0.12;
const TEC_HILL_WEIGHT: f32 = 0.06;
const TEC_MTN_WEIGHT: f32 = 0.95;
const TEC_ABYSS_WEIGHT: f32 = 0.05;

/// Per-cell elevations + the chosen sea level (+ the plate model in
/// `Tectonic` mode).
pub struct Terrain {
    /// `elevation[i]` for cell `i`, `0..=65535`.
    pub elevation: Vec<u16>,
    /// Elevation threshold; `< sea_level` ⇒ water.
    pub sea_level: u16,
    /// The tectonic plate model — `Some` in `Tectonic` mode, `None` in
    /// `Profile` mode.
    pub plates: Option<Plates>,
}

/// Build the heightmap for the given **spherical** mesh.
///
/// **Phase 2 (2026-05-21):** branches on [`CreativeSeed::terrain_mode`].
/// `Tectonic` (default) builds a plate model ([`crate::plates`]) and composes
/// `plate_base + orogeny_uplift + fine fBm texture` — multi-continent, no
/// radial mask, no forced single landmass. `Profile` keeps the Phase-1
/// single-continent path (`height_at` + `apply_falloff` + `enforce_coherence`).
pub fn build(
    seed: u64,
    cs: &CreativeSeed,
    centers: &[[f32; 3]],
    neighbors: &[Vec<u32>],
) -> Terrain {
    let count = centers.len();
    let s = sub_seed(seed, b"terrain-height");
    let nseed = (s ^ (s >> 32)) as u32;

    match cs.terrain_mode {
        TerrainMode::Tectonic => {
            let plates = plates::build(
                seed,
                cs.plate_count,
                cs.continental_fraction,
                centers,
                neighbors,
            );
            // elev = plate base + orogeny uplift + rich continental relief
            // (varied base + hills + ranges on land; gentle abyssal texture in
            // the oceans). The relief is what makes continents read as *alive*
            // rather than flat slabs.
            // Signed elevation, sea level = 0: continental platform just above,
            // ocean floor well below; mountain belts the high minority.
            let mut elev: Vec<f32> = (0..count)
                .map(|i| plates.base[i] + plates.uplift[i] + tectonic_relief(centers[i], plates.base[i], nseed))
                .collect();

            let land_fraction = cs.continental_fraction.clamp(0.1, 0.9);
            erosion::apply(&mut elev, neighbors, land_fraction, cs.erosion);

            // Quantize with a fixed scale (sea level pinned at SEA_FRAC) so
            // land keeps a generous, fixed share of the range — distinct
            // plains/uplands/mountains, not a deep-ocean-squeezed flat slab.
            let (elevation, sea_level) = quantize_fixed_scale(&elev, count);

            Terrain {
                elevation,
                sea_level,
                plates: Some(plates),
            }
        }
        TerrainMode::Profile => {
            let profile = cs.coastline_profile;
            let mut elev: Vec<f32> = centers
                .iter()
                .map(|&p| height_at(p, profile, nseed))
                .collect();

            // Coastline-profile radial falloff — shapes *where* land is.
            apply_falloff(profile, centers, &mut elev);

            // Hydraulic erosion — skipped for Archipelago (incision carving a
            // strait would dissect its fixed 5-island invariant).
            if !profile.is_archipelago() {
                erosion::apply(&mut elev, neighbors, profile.land_fraction(), cs.erosion);
            }

            let mut elevation = normalize_to_u16(&elev, count);
            let sea_level = choose_sea_level(profile, &elevation, neighbors);
            enforce_coherence(profile, &mut elevation, neighbors, sea_level);

            Terrain {
                elevation,
                sea_level,
                plates: None,
            }
        }
    }
}

/// Sea level as a fraction of the `u16` range under [`quantize_fixed_scale`].
/// Oceans get the lower `SEA_FRAC`; land gets the upper `1 − SEA_FRAC`.
const SEA_FRAC: f32 = 0.40;
/// Percentile of land/ocean elevation that maps to the top/bottom of the
/// range. The top `1 − this` of peaks (and deepest trenches) clamp to white /
/// abyss — so a few dramatic extremes don't compress everything else.
const SCALE_PCT: f32 = 0.99;

/// Quantize a **signed** elevation field (sea level = 0) to `u16`. Sea level
/// is pinned at `SEA_FRAC`; **land is stretched by its own `SCALE_PCT`
/// percentile to fill the upper `1 − SEA_FRAC`**, and ocean likewise fills the
/// lower `SEA_FRAC`. So land always uses its full share of the range — coastal
/// plains → green, uplands → brown, the tallest peaks → white — *robustly
/// across seeds*, regardless of the absolute relief amplitude.
///
/// This replaced a min-max normalize (which let deep ocean stretch the bottom
/// and squeeze all land into the top ~20% — the "flattened terrain" bug) and a
/// fixed-scale variant (which under-used the land range when the relief
/// amplitude was modest, rendering mountains brown-not-white).
fn quantize_fixed_scale(elev: &[f32], count: usize) -> (Vec<u16>, u16) {
    let sea_u16 = (SEA_FRAC * 65535.0).round() as u16;

    // Percentile scale for land (signed > 0) and ocean depth (|signed < 0|).
    let mut land: Vec<f32> = elev.iter().copied().filter(|&e| e > 0.0).collect();
    let mut ocean: Vec<f32> = elev.iter().copied().filter(|&e| e < 0.0).map(|e| -e).collect();
    land.sort_by(f32::total_cmp);
    ocean.sort_by(f32::total_cmp);
    let pctl = |v: &[f32]| -> f32 {
        if v.is_empty() {
            1.0
        } else {
            v[((SCALE_PCT * v.len() as f32) as usize).min(v.len() - 1)].max(1e-4)
        }
    };
    let land_scale = pctl(&land);
    let ocean_scale = pctl(&ocean);

    let mut elevation = vec![0u16; count];
    for (i, &e) in elev.iter().enumerate() {
        let u = if e >= 0.0 {
            SEA_FRAC + (e / land_scale).min(1.0) * (1.0 - SEA_FRAC)
        } else {
            SEA_FRAC - ((-e) / ocean_scale).min(1.0) * SEA_FRAC
        };
        elevation[i] = (u.clamp(0.0, 1.0) * 65535.0).round() as u16;
    }
    (elevation, sea_u16)
}

/// Min-max normalize an f32 elevation field to the full `u16` range.
fn normalize_to_u16(elev: &[f32], count: usize) -> Vec<u16> {
    let mut lo = f32::INFINITY;
    let mut hi = f32::NEG_INFINITY;
    for &e in elev {
        lo = lo.min(e);
        hi = hi.max(e);
    }
    let span = (hi - lo).max(1e-6);
    let mut elevation = vec![0u16; count];
    for (i, &e) in elev.iter().enumerate() {
        let n = ((e - lo) / span).clamp(0.0, 1.0);
        elevation[i] = (n * 65535.0).round() as u16;
    }
    elevation
}

/// 3D domain warp of a unit-sphere point, re-normalized back onto the sphere.
/// Shared by [`height_at`] (Profile) and [`texture_at`] (Tectonic).
fn warp_point(p: [f32; 3], seed: u32) -> [f32; 3] {
    let warp_x = fbm_3d(p[0] * WARP_FREQ, p[1] * WARP_FREQ, p[2] * WARP_FREQ, seed ^ SALT_WARP_X, WARP_OCTAVES);
    let warp_y = fbm_3d(p[0] * WARP_FREQ, p[1] * WARP_FREQ, p[2] * WARP_FREQ, seed ^ SALT_WARP_Y, WARP_OCTAVES);
    let warp_z = fbm_3d(p[0] * WARP_FREQ, p[1] * WARP_FREQ, p[2] * WARP_FREQ, seed ^ SALT_WARP_Z, WARP_OCTAVES);
    let mut w = [
        p[0] + WARP_AMP * warp_x,
        p[1] + WARP_AMP * warp_y,
        p[2] + WARP_AMP * warp_z,
    ];
    let wn = (w[0] * w[0] + w[1] * w[1] + w[2] * w[2]).sqrt();
    if wn > 1e-6 {
        w[0] /= wn;
        w[1] /= wn;
        w[2] /= wn;
    }
    w
}

/// Rich relief for `Tectonic` mode, layered on top of the plate base + orogeny
/// uplift. The plate model owns *where* land and big belts are; this gives the
/// terrain its *life*:
/// - **continental base variation** (low-freq fBm) so the land rolls and the
///   coastline fractal-izes (bays, peninsulas, offshore islands) instead of
///   tracing a smooth plate edge;
/// - **hills** (mid-freq) for texture between ranges;
/// - **ridged ranges** (belt-masked) so continental *interiors* carry mountain
///   ranges, not just the plate boundaries;
/// - **gentle abyssal texture** in the oceans (kept well below sea level) so
///   the sea floor isn't a dead flat sheet.
///
/// `landness` (smoothstepped plate base) gates land vs ocean contributions.
fn tectonic_relief(p: [f32; 3], base: f32, seed: u32) -> f32 {
    // `base` is signed (sea level = 0): continental platform ≈ +0.10, ocean
    // floor ≈ −0.55. Land where base ≥ 0.
    let landness = smoothstep(-0.05, 0.08, base);
    let w = warp_point(p, seed);

    // Gentle low-freq platform variation — keeps the vast plains *low* (some
    // dips below sea → natural bays/coast) without lifting the whole continent.
    let cont = fbm_3d(w[0] * CONT_FREQ, w[1] * CONT_FREQ, w[2] * CONT_FREQ, seed ^ SALT_CONT, CONT_OCTAVES);
    // Mid-freq hills.
    let hills = fbm_3d(w[0] * HILL_FREQ, w[1] * HILL_FREQ, w[2] * HILL_FREQ, seed ^ SALT_HILL, HILL_OCTAVES);
    // Belt-masked ridged ranges — a *minority* of the land (rarer belt mask →
    // linear mountain chains, not a blanket of highland).
    let belt_raw = 0.5
        + 0.5 * fbm_3d(p[0] * BELT_FREQ, p[1] * BELT_FREQ, p[2] * BELT_FREQ, seed ^ SALT_BELT, BELT_OCTAVES);
    let belt = smoothstep(0.52, 0.76, belt_raw);
    let ridges = ridged_fbm_3d(w[0] * MTN_FREQ, w[1] * MTN_FREQ, w[2] * MTN_FREQ, seed ^ SALT_MTN, MTN_OCTAVES);

    // On land: gentle plains + sparse ranges. In ocean: only a faint abyssal ripple.
    let land_relief =
        TEC_CONT_WEIGHT * cont + TEC_HILL_WEIGHT * hills + TEC_MTN_WEIGHT * belt * ridges;
    let ocean_relief = TEC_ABYSS_WEIGHT * hills;
    landness * land_relief + (1.0 - landness) * ocean_relief
}

/// The Path B heightmap — a pure function of position on the **unit sphere**.
/// A low-frequency 3D fBm continent, 3D ridged-multifractal mountain ranges
/// gated by a belt mask and a landness gate, mid-frequency hills, all 3D
/// domain-warped, plus the optional Inland continental dome (centred at the
/// `+z` pole). 3D Perlin gives **antimeridian-seamless** terrain — no edge
/// artefacts. Always `≥ 0` (the normalize + `apply_falloff` multiply both
/// assume a non-negative field).
fn height_at(p: [f32; 3], profile: CoastlineProfile, seed: u32) -> f32 {
    // Domain warp — displace the sample point with low-frequency 3D fBm, then
    // re-normalize back onto the unit sphere (shared with `texture_at`).
    let warped = warp_point(p, seed);

    // Continent base — the broad landmass, 3D fBm mapped to ~[0,1].
    let continent = 0.5
        + 0.5
            * fbm_3d(
                warped[0] * CONT_FREQ,
                warped[1] * CONT_FREQ,
                warped[2] * CONT_FREQ,
                seed ^ SALT_CONT,
                CONT_OCTAVES,
            );

    // Hills — mid-frequency rolling terrain, signed (raises and lowers).
    let hills = fbm_3d(
        warped[0] * HILL_FREQ,
        warped[1] * HILL_FREQ,
        warped[2] * HILL_FREQ,
        seed ^ SALT_HILL,
        HILL_OCTAVES,
    );

    // Mountain-belt mask — a soft low-frequency gate so ranges cluster into
    // belts rather than blanketing the whole map. Sampled at the *unwarped*
    // point so the belt structure is independent of the local domain warp.
    let belt_raw = 0.5
        + 0.5
            * fbm_3d(
                p[0] * BELT_FREQ,
                p[1] * BELT_FREQ,
                p[2] * BELT_FREQ,
                seed ^ SALT_BELT,
                BELT_OCTAVES,
            );
    let belt = smoothstep(0.46, 0.72, belt_raw);

    // Ridged ranges — sharp linear ridgelines (the bullseye-killer).
    let ridges = ridged_fbm_3d(
        warped[0] * MTN_FREQ,
        warped[1] * MTN_FREQ,
        warped[2] * MTN_FREQ,
        seed ^ SALT_MTN,
        MTN_OCTAVES,
    );

    // Landness gate — ranges rise on continental crust, fade over deep ocean.
    let landness = smoothstep(0.32, 0.52, continent);

    // Inland continental dome — a broad bias centred at the `+z` pole so the
    // high-land Inland profile forms one coherent mass. `base_amplitude` is
    // 0 for the rest.
    let dome = profile.base_amplitude() * dome_bias(p);

    let height = CONT_WEIGHT * continent
        + HILL_WEIGHT * hills
        + MTN_WEIGHT * belt * ridges * landness
        + dome;
    height.max(0.0)
}

/// Broad dome — 1 at the `+z` pole, falling to 0 by ~π/2 (a hemisphere) —
/// the Inland profile's coherent-landmass bias on the sphere. Falloff = the
/// great-circle angle from `[0, 0, 1]`, normalized by π/2.
fn dome_bias(p: [f32; 3]) -> f32 {
    // `p[2]` is the dot product with `[0, 0, 1]` for unit-sphere `p`, so
    // `acos(p[2])` is the great-circle angle to the +z pole.
    let cos_d = p[2].clamp(-1.0, 1.0);
    let angle = cos_d.acos();
    let r = angle / std::f32::consts::FRAC_PI_2;
    (1.0 - r * r).max(0.0)
}

/// Hermite smoothstep — 0 at/below `e0`, 1 at/above `e1`, smooth between.
fn smoothstep(e0: f32, e1: f32, x: f32) -> f32 {
    let t = ((x - e0) / (e1 - e0)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

/// Multiply each cell's elevation by a coastline-profile mask, computed on
/// the **unit sphere** via great-circle distances.
///
/// All masks are anchored at the `+z` pole — the canonical "centre" of the
/// world. Future plate-tectonic Phase 2 will replace this single-anchor
/// scheme with multiple continent seeds.
fn apply_falloff(profile: CoastlineProfile, centers: &[[f32; 3]], elev: &mut [f32]) {
    /// Canonical centre point for radial masks: the `+z` pole.
    const POLE: [f32; 3] = [0.0, 0.0, 1.0];

    for (i, &p) in centers.iter().enumerate() {
        let mask = match profile {
            CoastlineProfile::Island => {
                // Single island disc centred at +z pole; radius ~63°.
                let d = great_circle(p, POLE);
                let r = d / 1.10;
                (1.0 - r * r).max(0.0)
            }
            CoastlineProfile::Peninsula => {
                // Land extends from the +z hemisphere; falloff toward −z.
                // `p[2]` is the projection onto the pole axis ∈ [-1, 1].
                // Ramp from 0 below the equator down to 1 by mid-northern.
                edge_ramp(p[2] + 0.30, 0.50)
            }
            CoastlineProfile::Coastal => {
                // Falloff toward one longitude band — pick lon = π as the
                // "ocean side". Mask high near lon = 0, low near lon = ±π.
                let lon = p[1].atan2(p[0]);
                let coastal = 1.0 - (lon.abs() / std::f32::consts::PI);
                edge_ramp(coastal, 0.40)
            }
            CoastlineProfile::Inland => {
                // Mild non-uniform mask centred at +z pole. The Inland dome
                // already biases interior land via `dome_bias`; the mask is
                // gentle (`0.85..=1.00`) so the broad geometry stays driven
                // by the dome.
                let d = great_circle(p, POLE);
                0.85 + 0.15 * (1.0 - (d / std::f32::consts::PI).min(1.0))
            }
            CoastlineProfile::Archipelago => {
                // Max over 5 sphere-distributed island discs; exactly 0 in
                // the sea bands between (each disc radius ≪ pairwise sep).
                let mut best = 0.0f32;
                for centre in &ARCH_ISLANDS {
                    let d = great_circle(p, *centre);
                    let r = d / ARCH_RADIUS;
                    let m = 1.0 - r * r;
                    best = best.max(m.max(0.0));
                }
                best
            }
        };
        elev[i] *= mask;
    }
}

/// 0 at the edge, ramping linearly to 1 by `width`.
fn edge_ramp(edge_dist: f32, width: f32) -> f32 {
    (edge_dist / width).clamp(0.0, 1.0)
}

/// Great-circle angle between two **unit-sphere** points — in radians.
fn great_circle(a: [f32; 3], b: [f32; 3]) -> f32 {
    let cos_d = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]).clamp(-1.0, 1.0);
    cos_d.acos()
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

    fn unit(x: f32, y: f32, z: f32) -> [f32; 3] {
        let n = (x * x + y * y + z * z).sqrt();
        [x / n, y / n, z / n]
    }

    #[test]
    fn height_at_is_deterministic() {
        for i in 0..500 {
            let p = unit(i as f32 * 0.0017 + 1.0, 1.0 - i as f32 * 0.0019, 0.3);
            let a = height_at(p, CoastlineProfile::Coastal, 12345);
            let b = height_at(p, CoastlineProfile::Coastal, 12345);
            assert_eq!(a.to_bits(), b.to_bits(), "height_at not reproducible");
        }
    }

    #[test]
    fn height_at_is_non_negative_and_finite() {
        for profile in PROFILES {
            // Sweep a `lat × lon` grid; resample on the sphere.
            for i in 0..40 {
                for j in 0..40 {
                    let lat = -std::f32::consts::FRAC_PI_2 + i as f32 * (std::f32::consts::PI / 40.0);
                    let lon = -std::f32::consts::PI + j as f32 * (std::f32::consts::TAU / 40.0);
                    let p = [lat.cos() * lon.cos(), lat.cos() * lon.sin(), lat.sin()];
                    let h = height_at(p, profile, 99);
                    assert!(h.is_finite() && h >= 0.0, "height_at({profile:?}) = {h}");
                }
            }
        }
    }

    #[test]
    fn height_at_varies_across_space() {
        let first = height_at(unit(1.0, 0.0, 0.0), CoastlineProfile::Coastal, 7);
        let differs = (1..400).any(|i| {
            let theta = i as f32 * 0.0157;
            let p = unit(theta.cos(), theta.sin(), 0.2);
            (height_at(p, CoastlineProfile::Coastal, 7) - first).abs() > 1e-3
        });
        assert!(differs, "height_at produced a constant field");
    }

    #[test]
    fn height_at_is_continuous_across_the_antimeridian() {
        // 3D Perlin on the unit sphere is naturally seamless — two cells just
        // either side of lon = π should produce nearly identical heights.
        let eps = 1e-4;
        for lat_step in -3..=3 {
            let lat = lat_step as f32 * 0.3;
            // lon ≈ +π - eps and lon ≈ -π + eps — same physical point.
            let pa = unit(
                lat.cos() * (std::f32::consts::PI - eps).cos(),
                lat.cos() * (std::f32::consts::PI - eps).sin(),
                lat.sin(),
            );
            let pb = unit(
                lat.cos() * (-std::f32::consts::PI + eps).cos(),
                lat.cos() * (-std::f32::consts::PI + eps).sin(),
                lat.sin(),
            );
            let ha = height_at(pa, CoastlineProfile::Coastal, 7);
            let hb = height_at(pb, CoastlineProfile::Coastal, 7);
            assert!(
                (ha - hb).abs() < 0.05,
                "antimeridian discontinuity at lat={lat}: {ha} vs {hb}"
            );
        }
    }
}
