//! Phase 2 — mock-gateway integration tests for the L3 retry loop
//! (`run_l3_with_retries`). A wiremock gateway scripts fail-then-succeed SSE
//! responses to exercise the §5 partial-success retry + §6 canonical-default
//! fallback branches a clean live model never produces.

use std::sync::atomic::{AtomicUsize, Ordering};

use serde_json::json;
use uuid::Uuid;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, Request, Respond, ResponseTemplate};

use tilemap_service::harness::bootstrap::bootstrap_small_reality;
use tilemap_service::harness::prompt::{L3Placeholder, fixture_placeholders};
use tilemap_service::harness::retry::run_l3_with_retries;
use tilemap_service::llm::{GatewayClient, ModelSource};

/// Wrap a tool-call argument JSON string as an SSE `tool_call` stream (the
/// canonical gateway envelope — three argument fragments + usage + done).
fn tool_call_sse(tool_args: &str) -> String {
    let chars: Vec<char> = tool_args.chars().collect();
    let third = chars.len() / 3;
    let a: String = chars[..third].iter().collect();
    let b: String = chars[third..third * 2].iter().collect();
    let c: String = chars[third * 2..].iter().collect();
    let frames = [
        json!({"event":"tool_call","index":0,"id":"call_1","name":"submit_zone_classifications","arguments_delta":""}),
        json!({"event":"tool_call","index":0,"arguments_delta":a}),
        json!({"event":"tool_call","index":0,"arguments_delta":b}),
        json!({"event":"tool_call","index":0,"arguments_delta":c}),
        json!({"event":"usage","input_tokens":500,"output_tokens":200}),
        json!({"event":"done","finish_reason":"tool_calls"}),
    ];
    frames
        .iter()
        .map(|f| format!("event: {}\ndata: {}\n\n", f["event"].as_str().unwrap(), f))
        .collect()
}

/// An SSE body classifying the given `(obj_id, canon_kind, narrative_tag)`
/// entries (all with `canon_ref: null`).
fn classify_sse(entries: &[(&str, &str, &str)]) -> String {
    let arr: Vec<_> = entries
        .iter()
        .map(|(id, kind, tag)| {
            json!({"obj_id": id, "canon_kind": kind, "narrative_tag": tag, "canon_ref": null})
        })
        .collect();
    tool_call_sse(&json!({ "classifications": arr }).to_string())
}

/// A responder that returns each scripted `(status, body)` in turn, repeating
/// the last entry once the script is exhausted.
struct Scripted {
    responses: Vec<(u16, String)>,
    next: AtomicUsize,
}

impl Respond for Scripted {
    fn respond(&self, _: &Request) -> ResponseTemplate {
        let i = self
            .next
            .fetch_add(1, Ordering::SeqCst)
            .min(self.responses.len() - 1);
        let (status, body) = &self.responses[i];
        ResponseTemplate::new(*status)
            .insert_header("content-type", "text/event-stream")
            .set_body_string(body.clone())
    }
}

async fn scripted_server(responses: Vec<(u16, String)>) -> MockServer {
    assert!(!responses.is_empty(), "scripted_server needs at least one response");
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/internal/llm/stream"))
        .respond_with(Scripted {
            responses,
            next: AtomicUsize::new(0),
        })
        .mount(&server)
        .await;
    server
}

/// A `GatewayClient` pointing at a dead address — for tests whose code path
/// never issues a gateway call.
fn unused_client() -> GatewayClient {
    GatewayClient::new("http://127.0.0.1:1".to_string(), "test-token")
}

#[tokio::test]
async fn ac2_clean_first_response_no_retry_no_fallback() {
    let body = classify_sse(&[
        ("obj_1", "BanditCache", "bandit_cache"),
        ("obj_2", "BanditCamp", "bandit_camp"),
        ("obj_3", "AncientTree", "ancient_tree"),
    ]);
    let server = scripted_server(vec![(200, body)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let result = run_l3_with_retries(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &fixture_placeholders(),
        &[],
        3,
    )
    .await
    .expect("valid input");

    assert_eq!(result.llm_attempts, 1, "a clean response needs no retry");
    assert_eq!(result.fallback_count, 0);
    assert_eq!(result.classifications.len(), 3);
}

#[tokio::test]
async fn ac3_retry_re_sends_only_the_failing_subset() {
    // Attempt 1 — obj_3 has a canon_kind not in its suggested list (R3).
    let attempt1 = classify_sse(&[
        ("obj_1", "BanditCache", "ok_one"),
        ("obj_2", "BanditCamp", "ok_two"),
        ("obj_3", "LavaLair", "ok_three"),
    ]);
    // Attempt 2 — obj_3 fixed.
    let attempt2 = classify_sse(&[("obj_3", "AncientTree", "ok_three")]);
    let server = scripted_server(vec![(200, attempt1), (200, attempt2)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let result = run_l3_with_retries(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &fixture_placeholders(),
        &[],
        3,
    )
    .await
    .expect("valid input");

    assert_eq!(result.llm_attempts, 2);
    assert_eq!(result.fallback_count, 0);
    assert_eq!(result.classifications.len(), 3);

    // The 2nd request must carry obj_3 ONLY — partial-success preservation.
    // Match the real payload line (`suggested_canon_kind=`), not the system
    // prompt's few-shot example (which uses the shorter `suggested=`).
    let reqs = server.received_requests().await.unwrap();
    assert_eq!(reqs.len(), 2);
    let body2 = String::from_utf8_lossy(&reqs[1].body);
    // `obj_N: zone=` is unique to the real payload (the system-prompt few-shot
    // example renders objects without a `zone=` field).
    assert!(body2.contains("obj_3: zone="), "retry must re-send obj_3");
    assert!(!body2.contains("obj_1: zone="), "retry must not re-send obj_1");
    assert!(!body2.contains("obj_2: zone="), "retry must not re-send obj_2");
    // The retry must carry the §4.2 reframed-preamble context (D3) — guards
    // against the retry-context message being silently dropped.
    assert!(
        body2.contains("re-classify ONLY"),
        "retry request must carry the §4.2 reframed retry-context preamble",
    );
}

#[tokio::test]
async fn ac6_bootstrap_small_reality_end_to_end() {
    // place_tilemap (offline Phase-1 engine) + the L3 retry loop over the six
    // bootstrap fixture objects, classified clean in one mock response.
    let body = classify_sse(&[
        ("obj_1", "BanditCache", "cap_treasure"),
        ("obj_2", "AncientTree", "cap_landmark"),
        ("obj_3", "BanditCache", "wilds_treasure"),
        ("obj_4", "BanditCamp", "wilds_lair"),
        ("obj_5", "BanditCamp", "grove_lair"),
        ("obj_6", "AncientTree", "grove_landmark"),
    ]);
    let server = scripted_server(vec![(200, body)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let report = bootstrap_small_reality(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        3,
    )
    .await
    .expect("bootstrap runs end-to-end");

    assert_eq!(report.tilemap.zones.len(), 3, "the 3-zone template was placed");
    assert_eq!(report.l3.classifications.len(), 6, "all 6 fixture objects classified");
    assert_eq!(report.l3.fallback_count, 0);
    assert_eq!(report.l3.llm_attempts, 1);
}

#[tokio::test]
async fn ac4_persistent_failure_falls_back_after_max_attempts() {
    // Every attempt leaves obj_3 invalid; obj_1/obj_2 are always valid.
    let body = classify_sse(&[
        ("obj_1", "BanditCache", "ok_one"),
        ("obj_2", "BanditCamp", "ok_two"),
        ("obj_3", "LavaLair", "ok_three"),
    ]);
    let server = scripted_server(vec![(200, body)]).await; // repeats
    let client = GatewayClient::new(server.uri(), "test-token");

    let result = run_l3_with_retries(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &fixture_placeholders(),
        &[],
        3,
    )
    .await
    .expect("valid input");

    assert_eq!(result.llm_attempts, 3);
    assert_eq!(result.fallback_count, 1);
    assert_eq!(result.classifications.len(), 3);
    let obj3 = result
        .classifications
        .iter()
        .find(|c| c.obj_id == "obj_3")
        .unwrap();
    assert_eq!(obj3.canon_kind, "AncientTree", "obj_3 → canonical default (suggested[0])");
    assert!(
        obj3.rationale.as_deref().unwrap_or("").contains("Canonical default"),
        "obj_3 should carry the canonical-default rationale",
    );
}

#[tokio::test]
async fn ac8_empty_suggested_canon_kind_errors_at_entry() {
    let bad = vec![L3Placeholder::new("obj_1", "Treasure", "zone_1", &[])];
    let err = run_l3_with_retries(
        &unused_client(),
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &bad,
        &[],
        3,
    )
    .await
    .expect_err("empty suggested_canon_kind must error at entry");
    assert!(
        err.to_string().contains("obj_1"),
        "error must name the offending obj_id: {err}",
    );
}

#[tokio::test]
async fn ac9_max_attempts_zero_is_all_fallback() {
    let result = run_l3_with_retries(
        &unused_client(),
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &fixture_placeholders(),
        &[],
        0,
    )
    .await
    .expect("valid input");

    assert_eq!(result.llm_attempts, 0, "no gateway call when max_attempts == 0");
    assert_eq!(result.fallback_count, 3);
    assert_eq!(result.classifications.len(), 3);
}

#[tokio::test]
async fn ac10_mid_loop_transport_error_still_completes() {
    let ok = classify_sse(&[
        ("obj_1", "BanditCache", "ok_one"),
        ("obj_2", "BanditCamp", "ok_two"),
        ("obj_3", "AncientTree", "ok_three"),
    ]);
    // Attempt 1 — HTTP 500 (transport failure); attempt 2 — clean success.
    let server = scripted_server(vec![(500, String::new()), (200, ok)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let result = run_l3_with_retries(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &fixture_placeholders(),
        &[],
        3,
    )
    .await
    .expect("the loop completes despite a transport error");

    assert_eq!(result.llm_attempts, 2, "the failed attempt still counts");
    assert_eq!(result.fallback_count, 0);
    assert_eq!(result.classifications.len(), 3);
}

#[tokio::test]
async fn ac12_partial_final_attempt_no_double_count() {
    // max_attempts = 2. Attempt 1 — only obj_1 valid. Attempt 2 (the FINAL
    // one) — obj_2 fixed, obj_3 still invalid → obj_3 falls back.
    let attempt1 = classify_sse(&[
        ("obj_1", "BanditCache", "ok_one"),
        ("obj_2", "LavaLair", "bad_two"),
        ("obj_3", "LavaLair", "bad_three"),
    ]);
    let attempt2 = classify_sse(&[
        ("obj_2", "BanditCamp", "ok_two"),
        ("obj_3", "LavaLair", "still_bad"),
    ]);
    let server = scripted_server(vec![(200, attempt1), (200, attempt2)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let result = run_l3_with_retries(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &fixture_placeholders(),
        &[],
        2,
    )
    .await
    .expect("valid input");

    assert_eq!(result.llm_attempts, 2);
    assert_eq!(result.fallback_count, 1, "only obj_3 falls back");

    // Exactly-once — obj_1/obj_2/obj_3 each appear exactly one time.
    assert_eq!(result.classifications.len(), 3);
    let mut ids: Vec<&str> = result
        .classifications
        .iter()
        .map(|c| c.obj_id.as_str())
        .collect();
    ids.sort_unstable();
    assert_eq!(ids, ["obj_1", "obj_2", "obj_3"]);

    // obj_2 was LLM-classified on the final attempt (not a fallback).
    let obj2 = result
        .classifications
        .iter()
        .find(|c| c.obj_id == "obj_2")
        .unwrap();
    assert_eq!(obj2.canon_kind, "BanditCamp");
    // obj_3 is the canonical-default fallback.
    let obj3 = result
        .classifications
        .iter()
        .find(|c| c.obj_id == "obj_3")
        .unwrap();
    assert!(obj3.rationale.as_deref().unwrap_or("").contains("Canonical default"));
}

#[tokio::test]
async fn transport_failure_clears_the_retry_context() {
    // Attempt 1 — HTTP 500 (transport failure). Attempt 2 must retry FRESH:
    // no validation errors existed, so its request carries no retry preamble.
    let ok = classify_sse(&[
        ("obj_1", "BanditCache", "ok_one"),
        ("obj_2", "BanditCamp", "ok_two"),
        ("obj_3", "AncientTree", "ok_three"),
    ]);
    let server = scripted_server(vec![(500, String::new()), (200, ok)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");
    let result = run_l3_with_retries(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &fixture_placeholders(),
        &[],
        3,
    )
    .await
    .expect("the loop completes despite the transport error");
    assert_eq!(result.llm_attempts, 2);

    let reqs = server.received_requests().await.unwrap();
    let body2 = String::from_utf8_lossy(&reqs[1].body);
    assert!(
        !body2.contains("re-classify ONLY"),
        "a transport failure must not carry a retry-context preamble into the next attempt",
    );
}
