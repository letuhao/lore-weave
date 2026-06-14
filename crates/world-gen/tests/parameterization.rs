//! Parameterization arc acceptance — the load-bearing invariant is
//! **byte-identical default baseline**: exposing tuning as parameters must not
//! change the output for a default profile. Plus: a macro/granular knob must
//! actually change the world (otherwise it's a no-op surface).
//!
//! Spec: `docs/specs/2026-06-14-world-gen-parameterization.md`.

use world_gen::{
    BiomeKind, ClimateParams, CoastlineProfile, CreativeSeed, CultureParams, ErosionParams,
    ErosionStrength, HierarchyParams, HydrologyParams, IntensityKnobs, PoliticalParams,
    ReliefParams, RouteParams, SettlementParams, TectonicsParams, TerrainMode, WorldScale, generate,
};

fn hex(h: [u8; 32]) -> String {
    h.iter().map(|b| format!("{b:02x}")).collect()
}

/// **Profile-mode byte-identical baseline** (P2) — the default-relief Tectonic
/// pins above don't exercise the Profile-only `ReliefParams` fields (`warp_*`,
/// `cont_*`, `belt_*`, `*_weight`, `arch_radius`); this pins the legacy
/// single-continent path so a wrong default there can't ship silently. Hashes
/// captured at P1 HEAD (pre-P2). Same re-pin caveat as the Tectonic baseline.
#[test]
fn profile_mode_is_byte_identical_baseline() {
    let cases: [(CoastlineProfile, &str); 5] = [
        (CoastlineProfile::Coastal, "be40cf388e2f319c7c7cf8aba4172910025b2c000e8e1acb31b6ae878006d50f"),
        (CoastlineProfile::Island, "234c65d7d7dfe140608d6082a7ae26fa9758678f18d9219f923589317a2547a3"),
        (CoastlineProfile::Archipelago, "1e33dd38ab22fbfb0ca4b554e1a0ab408422954a0cb81d6596f61063d9341e9e"),
        (CoastlineProfile::Inland, "6b60b3f4ce4bfa546a488389b1ce7012789b97800b3d1f8331c36497ef2415ba"),
        (CoastlineProfile::Peninsula, "c0d6a1dba4524adc62d326c209690fb5e12f3aee42ec0b37df66aebae758f182"),
    ];
    for (profile, want) in cases {
        let cs = CreativeSeed {
            terrain_mode: TerrainMode::Profile,
            coastline_profile: profile,
            world_scale: WorldScale::Continent,
            ..CreativeSeed::default()
        };
        assert_eq!(hex(generate(7, &cs).content_hash), want, "Profile {profile:?} output drifted");
    }
}

/// **Byte-identical baseline** — a default profile reproduces the exact
/// content_hash captured *before* the parameterization arc began. Pinned per
/// seed/scale; if a stage ever changes default output this trips loudly (the
/// whole arc is supposed to be output-preserving). Pins captured at the P1
/// pre-refactor HEAD.
///
/// NOTE: this pins the **whole-pipeline** default output. The parameterization
/// arc (P1–P8) preserves it. A *deliberate generation change* in another arc —
/// e.g. elevation **S4 age-bathymetry**, which changes default ocean depth — will
/// (correctly) break this; re-capture the hashes then. A break here is "did
/// default output change?", not "is the param wiring broken" (that's the other
/// tests below).
#[test]
fn default_profile_is_byte_identical_baseline() {
    let cases: [(u64, WorldScale, &str); 3] = [
        (7, WorldScale::Continent, "6ecf94fa242bd8b9c464d0e2ef7f13b2c1b9859b79ceeb7c539b46f9ef513ffd"),
        (42, WorldScale::Continent, "25fb88039516430753b6ad8cef11564db9c040401dfe1988b67e3dc6bafacbc7"),
        (7, WorldScale::Pocket, "f938c8c3e06dfaffaa97b0201df7361ed4276d985dfa4e438708c00e393dc447"),
    ];
    for (seed, scale, want) in cases {
        let cs = CreativeSeed { world_scale: scale, ..CreativeSeed::default() };
        let got = hex(generate(seed, &cs).content_hash);
        assert_eq!(
            got, want,
            "default profile output drifted for seed {seed} {scale:?} — \
             parameterization must be byte-identical at default"
        );
    }
}

/// An explicit all-default params profile equals the bare default (serde-default
/// wiring of the new nested fields is correct).
#[test]
fn explicit_default_params_equal_bare_default() {
    let bare = CreativeSeed::default();
    let explicit = CreativeSeed {
        tectonics: TectonicsParams::default(),
        relief_params: ReliefParams::default(),
        climate_params: ClimateParams::default(),
        erosion_params: ErosionParams::default(),
        hydrology_params: HydrologyParams::default(),
        settlement_params: SettlementParams::default(),
        route_params: RouteParams::default(),
        political_params: PoliticalParams::default(),
        culture_params: CultureParams::default(),
        hierarchy_params: HierarchyParams::default(),
        intensity: IntensityKnobs::default(),
        ..CreativeSeed::default()
    };
    assert_eq!(
        generate(7, &bare).content_hash,
        generate(7, &explicit).content_hash
    );
}

/// **The macro `orogeny` knob actually changes the world** — a non-default knob
/// must alter the output (else the exposed surface is a no-op).
#[test]
fn orogeny_knob_changes_the_world() {
    let base = CreativeSeed::default();
    let stronger = CreativeSeed {
        intensity: IntensityKnobs { orogeny: 2.5, ..IntensityKnobs::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(7, &base).content_hash,
        generate(7, &stronger).content_hash,
        "orogeny=2.5 must change the terrain"
    );
}

/// **`collision_frequency` changes the world** — fewer faults / more collisions
/// alters plate boundaries → terrain.
#[test]
fn collision_frequency_knob_changes_the_world() {
    let base = CreativeSeed::default();
    let more = CreativeSeed {
        intensity: IntensityKnobs { collision_frequency: 2.5, ..IntensityKnobs::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(7, &base).content_hash,
        generate(7, &more).content_hash,
        "collision_frequency=2.5 must change the boundaries"
    );
}

/// **A granular tectonics override changes the world** — config-file (human)
/// path: setting one field differently alters the output.
#[test]
fn granular_tectonics_override_changes_the_world() {
    let base = CreativeSeed::default();
    let flat = CreativeSeed {
        tectonics: TectonicsParams { fold_peak: 0.0, arc_peak: 0.0, ..TectonicsParams::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(7, &base).content_hash,
        generate(7, &flat).content_hash,
        "zeroing fold/arc peaks must change the terrain"
    );
}

/// **The `relief` knob changes the world** (P2) — scales the land relief detail.
#[test]
fn relief_knob_changes_the_world() {
    let base = CreativeSeed::default();
    let rugged = CreativeSeed {
        intensity: IntensityKnobs { relief: 2.5, ..IntensityKnobs::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(7, &base).content_hash,
        generate(7, &rugged).content_hash,
        "relief=2.5 must change the terrain detail"
    );
}

/// **The `ocean_depth` knob changes the world** (P2) — scales bathymetry/quantize.
#[test]
fn ocean_depth_knob_changes_the_world() {
    let base = CreativeSeed::default();
    let deep = CreativeSeed {
        intensity: IntensityKnobs { ocean_depth: 2.0, ..IntensityKnobs::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(7, &base).content_hash,
        generate(7, &deep).content_hash,
        "ocean_depth=2.0 must change the bathymetry"
    );
}

/// **A granular relief override changes the world** (config-file path).
#[test]
fn granular_relief_override_changes_the_world() {
    let base = CreativeSeed::default();
    let shallow = CreativeSeed {
        relief_params: ReliefParams { ocean_abyss: -0.20, ..ReliefParams::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(7, &base).content_hash,
        generate(7, &shallow).content_hash,
        "shallower ocean_abyss must change the terrain"
    );
}

/// **The climate knobs change the world** (P3) — `warmth`/`rainfall`/`seasonality`.
#[test]
fn climate_knobs_change_the_world() {
    let base = generate(7, &CreativeSeed::default()).content_hash;
    for knobs in [
        IntensityKnobs { warmth: 1.6, ..IntensityKnobs::default() },
        IntensityKnobs { rainfall: 0.4, ..IntensityKnobs::default() },
        IntensityKnobs { seasonality: 2.0, ..IntensityKnobs::default() },
    ] {
        let cs = CreativeSeed { intensity: knobs, ..CreativeSeed::default() };
        assert_ne!(base, generate(7, &cs).content_hash, "a climate knob must change the world: {knobs:?}");
    }
}

/// **Direction check (P3)** — `assert_ne` above proves a climate knob *changes*
/// the world; this proves it changes it in the *physically correct direction*. A
/// sign-flip in `resolved()` (e.g. `(1−warmth)·20`) would still differ from
/// default and silently pass `assert_ne`, but would move the histogram the wrong
/// way. Counts over the whole per-cell `climate` field.
#[test]
fn climate_knobs_move_the_histogram_the_right_way() {
    use world_gen::ClimateZone;
    let count = |cs: &CreativeSeed, z: ClimateZone| {
        generate(7, cs).climate.iter().filter(|&&c| c == z).count()
    };
    let base = CreativeSeed::default();

    // Warmer world → more Tropical, fewer Polar.
    let hot = CreativeSeed {
        intensity: IntensityKnobs { warmth: 1.6, ..IntensityKnobs::default() },
        ..CreativeSeed::default()
    };
    assert!(
        count(&hot, ClimateZone::Tropical) > count(&base, ClimateZone::Tropical),
        "warmth>1 must yield more Tropical cells"
    );
    assert!(
        count(&hot, ClimateZone::Polar) < count(&base, ClimateZone::Polar),
        "warmth>1 must yield fewer Polar cells"
    );

    // Drier world → more Arid.
    let dry = CreativeSeed {
        intensity: IntensityKnobs { rainfall: 0.4, ..IntensityKnobs::default() },
        ..CreativeSeed::default()
    };
    assert!(
        count(&dry, ClimateZone::Arid) > count(&base, ClimateZone::Arid),
        "rainfall<1 must yield more Arid cells"
    );
}

/// **A granular erosion-table override changes the world** (P4) — heavier
/// incision on the live `Moderate` row carves a different heightmap. Tectonic
/// mode (the live erosion path that's ruggedness-gated).
#[test]
fn granular_erosion_override_changes_the_world() {
    let base = generate(7, &CreativeSeed::default()).content_hash;
    let carved = CreativeSeed {
        erosion_params: ErosionParams {
            moderate_erodibility: 8.0,
            moderate_carve_iters: 30,
            ..ErosionParams::default()
        },
        ..CreativeSeed::default()
    };
    assert_ne!(base, generate(7, &carved).content_hash, "stronger erosion must change terrain");
}

/// **A granular hydrology override changes the world** (P4) — a lower river
/// percentile promotes more cells to River biome → different biome map.
#[test]
fn granular_hydrology_override_changes_the_world() {
    let base = generate(7, &CreativeSeed::default()).content_hash;
    let rivery = CreativeSeed {
        hydrology_params: HydrologyParams { river_percentile: 0.50, ..HydrologyParams::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(base, generate(7, &rivery).content_hash, "a lower river percentile must change biomes");
}

/// **Direction (P4, review-impl #2)** — a *lower* river percentile must yield
/// strictly *more* River cells (not just a different hash). Guards a sign error
/// in the `(land.len() * percentile)` index that `assert_ne` would miss.
#[test]
fn lower_river_percentile_makes_more_rivers() {
    let rivers = |pct: f32| {
        let cs = CreativeSeed {
            hydrology_params: HydrologyParams { river_percentile: pct, ..HydrologyParams::default() },
            ..CreativeSeed::default()
        };
        generate(7, &cs).biome.iter().filter(|&&b| b == BiomeKind::River).count()
    };
    assert!(
        rivers(0.50) > rivers(0.96),
        "a lower river percentile must classify more cells as River"
    );
}

/// **The `lake_max_*` fields are wired (P4, review-impl #1)** — set the floor
/// above the cell count so *no* water component qualifies as ocean; with no
/// ocean the coast/biome map must change. Proves the lake-threshold path is
/// connected end-to-end (a mis-mapped field would pass every other test).
#[test]
fn lake_max_floor_changes_the_world() {
    let base = generate(7, &CreativeSeed::default()).content_hash;
    let no_ocean = CreativeSeed {
        hydrology_params: HydrologyParams { lake_max_floor: 100_000_000, ..HydrologyParams::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(
        base,
        generate(7, &no_ocean).content_hash,
        "an absurd lake_max_floor (no water body is ocean) must change the world"
    );
}

/// **The Light/Heavy erosion rows are wired (P4, review-impl #3)** — the
/// `moderate_*` override test exercises only the default strength; this hits the
/// other two `row()` branches so a Light↔Heavy field mis-map is caught.
#[test]
fn erosion_light_and_heavy_rows_are_wired() {
    let world = |strength: ErosionStrength, ep: ErosionParams| {
        let cs = CreativeSeed { erosion: strength, erosion_params: ep, ..CreativeSeed::default() };
        generate(7, &cs).content_hash
    };
    // Light: bumping light_* must change a Light world.
    let light_base = world(ErosionStrength::Light, ErosionParams::default());
    let light_hit = world(
        ErosionStrength::Light,
        ErosionParams { light_erodibility: 9.0, light_carve_iters: 35, ..ErosionParams::default() },
    );
    assert_ne!(light_base, light_hit, "light_* fields must drive a Light world");
    // Heavy: bumping heavy_* must change a Heavy world.
    let heavy_base = world(ErosionStrength::Heavy, ErosionParams::default());
    let heavy_hit = world(
        ErosionStrength::Heavy,
        ErosionParams { heavy_erodibility: 12.0, heavy_carve_iters: 40, ..ErosionParams::default() },
    );
    assert_ne!(heavy_base, heavy_hit, "heavy_* fields must drive a Heavy world");
}

/// A granular climate override changes the world (config-file path).
#[test]
fn granular_climate_override_changes_the_world() {
    let base = generate(7, &CreativeSeed::default()).content_hash;
    let cold = CreativeSeed {
        climate_params: ClimateParams { t_eq: 10.0, t_pole: -40.0, ..ClimateParams::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(base, generate(7, &cold).content_hash, "a colder world must differ");
}

/// **A granular settlement override changes the world** (P5) — a high burg
/// threshold suppresses placement (only force-placed Capitals survive), and the
/// climate-habitability + role-percentile tables feed placement/role → hash.
#[test]
fn granular_settlement_override_changes_the_world() {
    let base = generate(7, &CreativeSeed::default()).content_hash;
    let sparse = CreativeSeed {
        settlement_params: SettlementParams {
            burg_threshold: 5.0,
            habit_tropical: 3.0,
            city_frac: 0.40,
            ..SettlementParams::default()
        },
        ..CreativeSeed::default()
    };
    assert_ne!(base, generate(7, &sparse).content_hash, "settlement tuning must change the world");
}

/// **A granular route override changes the world** (P5) — a road tier gate above
/// every settlement's tier removes the entire road/trail network.
#[test]
fn granular_route_override_changes_the_world() {
    let base = generate(7, &CreativeSeed::default()).content_hash;
    let no_roads = CreativeSeed {
        // No settlement has tier ≥ 6 (max is 5) ⇒ no Road-eligible settlements.
        route_params: RouteParams { road_tier_min: 6, ..RouteParams::default() },
        ..CreativeSeed::default()
    };
    assert_ne!(base, generate(7, &no_roads).content_hash, "removing roads must change the world");
}

/// **Each `RouteParams` gate is wired (P5, review-impl #1)** — the override test
/// above only exercises `road_tier_min`; this proves the other three fields are
/// connected by zeroing out each route kind individually. (Seed-7 Continent has
/// Trail=1, MtnPass=5, RiverNav=1 by default, so each removal is observable.)
#[test]
fn each_route_param_gate_is_wired() {
    use world_gen::RouteKind;
    let count = |rp: RouteParams, kind: RouteKind| {
        let cs = CreativeSeed { route_params: rp, ..CreativeSeed::default() };
        generate(7, &cs).routes.iter().filter(|r| r.kind == kind).count()
    };
    let def = RouteParams::default();
    // trail_tier_max = 0 ⇒ no settlement has tier ≤ 0 ⇒ no Trails.
    assert!(count(def, RouteKind::Trail) > 0, "seed-7 must have Trails by default");
    assert_eq!(
        count(RouteParams { trail_tier_max: 0, ..def }, RouteKind::Trail), 0,
        "trail_tier_max must gate Trails"
    );
    // mountain_pass_target = 0 ⇒ take(0) ⇒ no MountainPass.
    assert!(count(def, RouteKind::MountainPass) > 0, "seed-7 must have MountainPasses by default");
    assert_eq!(
        count(RouteParams { mountain_pass_target: 0, ..def }, RouteKind::MountainPass), 0,
        "mountain_pass_target must gate MountainPass count"
    );
    // river_nav_min_run huge ⇒ no run is long enough ⇒ no RiverNavigation.
    assert!(count(def, RouteKind::RiverNavigation) > 0, "seed-7 must have RiverNav by default");
    assert_eq!(
        count(RouteParams { river_nav_min_run: 100_000, ..def }, RouteKind::RiverNavigation), 0,
        "river_nav_min_run must gate RiverNavigation"
    );
}

/// **A granular political override changes the world** (P6) — a tighter county
/// clamp yields fewer counties (`county_subdivision=4` default ⇒ 4/province; cap
/// at 2 halves them).
#[test]
fn granular_political_override_changes_the_world() {
    let base = generate(7, &CreativeSeed::default());
    let cs = CreativeSeed {
        political_params: PoliticalParams { county_max: 2, ..PoliticalParams::default() },
        ..CreativeSeed::default()
    };
    let m = generate(7, &cs);
    assert_ne!(base.content_hash, m.content_hash, "county_max must change the world");
    assert!(m.counties.len() < base.counties.len(), "a tighter county_max yields fewer counties");
}

/// **Each political quota divisor is wired in the right direction** (P6) — a
/// smaller `*_per_seed` divisor means more seeds per parent ⇒ strictly more
/// provinces / states / realms. Counts (not just hashes) guard a divisor swap.
#[test]
fn political_divisors_increase_tier_counts() {
    let base = generate(7, &CreativeSeed::default());
    let mk = |pp: PoliticalParams| {
        generate(7, &CreativeSeed { political_params: pp, ..CreativeSeed::default() })
    };
    let more_prov = mk(PoliticalParams { prov_cells_per_seed: 10, ..PoliticalParams::default() });
    assert!(more_prov.provinces.len() > base.provinces.len(), "smaller prov divisor ⇒ more provinces");
    let more_states = mk(PoliticalParams { state_provs_per_seed: 1, ..PoliticalParams::default() });
    assert!(more_states.states.len() > base.states.len(), "smaller state divisor ⇒ more states");
    let more_realms = mk(PoliticalParams { realm_states_per_seed: 1, ..PoliticalParams::default() });
    assert!(more_realms.realms.len() > base.realms.len(), "smaller realm divisor ⇒ more realms");
}

/// **Each political tier max is wired** (P6) — with a small divisor (so the max
/// is the binding constraint), a larger `*_max` admits more seeds. Catches a
/// prov/state/realm max field mis-map.
#[test]
fn political_maxes_are_wired() {
    let mk = |pp: PoliticalParams| {
        generate(7, &CreativeSeed { political_params: pp, ..CreativeSeed::default() })
    };
    // provinces: tiny divisor ⇒ prov_max binds.
    let p_lo = mk(PoliticalParams { prov_cells_per_seed: 1, prov_max: 2, ..PoliticalParams::default() });
    let p_hi = mk(PoliticalParams { prov_cells_per_seed: 1, prov_max: 8, ..PoliticalParams::default() });
    assert!(p_hi.provinces.len() > p_lo.provinces.len(), "higher prov_max ⇒ more provinces");
    // states: tiny divisor ⇒ state_max binds.
    let s_lo = mk(PoliticalParams { state_provs_per_seed: 1, state_max: 2, ..PoliticalParams::default() });
    let s_hi = mk(PoliticalParams { state_provs_per_seed: 1, state_max: 6, ..PoliticalParams::default() });
    assert!(s_hi.states.len() > s_lo.states.len(), "higher state_max ⇒ more states");
    // realms: tiny divisor ⇒ realm_max binds.
    let r_lo = mk(PoliticalParams { realm_states_per_seed: 1, realm_max: 1, ..PoliticalParams::default() });
    let r_hi = mk(PoliticalParams { realm_states_per_seed: 1, realm_max: 4, ..PoliticalParams::default() });
    assert!(r_hi.realms.len() > r_lo.realms.len(), "higher realm_max ⇒ more realms");
}

/// **A granular culture override changes the world** (P6) — `count_max` caps the
/// `culture_count` input (5 ⇒ 2 here), and the hearth spacing coeff drives
/// placement.
#[test]
fn granular_culture_override_changes_the_world() {
    let base = generate(7, &CreativeSeed::default());
    let capped = generate(7, &CreativeSeed {
        culture_params: CultureParams { count_max: 2, ..CultureParams::default() },
        ..CreativeSeed::default()
    });
    assert!(capped.culture_regions.len() < base.culture_regions.len(), "count_max caps cultures");
    let spaced = generate(7, &CreativeSeed {
        culture_params: CultureParams { hearth_spacing_coeff: 3.0, ..CultureParams::default() },
        ..CreativeSeed::default()
    });
    assert_ne!(base.content_hash, spaced.content_hash, "hearth spacing must change placement");
}

/// **A granular hierarchy override changes the world** (P6) — capping the
/// region-subdivision ceiling below the `region_subdivision=4` input yields
/// fewer regions, which cascades into the political nesting.
#[test]
fn granular_hierarchy_override_changes_the_world() {
    let base = generate(7, &CreativeSeed::default());
    let m = generate(7, &CreativeSeed {
        hierarchy_params: HierarchyParams { region_subdivision_max: 2 },
        ..CreativeSeed::default()
    });
    assert_ne!(base.content_hash, m.content_hash, "region_subdivision_max must change the world");
    assert!(m.regions.len() < base.regions.len(), "a tighter region ceiling yields fewer regions");
}

/// An out-of-range knob is clamped, not panicked — generation still succeeds and
/// equals the clamped-ceiling value.
#[test]
fn out_of_range_knob_clamps_and_generates() {
    let insane = CreativeSeed {
        intensity: IntensityKnobs { orogeny: 999.0, collision_frequency: 0.0, ..IntensityKnobs::default() },
        ..CreativeSeed::default()
    };
    let ceiling = CreativeSeed {
        intensity: IntensityKnobs { orogeny: 3.0, collision_frequency: 0.05, ..IntensityKnobs::default() },
        ..CreativeSeed::default()
    };
    // does not panic, and clamps to the same world as the rail ceiling.
    assert_eq!(
        generate(7, &insane).content_hash,
        generate(7, &ceiling).content_hash,
        "out-of-range knobs must clamp to the rail, not panic or differ"
    );
}
