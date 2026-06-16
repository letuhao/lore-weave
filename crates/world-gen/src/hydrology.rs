//! Stage 4 — hydrology: depression-filled flow, river flux, water network.
//!
//! Priority-flood (Barnes 2014) fills depressions so every land cell drains
//! to the sea; flow accumulation over the resulting receiver tree gives
//! `river_flux`; a connected-components pass tags ocean vs lake.

use std::cmp::Reverse;
use std::collections::BinaryHeap;

use crate::climate::ClimateZone;
use crate::params::HydrologyParams;

/// Output of the hydrology stage.
pub struct Hydrology {
    /// Accumulated downhill flow per cell.
    pub river_flux: Vec<f32>,
    /// Flux above which a land cell is a `River` biome (96th-percentile pick).
    pub river_threshold: f32,
    /// Per cell: belongs to an ocean water body (vs. an isolated lake).
    pub is_in_ocean: Vec<bool>,
    /// Per cell: land cell adjacent to an ocean water cell.
    pub is_coast: Vec<bool>,
}

/// Run the hydrology stage.
///
/// **Phase 1 Stage B (2026-05-20):** `centers` is now 3D unit-sphere points.
/// The `is_border` check is gone (a sphere has no edge); a water component is
/// ocean iff `len() > lake_max` — i.e. it's significantly large. The previous
/// "touches the [0,1]² perimeter" path is no longer applicable.
pub fn build(
    centers: &[[f32; 3]],
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
    climate: &[ClimateZone],
) -> Hydrology {
    build_with(centers, elevation, sea_level, neighbors, climate, &HydrologyParams::default())
}

/// [`build`] with a caller-tuned [`HydrologyParams`] (parameterization P4).
/// Default params ⇒ byte-identical to the prior hardcoded thresholds.
pub fn build_with(
    centers: &[[f32; 3]],
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
    climate: &[ClimateZone],
    hp: &HydrologyParams,
) -> Hydrology {
    let _ = centers; // kept in signature for downstream forward-compat.
    let (receiver, pop_order) = priority_flood(elevation, sea_level, neighbors);
    let river_flux = flow_accumulation(elevation, sea_level, climate, &receiver, &pop_order);
    let river_threshold = percentile_threshold(&river_flux, elevation, sea_level, hp.river_percentile);
    let is_in_ocean = water_network(elevation, sea_level, neighbors, hp);
    let is_coast = coast_cells(elevation, sea_level, neighbors, &is_in_ocean);
    Hydrology {
        river_flux,
        river_threshold,
        is_in_ocean,
        is_coast,
    }
}

/// Priority-flood: returns `(receiver, pop_order)`. `receiver[c]` is the cell
/// `c` drains into (`u32::MAX` for water cells); `pop_order` is the order
/// cells leave the heap (ascending filled elevation). Cells are marked
/// closed at *push* time → each is pushed exactly once → every heap entry
/// has a unique cell index → fully deterministic.
fn priority_flood(
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
) -> (Vec<u32>, Vec<usize>) {
    let n = elevation.len();
    let mut receiver = vec![u32::MAX; n];
    let mut closed = vec![false; n];
    let mut pop_order = Vec::with_capacity(n);
    // Min-heap over (filled_elev, cell); `cell` makes every key unique.
    let mut heap: BinaryHeap<Reverse<(u16, u32)>> = BinaryHeap::new();

    for (i, &e) in elevation.iter().enumerate() {
        if e < sea_level {
            closed[i] = true;
            heap.push(Reverse((e, i as u32)));
        }
    }
    while let Some(Reverse((fe, c))) = heap.pop() {
        let c = c as usize;
        pop_order.push(c);
        for &nb in &neighbors[c] {
            let nb = nb as usize;
            if !closed[nb] {
                let filled = elevation[nb].max(fe);
                receiver[nb] = c as u32;
                closed[nb] = true;
                heap.push(Reverse((filled, nb as u32)));
            }
        }
    }
    (receiver, pop_order)
}

/// Flow accumulation over the priority-flood receiver tree. Processing cells
/// in reverse pop order guarantees a cell is fully accumulated before its
/// receiver consumes it; the order is deterministic, so the `f32` sums are.
fn flow_accumulation(
    elevation: &[u16],
    sea_level: u16,
    climate: &[ClimateZone],
    receiver: &[u32],
    pop_order: &[usize],
) -> Vec<f32> {
    let mut flux = vec![0.0f32; elevation.len()];
    for &c in pop_order.iter().rev() {
        if elevation[c] >= sea_level {
            flux[c] += climate[c].wetness(); // rainfall on land
        }
        let r = receiver[c];
        if r != u32::MAX {
            flux[r as usize] += flux[c];
        }
    }
    flux
}

/// River threshold = 96th percentile of land-cell flux (~4 % of land is
/// river). Self-tuning and deterministic.
fn percentile_threshold(flux: &[f32], elevation: &[u16], sea_level: u16, percentile: f32) -> f32 {
    let mut land: Vec<f32> = elevation
        .iter()
        .zip(flux)
        .filter(|&(&e, _)| e >= sea_level)
        .map(|(_, &f)| f)
        .collect();
    if land.len() < 2 {
        return f32::INFINITY; // ~no land ⇒ no rivers
    }
    land.sort_by(f32::total_cmp);
    let idx = ((land.len() as f32 * percentile) as usize).min(land.len() - 1);
    land[idx]
}

/// Connected components of water cells; a component is ocean if it exceeds
/// `LAKE_MAX`, else a lake. Ascending start-cell sweep + DFS over sorted
/// neighbours (same order as `terrain::land_components`).
///
/// **Sphere migration (Stage B):** the previous "touches the [0,1]² border"
/// criterion is dropped — a sphere has no border. The size criterion alone
/// distinguishes ocean (a globe-spanning water body, > ~1% of cells) from
/// a lake. Empirically the size threshold reliably picks the right thing
/// for every CoastlineProfile.
fn water_network(
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
    hp: &HydrologyParams,
) -> Vec<bool> {
    let n = elevation.len();
    let is_water = |i: usize| elevation[i] < sea_level;
    let lake_max = (n / (hp.lake_max_divisor as usize).max(1)).max(hp.lake_max_floor as usize);
    let mut seen = vec![false; n];
    let mut is_in_ocean = vec![false; n];

    for start in 0..n {
        if seen[start] || !is_water(start) {
            continue;
        }
        let mut component = Vec::new();
        let mut stack = vec![start];
        seen[start] = true;
        while let Some(c) = stack.pop() {
            component.push(c);
            for &nb in &neighbors[c] {
                let nb = nb as usize;
                if !seen[nb] && is_water(nb) {
                    seen[nb] = true;
                    stack.push(nb);
                }
            }
        }
        if component.len() > lake_max {
            for c in component {
                is_in_ocean[c] = true;
            }
        }
    }
    is_in_ocean
}

/// Land cells with ≥1 ocean-water neighbour.
fn coast_cells(
    elevation: &[u16],
    sea_level: u16,
    neighbors: &[Vec<u32>],
    is_in_ocean: &[bool],
) -> Vec<bool> {
    (0..elevation.len())
        .map(|i| {
            elevation[i] >= sea_level
                && neighbors[i].iter().any(|&nb| {
                    let nb = nb as usize;
                    elevation[nb] < sea_level && is_in_ocean[nb]
                })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A linear chain of `n` cells linked to neighbours `i-1` and `i+1`.
    /// **Sphere migration (Stage B):** the previous `(centers, neighbors)`
    /// shape was halved — `water_network` no longer reads centres
    /// (there's no map border on a globe).
    fn chain(n: usize) -> Vec<Vec<u32>> {
        (0..n)
            .map(|i| {
                let mut nb = Vec::new();
                if i > 0 {
                    nb.push((i - 1) as u32);
                }
                if i + 1 < n {
                    nb.push((i + 1) as u32);
                }
                nb
            })
            .collect()
    }

    #[test]
    fn small_interior_basin_is_lake() {
        let neighbors = chain(40);
        // cells 18..22 water (4 cells); endpoints stay land.
        let mut elevation = [100u16; 40];
        for e in &mut elevation[18..22] {
            *e = 0;
        }
        let ocean = water_network(&elevation, 50, &neighbors, &HydrologyParams::default());
        assert!(!ocean[18], "small interior basin must be a lake");
    }

    #[test]
    fn large_interior_basin_is_ocean() {
        let neighbors = chain(80);
        // cells 20..60 water (40 cells > LAKE_MAX = 24).
        let mut elevation = [100u16; 80];
        for e in &mut elevation[20..60] {
            *e = 0;
        }
        let ocean = water_network(&elevation, 50, &neighbors, &HydrologyParams::default());
        assert!(
            ocean[20],
            "large interior basin must be ocean (inland sea)"
        );
    }
}
