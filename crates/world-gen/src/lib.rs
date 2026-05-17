//! `world_gen` — a standalone procedural world-map generator.
//!
//! [`generate`] is a **pure function**: the same `(seed, CreativeSeed)` always
//! produces a byte-identical [`WorldMap`] (same binary, same platform). That
//! regeneration-determinism is the load-bearing invariant — see
//! [`WorldMap::content_hash`].
//!
//! Pipeline: P1 — Voronoi dual-mesh + heightmap; P2 — climate, rivers, water
//! network, biomes; P3 — provinces + states, settlements, routes, cultures.

pub mod biome;
pub mod climate;
pub mod creative_seed;
pub mod culture;
pub mod hydrology;
pub mod mesh;
pub mod pathfind;
pub mod political;
pub mod render;
pub mod rng;
pub mod routes;
pub mod settlement;
pub mod terrain;
pub mod world_map;

pub use biome::BiomeKind;
pub use climate::ClimateZone;
pub use creative_seed::{
    CoastlineProfile, CreativeSeed, HemisphereOrientation, SettlementDensity, WorldArchetype,
    WorldScale,
};
pub use world_map::{
    Cell, CultureRegion, Province, Route, RouteKind, Settlement, SettlementRole, State, WorldMap,
};

/// Generate a world map from a `u64` seed + creative direction.
///
/// Pure and deterministic — identical inputs yield a byte-identical map.
pub fn generate(seed: u64, cs: &CreativeSeed) -> WorldMap {
    // Stage 1–2 — mesh + heightmap.
    let mesh = mesh::build(seed, cs.world_scale);
    let terrain = terrain::build(seed, cs.coastline_profile, &mesh.centers, &mesh.neighbors);

    // Stage 3 — climate.
    let climate = climate::build(
        &mesh.centers,
        &terrain.elevation,
        terrain.sea_level,
        &mesh.neighbors,
        cs.hemisphere_orientation,
        cs.climate_bias,
    );

    // Stage 4 — hydrology + biomes.
    let hydro = hydrology::build(
        &mesh.centers,
        &terrain.elevation,
        terrain.sea_level,
        &mesh.neighbors,
        &climate,
    );
    let biome = biome::build(
        &terrain.elevation,
        terrain.sea_level,
        &climate,
        &hydro.river_flux,
        hydro.river_threshold,
        &hydro.is_in_ocean,
        &hydro.is_coast,
    );

    // Stage 5–8 — political, settlement, route, culture.
    let political = political::build(seed, &mesh.centers, &mesh.neighbors, &biome);
    let settlements = settlement::build(
        seed,
        &mesh.centers,
        &biome,
        &climate,
        &hydro.river_flux,
        &hydro.is_coast,
        cs.settlement_density,
        &political,
    );
    let routes = routes::build(
        &mesh.centers,
        &mesh.neighbors,
        &biome,
        &hydro.river_flux,
        hydro.river_threshold,
        &hydro.is_coast,
        &settlements,
    );
    let culture = culture::build(seed, &mesh.centers, &mesh.neighbors, &biome, cs.culture_count);

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
        climate,
        biome,
        river_flux: hydro.river_flux,
        is_coast: hydro.is_coast,
        province_of: political.province_of,
        provinces: political.provinces,
        states: political.states,
        settlements,
        routes,
        culture_of: culture.culture_of,
        culture_regions: culture.culture_regions,
        content_hash: [0u8; 32],
    };
    map.content_hash = content_hash(&map);
    map
}

/// blake3 over a canonical fixed-order byte view of the map. f32 fields are
/// hashed by their IEEE-754 bit pattern (`to_le_bytes`).
///
/// MAINTENANCE: every `WorldMap` field must be fed in here. When `WorldMap`
/// grows, extend this function — otherwise the hash silently goes stale.
/// (`determinism.rs` also asserts full `PartialEq`, so determinism *detection*
/// is safe regardless, but keep the hash honest.)
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
        h.update(&(list.len() as u32).to_le_bytes());
        for &n in list {
            h.update(&n.to_le_bytes());
        }
    }
    for &z in &map.climate {
        h.update(&[z.tag()]);
    }
    for &b in &map.biome {
        h.update(&[b.tag()]);
    }
    for &f in &map.river_flux {
        h.update(&f.to_le_bytes());
    }
    for &coast in &map.is_coast {
        h.update(&[u8::from(coast)]);
    }
    for &p in &map.province_of {
        h.update(&p.to_le_bytes());
    }
    for p in &map.provinces {
        h.update(&p.id.to_le_bytes());
        h.update(&p.capital_cell.to_le_bytes());
        h.update(&p.state.to_le_bytes());
    }
    for s in &map.states {
        h.update(&s.id.to_le_bytes());
        h.update(&s.capital_province.to_le_bytes());
    }
    for s in &map.settlements {
        h.update(&s.cell.to_le_bytes());
        h.update(&[s.role.tag(), s.population_tier]);
    }
    for r in &map.routes {
        h.update(&[r.kind.tag()]);
        h.update(&r.from_cell.to_le_bytes());
        h.update(&r.to_cell.to_le_bytes());
        h.update(&r.distance.to_le_bytes());
    }
    for &c in &map.culture_of {
        h.update(&c.to_le_bytes());
    }
    for cr in &map.culture_regions {
        h.update(&cr.id.to_le_bytes());
        h.update(&cr.hearth_cell.to_le_bytes());
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

    #[test]
    fn all_layers_are_populated() {
        let map = generate(7, &CreativeSeed::default());
        let n = map.cell_count();
        assert_eq!(map.climate.len(), n);
        assert_eq!(map.biome.len(), n);
        assert_eq!(map.province_of.len(), n);
        assert_eq!(map.culture_of.len(), n);
        assert!(!map.provinces.is_empty());
        assert!(!map.states.is_empty());
        assert!(!map.settlements.is_empty());
        assert!(!map.culture_regions.is_empty());
    }
}
