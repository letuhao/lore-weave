# loreweave_llm — Rust SDK

Rust client for the LoreWeave unified LLM gateway. Mirror of [`sdks/python/loreweave_llm`](../../python/loreweave_llm).

> **Status: Phase 0a (2026-05-14).** Wire-type mirrors + `GatewayClient` with `from_env()` + correct `X-Internal-Token` auth + required `user_id` query parameter. The actual streaming call (`GatewayClient::stream`) returns `LlmError::NotImplementedPhase0a` — SSE parsing lands at Phase 0b.

---

## Why this exists

Per CLAUDE.md **provider gateway invariant**, no LoreWeave service may call a provider SDK (anthropic / openai / litellm / etc.) directly. All LLM access routes through the unified gateway at `provider-registry-service`. The Python SDK [`sdks/python/loreweave_llm`](../../python/loreweave_llm) has covered this for Go-via-FFI, Python, and TypeScript services since Phase 1b.

`services/tilemap-service` (the first Rust microservice) needed a typed client; this crate is that client, extracted from the original in-service module so any future Rust service can depend on the same surface.

## Contract source

The SDK's wire types mirror [`contracts/api/llm-gateway/v1/openapi.yaml`](../../../contracts/api/llm-gateway/v1/openapi.yaml). Hand-rolled, not generated — the surface is small (~150 lines). Wire-format conformance is verified in `tests/wire_format.rs` against canonical JSON shapes from the openapi schema.

## What ships in Phase 0a

| Component | Status |
|---|---|
| `ChatStreamRequest` — request body for `/internal/llm/stream` | ✅ mirrors openapi `ChatStreamRequest` |
| `StreamEvent` — tagged discriminator on `event` field | ✅ mirrors openapi `StreamEventEnvelope` (Token / Reasoning / Usage / Done / Error / AudioChunk) |
| `FinishReason` — closed enum on `DoneEvent` | ✅ 5 variants `[stop, length, content_filter, tool_calls, error]` |
| `ModelSource`, `StreamFormat`, `Operation` enums | ✅ |
| `LlmError` — typed error variants | ✅ 8 variants |
| `GatewayClient::from_env()` — fails fast on missing `LOREWEAVE_INTERNAL_TOKEN` | ✅ |
| `GatewayClient::stream(req, user_id)` — returns `NotImplementedPhase0a` | ⏸ Phase 0b |
| SSE parsing loop | ⏸ Phase 0b |
| Retry / fallback patterns (TMP_008b §5/§6) | ⏸ Phase 2 |
| Async-job submission (`SubmitJobRequest`) | ⏸ Later phase |

## Quick start (post Phase 0b)

```rust
use loreweave_llm::{
    GatewayClient, ChatStreamRequest, ModelSource, StreamFormat,
};
use uuid::Uuid;

let client = GatewayClient::from_env()?;          // reads LOREWEAVE_INTERNAL_TOKEN
let model_ref = Uuid::parse_str(env!("LMSTUDIO_MODEL_REF"))?;
let user_id = Uuid::parse_str(env!("USER_ID"))?;

let request = ChatStreamRequest::new_chat_with_tools(
    ModelSource::PlatformModel,
    model_ref,
    vec![serde_json::json!({"role": "user", "content": "Hello"})],
    vec![/* OpenAI-shaped tool definitions */],
    StreamFormat::Anthropic,
).normalize();

let _handle = client.stream(request, user_id).await?;  // Phase 0b implements
```

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LOREWEAVE_INTERNAL_TOKEN` | **Yes** | (no default — fail-fast) | Bearer-style token in the `X-Internal-Token` header |
| `LOREWEAVE_GATEWAY_URL` | No | `http://provider-registry-service:8085` | Gateway base URL |

## Known limitations / contract gaps

These are documented for downstream design tracks (TMP_008b feedback path):

1. **Anthropic `cache_control` not exposed.** The gateway translates provider-native delta formats but does not surface Anthropic-specific prompt-caching headers / metadata. Callers cannot observe cache hit rate via this SDK. If empirical Anthropic prompt-caching measurement is required, either (a) accept it as gateway-managed and opaque, or (b) request a gateway extension exposing provider-specific knobs.
2. **`tools` field is OpenAI-shaped per gateway contract** regardless of `stream_format`. Callers using Anthropic models must construct OpenAI-shaped function-tool objects (`{"type":"function","function":{...}}`) — the gateway translates internally. Anthropic-shaped `input_schema` / `tool_choice` payloads are **not** accepted directly.

Both are flagged in `services/tilemap-service/DESIGN.md` §8 (where the SDK was extracted from) as architectural findings for the TMP_008b spec's next revision.

## Testing

```bash
# From workspace root:
cargo test -p loreweave_llm
```

22 tests pass: 5 inline (client behaviour + env handling) + 17 integration (`tests/wire_format.rs` wire conformance against canonical openapi shapes).

The defensive test `stream_event_rejects_event_type_field_name` guards against the regression that surfaced 6 HIGH defects during the original Phase 0a `/review-impl` pass — the Pythonic `event_type` field name had leaked into the Rust mirror. The gateway uses `event`; this test enforces it.

## License

Same as parent repo (LoreWeave, AGPL-3.0-only).
