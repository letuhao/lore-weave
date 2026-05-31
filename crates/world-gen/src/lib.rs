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
pub mod civ_adapter;
pub mod climate;
pub mod creative_seed;
pub mod culture;
pub mod erosion;
pub mod feature;
pub mod flat_climate;
pub mod flatworld;
pub mod hierarchy;
pub mod hydrology;
pub mod mesh;
pub mod naming;
pub mod noise;
pub mod pathfind;
pub mod plates;
pub mod political;
pub mod projection;
pub mod relief;
pub mod render;
pub mod rng;
pub mod routes;
pub mod settlement;
pub mod shape;
pub mod terrain;
pub mod world_map;
pub mod zonegen;

pub use biome::BiomeKind;
pub use climate::ClimateZone;
pub use projection::Projection;
pub use relief::RenderStyle;
pub use creative_seed::{
    CoastlineProfile, CreativeSeed, ErosionStrength, HemisphereOrientation, PrevailingWind,
    SettlementDensity, TerrainMode, WorldArchetype, WorldScale,
};
pub use world_map::{
    BoundaryKind, Cell, Continent, County, CultureRegion, MountainRange, Plate, PlateBoundary,
    PlateKind, Province, Realm, Region, River, Route, RouteKind, Settlement, SettlementRole, State,
    Subcontinent, WaterBody, WaterBodyKind, World, WorldMap,
};

/// Generate a world map from a `u64` seed + creative direction.
///
/// Pure and deterministic — identical inputs yield a byte-identical map.
pub fn generate(seed: u64, cs: &CreativeSeed) -> WorldMap {
    // Stage 1 — spherical Voronoi mesh on the unit sphere (Phase 1 world-tier
    // redesign, 2026-05-20).
    let mesh = mesh::build(seed, cs.world_scale);

    // **Phase 1 Stage B (2026-05-20):** the (u, v) adapter scaffold is gone;
    // every consumer takes the 3D mesh centres directly.

    // Stage 2 — heightmap (Tectonic plate model or legacy Profile, per
    // `cs.terrain_mode`; 3D Perlin texture, antimeridian-seamless).
    let terrain = terrain::build(seed, cs, &mesh.centers, &mesh.neighbors);

    // Stage 3 — climate (latitude from 3D centre; tangent-projected wind).
    let climate = climate::build(
        &mesh.centers,
        &terrain.elevation,
        terrain.sea_level,
        &mesh.neighbors,
        cs.hemisphere_orientation,
        cs.prevailing_wind,
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

    // Plate layer (Phase 2) — present in Tectonic mode, empty in Profile mode.
    // Computed before the hierarchy because L1 subcontinents reuse `plate_of`.
    let n_cells = mesh.centers.len();
    let (plate_of, plates, plate_boundaries) = match terrain.plates {
        Some(p) => (p.plate_of, p.plates, p.boundaries),
        None => (vec![u32::MAX; n_cells], Vec::new(), Vec::new()),
    };

    // Stage 9 — geometric region hierarchy (continents → subcontinents →
    // regions; C3 arc, C-1a). Reuses the land-connectivity mask + the plate
    // layer; only the L2 region Voronoi is new geometry.
    let region_tree = hierarchy::build(
        &mesh.centers,
        &mesh.neighbors,
        &biome,
        &plate_of,
        cs.region_subdivision,
    );

    // Stage 5–8 — political (5-tier strict-nested INSIDE the hierarchy, C-2:
    // province⊆region, state⊆subcontinent, realm⊆continent, county⊆province),
    // settlement, route, culture (great-circle distances on the sphere).
    let nested = political::build_nested(
        &mesh.centers,
        &mesh.neighbors,
        &biome,
        &region_tree.region_of,
        &region_tree.subcontinent_of,
        &region_tree.continent_of,
        region_tree.regions.len(),
        region_tree.subcontinents.len(),
        region_tree.continents.len(),
        cs.county_subdivision,
    );
    let county_of = nested.county_of;
    let counties = nested.counties;
    let realms = nested.realms;
    let world = nested.world;
    // `settlement` consumes a `Political`; the 5-tier builder's province/state
    // data fills it (the extra county/realm/world tiers ride alongside).
    let political = political::Political {
        province_of: nested.province_of,
        provinces: nested.provinces,
        states: nested.states,
    };
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

    // Stage 9b — geographic feature extraction (deterministic; names added
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
        plate_of,
        plates,
        plate_boundaries,
        continent_of: region_tree.continent_of,
        subcontinent_of: region_tree.subcontinent_of,
        region_of: region_tree.region_of,
        continents: region_tree.continents,
        subcontinents: region_tree.subcontinents,
        regions: region_tree.regions,
        county_of,
        counties,
        realms,
        world,
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

    #[test]
    fn region_hierarchy_partitions_land_coherently() {
        let map = generate(7, &CreativeSeed::default());
        let n = map.cell_count();
        assert_eq!(map.continent_of.len(), n);
        assert_eq!(map.subcontinent_of.len(), n);
        assert_eq!(map.region_of.len(), n);
        assert!(!map.continents.is_empty(), "land ⇒ ≥1 continent");
        assert!(!map.subcontinents.is_empty());
        assert!(!map.regions.is_empty());

        const NONE: u32 = u32::MAX;
        for c in 0..n {
            if map.biome[c].is_water() {
                // Water cells are unassigned at every level.
                assert_eq!(map.continent_of[c], NONE);
                assert_eq!(map.subcontinent_of[c], NONE);
                assert_eq!(map.region_of[c], NONE);
                continue;
            }
            // No orphan land cell.
            assert_ne!(map.continent_of[c], NONE, "land cell {c} has no continent");
            assert_ne!(map.subcontinent_of[c], NONE);
            assert_ne!(map.region_of[c], NONE);
            // Containment: region ⊆ subcontinent ⊆ continent.
            let r = map.region_of[c] as usize;
            let s = map.subcontinent_of[c];
            assert_eq!(map.regions[r].subcontinent, s);
            assert_eq!(map.subcontinents[s as usize].continent, map.continent_of[c]);
            // A subcontinent is exactly one plate's slice of a continent.
            assert_eq!(map.plate_of[c], map.subcontinents[s as usize].plate);
        }
        // Every level nests in the one above (counts are monotone non-decreasing
        // because each parent yields ≥1 child).
        assert!(map.subcontinents.len() >= map.continents.len());
        assert!(map.regions.len() >= map.subcontinents.len());
        for sc in &map.subcontinents {
            assert!((sc.continent as usize) < map.continents.len());
        }
        for r in &map.regions {
            assert!((r.subcontinent as usize) < map.subcontinents.len());
        }
    }

    #[test]
    fn region_hierarchy_handles_profile_mode_without_plates() {
        // `Profile` mode has no plate layer (`plate_of` is all `u32::MAX`), so
        // every continent collapses to a single subcontinent with the sentinel
        // plate — the L1 fallback path the Tectonic default never exercises.
        let cs = CreativeSeed {
            terrain_mode: TerrainMode::Profile,
            ..CreativeSeed::default()
        };
        let map = generate(7, &cs);
        const NONE: u32 = u32::MAX;
        assert!(!map.continents.is_empty(), "a Profile world still has land");
        assert_eq!(
            map.subcontinents.len(),
            map.continents.len(),
            "Profile mode: exactly one subcontinent per continent"
        );
        for sc in &map.subcontinents {
            assert_eq!(sc.plate, NONE, "Profile mode: subcontinent plate is the sentinel");
        }
        // The partition invariants still hold without a plate layer.
        for c in 0..map.cell_count() {
            if map.biome[c].is_water() {
                assert_eq!(map.continent_of[c], NONE);
                continue;
            }
            assert_ne!(map.region_of[c], NONE, "land cell {c} unassigned in Profile mode");
            let r = map.region_of[c] as usize;
            let s = map.subcontinent_of[c];
            assert_eq!(map.regions[r].subcontinent, s);
            assert_eq!(map.subcontinents[s as usize].continent, map.continent_of[c]);
        }
    }

    /// Assert the C-2 strict-nesting invariants on a generated map: province ⊆
    /// region, county ⊆ province, state ⊆ subcontinent, realm ⊆ continent, plus
    /// no-orphan, valid parent links, non-empty tiers, and monotone counts.
    fn assert_political_nesting(map: &WorldMap) {
        const NONE: u32 = u32::MAX;
        assert!(!map.provinces.is_empty() && !map.states.is_empty());
        assert!(!map.counties.is_empty() && !map.realms.is_empty());
        for c in 0..map.cell_count() {
            if map.biome[c].is_water() {
                assert_eq!(map.province_of[c], NONE);
                assert_eq!(map.county_of[c], NONE);
                continue;
            }
            assert_ne!(map.province_of[c], NONE, "land cell {c} has no province");
            assert_ne!(map.county_of[c], NONE, "land cell {c} has no county");
            let prov = &map.provinces[map.province_of[c] as usize];
            assert_eq!(prov.region, map.region_of[c], "province ⊄ region at cell {c}");
            assert_eq!(
                map.counties[map.county_of[c] as usize].province,
                map.province_of[c],
                "county ⊄ province at cell {c}"
            );
            let state = &map.states[prov.state as usize];
            assert_eq!(
                state.subcontinent, map.subcontinent_of[c],
                "state ⊄ subcontinent at cell {c}"
            );
            assert_eq!(
                map.realms[state.realm as usize].continent,
                map.continent_of[c],
                "realm ⊄ continent at cell {c}"
            );
        }
        // Parent links valid + counts monotone (each parent yields ≥1 child).
        for ct in &map.counties {
            assert!((ct.province as usize) < map.provinces.len());
        }
        for p in &map.provinces {
            assert!((p.state as usize) < map.states.len());
        }
        for s in &map.states {
            assert!((s.realm as usize) < map.realms.len());
        }
        assert!(map.counties.len() >= map.provinces.len());
        assert!(map.provinces.len() >= map.states.len());
        assert!(map.states.len() >= map.realms.len());

        // No dangling entity: every county/state/realm owns ≥1 cell / ≥1 child.
        let mut province_has_county = vec![false; map.provinces.len()];
        for ct in &map.counties {
            province_has_county[ct.province as usize] = true;
        }
        assert!(province_has_county.iter().all(|&b| b), "a province has no county");
        let mut subcontinents_used = std::collections::BTreeSet::new();
        for s in &map.states {
            subcontinents_used.insert(s.subcontinent);
        }
        assert!(!subcontinents_used.is_empty());
    }

    #[test]
    fn political_tiers_nest_strictly_in_geometric_hierarchy() {
        // C-2: province ⊆ region, county ⊆ province, state ⊆ subcontinent,
        // realm ⊆ continent — verified per land cell against the C-1a frame.
        assert_political_nesting(&generate(7, &CreativeSeed::default()));
    }

    #[test]
    fn political_tiers_nest_in_profile_mode() {
        // Profile mode (no plates ⇒ one subcontinent per continent) is a
        // distinct geometric shape the Tectonic default never exercises; the
        // strict-nesting invariants must still hold through `build_nested`.
        let cs = CreativeSeed {
            terrain_mode: TerrainMode::Profile,
            ..CreativeSeed::default()
        };
        assert_political_nesting(&generate(11, &cs));
    }

    /// Count connected components of land cells (`elevation >= sea_level`).
    fn land_component_count(map: &WorldMap) -> usize {
        let n = map.cell_count();
        let mut seen = vec![false; n];
        let mut comps = 0;
        for start in 0..n {
            if seen[start] || !map.is_land(start) {
                continue;
            }
            comps += 1;
            let mut stack = vec![start];
            seen[start] = true;
            while let Some(c) = stack.pop() {
                for &nb in &map.neighbors[c] {
                    let nb = nb as usize;
                    if !seen[nb] && map.is_land(nb) {
                        seen[nb] = true;
                        stack.push(nb);
                    }
                }
            }
        }
        comps
    }

    #[test]
    fn tectonic_mode_produces_multiple_continents() {
        // The whole point of Phase 2: the default (Tectonic) world is a planet
        // with several landmasses. A single supercontinent (Pangaea) is a
        // *valid* tectonic outcome for some seeds, so we assert the
        // capability across a sweep — most seeds multi-continent + at least
        // one clearly so — rather than ≥2 for every seed.
        let cs = CreativeSeed {
            world_scale: WorldScale::Continent,
            ..CreativeSeed::default()
        };
        let counts: Vec<usize> = [1u64, 7, 31, 101, 2026, 77]
            .iter()
            .map(|&s| {
                let map = generate(s, &cs);
                assert_eq!(map.plate_of.len(), map.cell_count());
                assert!(!map.plates.is_empty(), "tectonic map must expose plates");
                land_component_count(&map)
            })
            .collect();
        let multi = counts.iter().filter(|&&c| c >= 2).count();
        assert!(
            counts.iter().any(|&c| c >= 3),
            "tectonic never produced ≥3 continents across seeds: {counts:?}"
        );
        assert!(
            multi >= 4,
            "only {multi}/6 tectonic seeds were multi-continent: {counts:?}"
        );
    }

    #[test]
    fn tectonic_map_has_both_land_and_ocean() {
        let cs = CreativeSeed {
            world_scale: WorldScale::SuperContinent,
            ..CreativeSeed::default()
        };
        let map = generate(7, &cs);
        let land = (0..map.cell_count()).filter(|&c| map.is_land(c)).count();
        assert!(land > 0, "tectonic map has no land");
        assert!(land < map.cell_count(), "tectonic map has no ocean");
    }

    #[test]
    fn profile_mode_still_single_continent_and_no_plates() {
        // Legacy Profile mode keeps `enforce_coherence` → exactly one land
        // component, and exposes no plate layer.
        let cs = CreativeSeed {
            terrain_mode: crate::TerrainMode::Profile,
            coastline_profile: crate::CoastlineProfile::Coastal,
            world_scale: WorldScale::Continent,
            ..CreativeSeed::default()
        };
        let map = generate(7, &cs);
        assert_eq!(land_component_count(&map), 1, "Profile mode must be one continent");
        assert!(map.plates.is_empty(), "Profile mode must expose no plates");
        assert!(map.plate_boundaries.is_empty());
        assert!(map.plate_of.iter().all(|&p| p == u32::MAX));
        assert!(map.verify_hash());
    }

    #[test]
    fn tectonic_is_deterministic() {
        let cs = CreativeSeed::default();
        let a = generate(99, &cs);
        let b = generate(99, &cs);
        assert_eq!(a.content_hash, b.content_hash);
        assert_eq!(a, b);
    }
}
