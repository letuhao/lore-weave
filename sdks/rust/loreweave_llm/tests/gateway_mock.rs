//! End-to-end tests for `GatewayClient::stream()` against a mocked gateway
//! (wiremock). Offline — no provider-registry-service, no lmstudio. Validates
//! the SSE parsing loop + tool-call reassembly across the real HTTP path.

use uuid::Uuid;
use wiremock::matchers::{method, path};
use wiremock::{Mock, MockServer, ResponseTemplate};

use loreweave_llm::{
    ChatStreamRequest, GatewayClient, LlmError, ModelSource, StreamEvent, StreamFormat,
    ToolCallAccumulator,
};

fn tool_request() -> ChatStreamRequest {
    ChatStreamRequest::new_chat_with_tools(
        ModelSource::PlatformModel,
        Uuid::nil(),
        vec![serde_json::json!({"role": "user", "content": "classify"})],
        vec![serde_json::json!({"type": "function", "function": {"name": "submit_zone_classifications"}})],
        StreamFormat::Openai,
    )
    .with_tool_choice(serde_json::json!({"type": "function", "function": {"name": "submit_zone_classifications"}}))
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

async fn collect(handle: &mut loreweave_llm::StreamHandle) -> Vec<Result<StreamEvent, LlmError>> {
    let mut out = Vec::new();
    while let Some(ev) = handle.next().await {
        out.push(ev);
    }
    out
}

#[tokio::test]
async fn streams_token_tool_call_usage_done() {
    let body = "\
event: token
data: {\"event\":\"token\",\"delta\":\"ok\"}

event: tool_call
data: {\"event\":\"tool_call\",\"index\":0,\"id\":\"call_1\",\"name\":\"submit_zone_classifications\",\"arguments_delta\":\"\"}

event: tool_call
data: {\"event\":\"tool_call\",\"index\":0,\"arguments_delta\":\"{\\\"classifications\\\":\"}

event: tool_call
data: {\"event\":\"tool_call\",\"index\":0,\"arguments_delta\":\"[]}\"}

event: usage
data: {\"event\":\"usage\",\"input_tokens\":120,\"output_tokens\":18}

event: done
data: {\"event\":\"done\",\"finish_reason\":\"tool_calls\"}

";
    let server = MockServer::start().await;
    mount_sse(&server, body).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let mut handle = client
        .stream(tool_request(), Uuid::nil())
        .await
        .expect("stream opens");

    let mut acc = ToolCallAccumulator::new();
    let mut events = Vec::new();
    while let Some(ev) = handle.next().await {
        let ev = ev.expect("no stream error");
        acc.push(&ev);
        events.push(ev);
    }

    // token, 3× tool_call, usage, done.
    assert_eq!(events.len(), 6, "events = {events:?}");
    assert!(matches!(events.last(), Some(StreamEvent::Done { .. })));
    assert!(events.iter().any(|e| matches!(e, StreamEvent::Usage { input_tokens, .. } if *input_tokens == 120)));

    let calls = acc.finish();
    assert_eq!(calls.len(), 1);
    assert_eq!(calls[0].id.as_deref(), Some("call_1"));
    assert_eq!(calls[0].name.as_deref(), Some("submit_zone_classifications"));
    assert_eq!(calls[0].arguments, r#"{"classifications":[]}"#);
}

#[tokio::test]
async fn non_2xx_status_surfaces_gateway_http_status() {
    let server = MockServer::start().await;
    Mock::given(method("POST"))
        .and(path("/internal/llm/stream"))
        .respond_with(ResponseTemplate::new(400).set_body_string(
            r#"{"error":{"code":"LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER","message":"provider 'anthropic' does not support tools/tool_choice"}}"#,
        ))
        .mount(&server)
        .await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let result = client.stream(tool_request(), Uuid::nil()).await;
    match result {
        Err(LlmError::GatewayHttpStatus { status, body }) => {
            assert_eq!(status, 400);
            assert!(body.contains("LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER"));
        }
        other => panic!("expected GatewayHttpStatus, got {other:?}"),
    }
}

#[tokio::test]
async fn error_event_terminates_stream_with_err() {
    let body = "\
event: token
data: {\"event\":\"token\",\"delta\":\"partial\"}

event: error
data: {\"event\":\"error\",\"code\":\"LLM_UPSTREAM_ERROR\",\"message\":\"boom\"}

";
    let server = MockServer::start().await;
    mount_sse(&server, body).await;
    let client = GatewayClient::new(server.uri(), "test-token");

    let mut handle = client
        .stream(tool_request(), Uuid::nil())
        .await
        .expect("stream opens");
    let events = collect(&mut handle).await;

    // The token arrives, then the error event terminates as an Err.
    assert_eq!(events.len(), 2, "events = {events:?}");
    assert!(matches!(&events[0], Ok(StreamEvent::Token { .. })));
    assert!(
        matches!(&events[1], Err(LlmError::GatewayErrorEvent { code, .. }) if code == "LLM_UPSTREAM_ERROR")
    );
}
