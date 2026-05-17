//! Phase 4 — JSON round-trip stability + hash verification.

use world_gen::{
    ClimateZone, CoastlineProfile, CreativeSeed, HemisphereOrientation, SettlementDensity,
    WorldArchetype, WorldMap, WorldScale, generate,
};

/// `generate → to_string_pretty → from_str` is identity, and the loaded map
/// verifies its own hash (recompute-after-load, not just struct equality).
#[test]
fn worldmap_json_round_trip_is_identity() {
    let cases = [
        (1u64, WorldScale::Pocket),
        (42, WorldScale::Region),
        (0x00C0_FFEE, WorldScale::Continent),
        (2_026_051_700, WorldScale::Continent), // heavy hydrology — river_flux finiteness
    ];
    for (seed, scale) in cases {
        let cs = CreativeSeed {
            world_scale: scale,
            ..CreativeSeed::default()
        };
        let map = generate(seed, &cs);
        let json = serde_json::to_string_pretty(&map).expect("serialize");
        let loaded: WorldMap = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(map, loaded, "seed {seed} {scale:?}: round-trip not identity");
        assert!(
            loaded.verify_hash(),
            "seed {seed} {scale:?}: loaded map fails verify_hash"
        );
    }
}

/// `CreativeSeed` round-trips through JSON, with `climate_bias` both `Some`
/// and `None`.
#[test]
fn creative_seed_json_round_trip() {
    for bias in [None, Some(ClimateZone::Arid)] {
        let cs = CreativeSeed {
            climate_bias: bias,
            ..CreativeSeed::default()
        };
        let json = serde_json::to_string(&cs).expect("serialize");
        let loaded: CreativeSeed = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(cs, loaded, "CreativeSeed round-trip (bias {bias:?})");
    }
}

/// Criterion #4 — a `CreativeSeed` loaded from a JSON `--config` file equals
/// the one the equivalent flags build (direct `Eq`), and `generate()` on each
/// yields an identical `content_hash`.
#[test]
fn config_loaded_creative_seed_matches_flag_built() {
    // what the `generate` flags would construct.
    let flag_built = CreativeSeed {
        world_scale: WorldScale::Region,
        world_archetype: WorldArchetype::Wuxia,
        coastline_profile: CoastlineProfile::Island,
        hemisphere_orientation: HemisphereOrientation::Southern,
        climate_bias: Some(ClimateZone::Highland),
        settlement_density: SettlementDensity::Sparse,
        culture_count: 7,
    };
    // the `--config` load path: serialize to a JSON file's contents, reload.
    let json = serde_json::to_string_pretty(&flag_built).expect("serialize");
    let config_loaded: CreativeSeed = serde_json::from_str(&json).expect("deserialize");
    assert_eq!(
        flag_built, config_loaded,
        "config-loaded CreativeSeed must equal the flag-built one"
    );
    assert_eq!(
        generate(123, &flag_built).content_hash,
        generate(123, &config_loaded).content_hash,
        "config and flag paths must generate an identical map"
    );
}

/// A hand-edited `WorldMap` JSON (one field changed, `content_hash` left
/// stale) is caught by `verify_hash` — the load-bearing point of the hash.
#[test]
fn hand_edited_map_fails_hash_verification() {
    let map = generate(5, &CreativeSeed::default());
    assert!(map.verify_hash(), "fresh map should verify");

    let mut json: serde_json::Value = serde_json::to_value(&map).expect("to_value");
    // corrupt one cell's elevation; content_hash is NOT updated.
    json["cells"][0]["elevation"] = serde_json::json!(12_345);
    let tampered: WorldMap = serde_json::from_value(json).expect("from_value");
    assert!(
        !tampered.verify_hash(),
        "a tampered map must fail verify_hash"
    );
}
