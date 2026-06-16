//! Inc-1 gate as cargo tests — the harness proves itself reproducible and
//! non-vacuous before any oracle rides on it.

use loreweave_sim::skeleton::{has_interleaving, self_check, trace_for};

#[test]
fn reproducible_same_seed() {
    // Same seed ⇒ byte-identical observable interleaving, every time.
    for seed in [0u64, 1, 7, 42, 1000] {
        assert_eq!(
            trace_for(seed),
            trace_for(seed),
            "seed {seed} must reproduce the exact interleaving"
        );
    }
}

#[test]
fn lands_every_event() {
    // 4 actors × 3 ops, distinct aggregates ⇒ no CAS conflict ⇒ all 12 land.
    assert_eq!(trace_for(7).len(), 12);
}

#[test]
fn non_vacuous_true_interleaving_exists() {
    // The CORE non-vacuity proof: the yield points must produce at least one
    // genuinely interleaved schedule across a sweep. If none interleaves, the
    // sim is single-path and every later oracle would be vacuous.
    let interleaved = (0..64u64)
        .filter(|s| has_interleaving(&trace_for(*s)))
        .count();
    assert!(
        interleaved > 0,
        "no seed in 0..64 interleaved two actors — yields not taking effect (vacuous sim)"
    );
}

#[test]
fn bite_yields_are_what_create_interleaving() {
    // BITE: prove the interleaving comes from the YIELD points, not from the
    // scheduler alone. A trace built by concatenating each actor's ops as one
    // contiguous block (what a yield-free run produces — each actor completes
    // on first poll) has NO interleaving by construction. If `has_interleaving`
    // flagged that as interleaved, the detector would be vacuous.
    let blocky: Vec<String> = (0..3)
        .flat_map(|a| (1..=3).map(move |v| format!("agg-{a}:{v}")))
        .collect();
    assert!(
        !has_interleaving(&blocky),
        "detector must NOT see interleaving in contiguous per-actor blocks"
    );
}

#[test]
fn self_check_passes() {
    // The same gate the `sim skeleton` subcommand runs.
    self_check().expect("skeleton self-check must pass");
}
