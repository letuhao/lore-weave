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

/// Parse one L3 `user_payload` object line —
/// `  obj_N: zone=Z kind=K suggested_canon_kind=[A,B,C]` — into
/// `(obj_id, first_suggested_kind)`. The bootstrap places a *variable*
/// engine-derived object set, so the L3 mock cannot hardcode obj_ids — it
/// echoes back whatever the request asked it to classify.
fn parse_obj_line(line: &str) -> Option<(String, String)> {
    let line = line.trim();
    if !line.starts_with("obj_") {
        return None;
    }
    let obj_id = line.split(':').next()?.trim().to_string();
    let inner = line.split("suggested_canon_kind=[").nth(1)?.split(']').next()?;
    let first = inner.split(',').next()?.trim().to_string();
    (!first.is_empty()).then_some((obj_id, first))
}

/// A two-call mock for `bootstrap_small_reality`: call 0 is the L3 request —
/// parsed, then echoed with one classification per object (its default
/// suggested kind, or a deliberately-invalid kind when `l3_fallback_all` is
/// set, to force every object through the §6 canonical-default fallback);
/// call 1+ returns the static L4 narration body.
struct BootstrapMock {
    calls: AtomicUsize,
    l4_body: String,
    l3_fallback_all: bool,
}

impl Respond for BootstrapMock {
    fn respond(&self, req: &Request) -> ResponseTemplate {
        let n = self.calls.fetch_add(1, Ordering::SeqCst);
        let body = if n == 0 {
            // `req.body` is the StreamRequest JSON — the L3 `user_payload`
            // newlines are JSON-escaped, so un-escape `\n` before splitting.
            // System-prompt example lines use `suggested=[` (not
            // `suggested_canon_kind=[`), so `parse_obj_line` ignores them.
            let text = String::from_utf8_lossy(&req.body).replace("\\n", "\n");
            let parsed: Vec<(String, String)> = text.lines().filter_map(parse_obj_line).collect();
            let entries: Vec<(&str, &str, &str)> = parsed
                .iter()
                .map(|(id, sug)| {
                    let kind = if self.l3_fallback_all { "__not_a_suggested_kind__" } else { sug.as_str() };
                    (id.as_str(), kind, "t")
                })
                .collect();
            classify_sse(&entries)
        } else {
            self.l4_body.clone()
        };
        ResponseTemplate::new(200)
            .insert_header("content-type", "text/event-stream")
            .set_body_string(body)
    }
}

async fn bootstrap_mock_server(l4_body: String, l3_fallback_all: bool) -> MockServer {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/internal/llm/stream"))
        .respond_with(BootstrapMock {
            calls: AtomicUsize::new(0),
            l4_body,
            l3_fallback_all,
        })
        .mount(&server)
        .await;
    server
}

/// The four zone_ids `bootstrap_template` defines (all narrated by L4).
const BOOTSTRAP_ZONES: [&str; 4] =
    ["jianghu_capital", "western_wilds", "lotus_grove", "forbidden_vault"];

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
    // The bootstrap classifies its own engine-placed object set (a variable
    // count) — the L3 mock echoes a valid classification for each, then L4
    // narrates all four template zones.
    let g = good();
    let l4_entries: Vec<(&str, &str)> = BOOTSTRAP_ZONES.iter().map(|z| (*z, g.as_str())).collect();
    let server = bootstrap_mock_server(narrate_sse(&l4_entries), false).await;
    let client = GatewayClient::new(server.uri(), "test-token");
    let report = bootstrap_small_reality(&client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(), 3)
        .await
        .expect("bootstrap runs L3 then L4");

    assert!(!report.l3.classifications.is_empty(), "L3 classified the engine objects");
    assert_eq!(
        report.l3.classifications.len(),
        report.tilemap.object_placements.len(),
        "every engine-placed object was classified",
    );
    assert_eq!(report.l3.fallback_count, 0, "a clean L3 echo — no fallback");
    assert_eq!(report.l3.llm_attempts, 1, "a clean L3 echo completes in one attempt");
    assert_eq!(report.l4.narrations.len(), 4, "all four zones narrated");
    assert_eq!(report.l4.fallback_count, 0);
}

#[tokio::test]
async fn ac11_zones_are_narrated_even_when_every_l3_object_falls_back() {
    // The L3 mock returns an invalid canon_kind for every engine object ⇒ all
    // fall back to the §6 canonical default. L4 must still narrate every zone
    // cleanly (the L4 join is robust to total L3 fallback). max_attempts=1 so
    // L3 makes exactly one call before the L4 body is served.
    let g = good();
    let l4_entries: Vec<(&str, &str)> = BOOTSTRAP_ZONES.iter().map(|z| (*z, g.as_str())).collect();
    let server = bootstrap_mock_server(narrate_sse(&l4_entries), true).await;
    let client = GatewayClient::new(server.uri(), "test-token");
    let report = bootstrap_small_reality(&client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil(), 1)
        .await
        .expect("bootstrap runs");

    assert!(!report.l3.classifications.is_empty());
    assert_eq!(
        report.l3.fallback_count,
        report.l3.classifications.len(),
        "every L3 object fell back — each got an invalid canon_kind",
    );
    assert_eq!(report.l4.narrations.len(), 4, "every zone narrated despite total L3 fallback");
    assert_eq!(report.l4.fallback_count, 0);
    for n in &report.l4.narrations {
        assert!(
            !n.narration.contains("Engine-default"),
            "zone {} was L4-narrated, not L3-fallback'd",
            n.zone_id,
        );
    }
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
