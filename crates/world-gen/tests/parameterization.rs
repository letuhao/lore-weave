//! Parameterization arc acceptance — the load-bearing invariant is
//! **byte-identical default baseline**: exposing tuning as parameters must not
//! change the output for a default profile. Plus: a macro/granular knob must
//! actually change the world (otherwise it's a no-op surface).
//!
//! Spec: `docs/specs/2026-06-14-world-gen-parameterization.md`.

use world_gen::{CreativeSeed, IntensityKnobs, TectonicsParams, WorldScale, generate};

fn hex(h: [u8; 32]) -> String {
    h.iter().map(|b| format!("{b:02x}")).collect()
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

/// An out-of-range knob is clamped, not panicked — generation still succeeds and
/// equals the clamped-ceiling value.
#[test]
fn out_of_range_knob_clamps_and_generates() {
    let insane = CreativeSeed {
        intensity: IntensityKnobs { orogeny: 999.0, collision_frequency: 0.0 },
        ..CreativeSeed::default()
    };
    let ceiling = CreativeSeed {
        intensity: IntensityKnobs { orogeny: 3.0, collision_frequency: 0.05 },
        ..CreativeSeed::default()
    };
    // does not panic, and clamps to the same world as the rail ceiling.
    assert_eq!(
        generate(7, &insane).content_hash,
        generate(7, &ceiling).content_hash,
        "out-of-range knobs must clamp to the rail, not panic or differ"
    );
}
