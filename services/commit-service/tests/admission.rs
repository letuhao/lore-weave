//! Admission bite-tests — schema, EVT-L3 dedup, decision vocabulary, and
//! the D6 no-silent-skip record.

use std::time::Duration;

use commit_service::admission::{
    admit_t6, input_id_for, AdmissionOutcome, DedupCache, Verdict,
};
use commit_service::{CombatPayload, Vocabulary, COMBAT_V1_JSON};
use sim_core::EntityId;

/// The shipped reality's declared verbs. Admission judges against the rules in
/// force (`M2`), so a test that passed `VerbTable::EMPTY` would be testing an
/// admission path no deployment has.
fn verbs() -> ruleset_core::VerbTable {
    commit_service::RealityRules::proving_ground().rules().verbs
}

fn vocab() -> Vocabulary {
    Vocabulary::from_json(COMBAT_V1_JSON).unwrap()
}

fn proposal_json(proposal_id: &str, tool: &str, target: &str) -> String {
    serde_json::json!({
        "producer_service": "ai-npc-driver",
        "proposal_id": proposal_id,
        "target_channel": 1,
        "actor": 1,
        "candidates": [[2, "hostile-2"], [3, "hostile-3"]],
        "decision": {"vocabulary": "combat_v1", "tool": tool, "params": {"target": target}},
    })
    .to_string()
}

/// Valid T6 → Admitted, with EVERY registered-but-unbuilt stage recorded
/// NotRun (D6). Kill-mutations: dropping the NotRun records · admitting
/// without the vocabulary stage.
#[test]
fn valid_proposal_admits_with_notrun_stages_recorded() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let rec = admit_t6(&proposal_json("p-1", "strike", "hostile-3"), &vocab(), &verbs(), &mut dedup);

    let AdmissionOutcome::Admitted(input) = rec.outcome else {
        panic!("expected admit, got {:?}", rec.outcome);
    };
    assert_eq!(
        input.input().payload,
        CombatPayload::Strike { attacker: EntityId(1), target: EntityId(3) }
    );
    let notrun = rec.stages.iter().filter(|(_, v)| matches!(v, Verdict::NotRun)).count();
    assert_eq!(notrun, 10, "all 10 unbuilt pipeline stages are DECLARED absences");
    assert!(rec.stages.iter().any(|(n, v)| *n == "schema" && *v == Verdict::Pass));
    assert!(rec.stages.iter().any(|(n, v)| *n == "idempotency" && *v == Verdict::Pass));
}

/// EVT-L3: the second delivery of the same triple REJECTS at the
/// idempotency gate. Kill-mutation: keying the cache on proposal_id alone.
#[test]
fn duplicate_triple_rejects_at_idempotency_gate() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let v = vocab();
    let json = proposal_json("p-dup", "defend", "");
    assert!(matches!(admit_t6(&json, &v, &verbs(), &mut dedup).outcome, AdmissionOutcome::Admitted(_)));
    let rec = admit_t6(&json, &v, &verbs(), &mut dedup);
    assert!(matches!(
        rec.outcome,
        AdmissionOutcome::Rejected { stage: "idempotency", .. }
    ));

    // Same proposal_id, DIFFERENT producer — a different triple, not a dup.
    let other = json.replace("ai-npc-driver", "other-driver");
    assert!(matches!(admit_t6(&other, &v, &verbs(), &mut dedup).outcome, AdmissionOutcome::Admitted(_)));
}

/// Malformed body → schema reject; off-vocabulary decision → vocabulary
/// reject with the reason preserved. Both are EVT-L2 ack-on-reject
/// resolutions, never errors.
#[test]
fn schema_and_vocabulary_rejects_are_recorded() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let v = vocab();

    let rec = admit_t6("{not json", &v, &verbs(), &mut dedup);
    assert!(matches!(rec.outcome, AdmissionOutcome::Rejected { stage: "schema", .. }));

    let rec = admit_t6(&proposal_json("p-2", "cast_meteor", ""), &v, &verbs(), &mut dedup);
    let AdmissionOutcome::Rejected { stage, reason } = rec.outcome else {
        panic!("expected reject");
    };
    assert_eq!(stage, "decision-vocabulary");
    assert!(reason.contains("cast_meteor"));

    // THR-A4/REC-79: a target outside the OFFERED candidates rejects.
    let rec = admit_t6(&proposal_json("p-3", "strike", "the-king"), &v, &verbs(), &mut dedup);
    assert!(matches!(
        rec.outcome,
        AdmissionOutcome::Rejected { stage: "decision-vocabulary", .. }
    ));
}

/// InputId is a pure function of the EVT-L3 triple — a bus redelivery that
/// somehow passes the 60 s cache still collides in the kernel seen-set.
/// Kill-mutation: hashing with a random salt / minting fresh ids.
#[test]
fn input_id_is_deterministic_over_the_triple() {
    let t = ("svc".to_string(), "p-9".to_string(), 4i64);
    assert_eq!(input_id_for(&t), input_id_for(&t.clone()));
    let t2 = ("svc".to_string(), "p-9".to_string(), 5i64);
    assert_ne!(input_id_for(&t), input_id_for(&t2), "channel is part of the key");
}

/// Dedup cache expires by TTL — after the window the same triple MAY be
/// reprocessed (the kernel seen-set is the second layer). Kill-mutation:
/// unbounded cache.
#[test]
fn dedup_cache_expires_by_ttl() {
    let mut dedup = DedupCache::new(Duration::from_millis(1));
    let key = ("s".to_string(), "p".to_string(), 1i64);
    assert!(dedup.insert(key.clone()));
    std::thread::sleep(Duration::from_millis(5));
    assert!(dedup.insert(key), "expired entry is reprocessable by contract");
    assert_eq!(dedup.len(), 1, "expired entries were evicted, not accumulated");
}
