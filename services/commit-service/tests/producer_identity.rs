//! PID-A1..A4 — producer identity, plus the polyglot fixture that keeps the
//! Rust verifier and the TypeScript producer honest about each other.
//!
//! The defect being guarded: `event_category` used to ride the wire and select
//! the validator subset, so a message could elect its own trust tier. These
//! tests assert the tier now comes from WHO SIGNED, and that a forged claim
//! fails at the signature rather than being believed.

use std::time::Duration;

use commit_service::admission::{admit_signed, AdmissionOutcome, Category, DedupCache, Verdict};
use commit_service::producer::{sign, ProducerError, ProducerRegistry};
use commit_service::{Vocabulary, COMBAT_V1_JSON};

/// The shipped reality's declared verbs. Admission judges against the rules in
/// force (`M2`), so a test that passed `VerbTable::EMPTY` would be testing an
/// admission path no deployment has.
fn verbs() -> ruleset_core::VerbTable {
    commit_service::RealityRules::proving_ground().rules().verbs
}

fn vocab() -> Vocabulary {
    Vocabulary::from_json(COMBAT_V1_JSON).unwrap()
}

const GS_KEY: &[u8] = b"game-server-key";
const LLM_KEY: &[u8] = b"llm-driver-key";

fn registry() -> ProducerRegistry {
    ProducerRegistry::new()
        .with("game-server", Category::T1, GS_KEY)
        .with("llm-driver", Category::T6, LLM_KEY)
}

fn proposal(producer: &str, id: &str) -> String {
    serde_json::json!({
        "producer_service": producer,
        "proposal_id": id,
        "target_channel": 1,
        "actor": 1,
        "candidates": [[2, "hostile-2"]],
        "decision": {"vocabulary": "combat_v1", "tool": "strike", "params": {"target": "hostile-2"}},
    })
    .to_string()
}

/// A correctly signed proposal is admitted, and its category comes from the
/// REGISTRY rather than from anything the message said.
#[test]
fn a_signed_proposal_is_admitted_under_its_producers_tier() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let raw = proposal("game-server", "p-1");
    let sig = sign(GS_KEY, raw.as_bytes());

    let rec = admit_signed(&raw, Some(&sig), &registry(), &vocab(), &verbs(), &mut dedup);
    assert!(matches!(rec.outcome, AdmissionOutcome::Admitted(_)));
    assert!(rec.stages.iter().any(|(n, v)| *n == "producer-identity" && *v == Verdict::Pass));

    // game-server is T1, whose declared subset SKIPS the LLM-safety stages.
    let skipped: Vec<&str> =
        rec.stages.iter().filter(|(_, v)| *v == Verdict::Skip).map(|(n, _)| *n).collect();
    assert!(skipped.contains(&"a5-intent"), "T1 declares the LLM stages inapplicable");
}

/// **The escalation that started doc 25.** The LLM driver signs with ITS key
/// while the body claims `game-server`, reaching for the reduced player
/// subset. Verification uses the key of the producer NAMED in the body, so the
/// forged claim fails at the MAC.
#[test]
fn a_producer_cannot_claim_another_producers_tier() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let raw = proposal("game-server", "p-forge");
    let sig = sign(LLM_KEY, raw.as_bytes());

    let rec = admit_signed(&raw, Some(&sig), &registry(), &vocab(), &verbs(), &mut dedup);
    assert!(
        matches!(rec.outcome, AdmissionOutcome::Rejected { stage: "producer-identity", .. }),
        "claiming another producer must fail at the SIGNATURE, not be believed"
    );
}

/// An honest LLM proposal runs the full pipeline — the tier it cannot escape.
#[test]
fn the_llm_driver_gets_the_full_pipeline() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let raw = proposal("llm-driver", "p-llm");
    let sig = sign(LLM_KEY, raw.as_bytes());

    let rec = admit_signed(&raw, Some(&sig), &registry(), &vocab(), &verbs(), &mut dedup);
    assert!(matches!(rec.outcome, AdmissionOutcome::Admitted(_)));
    let notrun = rec.stages.iter().filter(|(_, v)| matches!(v, Verdict::NotRun)).count();
    assert_eq!(notrun, 10, "T6 owes all ten stages — none declared inapplicable");
}

/// Default-DENY (PID-A4), and it happens BEFORE dedup: the dedup triple
/// contains the producer name, so deduping an unverified identity would let a
/// forger evict a real proposal from the window by claiming its name.
#[test]
fn an_unknown_producer_is_denied_before_dedup() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let raw = proposal("who-am-i", "p-x");
    let sig = sign(GS_KEY, raw.as_bytes());

    let rec = admit_signed(&raw, Some(&sig), &registry(), &vocab(), &verbs(), &mut dedup);
    assert!(matches!(rec.outcome, AdmissionOutcome::Rejected { stage: "producer-identity", .. }));
    assert!(
        !rec.stages.iter().any(|(n, _)| *n == "idempotency"),
        "identity runs FIRST, so nothing was deduped on an unverified name"
    );
}

/// A missing signature is a rejection, not a fallthrough. Kill-mutation:
/// treating `None` as "unsigned is fine" restores the entire defect.
#[test]
fn a_missing_signature_is_rejected() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let raw = proposal("game-server", "p-nosig");
    let rec = admit_signed(&raw, None, &registry(), &vocab(), &verbs(), &mut dedup);
    assert!(matches!(rec.outcome, AdmissionOutcome::Rejected { stage: "producer-identity", .. }));
}

/// One flipped byte in the body invalidates the signature — the MAC covers the
/// payload, not merely the producer name.
#[test]
fn tampering_with_the_body_invalidates_the_signature() {
    let mut dedup = DedupCache::new(Duration::from_secs(60));
    let raw = proposal("game-server", "p-tamper");
    let sig = sign(GS_KEY, raw.as_bytes());
    let tampered = raw.replace(r#""actor":1"#, r#""actor":99"#);
    assert_ne!(raw, tampered, "the tamper must actually change the bytes");

    let rec = admit_signed(&tampered, Some(&sig), &registry(), &vocab(), &verbs(), &mut dedup);
    assert!(matches!(rec.outcome, AdmissionOutcome::Rejected { stage: "producer-identity", .. }));
}

/// Malformed hex is a clean rejection rather than a partial comparison.
#[test]
fn malformed_signatures_are_rejected_cleanly() {
    let reg = registry();
    let raw = proposal("game-server", "p-hex");
    for bad in ["zz", "abc", ""] {
        let err = reg.verify_and_derive("game-server", raw.as_bytes(), Some(bad)).unwrap_err();
        assert!(
            matches!(err, ProducerError::MalformedSignature | ProducerError::BadSignature(_)),
            "{bad:?} produced {err:?}"
        );
    }
}

/// **The polyglot half.** `game-server` signs with Node's `crypto`; this
/// verifier must accept those exact bytes. The fixture is the only thing
/// joining the two implementations, so a change to either side's MAC input
/// reds the other — the same discipline as `contracts/game-wire/`.
#[test]
fn the_polyglot_fixture_verifies() {
    let text = std::fs::read_to_string("../../contracts/agent/producer-identity.fixture.json")
        .expect("fixture readable");
    let fixture: serde_json::Value = serde_json::from_str(&text).expect("fixture parses");

    let key = fixture["key"].as_str().unwrap().as_bytes();
    let raw = fixture["raw"].as_str().unwrap();
    let sig = fixture["sig"].as_str().unwrap();

    let reg = ProducerRegistry::new().with("game-server", Category::T1, key);
    assert_eq!(
        reg.verify_and_derive("game-server", raw.as_bytes(), Some(sig)).unwrap(),
        Category::T1,
        "the fixture signature must verify — if this reds, the Rust and TS \
         sides disagree about what is signed"
    );
}
