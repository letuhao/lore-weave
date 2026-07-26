//! LlmDriver dispatch tests against a mocked gateway (wiremock) — the same
//! offline pattern as the SDK's own `gateway_mock.rs`. Proves the full
//! decide() path: SSE reassembly → select-by-name → closed-set validation →
//! payload, and every reject route.

use commit_service::{decide, Candidate, CombatPayload, DecisionContext, Vocabulary, COMBAT_V1_JSON};
use loreweave_llm::{GatewayClient, ModelSource};
use sim_core::EntityId;
use uuid::Uuid;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

fn ctx() -> DecisionContext {
    DecisionContext {
        actor: EntityId(1),
        actor_label: "npc-1".into(),
        actor_hp: (80, 100),
        defending: false,
        candidates: vec![
            Candidate { id: EntityId(2), token: "hostile-2".into(), condition: "healthy" },
            Candidate { id: EntityId(3), token: "hostile-3".into(), condition: "critical" },
        ],
    }
}

async fn mount_sse(server: &MockServer, body: &str) {
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

async fn run(body: &str) -> commit_service::Dispatch {
    let server = MockServer::start().await;
    mount_sse(&server, body).await;
    let client = GatewayClient::new(server.uri(), "test-token");
    let vocab = Vocabulary::from_json(COMBAT_V1_JSON).unwrap();
    decide(&client, ModelSource::UserModel, Uuid::nil(), Uuid::nil(), &vocab, &ctx()).await
}

/// Happy path: fragmented strike tool-call reassembles, validates against
/// the offered candidates, and carries the usage numbers.
/// Kill-mutation: dropping the ToolCallAccumulator or the usage capture.
#[tokio::test]
async fn valid_strike_dispatch_end_to_end() {
    let body = "\
event: tool_call
data: {\"event\":\"tool_call\",\"index\":0,\"id\":\"c1\",\"name\":\"strike\",\"arguments_delta\":\"{\\\"target\\\":\"}

event: tool_call
data: {\"event\":\"tool_call\",\"index\":0,\"arguments_delta\":\"\\\"hostile-3\\\"}\"}

event: usage
data: {\"event\":\"usage\",\"input_tokens\":210,\"output_tokens\":18}

event: done
data: {\"event\":\"done\",\"finish_reason\":\"tool_calls\"}

";
    let d = run(body).await;
    assert_eq!(
        d.payload,
        Some(CombatPayload::Strike { attacker: EntityId(1), target: EntityId(3) })
    );
    assert_eq!(d.input_tokens, 210);
    assert_eq!(d.output_tokens, 18);
    assert_eq!(d.reject, None);
}

/// The tilemap lesson, inherited: an off-vocabulary echo call at a LOWER
/// index must not shadow the real call — selection is by name-in-vocabulary,
/// never `.first()`. Kill-mutation: `.first()`.
#[tokio::test]
async fn off_vocabulary_echo_call_does_not_shadow_the_real_one() {
    let body = "\
event: tool_call
data: {\"event\":\"tool_call\",\"index\":0,\"id\":\"c0\",\"name\":\"echo\",\"arguments_delta\":\"{}\"}

event: tool_call
data: {\"event\":\"tool_call\",\"index\":1,\"id\":\"c1\",\"name\":\"defend\",\"arguments_delta\":\"\"}

event: done
data: {\"event\":\"done\",\"finish_reason\":\"tool_calls\"}

";
    let d = run(body).await;
    assert_eq!(d.payload, Some(CombatPayload::Defend { actor: EntityId(1) }));
}

/// Hallucinated target → REJECT (→ caller commits the fallback). The
/// dispatch records the raw evidence for the audit trail.
#[tokio::test]
async fn hallucinated_target_rejects_with_evidence() {
    let body = "\
event: tool_call
data: {\"event\":\"tool_call\",\"index\":0,\"id\":\"c1\",\"name\":\"strike\",\"arguments_delta\":\"{\\\"target\\\":\\\"the-king\\\"}\"}

event: done
data: {\"event\":\"done\",\"finish_reason\":\"tool_calls\"}

";
    let d = run(body).await;
    assert_eq!(d.payload, None);
    assert!(d.reject.as_deref().unwrap().contains("the-king"));
    assert_eq!(d.raw_tool.as_deref(), Some("strike"));
}

/// Prose-only response (model ignored tool_choice) → NoToolCall reject.
#[tokio::test]
async fn prose_only_response_rejects() {
    let body = "\
event: token
data: {\"event\":\"token\",\"delta\":\"I attack the goblin!\"}

event: done
data: {\"event\":\"done\",\"finish_reason\":\"stop\"}

";
    let d = run(body).await;
    assert_eq!(d.payload, None);
    assert!(d.reject.as_deref().unwrap().contains("no tool call"));
}

/// A mid-stream gateway error is captured as a reject, and a tool call that
/// completed BEFORE the error is still salvaged (accumulator finish() works
/// on error-terminated streams — SDK contract).
#[tokio::test]
async fn mid_stream_error_still_salvages_completed_call() {
    let body = "\
event: tool_call
data: {\"event\":\"tool_call\",\"index\":0,\"id\":\"c1\",\"name\":\"flee\",\"arguments_delta\":\"\"}

event: error
data: {\"event\":\"error\",\"code\":\"LLM_PROVIDER_ERROR\",\"message\":\"upstream hiccup\"}

";
    let d = run(body).await;
    assert_eq!(d.payload, Some(CombatPayload::Flee { actor: EntityId(1) }));
    assert!(d.reject.as_deref().unwrap_or_default().contains("stream error") || d.reject.is_some());
}
