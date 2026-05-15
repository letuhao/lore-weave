//! Offline test for the Phase 0b L3 measurement harness — drives
//! `run_l3_measurement` against a wiremock gateway that streams a valid
//! `submit_zone_classifications` tool call. No provider-registry, no lmstudio.

use serde_json::json;
use uuid::Uuid;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

use tilemap_service::harness::run_l3_measurement;
use tilemap_service::llm::{GatewayClient, ModelSource};

/// Build an SSE body that streams `tool_args` (a JSON string) as the
/// `submit_zone_classifications` tool call, split into three argument
/// fragments, followed by usage + done.
fn tool_call_sse(tool_args: &str) -> String {
    // Split on CHAR boundaries (not byte fractions — `str::split_at` panics
    // mid-codepoint) so the helper is safe even if a fixture gains non-ASCII.
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
        json!({"event":"usage","input_tokens":840,"output_tokens":260}),
        json!({"event":"done","finish_reason":"tool_calls"}),
    ];
    frames
        .iter()
        .map(|f| format!("event: {}\ndata: {}\n\n", f["event"].as_str().unwrap(), f))
        .collect()
}

async fn mount(server: &MockServer, body: String) {
    Mock::given(method("POST"))
        .and(path("/internal/llm/stream"))
        .respond_with(
            ResponseTemplate::new(200)
                .insert_header("content-type", "text/event-stream")
                .set_body_string(body),
        )
        .mount(server)
        .await;
}

#[tokio::test]
async fn harness_reports_success_on_valid_tool_call() {
    // A clean classification for all three fixture objects (canon_kind from
    // each object's suggested list; snake_case tags).
    let args = json!({
        "classifications": [
            {"obj_id":"obj_1","canon_kind":"BanditCache","narrative_tag":"hidden_bandit_cache","canon_ref":null,"rationale":"treasure stash"},
            {"obj_id":"obj_2","canon_kind":"BanditCamp","narrative_tag":"forest_bandit_camp","canon_ref":null,"rationale":"a lair of bandits"},
            {"obj_id":"obj_3","canon_kind":"AncientTree","narrative_tag":"lotus_sect_elder_tree","canon_ref":"lotus_sect_homeland_v1","rationale":"the grove's iconic tree"}
        ]
    })
    .to_string();

    let server = MockServer::start().await;
    mount(&server, tool_call_sse(&args)).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let report = run_l3_measurement(&client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil())
        .await
        .expect("harness runs");

    assert!(report.tool_use_success, "report = {report:?}");
    assert_eq!(report.classifications_parsed, 3);
    assert_eq!(report.tool_calls_seen, 1);
    assert!(
        report.validation_errors.is_empty(),
        "validation errors = {:?}",
        report.validation_errors
    );
    assert_eq!(report.input_tokens, 840);
    assert_eq!(report.output_tokens, 260);
    assert_eq!(report.finish_reason.as_deref(), Some("ToolCalls"));
    assert!(report.failure.is_none());
    // Equivalent Haiku cost should be a small positive number.
    assert!(report.est_haiku_cost_usd() > 0.0);
}

#[tokio::test]
async fn harness_records_validation_errors_on_bad_classification() {
    // obj_2 gets a canon_kind NOT in its suggested list; obj_3 is missing.
    let args = json!({
        "classifications": [
            {"obj_id":"obj_1","canon_kind":"BanditCache","narrative_tag":"ok_tag"},
            {"obj_id":"obj_2","canon_kind":"LavaLair","narrative_tag":"ok_tag"}
        ]
    })
    .to_string();

    let server = MockServer::start().await;
    mount(&server, tool_call_sse(&args)).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let report = run_l3_measurement(&client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil())
        .await
        .expect("harness runs");

    // The tool call parsed (so tool-use mechanically succeeded) but the
    // content failed validation — the harness records both honestly.
    assert!(report.tool_use_success);
    assert_eq!(report.classifications_parsed, 2);
    assert!(
        !report.validation_errors.is_empty(),
        "expected R1/R3 violations"
    );
}

#[tokio::test]
async fn harness_records_failure_when_no_tool_call_streamed() {
    // The model replied with plain text instead of a tool call.
    let body = "event: token\ndata: {\"event\":\"token\",\"delta\":\"sure, here goes\"}\n\n\
                event: done\ndata: {\"event\":\"done\",\"finish_reason\":\"stop\"}\n\n"
        .to_string();
    let server = MockServer::start().await;
    mount(&server, body).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let report = run_l3_measurement(&client, ModelSource::PlatformModel, Uuid::nil(), Uuid::nil())
        .await
        .expect("harness runs even when tool-use fails");

    assert!(!report.tool_use_success);
    assert_eq!(report.tool_calls_seen, 0);
    assert!(report.failure.is_some(), "failure must be recorded");
}
