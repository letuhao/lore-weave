//! Regeneration-determinism — the load-bearing invariant. `generate` must be
//! a pure function: identical inputs ⇒ byte-identical `WorldMap`.
//! (Phase 1 acceptance criterion #2.)

use world_gen::{
    ClimateZone, CoastlineProfile, CreativeSeed, HemisphereOrientation, WorldScale, generate,
};

/// `generate` is byte-identical across two runs, for several fixture seeds
/// crossing multiple scales and coastline profiles.
#[test]
fn byte_identical_across_runs() {
    let cases = [
        (1u64, WorldScale::Pocket, CoastlineProfile::Island),
        (42, WorldScale::Region, CoastlineProfile::Coastal),
        (0xDEAD_BEEF, WorldScale::Continent, CoastlineProfile::Archipelago),
        (777, WorldScale::Continent, CoastlineProfile::Inland),
        (2_026_051_700, WorldScale::SuperContinent, CoastlineProfile::Peninsula),
    ];
    for (seed, scale, coast) in cases {
        let cs = CreativeSeed {
            world_scale: scale,
            coastline_profile: coast,
            ..CreativeSeed::default()
        };
        let a = generate(seed, &cs);
        let b = generate(seed, &cs);
        assert_eq!(
            a.content_hash, b.content_hash,
            "content_hash differs across runs — seed {seed}, {scale:?}"
        );
        assert_eq!(a, b, "WorldMap differs across runs — seed {seed}, {scale:?}");
    }
}

/// The content hash actually depends on the seed (it is not a constant).
#[test]
fn distinct_seeds_distinct_hashes() {
    let cs = CreativeSeed::default();
    let a = generate(1, &cs);
    let b = generate(2, &cs);
    assert_ne!(
        a.content_hash, b.content_hash,
        "distinct seeds produced an identical content_hash"
    );
}

/// The content hash depends on creative direction too.
#[test]
fn distinct_profiles_distinct_hashes() {
    let island = CreativeSeed {
        coastline_profile: CoastlineProfile::Island,
        ..CreativeSeed::default()
    };
    let inland = CreativeSeed {
        coastline_profile: CoastlineProfile::Inland,
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(5, &island).content_hash,
        generate(5, &inland).content_hash,
        "distinct coastline profiles produced an identical content_hash"
    );
}

/// The Phase 2 climate inputs (hemisphere, climate bias) are deterministic.
#[test]
fn hemisphere_and_climate_bias_are_deterministic() {
    let cs = CreativeSeed {
        hemisphere_orientation: HemisphereOrientation::Southern,
        climate_bias: Some(ClimateZone::Arid),
        ..CreativeSeed::default()
    };
    let a = generate(2026, &cs);
    let b = generate(2026, &cs);
    assert_eq!(a.content_hash, b.content_hash);
    assert_eq!(a, b);
}

/// Climate inputs actually feed the output — changing them changes the hash.
#[test]
fn climate_inputs_change_the_hash() {
    let base = CreativeSeed::default();
    let southern = CreativeSeed {
        hemisphere_orientation: HemisphereOrientation::Southern,
        ..CreativeSeed::default()
    };
    let arid = CreativeSeed {
        climate_bias: Some(ClimateZone::Arid),
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(9, &base).content_hash,
        generate(9, &southern).content_hash,
        "hemisphere flip did not change the map"
    );
    assert_ne!(
        generate(9, &base).content_hash,
        generate(9, &arid).content_hash,
        "climate bias did not change the map"
    );
}

/// The Phase 3 inputs (settlement density, culture count) are deterministic
/// and actually feed the output.
#[test]
fn phase3_inputs_are_deterministic_and_effective() {
    let cs = CreativeSeed {
        settlement_density: world_gen::SettlementDensity::Dense,
        culture_count: 9,
        ..CreativeSeed::default()
    };
    let a = generate(2026, &cs);
    let b = generate(2026, &cs);
    assert_eq!(a.content_hash, b.content_hash);
    assert_eq!(a, b);

    let sparse = CreativeSeed {
        settlement_density: world_gen::SettlementDensity::Sparse,
        ..CreativeSeed::default()
    };
    let dense = CreativeSeed {
        settlement_density: world_gen::SettlementDensity::Dense,
        ..CreativeSeed::default()
    };
    assert_ne!(
        generate(11, &sparse).content_hash,
        generate(11, &dense).content_hash,
        "settlement density did not change the map"
    );
}

/// review-impl C7 — cross-*process* determinism: the CLI binary, run as two
/// separate OS processes, writes byte-identical map JSON. The other
/// determinism tests only call `generate` twice within one process.
#[test]
fn cli_is_deterministic_across_processes() {
    use std::process::Command;
    let exe = env!("CARGO_BIN_EXE_world-gen");
    let dir = std::env::temp_dir();
    let run = |tag: &str| -> Vec<u8> {
        let out = dir.join(format!("world-gen-xproc-{tag}.json"));
        let status = Command::new(exe)
            .args([
                "generate",
                "--seed",
                "20260517",
                "--scale",
                "region",
                "--coastline",
                "peninsula",
                "--out",
            ])
            .arg(&out)
            .status()
            .expect("failed to run the world-gen CLI");
        assert!(status.success(), "CLI run {tag} exited non-zero");
        std::fs::read(&out).expect("read CLI output JSON")
    };
    assert_eq!(
        run("a"),
        run("b"),
        "the CLI produced different map JSON across two separate processes"
    );
}
