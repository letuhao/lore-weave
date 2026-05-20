//! `world_gen` — a standalone procedural world-map generator.
//!
//! [`generate`] is a **pure function**: the same `(seed, CreativeSeed)` always
//! produces a byte-identical [`WorldMap`] (same binary, same platform). That
//! regeneration-determinism is the load-bearing invariant — see
//! [`WorldMap::compute_hash`].
//!
//! Pipeline: P1 — Voronoi dual-mesh + heightmap; P2 — climate, rivers, water
//! network, biomes; P3 — provinces + states, settlements, routes, cultures.
//! P4 adds JSON (de)serialization, SVG export, and optional LLM authoring
//! ([`author`]).

pub mod author;
pub mod biome;
pub mod climate;
pub mod creative_seed;
pub mod culture;
pub mod erosion;
pub mod feature;
pub mod hydrology;
pub mod mesh;
pub mod naming;
pub mod noise;
pub mod pathfind;
pub mod political;
pub mod relief;
pub mod render;
pub mod rng;
pub mod routes;
pub mod settlement;
pub mod terrain;
pub mod world_map;

/// Equirectangular projection of a unit-sphere point to `(u, v) ∈ [0, 1]²` —
/// `u = (lon + π) / 2π`, `v = (π/2 − lat) / π`. Used by the B2 sphere-
/// migration scaffold ([`generate`]) and the equirectangular renderer.
pub(crate) fn project_uv(p: [f32; 3]) -> (f32, f32) {
    let lat = p[2].clamp(-1.0, 1.0).asin();
    let lon = p[1].atan2(p[0]);
    let u = (lon + std::f32::consts::PI) / std::f32::consts::TAU;
    let v = (std::f32::consts::FRAC_PI_2 - lat) / std::f32::consts::PI;
    (u, v)
}

pub use biome::BiomeKind;
pub use climate::ClimateZone;
pub use relief::RenderStyle;
pub use creative_seed::{
    CoastlineProfile, CreativeSeed, ErosionStrength, HemisphereOrientation, PrevailingWind,
    SettlementDensity, WorldArchetype, WorldScale,
};
pub use world_map::{
    Cell, CultureRegion, MountainRange, Province, River, Route, RouteKind, Settlement,
    SettlementRole, State, WaterBody, WaterBodyKind, WorldMap,
};

/// Generate a world map from a `u64` seed + creative direction.
///
/// Pure and deterministic — identical inputs yield a byte-identical map.
pub fn generate(seed: u64, cs: &CreativeSeed) -> WorldMap {
    // Stage 1 — spherical Voronoi mesh on the unit sphere (Phase 1 world-tier
    // redesign, 2026-05-20).
    let mesh = mesh::build(seed, cs.world_scale);

    // **Sphere migration scaffold (B2):** the per-cell (u, v) projection in
    // `[0, 1]²` of each cell centre via equirectangular — `u = (lon + π) /
    // 2π`, `v = (π/2 − lat) / π`. **`terrain` (B3) now uses native sphere
    // coords;** the remaining 2D consumers (`climate`, `hydrology`,
    // `political`, `settlement`, `routes`, `culture`) still take the legacy
    // (u, v) tuples and are migrated to 3D in B4 onward
    // (`docs/plans/2026-05-20-geo-spherical-topology.md`). The
    // **Cell.center stored on `WorldMap`** is the 3D unit vector — only the
    // *intermediate compute* still sees the 2D projection.
    let centers_2d: Vec<(f32, f32)> = mesh.centers.iter().map(|&p| project_uv(p)).collect();

    // Stage 2 — heightmap. **Native sphere** (B3 — 3D Perlin, seamless).
    let terrain = terrain::build(
        seed,
        cs.coastline_profile,
        cs.erosion,
        &mesh.centers,
        &mesh.neighbors,
    );

    // Stage 3 — climate.
    let climate = climate::build(
        &centers_2d,
        &terrain.elevation,
        terrain.sea_level,
        &mesh.neighbors,
        cs.hemisphere_orientation,
        cs.prevailing_wind,
        cs.climate_bias,
    );

    // Stage 4 — hydrology + biomes.
    let hydro = hydrology::build(
        &centers_2d,
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
    let political = political::build(seed, &centers_2d, &mesh.neighbors, &biome);
    let settlements = settlement::build(
        seed,
        &centers_2d,
        &biome,
        &climate,
        &hydro.river_flux,
        &hydro.is_coast,
        cs.settlement_density,
        &political,
    );
    let routes = routes::build(
        &centers_2d,
        &mesh.neighbors,
        &biome,
        &hydro.river_flux,
        hydro.river_threshold,
        &hydro.is_coast,
        &settlements,
    );
    let culture = culture::build(seed, &centers_2d, &mesh.neighbors, &biome, cs.culture_count);

    // Stage 9 — geographic feature extraction (deterministic; names added
    // later by the separate `naming` step).
    let features = feature::extract(&biome, &mesh.neighbors);

    // Build the `Cell` vector with the **3D** centres and polygons.
    let cells: Vec<Cell> = mesh
        .centers
        .iter()
        .zip(terrain.elevation.iter())
        .zip(mesh.polygons.iter())
        .map(|((&center, &elevation), polygon)| Cell {
            center,
            elevation,
            vertex_polygon: polygon.clone(),
        })
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
        mountain_ranges: features.mountain_ranges,
        rivers: features.rivers,
        water_bodies: features.water_bodies,
        content_hash: [0u8; 32],
    };
    // All f32 fields must be finite — non-finite values serialize as JSON
    // `null` and break the round-trip identity guarantee (Phase 4 §2).
    debug_assert!(
        map.cells.iter().all(|c| {
            c.center.iter().all(|x| x.is_finite())
                && c.vertex_polygon
                    .iter()
                    .all(|v| v.iter().all(|x| x.is_finite()))
        }) && map.river_flux.iter().all(|f| f.is_finite()),
        "non-finite f32 in WorldMap"
    );
    map.content_hash = map.compute_hash();
    map
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
    fn generated_map_verifies_its_own_hash() {
        let map = generate(7, &CreativeSeed::default());
        assert!(map.verify_hash(), "freshly generated map fails verify_hash");
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
        assert!(!map.water_bodies.is_empty(), "a map always has ocean");
    }
}
