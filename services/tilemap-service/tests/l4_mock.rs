//! Phase 3 — mock-gateway integration tests for the L4 narration retry loop
//! (`run_l4_with_retries`) and the L3→L4 bootstrap. A wiremock gateway scripts
//! fail-then-succeed SSE responses to exercise the §5 partial-success retry +
//! §6 fallback branches a clean live model never produces.

use std::sync::atomic::{AtomicUsize, Ordering};

use serde_json::json;
use uuid::Uuid;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, Request, Respond, ResponseTemplate};

use tilemap_service::harness::bootstrap::bootstrap_small_reality;
use tilemap_service::harness::l4_prompt::ZoneNarrationInput;
use tilemap_service::harness::l4_retry::run_l4_with_retries;
use tilemap_service::harness::style::{NarrationLanguage, NarrationVoice, NarrativeTone};
use tilemap_service::llm::{GatewayClient, ModelSource};

/// A ≥50-char English narration (passes §4.3 R3 length + R4 language).
fn good() -> String {
    "You walk a long quiet road beneath grey autumn skies, where old pines \
     lean over the path and the wind carries the scent of distant rain."
        .to_string()
}

/// Wrap a tool-call argument JSON string as an SSE `tool_call` stream.
fn tool_sse(tool_name: &str, tool_args: &str) -> String {
    let chars: Vec<char> = tool_args.chars().collect();
    let third = chars.len() / 3;
    let a: String = chars[..third].iter().collect();
    let b: String = chars[third..third * 2].iter().collect();
    let c: String = chars[third * 2..].iter().collect();
    let frames = [
        json!({"event":"tool_call","index":0,"id":"call_1","name":tool_name,"arguments_delta":""}),
        json!({"event":"tool_call","index":0,"arguments_delta":a}),
        json!({"event":"tool_call","index":0,"arguments_delta":b}),
        json!({"event":"tool_call","index":0,"arguments_delta":c}),
        json!({"event":"usage","input_tokens":600,"output_tokens":400}),
        json!({"event":"done","finish_reason":"tool_calls"}),
    ];
    frames
        .iter()
        .map(|f| format!("event: {}\ndata: {}\n\n", f["event"].as_str().unwrap(), f))
        .collect()
}

/// An SSE body narrating the given `(zone_id, narration)` entries.
fn narrate_sse(entries: &[(&str, &str)]) -> String {
    let arr: Vec<_> = entries
        .iter()
        .map(|(z, n)| json!({"zone_id": z, "narration": n}))
        .collect();
    tool_sse("submit_zone_narrations", &json!({ "zone_narrations": arr }).to_string())
}

/// An SSE body classifying the given `(obj_id, canon_kind, tag)` entries.
fn classify_sse(entries: &[(&str, &str, &str)]) -> String {
    let arr: Vec<_> = entries
        .iter()
        .map(|(id, k, t)| json!({"obj_id": id, "canon_kind": k, "narrative_tag": t, "canon_ref": null}))
        .collect();
    tool_sse("submit_zone_classifications", &json!({ "classifications": arr }).to_string())
}

/// A responder returning each scripted `(status, body)` in turn, repeating the
/// last entry once the script is exhausted.
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

/// Build `ZoneNarrationInput`s with a fixed `forest` terrain + no L3 objects.
fn inputs(ids: &[&str]) -> Vec<ZoneNarrationInput> {
    ids.iter()
        .map(|z| ZoneNarrationInput {
            zone_id: z.to_string(),
            terrain: "forest".to_string(),
            l3_objects: vec![],
        })
        .collect()
}

async fn run(server: &MockServer, zone_ids: &[&str], max_attempts: u32) -> tilemap_service::harness::l4_retry::L4Result {
    let client = GatewayClient::new(server.uri(), "test-token");
    run_l4_with_retries(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &inputs(zone_ids),
        NarrationLanguage::En,
        NarrativeTone::Wuxia,
        NarrationVoice::SecondPerson,
        max_attempts,
    )
    .await
    .expect("valid input")
}

#[tokio::test]
async fn ac2_clean_l4_response_no_retry_no_fallback() {
    let body = narrate_sse(&[("zone_a", &good()), ("zone_b", &good())]);
    let server = scripted_server(vec![(200, body)]).await;
    let r = run(&server, &["zone_a", "zone_b"], 3).await;
    assert_eq!(r.llm_attempts, 1);
    assert_eq!(r.fallback_count, 0);
    assert_eq!(r.narrations.len(), 2);
}

#[tokio::test]
async fn ac3_retry_re_narrates_only_the_failing_subset() {
    // Attempt 1 — zone_b's narration is too short (R3). Attempt 2 — fixed.
    let a1 = narrate_sse(&[("zone_a", &good()), ("zone_b", "short")]);
    let a2 = narrate_sse(&[("zone_b", &good())]);
    let server = scripted_server(vec![(200, a1), (200, a2)]).await;
    let r = run(&server, &["zone_a", "zone_b"], 3).await;
    assert_eq!(r.llm_attempts, 2);
    assert_eq!(r.fallback_count, 0);
    assert_eq!(r.narrations.len(), 2);

    // The 2nd request must carry zone_b only (`zone_X: terrain=` is unique to
    // the real payload — the system-prompt example uses `zone=`).
    let reqs = server.received_requests().await.unwrap();
    let body2 = String::from_utf8_lossy(&reqs[1].body);
    assert!(body2.contains("zone_b: terrain="), "retry must re-narrate zone_b");
    assert!(!body2.contains("zone_a: terrain="), "retry must not re-narrate zone_a");
    assert!(body2.contains("re-narrate ONLY"), "retry must carry the reframed preamble");
}

#[tokio::test]
async fn ac4_persistent_failure_falls_back_after_max_attempts() {
    // Every attempt leaves zone_b too short.
    let body = narrate_sse(&[("zone_a", &good()), ("zone_b", "short")]);
    let server = scripted_server(vec![(200, body)]).await;
    let r = run(&server, &["zone_a", "zone_b"], 3).await;
    assert_eq!(r.llm_attempts, 3);
    assert_eq!(r.fallback_count, 1);
    assert_eq!(r.narrations.len(), 2);
    let zb = r.narrations.iter().find(|n| n.zone_id == "zone_b").unwrap();
    assert!(zb.narration.contains("Engine-default"), "zone_b → canonical default");
}

#[tokio::test]
async fn ac10_parsed_empty_response_is_a_validation_failure() {
    // Attempt 1 — a parsed-but-empty {"zone_narrations":[]}. Attempt 2 — clean.
    let a1 = tool_sse(
        "submit_zone_narrations",
        &json!({"zone_narrations": []}).to_string(),
    );
    let a2 = narrate_sse(&[("zone_a", &good()), ("zone_b", &good())]);
    let server = scripted_server(vec![(200, a1), (200, a2)]).await;
    let r = run(&server, &["zone_a", "zone_b"], 3).await;
    assert_eq!(r.llm_attempts, 2);
    assert_eq!(r.fallback_count, 0);
    assert_eq!(r.narrations.len(), 2);

    // The empty response was a *validation* failure → the retry carries the
    // [MISSING-NARRATION] errors (not a context-free fresh retry).
    let reqs = server.received_requests().await.unwrap();
    let body2 = String::from_utf8_lossy(&reqs[1].body);
    assert!(
        body2.contains("[MISSING-NARRATION]"),
        "the retry after a parsed-empty response must carry the missing-zone errors",
    );
}

#[tokio::test]
async fn ac7_bootstrap_runs_l3_then_l4() {
    let l3 = classify_sse(&[
        ("obj_1", "BanditCache", "t1"),
        ("obj_2", "AncientTree", "t2"),
        ("obj_3", "BanditCache", "t3"),
        ("obj_4", "BanditCamp", "t4"),
        ("obj_5", "BanditCamp", "t5"),
        ("obj_6", "AncientTree", "t6"),
    ]);
    let l4 = narrate_sse(&[
        ("jianghu_capital", &good()),
        ("western_wilds", &good()),
        ("lotus_grove", &good()),
    ]);
    let server = scripted_server(vec![(200, l3), (200, l4)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");
    let report = bootstrap_small_reality(&client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(), 3)
        .await
        .expect("bootstrap runs L3 then L4");

    assert_eq!(report.l3.classifications.len(), 6);
    assert_eq!(report.l3.fallback_count, 0);
    assert_eq!(report.l4.narrations.len(), 3);
    assert_eq!(report.l4.fallback_count, 0);
}

#[tokio::test]
async fn ac11_all_l3_fallback_zone_is_still_narrated() {
    // lotus_grove's objects (obj_5, obj_6) get canon_kinds not in their
    // suggested lists → both fall back in L3. With max_attempts=1 L3 makes one
    // call, then L4 makes one — two scripted responses.
    let l3 = classify_sse(&[
        ("obj_1", "BanditCache", "t1"),
        ("obj_2", "AncientTree", "t2"),
        ("obj_3", "BanditCache", "t3"),
        ("obj_4", "BanditCamp", "t4"),
        ("obj_5", "LavaLair", "t5"),
        ("obj_6", "LavaLair", "t6"),
    ]);
    let l4 = narrate_sse(&[
        ("jianghu_capital", &good()),
        ("western_wilds", &good()),
        ("lotus_grove", &good()),
    ]);
    let server = scripted_server(vec![(200, l3), (200, l4)]).await;
    let client = GatewayClient::new(server.uri(), "test-token");
    let report = bootstrap_small_reality(&client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(), 1)
        .await
        .expect("bootstrap runs");

    assert_eq!(report.l3.fallback_count, 2, "obj_5 + obj_6 fell back in L3");
    assert_eq!(report.l4.narrations.len(), 3, "every zone narrated, incl. lotus_grove");
    assert_eq!(report.l4.fallback_count, 0);
    let lg = report
        .l4
        .narrations
        .iter()
        .find(|n| n.zone_id == "lotus_grove")
        .expect("lotus_grove narrated");
    assert!(
        !lg.narration.contains("Engine-default"),
        "lotus_grove was L4-narrated despite its zone's L3 objects all falling back",
    );
}

#[tokio::test]
async fn duplicate_zone_id_errors_at_entry() {
    // `run_l4_with_retries`'s sole `Err` path — caught before any gateway call.
    let dup = vec![
        ZoneNarrationInput {
            zone_id: "dup".to_string(),
            terrain: "forest".to_string(),
            l3_objects: vec![],
        },
        ZoneNarrationInput {
            zone_id: "dup".to_string(),
            terrain: "grass".to_string(),
            l3_objects: vec![],
        },
    ];
    let client = GatewayClient::new("http://127.0.0.1:1".to_string(), "test-token");
    let err = run_l4_with_retries(
        &client,
        ModelSource::PlatformModel,
        Uuid::nil(),
        Uuid::nil(),
        &dup,
        NarrationLanguage::En,
        NarrativeTone::Wuxia,
        NarrationVoice::SecondPerson,
        3,
    )
    .await
    .expect_err("a duplicate zone_id must error at entry");
    assert!(err.to_string().contains("dup"), "error must name the duplicate zone: {err}");
}

#[tokio::test]
async fn transport_failure_clears_the_retry_context() {
    // Attempt 1 — HTTP 500 (transport failure). Attempt 2 must retry FRESH:
    // no validation errors existed, so its request carries no retry preamble.
    let ok = narrate_sse(&[("zone_a", &good()), ("zone_b", &good())]);
    let server = scripted_server(vec![(500, String::new()), (200, ok)]).await;
    let r = run(&server, &["zone_a", "zone_b"], 3).await;
    assert_eq!(r.llm_attempts, 2);
    assert_eq!(r.fallback_count, 0);

    let reqs = server.received_requests().await.unwrap();
    let body2 = String::from_utf8_lossy(&reqs[1].body);
    assert!(
        !body2.contains("re-narrate ONLY"),
        "a transport failure must not carry a retry-context preamble into the next attempt",
    );
}
