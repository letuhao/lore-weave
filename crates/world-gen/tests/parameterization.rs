//! Parameterization arc acceptance — the load-bearing invariant is
//! **byte-identical default baseline**: exposing tuning as parameters must not
//! change the output for a default profile. Plus: a macro/granular knob must
//! actually change the world (otherwise it's a no-op surface).
//!
//! Spec: `docs/specs/2026-06-14-world-gen-parameterization.md`.

use world_gen::{
    CoastlineProfile, CreativeSeed, IntensityKnobs, ReliefParams, TectonicsParams, TerrainMode,
    WorldScale, generate,
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
