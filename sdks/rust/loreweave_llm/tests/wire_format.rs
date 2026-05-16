//! Wire-format conformance tests for `loreweave_llm` against
//! [`contracts/api/llm-gateway/v1/openapi.yaml`].
//!
//! These verify the Rust types speak the same JSON the gateway speaks. They
//! exist as integration tests because the gateway's wire format is the
//! contract — anything Rust-side that diverges from openapi will fail here.
//!
//! Earlier SDK drafts (pre-extraction) mirrored Pythonic field names from
//! `sdks/python/loreweave_llm/models.py` instead of the openapi YAML and
//! shipped 6 HIGH defects (discriminator `event_type` vs `event`, invented
//! `cached_tokens` field, required-vs-nullable mismatches, wrong auth header,
//! missing `user_id` query param). These tests are the regression guard.
//!
//! [`contracts/api/llm-gateway/v1/openapi.yaml`]: ../../../../contracts/api/llm-gateway/v1/openapi.yaml

use serde_json::json;
use uuid::Uuid;

use loreweave_llm::{
    ChatStreamRequest, FinishReason, ModelSource, Operation, StreamEvent, StreamFormat,
};

// ─── StreamEvent (response envelope) ──────────────────────────────────

#[test]
fn stream_event_deserialises_token_from_openapi_shape() {
    let wire = json!({"event": "token", "delta": "hello"});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("token event deserialises");
    match parsed {
        StreamEvent::Token { delta, index } => {
            assert_eq!(delta, "hello");
            assert_eq!(index, None);
        }
        other => panic!("expected Token, got {other:?}"),
    }
}

#[test]
fn stream_event_deserialises_token_with_index() {
    let wire = json!({"event": "token", "delta": "x", "index": 42});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("token+index deserialises");
    match parsed {
        StreamEvent::Token { delta, index } => {
            assert_eq!(delta, "x");
            assert_eq!(index, Some(42));
        }
        other => panic!("expected Token, got {other:?}"),
    }
}

#[test]
fn stream_event_deserialises_reasoning() {
    let wire = json!({"event": "reasoning", "delta": "thinking..."});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("reasoning event deserialises");
    assert!(matches!(parsed, StreamEvent::Reasoning { ref delta, .. } if delta == "thinking..."));
}

#[test]
fn stream_event_deserialises_usage_with_reasoning_tokens() {
    // openapi UsageEvent — field is `reasoning_tokens` (NOT `cached_tokens`).
    let wire = json!({
        "event": "usage",
        "input_tokens": 100,
        "output_tokens": 50,
        "reasoning_tokens": 200
    });
    let parsed: StreamEvent = serde_json::from_value(wire).expect("usage event deserialises");
    match parsed {
        StreamEvent::Usage {
            input_tokens,
            output_tokens,
            reasoning_tokens,
        } => {
            assert_eq!(input_tokens, 100);
            assert_eq!(output_tokens, 50);
            assert_eq!(reasoning_tokens, Some(200));
        }
        other => panic!("expected Usage, got {other:?}"),
    }
}

#[test]
fn stream_event_deserialises_usage_without_reasoning_tokens() {
    let wire = json!({"event": "usage", "input_tokens": 10, "output_tokens": 5});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("usage without reasoning_tokens");
    assert!(matches!(
        parsed,
        StreamEvent::Usage {
            reasoning_tokens: None,
            ..
        }
    ));
}

#[test]
fn stream_event_deserialises_done_with_finish_reason() {
    let wire = json!({"event": "done", "finish_reason": "stop"});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("done event deserialises");
    assert!(matches!(
        parsed,
        StreamEvent::Done {
            finish_reason: Some(FinishReason::Stop)
        }
    ));
}

#[test]
fn stream_event_deserialises_done_with_null_finish_reason() {
    // openapi DoneEvent.finish_reason is nullable — must NOT fail when null.
    let wire = json!({"event": "done", "finish_reason": null});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("done with null deserialises");
    assert!(matches!(parsed, StreamEvent::Done { finish_reason: None }));
}

#[test]
fn stream_event_deserialises_done_with_absent_finish_reason() {
    // Only [event] is required on DoneEvent — finish_reason may be absent.
    let wire = json!({"event": "done"});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("done w/o finish_reason");
    assert!(matches!(parsed, StreamEvent::Done { finish_reason: None }));
}

#[test]
fn stream_event_deserialises_all_finish_reason_variants() {
    for (wire_value, expected) in [
        ("stop", FinishReason::Stop),
        ("length", FinishReason::Length),
        ("content_filter", FinishReason::ContentFilter),
        ("tool_calls", FinishReason::ToolCalls),
        ("error", FinishReason::Error),
    ] {
        let wire = json!({"event": "done", "finish_reason": wire_value});
        let parsed: StreamEvent =
            serde_json::from_value(wire).unwrap_or_else(|e| panic!("finish_reason={wire_value}: {e}"));
        assert!(
            matches!(parsed, StreamEvent::Done { finish_reason: Some(fr) } if fr == expected),
            "finish_reason {wire_value} maps to {expected:?}"
        );
    }
}

#[test]
fn stream_event_deserialises_error() {
    let wire = json!({"event": "error", "code": "LLM_RATE_LIMITED", "message": "slow down"});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("error event deserialises");
    match parsed {
        StreamEvent::Error { code, message } => {
            assert_eq!(code, "LLM_RATE_LIMITED");
            assert_eq!(message, "slow down");
        }
        other => panic!("expected Error, got {other:?}"),
    }
}

#[test]
fn stream_event_deserialises_audio_chunk_with_hyphenated_discriminator() {
    // Wire discriminator value is "audio-chunk" (hyphen), NOT "audio_chunk".
    let wire = json!({
        "event": "audio-chunk",
        "sequence_id": 7,
        "data": "ZGF0YQ==",
        "final": true
    });
    let parsed: StreamEvent = serde_json::from_value(wire).expect("audio-chunk deserialises");
    match parsed {
        StreamEvent::AudioChunk {
            sequence_id,
            data,
            is_final,
        } => {
            assert_eq!(sequence_id, 7);
            assert_eq!(data, "ZGF0YQ==");
            assert!(is_final);
        }
        other => panic!("expected AudioChunk, got {other:?}"),
    }
}

#[test]
fn stream_event_rejects_event_type_field_name() {
    // REGRESSION GUARD: an earlier SDK draft used `event_type` (Pythonic SDK
    // field name) — gateway sends `event`, not `event_type`, so a payload
    // keyed on `event_type` must fail to deserialise.
    let wrong_wire = json!({"event_type": "token", "delta": "x"});
    let result: Result<StreamEvent, _> = serde_json::from_value(wrong_wire);
    assert!(
        result.is_err(),
        "discriminator field name `event_type` must NOT deserialise (openapi uses `event`)"
    );
}

// ─── ChatStreamRequest (request body) ────────────────────────────────

#[test]
fn chat_stream_request_serialises_to_openapi_field_names() {
    let req = ChatStreamRequest::new_chat_with_tools(
        ModelSource::PlatformModel,
        Uuid::parse_str("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee").unwrap(),
        vec![json!({"role": "user", "content": "hi"})],
        vec![json!({"type": "function", "function": {"name": "x"}})],
        StreamFormat::Anthropic,
    );
    let json_value: serde_json::Value =
        serde_json::to_value(&req).expect("ChatStreamRequest serialises");

    assert_eq!(json_value["operation"], "chat");
    assert_eq!(json_value["model_source"], "platform_model");
    assert_eq!(
        json_value["model_ref"],
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    );
    assert_eq!(json_value["stream_format"], "anthropic");
    assert!(json_value["tools"].is_array());
    assert_eq!(json_value["temperature"], 0.0);
    // `max_tokens` / `trace_id` skip-when-none — must NOT appear.
    assert!(json_value.get("max_tokens").is_none());
    assert!(json_value.get("trace_id").is_none());
}

#[test]
fn chat_stream_request_normalize_clamps_temperature() {
    let mut req = ChatStreamRequest::new_chat_with_tools(
        ModelSource::PlatformModel,
        Uuid::nil(),
        vec![],
        vec![],
        StreamFormat::Openai,
    );
    req.temperature = 5.0;
    let normalised = req.normalize();
    assert!(
        (normalised.temperature - 2.0).abs() < f32::EPSILON,
        "temperature must clamp to openapi maximum 2.0; got {}",
        normalised.temperature
    );

    let mut req2 = ChatStreamRequest::new_chat_with_tools(
        ModelSource::PlatformModel,
        Uuid::nil(),
        vec![],
        vec![],
        StreamFormat::Openai,
    );
    req2.temperature = -1.0;
    let normalised2 = req2.normalize();
    assert_eq!(normalised2.temperature, 0.0);
}

#[test]
fn chat_stream_request_normalize_coerces_max_tokens_zero_to_none() {
    let mut req = ChatStreamRequest::new_chat_with_tools(
        ModelSource::PlatformModel,
        Uuid::nil(),
        vec![],
        vec![],
        StreamFormat::Openai,
    );
    req.max_tokens = Some(0);
    let normalised = req.normalize();
    assert_eq!(
        normalised.max_tokens, None,
        "max_tokens=0 must normalise to None per gateway SDK convention"
    );
}

#[test]
fn operation_default_is_chat() {
    let op: Operation = Default::default();
    assert!(matches!(op, Operation::Chat));
}

#[test]
fn stream_format_default_is_openai() {
    let fmt: StreamFormat = Default::default();
    assert!(matches!(fmt, StreamFormat::Openai));
}

// ─── ToolCallEvent (Phase 0b) ─────────────────────────────────────────

#[test]
fn stream_event_deserialises_tool_call_first_fragment() {
    // First fragment for an index: carries id + name, empty arguments.
    let wire = json!({
        "event": "tool_call",
        "index": 0,
        "id": "call_abc",
        "name": "submit_zone_classifications",
        "arguments_delta": ""
    });
    let parsed: StreamEvent = serde_json::from_value(wire).expect("tool_call deserialises");
    match parsed {
        StreamEvent::ToolCall {
            index,
            id,
            name,
            arguments_delta,
        } => {
            assert_eq!(index, 0);
            assert_eq!(id.as_deref(), Some("call_abc"));
            assert_eq!(name.as_deref(), Some("submit_zone_classifications"));
            assert_eq!(arguments_delta, "");
        }
        other => panic!("expected ToolCall, got {other:?}"),
    }
}

#[test]
fn stream_event_deserialises_tool_call_absent_index_and_args_default() {
    // Gateway omits `index` when 0 and `arguments_delta` when empty
    // (shared-struct omitempty) — consumers must default both.
    let wire = json!({"event": "tool_call", "id": "call_x", "name": "t"});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("sparse tool_call deserialises");
    match parsed {
        StreamEvent::ToolCall {
            index,
            arguments_delta,
            ..
        } => {
            assert_eq!(index, 0, "absent index defaults to 0");
            assert_eq!(arguments_delta, "", "absent arguments_delta defaults to \"\"");
        }
        other => panic!("expected ToolCall, got {other:?}"),
    }
}

#[test]
fn stream_event_deserialises_tool_call_arguments_fragment() {
    // A later fragment carries only an arguments_delta slice and the index.
    let wire = json!({"event": "tool_call", "index": 1, "arguments_delta": "{\"a\":1}"});
    let parsed: StreamEvent = serde_json::from_value(wire).expect("arg fragment deserialises");
    match parsed {
        StreamEvent::ToolCall {
            index,
            id,
            name,
            arguments_delta,
        } => {
            assert_eq!(index, 1);
            assert_eq!(id, None);
            assert_eq!(name, None);
            assert_eq!(arguments_delta, r#"{"a":1}"#);
        }
        other => panic!("expected ToolCall, got {other:?}"),
    }
}

#[test]
fn chat_stream_request_serialises_tool_choice() {
    let req = ChatStreamRequest::new_chat_with_tools(
        ModelSource::PlatformModel,
        Uuid::nil(),
        vec![],
        vec![json!({"type": "function", "function": {"name": "submit_zone_classifications"}})],
        StreamFormat::Openai,
    )
    .with_tool_choice(json!({"type": "function", "function": {"name": "submit_zone_classifications"}}));
    let v: serde_json::Value = serde_json::to_value(&req).expect("serialises");
    assert_eq!(v["tool_choice"]["type"], "function");
    assert_eq!(
        v["tool_choice"]["function"]["name"],
        "submit_zone_classifications"
    );
}

#[test]
fn chat_stream_request_omits_tool_choice_when_unset() {
    let req = ChatStreamRequest::new_chat_with_tools(
        ModelSource::PlatformModel,
        Uuid::nil(),
        vec![],
        vec![],
        StreamFormat::Openai,
    );
    let v: serde_json::Value = serde_json::to_value(&req).expect("serialises");
    assert!(
        v.get("tool_choice").is_none(),
        "tool_choice skip-when-none — must NOT appear"
    );
}
