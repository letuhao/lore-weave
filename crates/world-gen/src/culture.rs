//! Stage 8 — culture regions: barrier-cost flood-fill from cultural hearths.

use crate::biome::BiomeKind;
use crate::params::CultureParams;
use crate::pathfind::{self, NONE};
use crate::rng::{self, Rng};
use crate::world_map::CultureRegion;

/// Stage-8 output.
pub struct Culture {
    /// Per-cell culture id; `NONE` for water cells.
    pub culture_of: Vec<u32>,
    pub culture_regions: Vec<CultureRegion>,
}

/// Build the culture layer using the **default** tuning. Thin wrapper over
/// [`build_with`] for callers that don't tune it (the civ adapter + tests).
pub fn build(
    seed: u64,
    centers: &[[f32; 3]],
    neighbors: &[Vec<u32>],
    biomes: &[BiomeKind],
    culture_count: u8,
) -> Culture {
    build_with(seed, centers, neighbors, biomes, culture_count, &CultureParams::default())
}

/// Build the culture layer with caller-tuned [`CultureParams`]
/// (parameterization P6). `culture_count` is clamped to `1..=count_max`. Default
/// params ⇒ byte-identical to the prior consts.
///
/// **Phase 1 Stage B (2026-05-20):** `centers` is now 3D unit-sphere points;
/// hearth spacing uses great-circle angle in radians. The flood-fill stays
/// graph-based.
pub fn build_with(
    seed: u64,
    centers: &[[f32; 3]],
    neighbors: &[Vec<u32>],
    biomes: &[BiomeKind],
    culture_count: u8,
    cp: &CultureParams,
) -> Culture {
    let n = centers.len();
    let is_land: Vec<bool> = biomes.iter().map(|b| !b.is_water()).collect();
    let comps = pathfind::land_components(&is_land, neighbors);
    if comps.is_empty() {
        return Culture {
            culture_of: vec![NONE; n],
            culture_regions: Vec::new(),
        };
    }

    let k = usize::from(culture_count.clamp(1, cp.count_max.clamp(1, 255) as u8));
    let n_components = comps.len();

    // hearth quota per component: if k >= n_components, largest-remainder;
    // else the k largest components get one each (rest fall back to culture 0).
    let quotas: Vec<usize> = if k >= n_components {
        let sizes: Vec<usize> = comps.iter().map(Vec::len).collect();
        pathfind::apportion(k, &sizes)
    } else {
        let mut order: Vec<usize> = (0..n_components).collect();
        order.sort_by(|&a, &b| comps[b].len().cmp(&comps[a].len()).then(a.cmp(&b)));
        let mut q = vec![0usize; n_components];
        for &ci in order.iter().take(k) {
            q[ci] = 1;
        }
        q
    };

    // Hearth spacing — radians of great-circle angle (sphere migration).
    let min_sep = cp.hearth_spacing_coeff / (k as f32).sqrt() * std::f32::consts::PI;
    let mut rng = Rng::for_stage(seed, b"culture");
    let mut hearths: Vec<u32> = Vec::with_capacity(k);
    for (ci, comp) in comps.iter().enumerate() {
        let quota = quotas[ci];
        if quota == 0 {
            continue;
        }
        let mut cells = comp.clone();
        rng::shuffle(&mut rng, &mut cells);
        let start = hearths.len();
        for &cell in &cells {
            if hearths.len() - start >= quota {
                break;
            }
            if pathfind::spaced_ok(cell, &hearths, centers, min_sep) {
                hearths.push(cell);
            }
        }
        for &cell in &cells {
            if hearths.len() - start >= quota {
                break;
            }
            if !hearths[start..].contains(&cell) {
                hearths.push(cell);
            }
        }
    }

    // --- culture flood-fill (barrier cost) ---
    let owner = pathfind::multi_source_assign(&hearths, |c| biomes[c].culture_barrier(), neighbors);
    // A land cell unreachable from any hearth (a hearthless component, or a
    // Glacier cell — Glacier has no culture_barrier) falls back to culture 0.
    let mut culture_of = vec![NONE; n];
    for (c, &is_l) in is_land.iter().enumerate() {
        if is_l {
            culture_of[c] = if owner[c] == NONE { 0 } else { owner[c] };
        }
    }

    let culture_regions: Vec<CultureRegion> = hearths
        .iter()
        .enumerate()
        .map(|(i, &cell)| CultureRegion {
            id: i as u32,
            hearth_cell: cell,
            name: String::new(),
        })
        .collect();

    Culture {
        culture_of,
        culture_regions,
    }
}
