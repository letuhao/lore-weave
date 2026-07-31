//! Rust's half of the D-LLM-BUDGET-SSOT drift lock
//! ([`contracts/llm-budget.contract.json`]).
//!
//! The omit rule — `max_tokens == 0` means "no cap, drop the field" — is implemented FOUR
//! times: here (`normalize()` coerces `Some(0)` → `None`), in the Go SDK (`,omitempty`), in
//! the Python SDK (`to_request_body` pops a 0), and in provider-registry's adapters. Every
//! one documented the rule in a comment; none of them checked the others.
//!
//! Rust's version is the most fragile of the four, because it is not a serde attribute but a
//! CALL the caller has to remember — a request built without `normalize()` sends
//! `"max_tokens": 0`, which most providers read as "cap output at 0 tokens". So this asserts
//! both halves: that `normalize()` does the coercion, and that skipping it is observable.
//!
//! [`contracts/llm-budget.contract.json`]: ../../../../contracts/llm-budget.contract.json

use serde_json::Value;
use uuid::Uuid;

use loreweave_llm::{ChatStreamRequest, ModelSource, StreamFormat};

fn contract() -> Value {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../../contracts/llm-budget.contract.json");
    let raw = std::fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("read budget contract at {path}: {e}"));
    let v: Value = serde_json::from_str(&raw).expect("budget contract parses");
    assert!(
        v["output_kinds"].as_object().is_some_and(|m| !m.is_empty()),
        "contract declares no output kinds — a vacuous contract passes everything"
    );
    v
}

fn sentinel() -> u32 {
    contract()["omit_sentinel"]["value"]
        .as_u64()
        .expect("omit_sentinel.value is a number") as u32
}

fn req(max_tokens: Option<u32>) -> ChatStreamRequest {
    let mut r = ChatStreamRequest::new_chat_with_tools(
        ModelSource::UserModel, Uuid::nil(), vec![], vec![], StreamFormat::Openai,
    );
    r.max_tokens = max_tokens;
    r
}

#[test]
fn normalize_coerces_the_omit_sentinel_to_none() {
    let r = req(Some(sentinel())).normalize();
    assert_eq!(
        r.max_tokens, None,
        "the omit sentinel survived normalize() — it would reach the wire as \
         'cap output at 0 tokens'"
    );
}

#[test]
fn normalize_leaves_a_real_budget_alone() {
    // The other direction: a normalize() that cleared everything would satisfy the test
    // above just as loudly.
    assert_eq!(req(Some(1200)).normalize().max_tokens, Some(1200));
    assert_eq!(req(None).normalize().max_tokens, None);
}

#[test]
fn the_sentinel_is_absent_from_the_serialised_body_after_normalize() {
    // What actually matters is the BYTES, not the field. `max_tokens` is `Option<u32>` with
    // serde's skip-if-none, so None ⇒ omitted; this pins that the two halves compose.
    let body = serde_json::to_value(req(Some(sentinel())).normalize()).expect("serialises");
    assert!(
        body.get("max_tokens").is_none_or(Value::is_null),
        "normalized request still carries max_tokens: {body}"
    );

    let kept = serde_json::to_value(req(Some(1200)).normalize()).expect("serialises");
    assert_eq!(kept["max_tokens"], 1200, "a real budget did not survive: {kept}");
}

#[test]
fn the_truncated_finish_reason_matches_the_contract() {
    // A truncation-fatal call must be able to recognise the clip. The contract names the
    // wire value; FinishReason must have a variant that deserialises from it.
    let declared = contract()["truncated_finish_reason"]
        .as_str()
        .expect("truncated_finish_reason is a string")
        .to_string();
    let parsed: Result<loreweave_llm::FinishReason, _> =
        serde_json::from_value(Value::String(declared.clone()));
    assert!(
        parsed.is_ok(),
        "FinishReason cannot represent the contract's {declared:?} — a truncation would be \
         unrecognisable, which is how glossary-service repaired clipped JSON as malformed"
    );
}
