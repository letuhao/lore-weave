//! `Q0b B3c` — the committed payload against `contracts/events/reality.go`.
//!
//! **Why this is a test and not a code comment.** `RulesetEpochActivatedV1` is
//! defined in Go, in `contracts/events/`, and constructed in Rust, in
//! `commit-service`. Nothing in either language links them: the Rust side builds
//! a `serde_json::Value` by hand, so a renamed field on the Go side compiles
//! fine on both, ships fine, and is discovered by whoever writes the first
//! consumer.
//!
//! That is the same class of drift the repo already ships gates for (the
//! frontend-tool contract, the Go↔Rust envelope parity, the polyglot meta
//! allowlist). It bit this very event twice in two days: the barrels were
//! committed without their modules, and the registry entry was added without a
//! field map, so all three generated bindings were EMPTY structs.
//!
//! So the SoT is read at runtime — the Go file is parsed for its `json:` tags —
//! rather than a second hand-written list being compared to a first one.

use commit_service::epoch_commit::activation_payload;
use sim_core::RulesetEpoch;
use uuid::Uuid;

const GO_CONTRACT: &str = "../../contracts/events/reality.go";
const GO_STRUCT: &str = "RulesetEpochActivatedV1";

/// The `json:"…"` tag names of `GO_STRUCT`'s fields, in declaration order,
/// read from the Go source at test time.
fn go_json_fields() -> Vec<String> {
    let src = std::fs::read_to_string(GO_CONTRACT)
        .unwrap_or_else(|e| panic!("{GO_CONTRACT}: {e} — the contract SoT must be readable"));
    let start = src
        .find(&format!("type {GO_STRUCT} struct {{"))
        .unwrap_or_else(|| panic!("{GO_STRUCT} is not in {GO_CONTRACT}"));
    let body = &src[start..];
    let end = body.find("\n}").expect("the struct must be closed");
    let mut out = Vec::new();
    for line in body[..end].lines() {
        // `json:"name"` — the only thing this parser needs, and a field with no
        // tag would simply not appear, which the count assertion below catches.
        if let Some(i) = line.find("json:\"") {
            let rest = &line[i + 6..];
            if let Some(j) = rest.find('"') {
                out.push(rest[..j].to_string());
            }
        }
    }
    assert!(
        !out.is_empty(),
        "parsed ZERO json tags out of {GO_STRUCT} — the parser broke, and a \
         parser that finds nothing would make every assertion below vacuous"
    );
    out
}

fn sample_payload() -> serde_json::Value {
    activation_payload(
        Uuid::nil(),
        7,
        RulesetEpoch(4),
        RulesetEpoch(5),
        &"a".repeat(64),
        "epoch=5|reality_id=00000000-0000-0000-0000-000000000000",
        "2026-07-30T11:22:33Z",
    )
}

/// Exact set equality, both directions. A missing key means a consumer reading
/// the Go struct gets `null`; an extra key means the writer is emitting a fact
/// the contract does not describe, which no version of the struct will decode.
#[test]
fn the_committed_payload_has_exactly_the_contracts_fields() {
    let want: std::collections::BTreeSet<String> = go_json_fields().into_iter().collect();
    let payload = sample_payload();
    let got: std::collections::BTreeSet<String> =
        payload.as_object().expect("payload is an object").keys().cloned().collect();

    let missing: Vec<_> = want.difference(&got).collect();
    let extra: Vec<_> = got.difference(&want).collect();
    assert!(
        missing.is_empty() && extra.is_empty(),
        "the committed payload has drifted from {GO_STRUCT} in {GO_CONTRACT}\n  \
         missing (contract has, writer omits): {missing:?}\n  \
         extra   (writer emits, contract lacks): {extra:?}"
    );
}

/// The types the Go struct will decode into. `channel_id` is an `int64` and
/// therefore a JSON NUMBER — the same decision the eventgen field map records,
/// and the reason it is not a CWC-A2 decimal string: that rule is for monotonic
/// counters that grow past 2^53, not for a small per-reality index.
#[test]
fn the_scalar_types_match_what_go_would_decode() {
    let p = sample_payload();
    assert!(p["reality_id"].is_string(), "uuid.UUID decodes from a string");
    assert!(p["channel_id"].is_i64(), "int64 is a JSON number, not a string");
    assert!(p["from_epoch"].is_u64(), "uint32");
    assert!(p["to_epoch"].is_u64(), "uint32");
    assert!(p["digest"].is_string());
    assert!(p["authorised_by"].is_string());
    assert!(p["activated_at"].is_string(), "time.Time decodes from RFC-3339");
}

/// `digest` is 64 lowercase hex — *"the one spelling this value has outside
/// Rust"*, per the contract's own comment. An upper-case or truncated digest
/// would still be a `String` and would still decode.
#[test]
fn the_digest_is_the_one_spelling_the_contract_allows() {
    let p = sample_payload();
    let d = p["digest"].as_str().unwrap();
    assert_eq!(d.len(), 64, "a BLAKE3 digest is 64 hex characters");
    assert!(
        d.chars().all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c)),
        "lowercase hex only: {d}"
    );
}

/// The event NAME the writer stamps must be the one the registry declares, or
/// the dispatch table routes this nowhere.
#[test]
fn the_event_type_is_the_registered_name() {
    let registry = std::fs::read_to_string("../../contracts/events/_registry.yaml")
        .expect("the events registry must be readable");
    assert_eq!(commit_service::epoch_commit::EVENT_TYPE, "ruleset.epoch_activated");
    assert!(
        registry.contains(&format!("name: {}", commit_service::epoch_commit::EVENT_TYPE)),
        "commit-service stamps an event name the registry does not declare"
    );
}
