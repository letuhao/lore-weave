//! Civilization pipeline — chains System-A's mesh-agnostic builders
//! (feature::extract / political::build / hydrology::build /
//! settlement::build / routes::build / culture::build) over the
//! `mesh::CivView` adapter output.
//!
//! Every convenience function here projects to unit sphere internally
//! via `mesh::project_to_sphere` so the downstream metric
//! `1 - dot(c_a, c_b)` works correctly (HIGH-1 fix; see session 92
//! /review-impl).

use crate::creative_seed::SettlementDensity;
use crate::culture::{self, Culture};
use crate::feature::{self, Features};
use crate::flat_climate::WorldClimateParams;
use crate::flatworld::FlatWorld;
use crate::hydrology::{self, Hydrology};
use crate::political::{self, Political};
use crate::routes;
use crate::settlement;
use crate::world_map::{Route, Settlement};

use super::mesh::{
    augment_with_ocean, build_civ_view, elevation_to_u16, project_to_sphere, CivView,
};

/// **Civ Ship 2** — convenience pipeline: build a civ view, augment it
/// with synthetic ocean cells, then run [`feature::extract`] to get
/// named mountain ranges, rivers, and water bodies.
///
/// `ocean_target` is the number of ocean cells to synthesize. Default
/// world reads well with 40-80; tiny test worlds with 8-16. Pass `0`
/// to skip ocean augmentation.
///
/// **Projects to sphere** as the last step so the returned view's
/// centres are unit vectors (HIGH-1 fix). Returns `(view, features)`.
pub fn extract_features(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
) -> (CivView, Features) {
    let view = build_civ_view(world, climate_params);
    let mut view = if ocean_target > 0 {
        augment_with_ocean(view, world, ocean_target)
    } else {
        view
    };
    let features = feature::extract(&view.biomes, &view.neighbors);
    // **HIGH-1 fix**: project AFTER Delaunay (preserves topology) and
    // AFTER feature::extract (biomes/neighbors unchanged) so downstream
    // civilization builders get unit-vector centres for their
    // sphere-specific distance metric.
    project_to_sphere(&mut view, world);
    (view, features)
}

/// **Civ Ship 4** — run System-A's hydrology pipeline (priority-flood
/// receiver graph + flow accumulation → river flux) on the civ view.
/// Output's `river_flux` and `is_coast` override Ship 2's
/// adjacency-only `is_coast` since hydrology uses real drainage
/// connectivity.
pub fn build_hydrology_view(view: &CivView) -> Hydrology {
    let (elev_u16, sea_level_u16) = elevation_to_u16(view);
    hydrology::build(
        &view.centers,
        &elev_u16,
        sea_level_u16,
        &view.neighbors,
        &view.climate,
    )
}

/// **Civ Ship 3** — full pipeline through System-A's political builder.
/// Returns `(view, features, political)`.
pub fn build_political(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
) -> (CivView, Features, Political) {
    let (view, features) = extract_features(world, climate_params, ocean_target);
    let political = political::build(seed, &view.centers, &view.neighbors, &view.biomes);
    (view, features, political)
}

/// **Civ Ship 4** — full pipeline through System-A's settlement builder.
/// Chains build_political → build_hydrology_view → settlement::build.
/// Returns `(view, features, political, hydrology, settlements)`.
pub fn build_settlement(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
    density: SettlementDensity,
) -> (CivView, Features, Political, Hydrology, Vec<Settlement>) {
    let (mut view, features, political) =
        build_political(world, climate_params, ocean_target, seed);
    let hydro = build_hydrology_view(&view);
    view.river_flux = hydro.river_flux.clone();
    view.is_coast = hydro.is_coast.clone();
    let settlements = settlement::build(
        seed,
        &view.centers,
        &view.biomes,
        &view.climate,
        &view.river_flux,
        &view.is_coast,
        density,
        &political,
    );
    (view, features, political, hydro, settlements)
}

/// **Civ Ship 5** — full pipeline through System-A's routes builder.
/// Chains [`build_settlement`] then [`routes::build`] using the
/// `Hydrology.river_threshold` for river-route detection.
pub fn build_routes(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
    density: SettlementDensity,
) -> (
    CivView,
    Features,
    Political,
    Hydrology,
    Vec<Settlement>,
    Vec<Route>,
) {
    let (view, features, political, hydro, settlements) =
        build_settlement(world, climate_params, ocean_target, seed, density);
    let routes_v = routes::build(
        &view.centers,
        &view.neighbors,
        &view.biomes,
        &view.river_flux,
        hydro.river_threshold,
        &view.is_coast,
        &settlements,
    );
    (view, features, political, hydro, settlements, routes_v)
}

/// **Civ Ship 6** — full pipeline through System-A's culture builder.
/// `culture_count` clamped 1..=16 internally by System A. 5 is the
/// typical default.
#[allow(clippy::too_many_arguments)]
pub fn build_culture(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
    density: SettlementDensity,
    culture_count: u8,
) -> (
    CivView,
    Features,
    Political,
    Hydrology,
    Vec<Settlement>,
    Vec<Route>,
    Culture,
) {
    let (view, features, political, hydro, settlements, routes_v) =
        build_routes(world, climate_params, ocean_target, seed, density);
    let culture_v = culture::build(seed, &view.centers, &view.neighbors, &view.biomes, culture_count);
    (
        view,
        features,
        political,
        hydro,
        settlements,
        routes_v,
        culture_v,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::biome::BiomeKind;
    use crate::flatworld::{generate, FlatParams};

    fn small_world() -> crate::flatworld::FlatWorld {
        let p = FlatParams {
            width: 256,
            height: 192,
            plate_count: 4,
            seed: 7,
            ..Default::default()
        };
        generate(&p)
    }

    #[test]
    fn feature_extract_accepts_civ_view_without_panicking() {
        let world = small_world();
        let view = build_civ_view(&world, &WorldClimateParams::default());
        let features = feature::extract(&view.biomes, &view.neighbors);
        let _ = features.mountain_ranges.len()
            + features.rivers.len()
            + features.water_bodies.len();
    }

    #[test]
    fn extract_features_default_world_yields_water_and_mountains() {
        let world = generate(&FlatParams::default());
        let (_view, features) = extract_features(&world, &WorldClimateParams::default(), 64);
        assert!(
            !features.water_bodies.is_empty(),
            "default world should produce ≥1 water body after ocean synth"
        );
        assert!(
            !features.mountain_ranges.is_empty(),
            "default world should produce ≥1 mountain range from collision uplift"
        );
    }

    #[test]
    fn extract_features_with_zero_ocean_target_skips_augment() {
        let world = small_world();
        let view_ship1 = build_civ_view(&world, &WorldClimateParams::default());
        let (view_skip, _) = extract_features(&world, &WorldClimateParams::default(), 0);
        assert_eq!(view_skip.centers.len(), view_ship1.centers.len());
        assert_eq!(view_skip.biomes, view_ship1.biomes);
    }

    #[test]
    fn build_political_produces_provinces_and_states_on_default_world() {
        let world = generate(&FlatParams::default());
        let (_view, _features, political) =
            build_political(&world, &WorldClimateParams::default(), 64, 42);
        assert!(
            !political.provinces.is_empty(),
            "default world should produce ≥1 province"
        );
        assert!(
            !political.states.is_empty(),
            "default world should produce ≥1 state"
        );
    }

    #[test]
    fn build_political_assigns_every_land_cell_to_a_province() {
        let world = generate(&FlatParams::default());
        let (view, _features, political) =
            build_political(&world, &WorldClimateParams::default(), 64, 7);
        let none = u32::MAX;
        for (i, &biome) in view.biomes.iter().enumerate() {
            let p = political.province_of[i];
            if biome == BiomeKind::Ocean {
                assert_eq!(p, none, "ocean cell {i} got assigned province {p}");
            } else {
                assert_ne!(p, none, "land cell {i} (biome {biome:?}) has no province assignment");
            }
        }
    }

    #[test]
    fn build_political_is_deterministic_per_seed() {
        let world = generate(&FlatParams::default());
        let (_, _, a) = build_political(&world, &WorldClimateParams::default(), 32, 99);
        let (_, _, b) = build_political(&world, &WorldClimateParams::default(), 32, 99);
        assert_eq!(a.province_of, b.province_of);
        assert_eq!(a.provinces.len(), b.provinces.len());
        assert_eq!(a.states.len(), b.states.len());
    }

    #[test]
    fn build_settlement_produces_settlements_on_default_world() {
        let world = generate(&FlatParams::default());
        let (_, _, _, _, settlements) = build_settlement(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
        );
        assert!(
            settlements.len() >= 3,
            "expected ≥3 settlements on default world, got {}",
            settlements.len()
        );
    }

    #[test]
    fn settlements_only_land_cells_not_ocean() {
        let world = generate(&FlatParams::default());
        let (view, _, _, _, settlements) = build_settlement(
            &world,
            &WorldClimateParams::default(),
            64,
            7,
            SettlementDensity::Medium,
        );
        for s in &settlements {
            let cell = s.cell as usize;
            assert_ne!(
                view.biomes[cell],
                BiomeKind::Ocean,
                "settlement '{}' placed on Ocean cell {cell}",
                s.name
            );
        }
    }

    #[test]
    fn build_settlement_is_deterministic_per_seed() {
        let world = generate(&FlatParams::default());
        let (_, _, _, _, a) = build_settlement(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
        );
        let (_, _, _, _, b) = build_settlement(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
        );
        assert_eq!(a.len(), b.len());
        for (sa, sb) in a.iter().zip(b.iter()) {
            assert_eq!(sa.cell, sb.cell);
            assert_eq!(sa.role, sb.role);
        }
    }

    #[test]
    fn build_routes_produces_routes_on_default_world() {
        let world = generate(&FlatParams::default());
        let (_, _, _, _, _, routes_v) = build_routes(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
        );
        assert!(!routes_v.is_empty(), "default world should produce ≥1 route");
    }

    #[test]
    fn build_culture_produces_multiple_regions_on_default_world() {
        let world = generate(&FlatParams::default());
        let (_, _, _, _, _, _, culture_v) = build_culture(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
            5,
        );
        assert!(
            culture_v.culture_regions.len() >= 2,
            "default world should produce ≥2 culture regions, got {}",
            culture_v.culture_regions.len()
        );
    }

    #[test]
    fn build_culture_is_deterministic_per_seed() {
        let world = generate(&FlatParams::default());
        let (_, _, _, _, _, _, a) = build_culture(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
            5,
        );
        let (_, _, _, _, _, _, b) = build_culture(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
            5,
        );
        assert_eq!(a.culture_of, b.culture_of);
        assert_eq!(a.culture_regions.len(), b.culture_regions.len());
    }

    #[test]
    fn sphere_default_does_not_worsen_political_seed_spread_vs_flat() {
        // **review-impl HIGH-1 regression**: pin direction of fix.
        use super::super::render::cell_index_to_center;
        let world = generate(&FlatParams::default());
        let climate = WorldClimateParams::default();

        let flat_view = augment_with_ocean(
            build_civ_view(&world, &climate),
            &world,
            64,
        );
        let flat_pol = crate::political::build(
            42,
            &flat_view.centers,
            &flat_view.neighbors,
            &flat_view.biomes,
        );

        let (_, _, sphere_pol) = build_political(&world, &climate, 64, 42);

        if flat_pol.provinces.len() < 2 || sphere_pol.provinces.len() < 2 {
            return;
        }

        let capital_xy = |political: &crate::political::Political| {
            political
                .provinces
                .iter()
                .filter_map(|p| cell_index_to_center(&world, p.capital_cell as usize))
                .collect::<Vec<_>>()
        };
        let min_pairwise = |xy: &[(f32, f32)]| {
            let mut best = f32::INFINITY;
            for i in 0..xy.len() {
                for j in (i + 1)..xy.len() {
                    let dx = xy[i].0 - xy[j].0;
                    let dy = xy[i].1 - xy[j].1;
                    let d2 = dx * dx + dy * dy;
                    if d2 < best {
                        best = d2;
                    }
                }
            }
            best.sqrt()
        };

        let flat_min = min_pairwise(&capital_xy(&flat_pol));
        let sphere_min = min_pairwise(&capital_xy(&sphere_pol));

        assert!(
            sphere_min + 1e-3 >= flat_min,
            "sphere min-pairwise province seed distance ({sphere_min:.1} px) regressed below flat ({flat_min:.1} px)"
        );
    }
}
