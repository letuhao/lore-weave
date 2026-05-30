//! Phase 4 — JSON round-trip stability + hash verification.

use world_gen::{
    BiomeKind, ClimateZone, CoastlineProfile, CreativeSeed, ErosionStrength, HemisphereOrientation,
    PrevailingWind, SettlementDensity, WorldArchetype, WorldMap, WorldScale, generate,
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
        prevailing_wind: PrevailingWind::SouthEast,
        erosion: ErosionStrength::Heavy,
        climate_bias: Some(ClimateZone::Highland),
        settlement_density: SettlementDensity::Sparse,
        culture_count: 7,
        ..CreativeSeed::default()
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

/// review-impl C3 — every *deterministic* `WorldMap` field must feed
/// `compute_hash`. Tamper each field of a generated map and assert
/// `verify_hash` then fails; this pins field-list completeness. The `name`
/// fields are the deliberate exception (a non-deterministic LLM authoring
/// layer, `crate::naming`) — tampering a name must instead LEAVE `verify_hash`
/// true.
#[test]
fn compute_hash_covers_every_field() {
    let base = generate(31, &CreativeSeed::default());
    assert!(base.verify_hash(), "fresh map must verify");
    // the default Continent map populates every collection field.
    assert!(!base.cells.is_empty() && !base.neighbors.is_empty());
    assert!(!base.provinces.is_empty() && !base.states.is_empty());
    assert!(!base.settlements.is_empty() && !base.routes.is_empty());
    assert!(!base.culture_regions.is_empty());
    assert!(!base.water_bodies.is_empty(), "ocean ⇒ ≥1 water body");
    assert!(
        !base.mountain_ranges.is_empty() && !base.rivers.is_empty(),
        "the default Continent has mountains and rivers"
    );

    let tamper = |label: &str, mutate: &dyn Fn(&mut WorldMap)| {
        let mut m = base.clone();
        mutate(&mut m);
        assert!(
            !m.verify_hash(),
            "tampering `{label}` did not change content_hash — compute_hash omits it"
        );
    };

    tamper("seed", &|m| m.seed ^= 1);
    tamper("scale", &|m| {
        m.scale = if m.scale == WorldScale::Continent {
            WorldScale::Region
        } else {
            WorldScale::Continent
        };
    });
    tamper("cells.center", &|m| m.cells[0].center[0] += 1.0);
    tamper("cells.elevation", &|m| m.cells[0].elevation ^= 1);
    tamper("cells.vertex_polygon", &|m| {
        m.cells[0].vertex_polygon.push([0.5, 0.5, 0.5]);
    });
    tamper("neighbors", &|m| m.neighbors[0].push(0));
    tamper("sea_level", &|m| m.sea_level ^= 1);
    tamper("climate", &|m| {
        m.climate[0] = if m.climate[0] == ClimateZone::Arid {
            ClimateZone::Polar
        } else {
            ClimateZone::Arid
        };
    });
    tamper("biome", &|m| {
        m.biome[0] = if m.biome[0] == BiomeKind::Ocean {
            BiomeKind::Plain
        } else {
            BiomeKind::Ocean
        };
    });
    tamper("river_flux", &|m| m.river_flux[0] += 1.0);
    tamper("is_coast", &|m| m.is_coast[0] = !m.is_coast[0]);
    tamper("province_of", &|m| m.province_of[0] ^= 1);
    tamper("provinces", &|m| m.provinces[0].id ^= 1);
    tamper("states", &|m| m.states[0].id ^= 1);
    tamper("settlements", &|m| m.settlements[0].cell ^= 1);
    tamper("routes", &|m| m.routes[0].distance ^= 1);
    tamper("routes.path", &|m| m.routes[0].path.push(0));
    tamper("culture_of", &|m| m.culture_of[0] ^= 1);
    tamper("culture_regions", &|m| m.culture_regions[0].id ^= 1);
    // Tamper `cells` — the geometry-bearing field — not just `id`: a
    // regression dropping `cells` from `compute_hash` must be caught.
    tamper("mountain_ranges.cells", &|m| m.mountain_ranges[0].cells.push(0));
    tamper("rivers.cells", &|m| m.rivers[0].cells.push(0));
    tamper("water_bodies.cells", &|m| m.water_bodies[0].cells.push(0));
    // Phase 2 plate layer — the default (Tectonic) map populates all three.
    assert!(
        !base.plates.is_empty() && !base.plate_boundaries.is_empty(),
        "the default Tectonic map has plates + boundaries"
    );
    tamper("plate_of", &|m| m.plate_of[0] ^= 1);
    tamper("plates", &|m| m.plates[0].id ^= 1);
    tamper("plates.motion", &|m| m.plates[0].motion[0] += 1.0);
    tamper("plate_boundaries", &|m| {
        m.plate_boundaries[0].plate_a ^= 1;
    });

    // Geometric region hierarchy (C3 arc, C-1a). The default world has land ⇒
    // all three levels are populated.
    assert!(
        !base.continents.is_empty()
            && !base.subcontinents.is_empty()
            && !base.regions.is_empty(),
        "the default Continent world has a populated region hierarchy"
    );
    tamper("continent_of", &|m| m.continent_of[0] ^= 1);
    tamper("subcontinent_of", &|m| m.subcontinent_of[0] ^= 1);
    tamper("region_of", &|m| m.region_of[0] ^= 1);
    tamper("continents", &|m| m.continents[0].seed_cell ^= 1);
    tamper("subcontinents", &|m| m.subcontinents[0].plate ^= 1);
    tamper("regions", &|m| m.regions[0].seed_cell ^= 1);
    // Guard the parent links explicitly — they are the load-bearing C-2
    // anchoring seam; a future compute_hash refactor that drops them must fail.
    tamper("subcontinents.continent", &|m| m.subcontinents[0].continent ^= 1);
    tamper("regions.subcontinent", &|m| m.regions[0].subcontinent ^= 1);

    // Names are the deliberate carve-out: `compute_hash` excludes them, so a
    // name tamper must LEAVE `verify_hash` true — proof that the naming step
    // (`crate::naming`) can never break a map's determinism digest.
    let name_tamper = |label: &str, mutate: &dyn Fn(&mut WorldMap)| {
        let mut m = base.clone();
        mutate(&mut m);
        assert!(
            m.verify_hash(),
            "tampering `{label}` broke verify_hash — names must be excluded from compute_hash"
        );
    };
    name_tamper("settlements.name", &|m| m.settlements[0].name.push('x'));
    name_tamper("states.name", &|m| m.states[0].name.push('x'));
    name_tamper("provinces.name", &|m| m.provinces[0].name.push('x'));
    name_tamper("culture_regions.name", &|m| m.culture_regions[0].name.push('x'));
    name_tamper("mountain_ranges.name", &|m| m.mountain_ranges[0].name.push('x'));
    name_tamper("rivers.name", &|m| m.rivers[0].name.push('x'));
    name_tamper("water_bodies.name", &|m| m.water_bodies[0].name.push('x'));
    name_tamper("continents.name", &|m| m.continents[0].name.push('x'));
    name_tamper("subcontinents.name", &|m| m.subcontinents[0].name.push('x'));
    name_tamper("regions.name", &|m| m.regions[0].name.push('x'));
}
