//! W4.6 differential harness — runs the production projections against BOTH the
//! independent conformance oracle (all 20 events) and the from-design reproduction
//! reference (relationship + canon), plus the non-vacuity bites that prove each can
//! DISAGREE with a wrong implementation.

use dp_kernel::{EventEnvelope, ProjectionRunner, ProjectionUpdate};
use projection_reference::{KNOWN_TABLES, REPRODUCED_EVENTS, check_conformance, reference_project};
use serde_json::{Value, json};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

/// Run an envelope through the FULL production projection set — identical to the
/// C2 golden harness `full_delta`. Since `0018` that set is `canon` alone.
fn production(env: &EventEnvelope) -> Vec<ProjectionUpdate> {
    let canon = projections_canon::CanonProjection;
    ProjectionRunner::new()
        .with_projection(&canon)
        .apply_one(env)
}

fn fixtures_dir() -> PathBuf {
    // crates/projection-reference/.. /.. → crates/, then projection-golden/fixtures.
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../projection-golden/fixtures")
}

fn load_envelopes() -> Vec<(String, EventEnvelope)> {
    let mut out = Vec::new();
    for entry in std::fs::read_dir(fixtures_dir()).expect("fixtures dir") {
        let path = entry.unwrap().path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        // Skip the *.skip.json variants (idempotency-skip fixtures, no delta).
        let name = path.file_name().unwrap().to_string_lossy().to_string();
        if name.ends_with(".skip.json") {
            continue;
        }
        let bytes = std::fs::read(&path).unwrap();
        let fx = projection_golden::load(&bytes).unwrap_or_else(|e| panic!("{name}: {e}"));
        out.push((name, fx.envelope));
    }
    out
}

/// The conformance oracle must find ZERO violations in the LIVE production output
/// for every fixture event — production conforms to the DDL + contract.
#[test]
fn production_is_conformant_for_every_fixture() {
    let mut checked = 0;
    for (name, env) in load_envelopes() {
        let updates = production(&env);
        let violations = check_conformance(&env, &updates);
        assert!(
            violations.is_empty(),
            "{name}: production output is NOT conformant: {violations:#?}\nupdates: {updates:#?}"
        );
        checked += 1;
    }
    // The floor SHRANK twice: with the pc/npc fixtures (`0017`) and with the
    // region/session/world_kv ones (`0018`). It is a floor, not a pin: it exists so
    // a harness that silently stops loading fixtures cannot pass. 4 = the
    // `canon.entry.*` arms, the only events anything produces.
    assert!(checked >= 4, "expected >= 4 fixtures, checked {checked}");
}

/// The reproduction reference must MATCH the production output exactly for every
/// arm it covers (first-run agreement = a regression-lock, like C2; a FUTURE arm
/// change that diverges from this from-design reference is what it catches).
#[test]
fn reference_reproduces_production_for_covered_arms() {
    let mut covered = 0;
    for (name, env) in load_envelopes() {
        if let Some(reference) = reference_project(&env) {
            let prod = production(&env);
            assert_eq!(
                reference,
                prod,
                "{name}: reference_project != production\n--- reference ---\n{}\n--- production ---\n{}",
                serde_json::to_string_pretty(&reference).unwrap(),
                serde_json::to_string_pretty(&prod).unwrap(),
            );
            covered += 1;
        }
    }
    assert_eq!(
        covered,
        REPRODUCED_EVENTS.len(),
        "expected to reproduce {} events, covered {covered}",
        REPRODUCED_EVENTS.len()
    );
}

/// Drift guard (review #1): the schema model's table-set MUST equal the tables
/// production actually emits across the fixtures. Catches a STALE table (listed in
/// KNOWN_TABLES but no longer produced) or a missing one — the silent-rot risk the
/// loud unknown-table/unknown-column false-positives don't cover for removals.
#[test]
fn schema_model_table_set_matches_production() {
    let mut emitted: BTreeSet<String> = BTreeSet::new();
    for (_, env) in load_envelopes() {
        for u in production(&env) {
            emitted.insert(u.table().to_string());
        }
    }
    let known: BTreeSet<String> = KNOWN_TABLES.iter().map(|s| s.to_string()).collect();
    assert_eq!(
        known,
        emitted,
        "table_schema model drifted from the tables production emits\n  in-model-not-emitted: {:?}\n  emitted-not-in-model: {:?}",
        known.difference(&emitted).collect::<Vec<_>>(),
        emitted.difference(&known).collect::<Vec<_>>(),
    );
}

/// Anti-drift: every REPRODUCED_EVENTS entry has a fixture and is reproduced.
#[test]
fn reproduced_events_all_have_fixtures() {
    let names: Vec<String> = load_envelopes()
        .into_iter()
        .map(|(_, e)| e.event_type)
        .collect();
    for ev in REPRODUCED_EVENTS {
        assert!(
            names.iter().any(|n| n == ev),
            "no fixture for reproduced event {ev}"
        );
    }
}

// ───────────────────────────── non-vacuity bites ───────────────────────────────
//
// The oracle MUST be able to DISAGREE with a wrong implementation. Each bite takes
// a real envelope, constructs a BUGGY production-like update (a class C2 cannot
// catch), and asserts the conformance oracle / reproduction FLAGS it.

// Retargeted twice: off `npc.relationship_changed` (`0017`) and off
// `region.created` (`0018`), each time because the projector under the fixture was
// deleted for having no producer. **The property is that the oracle can DISAGREE**,
// and the vocabulary was incidental to it every time, so the fixtures moved and the
// tests did not. They now sit on the only projection anything writes.
fn canon_env() -> EventEnvelope {
    let (_, env) = load_envelopes()
        .into_iter()
        .find(|(_, e)| e.event_type == "canon.entry.created")
        .expect("canon.entry.created fixture");
    env
}

#[test]
fn bite_conformance_flags_hallucinated_column() {
    let env = canon_env();
    // A buggy arm writes to a column that does NOT exist in the DDL.
    let buggy = vec![ProjectionUpdate::Update {
        table: "canon_projection".into(),
        pk: json!({ "canon_entry_id": env.payload["canon_entry_id"] }),
        fields: json!({ "attribute_pat": "x" }), // typo: attribute_pat
        meta: dp_kernel::VerificationMeta::from_envelope(&env),
    }];
    let violations = check_conformance(&env, &buggy);
    assert!(
        violations.iter().any(|v| v.rule == "unknown-column"),
        "conformance should flag the hallucinated column attribute_pat: {violations:?}"
    );
}

#[test]
fn bite_conformance_flags_wrong_pk() {
    let env = canon_env();
    let buggy = vec![ProjectionUpdate::Update {
        table: "canon_projection".into(),
        pk: json!({ "book_id": env.payload["book_id"] }), // `book_id` is not the PK; `canon_entry_id` is
        fields: json!({ "attribute_path": env.payload["attribute_path"] }),
        meta: dp_kernel::VerificationMeta::from_envelope(&env),
    }];
    let violations = check_conformance(&env, &buggy);
    assert!(
        violations.iter().any(|v| v.rule == "wrong-pk"),
        "conformance should flag the wrong pk: {violations:?}"
    );
}

#[test]
fn bite_conformance_flags_wrong_key_read() {
    let env = canon_env();
    // A buggy arm writes a wrong VALUE into a REAL column. The direct-field
    // check (payload key vs written) catches it — the exact class C2
    // (same-author fixtures) cannot.
    let bad_value: Value = json!("DEFINITELY-WRONG");
    assert_ne!(
        bad_value, env.payload["attribute_path"],
        "test setup: value must differ"
    );
    let buggy = vec![ProjectionUpdate::Update {
        table: "canon_projection".into(),
        pk: json!({ "canon_entry_id": env.payload["canon_entry_id"] }),
        fields: json!({ "attribute_path": bad_value }),
        meta: dp_kernel::VerificationMeta::from_envelope(&env),
    }];
    let violations = check_conformance(&env, &buggy);
    assert!(
        violations.iter().any(|v| v.rule == "direct-field-mismatch"),
        "conformance should flag the wrong attribute_path value: {violations:?}"
    );
}

#[test]
fn bite_reproduction_disagrees_with_wrong_key_arm() {
    // review #2 — prove the REPRODUCTION differential (not just the conformance
    // oracle) can DISAGREE. Construct what a buggy arm that read the WRONG payload
    // key would emit (`value` <- `attribute_path` instead of `value`) and
    // assert the contract-derived reference (reading the RIGHT key) differs. This is
    // the exact class the same-author C2 fixtures cannot catch.
    let env = canon_env();
    let reference = reference_project(&env).expect("canon.entry.created is reproduced");
    assert_ne!(
        env.payload["value"], env.payload["attribute_path"],
        "test setup: the two keys must carry different values to distinguish a swap"
    );
    let wrong_key_arm = vec![ProjectionUpdate::Insert {
        table: "canon_projection".into(),
        row: json!({
            "canon_entry_id": env.payload["canon_entry_id"],
            "book_id": env.payload["book_id"],
            "attribute_path": env.payload["attribute_path"],
            "value": env.payload["attribute_path"], // BUG: wrong payload key read
            "canon_layer": env.payload["canon_layer"],
            "lock_level": env.payload["lock_level"],
            "source_event_id": env.event_id,
            "cascaded_from_reality_id": serde_json::Value::Null,
            "overridden_by_l3_event_id": serde_json::Value::Null,
            "last_synced_at": env.recorded_at,
        }),
        meta: dp_kernel::VerificationMeta::from_envelope(&env),
    }];
    assert_ne!(
        reference, wrong_key_arm,
        "the reproduction reference must DISAGREE with a wrong-key arm output"
    );
    // ...and it must AGREE with the real (correct) production — the discriminating pair.
    assert_eq!(
        reference,
        production(&env),
        "reference must still match correct production"
    );
}

#[test]
fn bite_conformance_flags_wrong_table() {
    let env = canon_env();
    // The canon event wrongly projects to a table it does not own. Since `0018`
    // there is only ONE projection table, so the wrong target is necessarily a
    // non-projection one — which is the sharper case anyway: the oracle must reject
    // a target it has never heard of, not merely the wrong member of a known set.
    let buggy = vec![ProjectionUpdate::Update {
        table: "reality_registry".into(),
        pk: json!({ "canon_entry_id": env.payload["canon_entry_id"] }),
        fields: json!({ "last_synced_at": 1 }),
        meta: dp_kernel::VerificationMeta::from_envelope(&env),
    }];
    let violations = check_conformance(&env, &buggy);
    assert!(
        violations
            .iter()
            .any(|v| v.rule == "unexpected-target" || v.rule == "missing-target"),
        "conformance should flag the wrong target table: {violations:?}"
    );
}
