//! C2 golden-fixture harness: every fixture in `fixtures/` must match the FULL
//! projection set's `apply_one` output, exactly and in order.

use dp_kernel::{EventEnvelope, ProjectionRunner, ProjectionUpdate};

/// Run an envelope through every L3.B projection (the same set the rebuilder
/// uses) and return the concatenated delta — so a fan-out event yields its
/// full set.
///
/// The set is ONE projection since `0018`. `ProjectionRunner` is kept rather than
/// calling `CanonProjection::apply_event` directly, because what this harness
/// asserts is the output of the RUNNER — the same composition the rebuilder uses —
/// and collapsing it would quietly stop testing the path that fans out.
fn full_delta(env: &EventEnvelope) -> Vec<ProjectionUpdate> {
    let canon = projections_canon::CanonProjection;
    ProjectionRunner::new()
        .with_projection(&canon)
        .apply_one(env)
}

fn fixtures_dir() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("fixtures")
}

#[test]
fn every_fixture_matches_apply_one() {
    let mut count = 0;
    for entry in std::fs::read_dir(fixtures_dir()).expect("fixtures dir") {
        let path = entry.unwrap().path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        let bytes = std::fs::read(&path).unwrap();
        let fx = projection_golden::load(&bytes)
            .unwrap_or_else(|e| panic!("{}: parse: {e}", path.display()));
        let actual = full_delta(&fx.envelope);
        if actual != fx.expected_updates {
            panic!(
                "{}: apply_one != fixture\n--- actual ---\n{}\n--- expected ---\n{}",
                path.display(),
                serde_json::to_string_pretty(&actual).unwrap(),
                serde_json::to_string_pretty(&fx.expected_updates).unwrap(),
            );
        }
        count += 1;
    }
    // Pinned, not `> 0`: every event type the full projection set handles must
    // have a fixture, and `read_dir` can't tell us one is MISSING. Adding or
    // removing a fixture is a deliberate, test-visible act — bump this count and
    // you have acknowledged the coverage change. If a NEW projection arm lands
    // without a fixture, this assert fails until one is added.
    //
    // 4 since `0018`: the four `canon.entry.*` arms. It was 10 until the region,
    // session and world_kv projectors went — none of their events had a producer,
    // so their fixtures were the only thing that had ever emitted them.
    assert_eq!(
        count,
        4,
        "expected 4 golden fixtures in {}, found {count} — a fixture was added or removed without updating this pin (every handled event type must keep a fixture)",
        fixtures_dir().display()
    );
}

#[test]
fn oracle_bites_on_value_difference() {
    // Prove the harness is not a rubber-stamp: the same event with a DIFFERENT
    // value must NOT match the fixture's expected delta.
    // Retargeted twice: off `npc.created.json` (2026-08-04, deleted with the npc
    // projectors) and off `region.created.json` (2026-08-05, deleted with the
    // region projector). **The property is the harness's non-vacuity and it must
    // survive**, so the fixture changed and the test did not. It now sits on the
    // only projection with a producer, which is where it should have been all
    // along — the first two homes were tables nothing wrote.
    let bytes = std::fs::read(fixtures_dir().join("canon.entry.created.json")).unwrap();
    let fx = projection_golden::load(&bytes).unwrap();
    let mut env = fx.envelope.clone();
    env.payload["attribute_path"] = serde_json::json!("DEFINITELY-WRONG");
    assert_ne!(
        full_delta(&env),
        fx.expected_updates,
        "a value difference must be caught"
    );
}
