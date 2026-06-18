//! C2 golden-fixture harness: every fixture in `fixtures/` must match the FULL
//! projection set's `apply_one` output, exactly and in order.

use dp_kernel::{EventEnvelope, ProjectionRunner, ProjectionUpdate};

/// Run an envelope through every L3.B projection (the same set the rebuilder
/// uses) and return the concatenated delta — so a fan-out event (e.g. npc.said →
/// npc_projection + npc_session_memory_projection) yields its full set.
fn full_delta(env: &EventEnvelope) -> Vec<ProjectionUpdate> {
    let pc = projections_pc::PcProjection;
    let pc_inv = projections_pc::PcInventoryProjection;
    let pc_rel = projections_pc::PcRelationshipProjection;
    let npc = projections_npc::NpcProjection;
    let npc_mem = projections_npc::NpcSessionMemoryProjection;
    let npc_pc_rel = projections_npc::NpcPcRelationshipProjection;
    let npc_emb = projections_npc::NpcSessionMemoryEmbeddingProjection;
    let region = projections_region::RegionProjection;
    let session = projections_session::SessionParticipantsProjection;
    let world_kv = projections_world_kv::WorldKvProjection;
    let canon = projections_canon::CanonProjection;

    ProjectionRunner::new()
        .with_projection(&pc)
        .with_projection(&pc_inv)
        .with_projection(&pc_rel)
        .with_projection(&npc)
        .with_projection(&npc_mem)
        .with_projection(&npc_pc_rel)
        .with_projection(&npc_emb)
        .with_projection(&region)
        .with_projection(&session)
        .with_projection(&world_kv)
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
    // have a fixture, and `read_dir` can't tell us one is MISSING. 21 = 20
    // handled event types (the 19 `=>` arms + npc.memory_embedded via handles())
    // plus the extra npc.memory_embedded.skip negative-branch fixture. Adding or
    // removing a fixture is now a deliberate, test-visible act — bump this count
    // and you've acknowledged the coverage change. If a NEW projection arm lands
    // without a fixture, this assert fails until one is added.
    assert_eq!(
        count,
        21,
        "expected 21 golden fixtures in {}, found {count} — a fixture was added or removed without updating this pin (every handled event type must keep a fixture)",
        fixtures_dir().display()
    );
}

#[test]
fn oracle_bites_on_value_difference() {
    // Prove the harness is not a rubber-stamp: the same event with a DIFFERENT
    // value must NOT match the fixture's expected delta.
    let bytes = std::fs::read(fixtures_dir().join("npc.created.json")).unwrap();
    let fx = projection_golden::load(&bytes).unwrap();
    let mut env = fx.envelope.clone();
    env.payload["initial_mood"] = serde_json::json!("DEFINITELY-WRONG");
    assert_ne!(
        full_delta(&env),
        fx.expected_updates,
        "a value difference must be caught"
    );
}
