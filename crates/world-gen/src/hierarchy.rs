//! Stage 10 — geometric region hierarchy (C3 arc, sub-phase C-1a).
//!
//! A three-level geographic subdivision of the **land** on the sphere, built
//! almost entirely by reusing existing primitives — the lift of the flat
//! track's plate→zone→subzone tree onto the production sphere substrate
//! (`docs/03_planning/LLM_MMO_RPG/FLAT_TO_3D_MIGRATION_PLAN.md` §7):
//!
//! - **L0 Continent** = a connected component of land cells
//!   ([`crate::pathfind::land_components`], the same machinery
//!   [`crate::political`] already uses). "Land" is `!BiomeKind::is_water()`,
//!   i.e. every biome except `Ocean` and `Lake`; rivers are land. A lake
//!   interior is therefore a barrier that can split one landmass into separate
//!   continents — intentional, and identical to how `political` partitions
//!   land, so the two layers agree (the C-2 seam depends on that). Ocean basins
//!   are *not* subdivided here (they are already [`crate::feature`] water
//!   bodies); C-1a is land-only.
//! - **L1 Subcontinent** = a continent split by tectonic plate
//!   ([`crate::plates`] `plate_of`): the cells of a continent that share one
//!   plate id form one subcontinent (cratonic blocks). In `Profile`
//!   `TerrainMode` (no plates) the whole continent is one subcontinent.
//! - **L2 Region** = a **great-circle Voronoi** partition inside each
//!   subcontinent: `region_subdivision` seeds picked by farthest-point
//!   sampling, each cell assigned to the nearest seed by maximum dot product on
//!   the unit sphere. This is the only genuinely new geometry — modelled on the
//!   nearest-seed test in [`crate::plates`], **never** a 2D pixel grid.
//!
//! Determinism: no RNG. Continents follow `land_components`' ascending-start
//! order; each component is sorted ascending before use; subcontinents follow
//! ascending plate id; region seeds are farthest-point sampled (deterministic,
//! lowest-index tie-break) and assignment ties go to the lowest seed index.

use crate::biome::BiomeKind;
use crate::pathfind;
use crate::world_map::{Continent, Region, Subcontinent};

/// Sentinel: a cell that belongs to no continent/subcontinent/region (i.e. an
/// ocean/water cell). Mirrors the `u32::MAX` convention `province_of` uses.
pub const NONE: u32 = u32::MAX;

/// The geometric hierarchy output. Every per-cell vector is parallel to the
/// mesh cells; water cells carry [`NONE`].
pub struct Hierarchy {
    pub continent_of: Vec<u32>,
    pub subcontinent_of: Vec<u32>,
    pub region_of: Vec<u32>,
    pub continents: Vec<Continent>,
    pub subcontinents: Vec<Subcontinent>,
    pub regions: Vec<Region>,
}

/// 3D dot product on unit-sphere cell centres — the great-circle nearest-seed
/// proximity measure (larger dot = smaller angle = nearer).
fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

/// Pick up to `k` region seeds from `cells` by farthest-point sampling: start
/// at the lowest-index cell, then repeatedly add the cell whose nearest already
/// chosen seed is farthest away (max-min great-circle distance). Deterministic;
/// `cells` must be ascending so the lowest-index tie-break is automatic.
fn farthest_point_seeds(cells: &[u32], centers: &[[f32; 3]], k: usize) -> Vec<u32> {
    let k = k.clamp(1, cells.len());
    let mut seeds: Vec<u32> = Vec::with_capacity(k);
    seeds.push(cells[0]);
    while seeds.len() < k {
        let mut best_cell: Option<u32> = None;
        let mut best_min_dist = f32::NEG_INFINITY;
        for &c in cells {
            if seeds.contains(&c) {
                continue;
            }
            let cc = centers[c as usize];
            // Distance to the nearest seed; `1 - dot` is monotonic in the
            // great-circle angle for unit vectors.
            let mut min_dist = f32::INFINITY;
            for &s in &seeds {
                let d = 1.0 - dot(cc, centers[s as usize]);
                if d < min_dist {
                    min_dist = d;
                }
            }
            // Strict `>` + ascending `cells` ⇒ lowest index wins ties.
            if min_dist > best_min_dist {
                best_min_dist = min_dist;
                best_cell = Some(c);
            }
        }
        match best_cell {
            Some(c) => seeds.push(c),
            None => break,
        }
    }
    seeds
}

/// Build the geometric region hierarchy.
///
/// `plate_of` may be empty (or shorter than the mesh) in `Profile` mode — a
/// missing plate id is read as [`NONE`], collapsing a continent to a single
/// subcontinent. `region_subdivision` is the target L2 seed count per
/// subcontinent (clamped to `≥1`; a subcontinent with fewer cells than seeds
/// gets one region per cell).
pub fn build(
    centers: &[[f32; 3]],
    neighbors: &[Vec<u32>],
    biomes: &[BiomeKind],
    plate_of: &[u32],
    region_subdivision: u8,
) -> Hierarchy {
    let n = centers.len();
    let is_land: Vec<bool> = biomes.iter().map(|b| !b.is_water()).collect();
    let comps = pathfind::land_components(&is_land, neighbors);

    let mut continent_of = vec![NONE; n];
    let mut subcontinent_of = vec![NONE; n];
    let mut region_of = vec![NONE; n];
    let mut continents: Vec<Continent> = Vec::new();
    let mut subcontinents: Vec<Subcontinent> = Vec::new();
    let mut regions: Vec<Region> = Vec::new();

    let k = usize::from(region_subdivision.clamp(1, 12));
    let plate_at = |c: u32| -> u32 { plate_of.get(c as usize).copied().unwrap_or(NONE) };

    for comp in &comps {
        // Sort ascending so seed_cell + grouping + seeds are deterministic
        // regardless of `land_components`' DFS pop order.
        let mut cells = comp.clone();
        cells.sort_unstable();

        let continent_id = continents.len() as u32;
        continents.push(Continent {
            id: continent_id,
            seed_cell: cells[0],
            name: String::new(),
        });
        for &c in &cells {
            continent_of[c as usize] = continent_id;
        }

        // L1 — distinct plate ids present in this continent, ascending.
        let mut plate_ids: Vec<u32> = cells.iter().map(|&c| plate_at(c)).collect();
        plate_ids.sort_unstable();
        plate_ids.dedup();

        for &pid in &plate_ids {
            // `cells` is ascending and `filter` preserves order ⇒ ascending.
            let sub_cells: Vec<u32> = cells.iter().copied().filter(|&c| plate_at(c) == pid).collect();
            let subcontinent_id = subcontinents.len() as u32;
            subcontinents.push(Subcontinent {
                id: subcontinent_id,
                continent: continent_id,
                plate: pid,
                seed_cell: sub_cells[0],
                name: String::new(),
            });
            for &c in &sub_cells {
                subcontinent_of[c as usize] = subcontinent_id;
            }

            // L2 — great-circle Voronoi over the subcontinent.
            let seeds = farthest_point_seeds(&sub_cells, centers, k);
            let region_base = regions.len() as u32;
            for (si, &seed_cell) in seeds.iter().enumerate() {
                regions.push(Region {
                    id: region_base + si as u32,
                    subcontinent: subcontinent_id,
                    seed_cell,
                    name: String::new(),
                });
            }
            for &c in &sub_cells {
                let cc = centers[c as usize];
                let mut best = 0usize;
                let mut best_dot = dot(cc, centers[seeds[0] as usize]);
                for (i, &seed_cell) in seeds.iter().enumerate().skip(1) {
                    let d = dot(cc, centers[seed_cell as usize]);
                    if d > best_dot {
                        best_dot = d;
                        best = i;
                    }
                }
                region_of[c as usize] = region_base + best as u32;
            }
        }
    }

    Hierarchy {
        continent_of,
        subcontinent_of,
        region_of,
        continents,
        subcontinents,
        regions,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A 4-cell line graph: 0–1 land, 2 water, 3 land. Two land components
    /// ({0,1} and {3}). Centres spread along x so farthest-point is meaningful.
    fn line_fixture() -> (Vec<[f32; 3]>, Vec<Vec<u32>>, Vec<BiomeKind>) {
        let centers = vec![
            [1.0, 0.0, 0.0],
            [0.7, 0.7, 0.0],
            [0.0, 1.0, 0.0],
            [-0.7, 0.7, 0.0],
        ];
        let neighbors = vec![vec![1u32], vec![0, 2], vec![1, 3], vec![2]];
        let biomes = vec![
            BiomeKind::Plain,
            BiomeKind::Plain,
            BiomeKind::Ocean,
            BiomeKind::Plain,
        ];
        (centers, neighbors, biomes)
    }

    #[test]
    fn water_cells_are_unassigned_land_cells_are_assigned() {
        let (centers, neighbors, biomes) = line_fixture();
        let h = build(&centers, &neighbors, &biomes, &[], 4);
        // Cell 2 is ocean.
        assert_eq!(h.continent_of[2], NONE);
        assert_eq!(h.subcontinent_of[2], NONE);
        assert_eq!(h.region_of[2], NONE);
        for c in [0usize, 1, 3] {
            assert_ne!(h.continent_of[c], NONE);
            assert_ne!(h.subcontinent_of[c], NONE);
            assert_ne!(h.region_of[c], NONE);
        }
    }

    #[test]
    fn two_land_components_yield_two_continents() {
        let (centers, neighbors, biomes) = line_fixture();
        let h = build(&centers, &neighbors, &biomes, &[], 4);
        assert_eq!(h.continents.len(), 2);
        // {0,1} is continent 0 (lowest start), {3} is continent 1.
        assert_eq!(h.continent_of[0], 0);
        assert_eq!(h.continent_of[1], 0);
        assert_eq!(h.continent_of[3], 1);
    }

    #[test]
    fn containment_holds_region_in_subcontinent_in_continent() {
        let (centers, neighbors, biomes) = line_fixture();
        // Give the two land cells of continent 0 different plate ids so it
        // splits into two subcontinents.
        let plate_of = vec![0u32, 1, 0, 2];
        let h = build(&centers, &neighbors, &biomes, &plate_of, 4);
        for c in [0usize, 1, 3] {
            let r = h.region_of[c] as usize;
            let s = h.subcontinent_of[c];
            assert_eq!(h.regions[r].subcontinent, s);
            let cont = h.continent_of[c];
            assert_eq!(h.subcontinents[s as usize].continent, cont);
        }
        // continent 0 spanned plates {0,1} ⇒ two subcontinents there + one for
        // continent 1 (plate 2) = 3 total.
        assert_eq!(h.subcontinents.len(), 3);
    }

    #[test]
    fn subcontinent_cells_share_one_plate() {
        let (centers, neighbors, biomes) = line_fixture();
        let plate_of = vec![0u32, 1, 0, 2];
        let h = build(&centers, &neighbors, &biomes, &plate_of, 4);
        for (cell, &sub) in h.subcontinent_of.iter().enumerate() {
            if sub == NONE {
                continue;
            }
            assert_eq!(plate_of[cell], h.subcontinents[sub as usize].plate);
        }
    }

    #[test]
    fn region_count_per_subcontinent_is_bounded_by_subdivision() {
        // A single 5-cell land blob, one plate, subdivision 3 ⇒ ≤3 regions.
        let centers = vec![
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.8, 0.2, 0.0],
            [0.7, 0.3, 0.0],
            [0.6, 0.4, 0.0],
        ];
        let neighbors = vec![vec![1], vec![0, 2], vec![1, 3], vec![2, 4], vec![3]];
        let biomes = vec![BiomeKind::Plain; 5];
        let h = build(&centers, &neighbors, &biomes, &[0, 0, 0, 0, 0], 3);
        assert_eq!(h.subcontinents.len(), 1);
        assert_eq!(h.regions.len(), 3);
        // Every land cell maps to one of the 3 regions.
        for c in 0..5 {
            assert!((h.region_of[c] as usize) < 3);
        }
    }

    #[test]
    fn is_deterministic() {
        let (centers, neighbors, biomes) = line_fixture();
        let plate_of = vec![0u32, 1, 0, 2];
        let a = build(&centers, &neighbors, &biomes, &plate_of, 4);
        let b = build(&centers, &neighbors, &biomes, &plate_of, 4);
        assert_eq!(a.continent_of, b.continent_of);
        assert_eq!(a.subcontinent_of, b.subcontinent_of);
        assert_eq!(a.region_of, b.region_of);
    }

    #[test]
    fn all_water_world_yields_empty_hierarchy() {
        // A degenerate all-ocean world: no land ⇒ no entities, every cell NONE,
        // and no panic (the `cells[0]` / `seeds[0]` indexing never runs).
        let centers = vec![[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]];
        let neighbors = vec![vec![1u32], vec![0]];
        let biomes = vec![BiomeKind::Ocean, BiomeKind::Lake];
        let h = build(&centers, &neighbors, &biomes, &[0, 0], 4);
        assert!(h.continents.is_empty());
        assert!(h.subcontinents.is_empty());
        assert!(h.regions.is_empty());
        assert_eq!(h.continent_of, vec![NONE, NONE]);
        assert_eq!(h.subcontinent_of, vec![NONE, NONE]);
        assert_eq!(h.region_of, vec![NONE, NONE]);
    }
}
