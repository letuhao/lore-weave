//! `SEALED-SUBJECT` — a submitter cannot name the actor it acts as.
//!
//! # The defect, and why the existing tests did not cover it
//!
//! `admission::Proposal` carried `pub actor: u64`, taken from the wire and
//! believed. `producer_identity.rs` already proved a THIRD PARTY cannot tamper
//! with that field — the MAC covers the body — but a signature says *"these
//! bytes came from this producer unaltered"*. It says nothing about whether the
//! producer was entitled to the claim inside them. The signer could always name
//! any actor it liked, and everything downstream accepted it.
//!
//! `PID-D5`'s comment states the principle, eleven lines below the field it did
//! not cover: *"a field that is not on the wire cannot be forged"*. It was
//! written about `event_category`, and never applied to `actor`.
//!
//! The PO sealed the fix (2026-08-06): *"the proposal carries the USER; the
//! authoritative side resolves user → actor… fixing the transport fixes one
//! instance; moving the resolution kills the class."*
//!
//! # What is asserted here
//!
//! That the class is dead: admission takes the subject as a PARAMETER, and no
//! bytes in the proposal can change it. The tests below feed admission a
//! proposal that tries every spelling of "I am actor 99" and check the admitted
//! input still acts as the entity the CALLER resolved.

use std::time::Duration;

use commit_service::admission::{admit_t6, AdmissionOutcome, DedupCache};
use commit_service::domain::CombatPayload;
use commit_service::{RealityRules, Vocabulary, COMBAT_V1_JSON};
use sim_core::EntityId;

const TEST_USER: &str = "7e57ab1e-0000-4000-8000-00000000ac70";
/// What the caller resolved from `actor_control_binding`.
const RESOLVED: EntityId = EntityId(1);
/// What a malicious submitter would rather be.
const CLAIMED: u64 = 99;

fn vocab() -> Vocabulary {
    Vocabulary::from_json(COMBAT_V1_JSON).expect("the shipped manifest parses")
}

fn rules() -> std::sync::Arc<RealityRules> {
    std::sync::Arc::new(RealityRules::proving_ground())
}

/// A proposal carrying `extra` fields alongside the legitimate ones.
fn proposal_with(id: &str, extra: serde_json::Value) -> String {
    let mut v = serde_json::json!({
        "producer_service": "game-server",
        "proposal_id": id,
        "target_channel": 1,
        "user_ref_id": TEST_USER,
        "candidates": [[3, "hostile-3"]],
        "decision": {"vocabulary": "combat_v1", "tool": "strike", "params": {"target": "hostile-3"}},
    });
    for (k, val) in extra.as_object().expect("an object").iter() {
        v[k] = val.clone();
    }
    v.to_string()
}

fn admitted_attacker(raw: &str) -> EntityId {
    let r = rules();
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let rec = admit_t6(raw, RESOLVED, &vocab(), &r.rules().verbs, &mut dedup);
    let AdmissionOutcome::Admitted(input) = rec.outcome else {
        panic!("expected an admit, got {:?}", rec.outcome);
    };
    match &input.input().payload {
        CombatPayload::Strike { attacker, .. } => *attacker,
        other => panic!("expected a strike, got {other:?}"),
    }
}

/// The heart of it: a proposal that names `actor: 99` still acts as the entity
/// the caller resolved.
///
/// Before `SEALED-SUBJECT` this field WAS the subject, so this test would have
/// reported `EntityId(99)` — a submitter acting as an actor it does not drive.
#[test]
fn a_proposal_naming_another_actor_does_not_become_that_actor() {
    let raw = proposal_with("p-forge-1", serde_json::json!({ "actor": CLAIMED }));
    assert_eq!(
        admitted_attacker(&raw),
        RESOLVED,
        "the subject came from the WIRE — a submitter can act as an actor it does not drive"
    );
}

/// The same claim under three other spellings, because a field removed from a
/// struct is still a field an attacker can put in the JSON. `serde` ignores
/// unknown keys by default; this asserts that ignoring them is all that happens.
#[test]
fn no_spelling_of_the_claim_reaches_the_subject() {
    for (i, extra) in [
        serde_json::json!({ "actor": CLAIMED }),
        serde_json::json!({ "actor_id": CLAIMED }),
        serde_json::json!({ "entity_id": CLAIMED }),
        serde_json::json!({ "subject": CLAIMED }),
    ]
    .into_iter()
    .enumerate()
    {
        let raw = proposal_with(&format!("p-forge-spell-{i}"), extra.clone());
        assert_eq!(
            admitted_attacker(&raw),
            RESOLVED,
            "the field {extra} reached the subject"
        );
    }
}

/// And the inverse, so this suite is non-vacuous: the subject the CALLER passes
/// is the one that lands. A test that only checked "not 99" would pass against
/// an admission that hardcoded `EntityId(1)` and ignored its parameter.
#[test]
fn the_callers_resolved_subject_is_the_one_that_acts() {
    let r = rules();
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let raw = proposal_with("p-resolved-7", serde_json::json!({}));
    let rec = admit_t6(&raw, EntityId(7), &vocab(), &r.rules().verbs, &mut dedup);
    let AdmissionOutcome::Admitted(input) = rec.outcome else {
        panic!("expected an admit, got {:?}", rec.outcome);
    };
    match &input.input().payload {
        CombatPayload::Strike { attacker, .. } => {
            assert_eq!(*attacker, EntityId(7), "admission ignored the resolved subject");
        }
        other => panic!("expected a strike, got {other:?}"),
    }
}

/// A proposal with no `user_ref_id` cannot be resolved, so it cannot be
/// admitted. Asserted through the SAME struct the wire deserialises into: the
/// field is required, so a body without it fails the schema stage.
#[test]
fn a_proposal_without_a_submitter_is_refused_at_the_schema_stage() {
    let r = rules();
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let raw = serde_json::json!({
        "producer_service": "game-server",
        "proposal_id": "p-no-user",
        "target_channel": 1,
        "candidates": [],
        "decision": {"vocabulary": "combat_v1", "tool": "strike", "params": {"target": "x"}},
    })
    .to_string();
    let rec = admit_t6(&raw, RESOLVED, &vocab(), &r.rules().verbs, &mut dedup);
    assert!(
        matches!(rec.outcome, AdmissionOutcome::Rejected { stage: "schema", .. }),
        "a proposal with no submitter must not be admitted: {:?}",
        rec.outcome
    );
}
