//! Stage 2 — heightmap.
//!
//! Azgaar-style blob seeds ("add hill/range") + a coastline-profile radial
//! falloff, normalized to `u16`. Sea level is picked by target land fraction.
//!
//! Land coherence (acceptance criterion #5) is then *enforced structurally*,
//! not left to emerge:
//! - non-Archipelago — `enforce_coherence` submerges every land component
//!   except the largest, so one dominant continent always remains;
//! - Archipelago — blobs are confined to 5 fixed, well-separated island discs
//!   (`ARCH_ISLANDS` / `ARCH_RADIUS`); the radial mask is exactly 0 between
//!   discs, so the islands are always separate connected components.

use crate::creative_seed::CoastlineProfile;
use crate::rng::Rng;

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
    centers: &[(f32, f32)],
    neighbors: &[Vec<u32>],
) -> Terrain {
    let count = centers.len();
    let mut rng = Rng::for_stage(seed, b"terrain");
    let mut elev = vec![0.0f32; count];

    // --- Blob seeds (exact, fully-pinned algorithm) ---
    let k = (count / 380).clamp(6, 40);
    for b in 0..k {
        let ux = rng.next_f32();
        let uy = rng.next_f32();
        let ua = rng.next_f32();
        let uf = rng.next_f32();
        let (bx, by) = if profile.is_archipelago() {
            // Seed inside one island disc (round-robin over the 5 islands).
            let island = ARCH_ISLANDS[b % ARCH_ISLANDS.len()];
            let angle = ux * std::f32::consts::TAU;
            let r = uy * ARCH_RADIUS * 0.6;
            (island.0 + r * angle.cos(), island.1 + r * angle.sin())
        } else {
            // Center-biased ⇒ one coherent mass (SPREAD = 0.70).
            (0.5 + (ux - 0.5) * 0.70, 0.5 + (uy - 0.5) * 0.70)
        };
        let seed_cell = nearest_cell(centers, bx, by);
        let amp = 0.45 + ua * 0.55;
        let falloff = 0.82 + uf * 0.08;
        grow_blob(seed_cell, amp, falloff, neighbors, &mut elev);
    }

    // --- Radial falloff by coastline profile ---
    apply_falloff(profile, centers, &mut elev);

    // --- Normalize to [0,1], then to u16 ---
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

    let sea_level = pick_sea_level(&elevation, profile.land_fraction());
    enforce_coherence(profile, &mut elevation, neighbors, sea_level);

    Terrain {
        elevation,
        sea_level,
    }
}

/// Index of the cell whose centre is nearest `(x,y)` (squared Euclidean;
/// ties resolve to the lower index).
fn nearest_cell(centers: &[(f32, f32)], x: f32, y: f32) -> usize {
    debug_assert!(!centers.is_empty(), "mesh must be non-empty");
    let mut best = 0usize;
    let mut best_d = f32::INFINITY;
    for (i, &(cx, cy)) in centers.iter().enumerate() {
        let d = (cx - x) * (cx - x) + (cy - y) * (cy - y);
        if d < best_d {
            best_d = d;
            best = i;
        }
    }
    best
}

/// BFS a blob outward from `seed_cell`: a cell first reached at ring `r`
/// receives `amp * falloff^r` (via `max`); expansion stops below 0.02.
fn grow_blob(seed_cell: usize, amp: f32, falloff: f32, neighbors: &[Vec<u32>], elev: &mut [f32]) {
    let mut visited = vec![false; elev.len()];
    let mut queue: std::collections::VecDeque<(usize, f32)> = std::collections::VecDeque::new();
    visited[seed_cell] = true;
    queue.push_back((seed_cell, amp));
    while let Some((cell, contrib)) = queue.pop_front() {
        if contrib < 0.02 {
            continue;
        }
        if contrib > elev[cell] {
            elev[cell] = contrib;
        }
        let next = contrib * falloff;
        for &n in &neighbors[cell] {
            let n = n as usize;
            if !visited[n] {
                visited[n] = true;
                queue.push_back((n, next));
            }
        }
    }
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

/// Pick the sea level so roughly `land_fraction` of cells are land — the
/// `(1 - land_fraction)` percentile of the sorted elevation list. Clamped
/// to GEO_001's sane `[8192, 57344]` band.
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
