//! `world_gen` — a standalone procedural world-map generator.
//!
//! [`generate`] is a **pure function**: the same `(seed, CreativeSeed)` always
//! produces a byte-identical [`WorldMap`] (same binary, same platform). That
//! regeneration-determinism is the load-bearing invariant — see
//! [`WorldMap::content_hash`].
//!
//! Phase 1 implements stages 1–2 of the GEO pipeline: the Voronoi dual-mesh
//! and the heightmap. Climate, biomes, rivers, political/settlement/route
//! layers arrive in later phases.

pub mod creative_seed;
pub mod mesh;
pub mod render;
pub mod rng;
pub mod terrain;
pub mod world_map;

pub use creative_seed::{CoastlineProfile, CreativeSeed, WorldArchetype, WorldScale};
pub use world_map::{Cell, WorldMap};

/// Generate a world map from a `u64` seed + creative direction.
///
/// Pure and deterministic — identical inputs yield a byte-identical map.
pub fn generate(seed: u64, cs: &CreativeSeed) -> WorldMap {
    let mesh = mesh::build(seed, cs.world_scale);
    let terrain = terrain::build(
        seed,
        cs.coastline_profile,
        &mesh.centers,
        &mesh.neighbors,
    );

    let cells: Vec<Cell> = mesh
        .centers
        .iter()
        .zip(terrain.elevation.iter())
        .map(|(&center, &elevation)| Cell { center, elevation })
        .collect();

    let mut map = WorldMap {
        seed,
        scale: cs.world_scale,
        cells,
        neighbors: mesh.neighbors,
        sea_level: terrain.sea_level,
        content_hash: [0u8; 32],
    };
    map.content_hash = content_hash(&map);
    map
}

/// blake3 over a canonical fixed-order byte view of the map. f32 fields are
/// hashed by their IEEE-754 bit pattern (`to_le_bytes`) to sidestep any
/// float-formatting ambiguity.
///
/// MAINTENANCE: every `WorldMap` field must be fed in here. When `WorldMap`
/// grows (Phase 2 climate/biome layers), extend this function — otherwise the
/// hash silently goes stale. (`determinism.rs` also asserts full `PartialEq`,
/// so determinism *detection* is safe regardless, but keep the hash honest.)
fn content_hash(map: &WorldMap) -> [u8; 32] {
    let mut h = blake3::Hasher::new();
    h.update(&map.seed.to_le_bytes());
    h.update(&[map.scale.tag()]);
    h.update(&map.sea_level.to_le_bytes());
    for c in &map.cells {
        h.update(&c.center.0.to_le_bytes());
        h.update(&c.center.1.to_le_bytes());
        h.update(&c.elevation.to_le_bytes());
    }
    for list in &map.neighbors {
        // list.len() is a small degree (<= ~12) ⇒ fits u32 trivially.
        h.update(&(list.len() as u32).to_le_bytes());
        for &n in list {
            h.update(&n.to_le_bytes());
        }
    }
    *h.finalize().as_bytes()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generate_is_deterministic() {
        let cs = CreativeSeed::default();
        let a = generate(2026, &cs);
        let b = generate(2026, &cs);
        assert_eq!(a.content_hash, b.content_hash);
        assert_eq!(a, b);
    }

    #[test]
    fn generated_cell_count_matches_scale() {
        for scale in [WorldScale::Pocket, WorldScale::Megaplanet] {
            let cs = CreativeSeed {
                world_scale: scale,
                ..CreativeSeed::default()
            };
            let map = generate(1, &cs);
            assert_eq!(map.cell_count(), scale.cell_count());
        }
    }
}
