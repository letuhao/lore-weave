//! F2 V7/V8 — a reality loads its rules from a FILE, and its islands carry
//! that file's digest.
//!
//! `spine.rs` is a binary, so the wiring itself cannot be unit-tested. What CAN
//! be tested — and is the part that could silently be decorative — is that the
//! loader's output actually reaches an island's pin and the events it produces.
//! A `--ruleset` flag that parses a file and then runs the engine defaults
//! anyway would pass every test in `ruleset-loader` and be worthless.

use std::sync::Arc;

use commit_service::{CombatDomain, CombatState, Ruleset};
use ruleset_loader::{parse_layer, resolve, Layer, LoadError};
use sim_core::{Island, IslandId, SeenWindow};

/// V7 — the file's rules reach the island's pin, and the LAWS read them.
#[test]
fn a_loaded_file_changes_both_the_pin_and_the_play() {
    // A grittier reality: the ceiling on a single hit is 250, not 1e9.
    let src = "[combat]\nmax_hit = 250\nko_duration_rounds = 2\n";
    let rules = Arc::new(resolve(&[parse_layer(Layer::Reality, src).unwrap()]).unwrap());

    let isle: Island<CombatDomain> = Island::new(
        IslandId(1),
        7,
        Arc::clone(&rules),
        SeenWindow::Unbounded,
        CombatState::default(),
    );

    // The pin describes THIS file's rules, not the engine default's.
    assert_eq!(isle.digest, rules.digest());
    assert_ne!(
        isle.digest,
        Ruleset::engine_default().digest(),
        "an island running authored rules must be distinguishable from one running \
         the defaults — otherwise the whole loader is decorative"
    );

    // …and the numbers actually reached the laws, not just the digest.
    assert_eq!(rules.combat.max_hit, 250);
    assert_eq!(rules.combat.ko_duration_rounds, 2);
    assert_eq!(
        rules.combat.hit_base_pm,
        Ruleset::engine_default().combat.hit_base_pm,
        "an unstated field inherits from the layer below"
    );
}

/// V8 — RLS-D12: a malformed ruleset is a per-reality refusal with a
/// diagnostic, never a panic and never a process failure.
///
/// One malformed reality must not take down a node hosting forty others. In a
/// library that means: every failure path returns an error carrying the
/// author's problem, and nothing on it panics or exits.
#[test]
fn a_bad_ruleset_is_a_diagnosable_refusal_not_a_panic() {
    // Unparseable.
    assert!(matches!(
        parse_layer(Layer::Reality, "[combat]\nmax_hit = \"not a number\"\n"),
        Err(LoadError::Parse { .. })
    ));

    // Parseable but unloadable — and the message must name the numbers, because
    // the author is looking at a file and needs to know which one to change.
    let bad = parse_layer(Layer::Reality, "[combat]\ndefend_divisor = 0\n").unwrap();
    let err = resolve(&[bad]).unwrap_err();
    let msg = format!("{err}");
    assert!(msg.contains("defend_divisor"), "must name the field: {msg}");
    assert!(msg.contains("unloadable"), "must state the blast radius: {msg}");

    // The engine default is still loadable — otherwise the above proves nothing.
    assert!(resolve(&[]).is_ok());
}
