//! Civilization bundle — Serialize/Deserialize-able snapshot of every
//! civ-layer output plus a blake3 content_hash for JSON round-trip
//! verification.

use serde::{Deserialize, Serialize};

use crate::biome::BiomeKind;
use crate::climate::ClimateZone;
use crate::creative_seed::SettlementDensity;
use crate::flat_climate::WorldClimateParams;
use crate::flatworld::FlatWorld;
use crate::world_map::{CultureRegion, MountainRange, Province, River, Route, Settlement, State, WaterBody};

use super::naming::apply_synthetic_names;
use super::pipeline::build_culture;

/// **Civ Ship 9** — flat Serialize-able bundle of every civ-layer
/// output. Use [`bundle_civ`] to build; [`compute_civ_hash`] +
/// [`verify_civ_hash`] for round-trip verification.
///
/// Embedded types come from `world_map.rs` (already Serialize). Fields
/// from Political / Hydrology / Culture are unrolled to their component
/// vectors so we don't have to add Serialize derives to System-A's
/// stage-output structs (which would ripple through `lib.rs::generate`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CivBundle {
    pub centers: Vec<[f32; 3]>,
    pub neighbors: Vec<Vec<u32>>,
    pub biomes: Vec<BiomeKind>,
    pub climate: Vec<ClimateZone>,
    pub river_flux: Vec<f32>,
    pub is_coast: Vec<bool>,
    pub elevation: Vec<f32>,
    pub sea_level: f32,

    // From Political (unrolled).
    pub province_of: Vec<u32>,
    pub provinces: Vec<Province>,
    pub states: Vec<State>,

    pub settlements: Vec<Settlement>,
    pub routes: Vec<Route>,

    // From Culture (unrolled).
    pub culture_of: Vec<u32>,
    pub culture_regions: Vec<CultureRegion>,

    // From Features (unrolled).
    pub mountain_ranges: Vec<MountainRange>,
    pub rivers: Vec<River>,
    pub water_bodies: Vec<WaterBody>,

    /// Blake3 digest over every other field. Cross-check via
    /// [`verify_civ_hash`] after JSON round-trip.
    pub content_hash: [u8; 32],
}

/// **Civ Ship 9** — run the full civ pipeline (build_culture +
/// apply_synthetic_names) and pack the output into a [`CivBundle`]
/// with a fresh [`compute_civ_hash`].
#[allow(clippy::too_many_arguments)]
pub fn bundle_civ(
    world: &FlatWorld,
    climate_params: &WorldClimateParams,
    ocean_target: usize,
    seed: u64,
    density: SettlementDensity,
    culture_count: u8,
) -> CivBundle {
    let (view, mut features, mut political, _hydro, mut settlements, routes_v, mut culture_v) =
        build_culture(world, climate_params, ocean_target, seed, density, culture_count);
    apply_synthetic_names(
        &mut features,
        &mut political,
        &mut settlements,
        &mut culture_v,
        seed,
    );
    let mut bundle = CivBundle {
        centers: view.centers,
        neighbors: view.neighbors,
        biomes: view.biomes,
        climate: view.climate,
        river_flux: view.river_flux,
        is_coast: view.is_coast,
        elevation: view.elevation,
        sea_level: view.sea_level,
        province_of: political.province_of,
        provinces: political.provinces,
        states: political.states,
        settlements,
        routes: routes_v,
        culture_of: culture_v.culture_of,
        culture_regions: culture_v.culture_regions,
        mountain_ranges: features.mountain_ranges,
        rivers: features.rivers,
        water_bodies: features.water_bodies,
        content_hash: [0u8; 32],
    };
    bundle.content_hash = compute_civ_hash(&bundle);
    bundle
}

/// Blake3 digest of every CivBundle field EXCEPT `content_hash` itself.
///
/// Implementation: clone the bundle with `content_hash = [0; 32]`,
/// serialize to JSON, hash the bytes. `serde_json` output is stable
/// for a given struct definition, the encoding is already a dependency,
/// and the round-trip test asserts the only property that matters —
/// deserialize-then-rehash equals the original hash. Switch to
/// `bincode` if hash becomes a hot path.
pub fn compute_civ_hash(bundle: &CivBundle) -> [u8; 32] {
    let mut hasher = blake3::Hasher::new();
    let mut clone = bundle.clone();
    clone.content_hash = [0u8; 32];
    let bytes = serde_json::to_vec(&clone)
        .expect("CivBundle is composed of Serialize types; encoding cannot fail");
    hasher.update(&bytes);
    *hasher.finalize().as_bytes()
}

/// Recompute the hash and compare to the bundled `content_hash`.
pub fn verify_civ_hash(bundle: &CivBundle) -> bool {
    compute_civ_hash(bundle) == bundle.content_hash
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flatworld::{generate, FlatParams};

    #[test]
    fn civ_bundle_json_round_trip_preserves_content_hash() {
        let world = generate(&FlatParams::default());
        let bundle = bundle_civ(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
            5,
        );
        assert!(verify_civ_hash(&bundle), "fresh bundle should verify");
        let json = serde_json::to_string(&bundle).expect("serialize");
        let parsed: CivBundle = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(
            parsed.content_hash, bundle.content_hash,
            "round-trip content_hash should be identical"
        );
        assert!(verify_civ_hash(&parsed));
        assert_eq!(parsed, bundle, "round-trip bundle equality");
    }

    #[test]
    fn civ_bundle_hash_is_deterministic_per_seed() {
        let world = generate(&FlatParams::default());
        let a = bundle_civ(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
            5,
        );
        let b = bundle_civ(
            &world,
            &WorldClimateParams::default(),
            32,
            99,
            SettlementDensity::Medium,
            5,
        );
        assert_eq!(a.content_hash, b.content_hash);
    }

    #[test]
    fn civ_bundle_hash_differs_across_seeds() {
        let world = generate(&FlatParams::default());
        let a = bundle_civ(
            &world,
            &WorldClimateParams::default(),
            32,
            7,
            SettlementDensity::Medium,
            5,
        );
        let b = bundle_civ(
            &world,
            &WorldClimateParams::default(),
            32,
            999,
            SettlementDensity::Medium,
            5,
        );
        assert_ne!(a.content_hash, b.content_hash);
    }

    #[test]
    fn bundle_civ_emits_sphere_centers_post_review_fix() {
        // **review-impl HIGH-1 regression**: direct evidence that the fix
        // is live — every bundle centre is a unit vector.
        let world = generate(&FlatParams::default());
        let bundle = bundle_civ(
            &world,
            &WorldClimateParams::default(),
            64,
            42,
            SettlementDensity::Medium,
            5,
        );
        for (i, c) in bundle.centers.iter().enumerate() {
            let mag2 = c[0] * c[0] + c[1] * c[1] + c[2] * c[2];
            assert!(
                (mag2 - 1.0).abs() < 1e-4,
                "bundle.centers[{i}] = {:?} has |c|² = {mag2}; expected unit vector",
                c
            );
        }
    }
}
