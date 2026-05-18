//! Phase 2 — mock-gateway integration tests for the L3 retry loop
//! (`run_l3_with_retries`). A wiremock gateway scripts fail-then-succeed SSE
//! responses to exercise the §5 partial-success retry + §6 canonical-default
//! fallback branches a clean live model never produces.

use std::sync::atomic::{AtomicUsize, Ordering};

use serde_json::json;
use uuid::Uuid;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, Request, Respond, ResponseTemplate};

use tilemap_service::harness::prompt::{L3Placeholder, fixture_placeholders};
use tilemap_service::harness::retry::{run_l3_batched, run_l3_with_retries};
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

// NOTE: the former `ac6_bootstrap_small_reality_end_to_end` was removed in the
// engine→L3 bootstrap rewire (2026-05-18). It hardcoded the retired 6-object
// fixture set + 3-zone template; the bootstrap now classifies a variable
// engine-placed object set. End-to-end `bootstrap_small_reality` coverage
// moved to `l4_mock.rs::ac7_bootstrap_runs_l3_then_l4`, which uses a
// request-parsing mock that adapts to the engine's actual object set.

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

// ── run_l3_batched (continent-scale per-zone batching) ────────────────────

/// An L3 placeholder in `zone` with a non-empty suggested set.
fn ph(obj_id: &str, zone: &str) -> L3Placeholder {
    L3Placeholder::new(obj_id, "Treasure", zone, &["BanditCache", "AbandonedCellar", "OldShrine"])
}

#[tokio::test]
async fn run_l3_batched_classifies_every_object_exactly_once() {
    // AC-2 — batches are a disjoint partition; the aggregate covers every
    // obj_id exactly once. max_attempts=0 ⇒ no gateway call, all §6 fallback —
    // this exercises the grouping + chunking + aggregation, no server needed.
    let phs: Vec<L3Placeholder> = vec![
        ph("obj_1", "zone_a"), ph("obj_2", "zone_a"), ph("obj_3", "zone_a"),
        ph("obj_4", "zone_b"), ph("obj_5", "zone_b"),
        ph("obj_6", "zone_c"),
    ];
    let r = run_l3_batched(
        &unused_client(), ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(),
        &phs, &[], 0, 2,
    )
    .await
    .expect("valid input");

    assert_eq!(r.llm_attempts, 0, "max_attempts=0 issues no gateway call");
    assert_eq!(r.fallback_count, 6, "every object fell back");
    assert_eq!(r.input_tokens, 0);
    let mut ids: Vec<&str> = r.classifications.iter().map(|c| c.obj_id.as_str()).collect();
    ids.sort_unstable();
    assert_eq!(ids, ["obj_1", "obj_2", "obj_3", "obj_4", "obj_5", "obj_6"], "exactly-once union");
}

#[tokio::test]
async fn run_l3_batched_issues_one_call_per_batch() {
    // AC-1/AC-3 — zone_a (5 objects) chunks(2) → 3 batches, zone_b (3) → 2;
    // 5 batches ⇒ 5 gateway calls, and llm_attempts sums to 5.
    let phs: Vec<L3Placeholder> = (1..=5)
        .map(|i| ph(&format!("obj_{i}"), "zone_a"))
        .chain((6..=8).map(|i| ph(&format!("obj_{i}"), "zone_b")))
        .collect();
    // A dummy response (classifies an object not in any batch) ⇒ each batch
    // falls back after its single attempt; we only count the requests.
    let server = scripted_server(vec![(200, classify_sse(&[("obj_x", "BanditCache", "t")]))]).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let r = run_l3_batched(
        &client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(),
        &phs, &[], 1, 2,
    )
    .await
    .expect("valid input");

    assert_eq!(server.received_requests().await.unwrap().len(), 5, "one call per batch");
    assert_eq!(r.llm_attempts, 5, "llm_attempts sums across batches");
    assert_eq!(r.classifications.len(), 8, "every object still classified");
    assert_eq!(r.fallback_count, 8, "the dummy response classified nothing valid");
}

#[tokio::test]
async fn run_l3_batched_aggregates_accepted_classifications_and_tokens() {
    // The happy path — each per-zone batch's LLM-accepted classifications (not
    // just §6 fallbacks) survive into the aggregate, and token counts sum.
    // zone_a (obj_1, obj_2) + zone_b (obj_3) ⇒ 2 batches at batch_size=2; one
    // scripted response per batch, classifying that batch's objects validly.
    let phs = vec![ph("obj_1", "zone_a"), ph("obj_2", "zone_a"), ph("obj_3", "zone_b")];
    let batch_a = classify_sse(&[
        ("obj_1", "BanditCache", "t1"),
        ("obj_2", "AbandonedCellar", "t2"),
    ]);
    let batch_b = classify_sse(&[("obj_3", "OldShrine", "t3")]);
    let server = scripted_server(vec![(200, batch_a), (200, batch_b)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let r = run_l3_batched(
        &client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(),
        &phs, &[], 3, 2,
    )
    .await
    .expect("valid input");

    assert_eq!(r.fallback_count, 0, "every object was LLM-classified, not a fallback");
    assert_eq!(r.llm_attempts, 2, "one clean attempt per batch");
    assert_eq!(r.classifications.len(), 3);
    let kind = |id: &str| {
        r.classifications.iter().find(|c| c.obj_id == id).unwrap().canon_kind.as_str()
    };
    assert_eq!(kind("obj_1"), "BanditCache", "batch-a accepted classification survived");
    assert_eq!(kind("obj_3"), "OldShrine", "batch-b accepted classification survived");
    // `tool_call_sse` scripts a usage event of 500 in / 200 out per call —
    // 2 batches ⇒ the aggregate sums them (AC-3).
    assert_eq!(r.input_tokens, 1000, "input tokens sum across batches");
    assert_eq!(r.output_tokens, 400, "output tokens sum across batches");
}

#[tokio::test]
async fn run_l3_batched_empty_input_is_an_empty_result() {
    let r = run_l3_batched(
        &unused_client(), ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(),
        &[], &[], 3, 2,
    )
    .await
    .expect("empty input is valid");
    assert!(r.classifications.is_empty());
    assert_eq!(r.llm_attempts, 0);
    assert_eq!(r.fallback_count, 0);
}

#[tokio::test]
async fn run_l3_batched_rejects_a_cross_batch_duplicate_obj_id() {
    // The global precondition catches a duplicate that per-batch checks (each
    // batch internally unique) would miss.
    let phs = vec![ph("obj_1", "zone_a"), ph("obj_1", "zone_b")];
    let err = run_l3_batched(
        &unused_client(), ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(),
        &phs, &[], 3, 2,
    )
    .await
    .expect_err("a cross-batch duplicate obj_id must error at entry");
    assert!(err.to_string().contains("obj_1"), "error names the duplicate: {err}");
}
