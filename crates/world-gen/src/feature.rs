//! Stage 9 — geographic feature extraction.
//!
//! Clusters the per-cell biome field into discrete, name-able entities:
//! mountain ranges, rivers, and water bodies (seas + lakes). Deterministic —
//! index-ordered flood-fills over the neighbour graph, the same pattern as
//! `terrain`'s land-component detection. `generate` runs this; the entities'
//! `name` fields stay empty until `crate::naming` fills them.

use crate::biome::BiomeKind;
use crate::world_map::{MountainRange, River, WaterBody, WaterBodyKind};

/// The extracted geographic features.
pub struct Features {
    pub mountain_ranges: Vec<MountainRange>,
    pub rivers: Vec<River>,
    pub water_bodies: Vec<WaterBody>,
}

/// Extract the name-able geographic features from the biome field.
pub fn extract(biome: &[BiomeKind], neighbors: &[Vec<u32>]) -> Features {
    let mountain_ranges = components(biome, neighbors, BiomeKind::Mountain)
        .into_iter()
        .enumerate()
        .map(|(id, cells)| MountainRange {
            id: id as u32,
            cells,
            name: String::new(),
        })
        .collect();
    let rivers = components(biome, neighbors, BiomeKind::River)
        .into_iter()
        .enumerate()
        .map(|(id, cells)| River {
            id: id as u32,
            cells,
            name: String::new(),
        })
        .collect();
    // Seas and lakes share one id space — seas first, then lakes.
    let mut water_bodies: Vec<WaterBody> = Vec::new();
    for cells in components(biome, neighbors, BiomeKind::Ocean) {
        water_bodies.push(WaterBody {
            id: water_bodies.len() as u32,
            kind: WaterBodyKind::Sea,
            cells,
            name: String::new(),
        });
    }
    for cells in components(biome, neighbors, BiomeKind::Lake) {
        water_bodies.push(WaterBody {
            id: water_bodies.len() as u32,
            kind: WaterBodyKind::Lake,
            cells,
            name: String::new(),
        });
    }
    Features {
        mountain_ranges,
        rivers,
        water_bodies,
    }
}

/// Connected components of cells whose biome equals `kind`. Deterministic:
/// ascending start-cell sweep, DFS over the (sorted) neighbour lists.
fn components(biome: &[BiomeKind], neighbors: &[Vec<u32>], kind: BiomeKind) -> Vec<Vec<u32>> {
    let n = biome.len();
    let mut seen = vec![false; n];
    let mut comps: Vec<Vec<u32>> = Vec::new();
    for start in 0..n {
        if seen[start] || biome[start] != kind {
            continue;
        }
        let mut comp: Vec<u32> = Vec::new();
        let mut stack = vec![start];
        seen[start] = true;
        while let Some(c) = stack.pop() {
            comp.push(c as u32);
            for &nb in &neighbors[c] {
                let nb = nb as usize;
                if !seen[nb] && biome[nb] == kind {
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

    /// A line graph: cell `i` neighbours `i-1` and `i+1`.
    fn line_neighbors(n: usize) -> Vec<Vec<u32>> {
        (0..n)
            .map(|i| {
                let mut v = Vec::new();
                if i > 0 {
                    v.push((i - 1) as u32);
                }
                if i + 1 < n {
                    v.push((i + 1) as u32);
                }
                v
            })
            .collect()
    }

    #[test]
    fn a_gap_splits_a_component() {
        use BiomeKind::{Mountain, Plain};
        // [Mtn, Mtn, Plain, Mtn] → two ranges: {0,1} and {3}.
        let biome = vec![Mountain, Mountain, Plain, Mountain];
        let f = extract(&biome, &line_neighbors(4));
        assert_eq!(f.mountain_ranges.len(), 2, "a Plain gap must split the range");
        let mut sizes: Vec<usize> = f.mountain_ranges.iter().map(|r| r.cells.len()).collect();
        sizes.sort_unstable();
        assert_eq!(sizes, vec![1, 2]);
    }

    #[test]
    fn extract_partitions_each_biome_and_numbers_ids_contiguously() {
        use BiomeKind::{Lake, Mountain, Ocean, River};
        let biome = vec![Ocean, Ocean, River, River, Mountain, Lake];
        let f = extract(&biome, &line_neighbors(6));
        // every matching cell lands in exactly one entity.
        let mtn: usize = f.mountain_ranges.iter().map(|r| r.cells.len()).sum();
        let riv: usize = f.rivers.iter().map(|r| r.cells.len()).sum();
        let wat: usize = f.water_bodies.iter().map(|w| w.cells.len()).sum();
        assert_eq!(mtn, 1);
        assert_eq!(riv, 2);
        assert_eq!(wat, 3, "2 ocean + 1 lake cell");
        // ids are 0..len within each list.
        for (i, r) in f.mountain_ranges.iter().enumerate() {
            assert_eq!(r.id, i as u32);
        }
        for (i, w) in f.water_bodies.iter().enumerate() {
            assert_eq!(w.id, i as u32);
        }
        // seas are numbered before lakes.
        assert_eq!(f.water_bodies[0].kind, WaterBodyKind::Sea);
        assert_eq!(f.water_bodies[1].kind, WaterBodyKind::Lake);
    }

    #[test]
    fn extract_is_deterministic() {
        use BiomeKind::{Lake, Mountain, Ocean, River};
        let biome = vec![Mountain, River, Ocean, Mountain, Lake, River];
        let nb = line_neighbors(6);
        let a = extract(&biome, &nb);
        let b = extract(&biome, &nb);
        assert_eq!(a.mountain_ranges, b.mountain_ranges);
        assert_eq!(a.rivers, b.rivers);
        assert_eq!(a.water_bodies, b.water_bodies);
    }
}
