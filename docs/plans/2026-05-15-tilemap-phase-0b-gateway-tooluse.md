# Plan — Tilemap Phase 0b: Gateway tool-use + SSE parser + L3 harness

> **Spec:** [docs/specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md](../specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md)
> **Size:** XL. AMAW. Branch `mmo-rpg/zone-map-amaw`.
> **Design review:** 4 Adversary rounds → APPROVED_WITH_WARNINGS; all r1-r4 findings folded into spec D1-D8.

## Build order

Contract-first: openapi → Go gateway → Rust SDK → Python SDK → harness → infra → live run.
Each step is TDD where a test harness exists (Go `_test.go`, Rust `tests/`, Python `pytest`).

### Step 1 — openapi contract (`contracts/api/llm-gateway/v1/openapi.yaml`)

- `ChatStreamRequest`: add `tool_choice` property (freeform — `oneOf` string/object;
  `additionalProperties: true` on the object form), described as OpenAI-shaped.
- New `ToolCallEvent` schema: `required: [event, arguments_delta]`; props `event`
  (enum `[tool_call]`), `index` (integer, default 0, optional), `id` (string, optional),
  `name` (string, optional), `arguments_delta` (string — allowed empty).
- `StreamEventEnvelope`: add `ToolCallEvent` to `oneOf` **and** the
  `discriminator.mapping` (`tool_call: '#/components/schemas/ToolCallEvent'`) — both edits.

### Step 2 — Go gateway (`services/provider-registry-service/`)

Files: `internal/provider/streamer.go`, `anthropic_streamer.go`, `adapters.go`,
`internal/api/stream_handler.go` + matching `_test.go`.

1. `streamer.go`: `StreamChunkToolCall StreamChunkKind = "tool_call"`; add
   `ToolCallID`/`ToolName`/`ArgumentsDelta` to `StreamChunk` (`arguments_delta` NOT
   omitempty; reuse `Index`). Extend `streamOpenAICompat`'s parsed struct with
   `delta.tool_calls[]{index,id,function{name,arguments}}`; emit one
   `StreamChunkToolCall` per fragment — emit when `id`||`name`||non-empty args; set
   `Index` directly from `tool_calls[].index` (no `++`).
2. `anthropic_streamer.go`: handle `content_block_start{content_block.type:"tool_use"}`
   (capture index→id/name into a per-stream map), `input_json_delta.partial_json` →
   `StreamChunkToolCall`.
3. `adapters.go`: add `SupportsTools() bool` to the `Adapter` interface;
   `openaiAdapter`/`lmStudioAdapter`/`ollamaAdapter` → `true`, `anthropicAdapter` →
   `false`. Add `tool_choice` pass-through to `openaiAdapter.Stream`; add **both**
   `tools` + `tool_choice` to `lmStudioAdapter.Stream` + `ollamaAdapter.Stream`.
4. `stream_handler.go`: `streamRequest` gains `ToolChoice any json:"tool_choice,omitempty"`;
   `streamChat` sets `input["tool_choice"]`; `doLlmStream` adds the D8 guard
   (`!adapter.SupportsTools()` + tools/tool_choice present → 400
   `LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER`, before SSE prelude).
5. Tests: openai tool-call fixture → `tool_call` events incl. multi-fragment + first
   fragment id/name; Anthropic tool_use fixture; D8 guard (anthropic reject +
   unknown-kind allow).

### Step 3 — Rust SDK (`sdks/rust/loreweave_llm/`)

Files: `src/models.rs`, `src/client.rs`, new `src/tool.rs`, `src/lib.rs`,
`Cargo.toml` (+ workspace root `Cargo.toml` for `futures` / dev `wiremock`),
`tests/wire_format.rs`, new `tests/gateway_mock.rs`.

1. `models.rs`: `ChatStreamRequest.tool_choice: Option<serde_json::Value>`
   (skip-if-none); `StreamEvent::ToolCall { index: u32 (#[serde(default, skip_serializing_if="is_zero")]),
   id: Option<String>, name: Option<String>, arguments_delta: String }`; `is_zero` helper.
2. `client.rs`: implement `GatewayClient::stream()` — POST → `bytes_stream()` →
   line-buffered SSE parser → `impl Stream<Item=Result<StreamEvent,LlmError>>`.
   Handle `data:`/`event:`/`:` comment lines, buffering across chunk boundaries,
   `error` event → `LlmError`. `StreamHandle` wraps the stream.
3. `tool.rs`: `ToolCallAccumulator` — `BTreeMap<u32, PartialToolCall>`; `push(&ToolCall)`;
   `finish() -> Vec<CompletedToolCall>` sorted by index; works on error-termination.
4. `lib.rs`: re-export new items.
5. Tests: `wire_format.rs` locks `tool_call` event; `gateway_mock.rs` (wiremock)
   drives `stream()` end-to-end; accumulator tests incl. interleaved indices +
   first-fragment-only id/name.

### Step 4 — Python SDK (`sdks/python/loreweave_llm/`)

`models.py`: `ToolCallEvent(_BaseEvent)` (discriminator idiom); add to union;
`tool_choice` on `StreamRequest`. `client.py`: `_dispatch_event` handles `tool_call`.
Tests: round-trip + dispatch.

### Step 5 — tilemap-service harness (`services/tilemap-service/`)

New harness module + `main.rs` CLI mode `classify`. Builds TMP_008b §3 tool def
(`submit_zone_classifications`, OpenAI-shaped) + §9 few-shot system prompt + small
hardcoded tilemap payload; `ChatStreamRequest` with `tools` + forced `tool_choice`;
calls gateway; `ToolCallAccumulator`; parses arguments JSON; runs §4.1 R1-R5
validators; prints token/cost report. Mock test + `#[ignore]` live test.

### Step 6 — Infra + creds

Bring up `infra` compose subset: `postgres`, `provider-registry-service`,
`usage-billing-service`, `auth-service`. Resolve lmstudio `platform_model` UUID from
`loreweave_provider_registry` DB. Write `.local/phase0b.env` (gitignored — add
`.local/` to `.gitignore`): `LOREWEAVE_GATEWAY_URL`, `LOREWEAVE_INTERNAL_TOKEN`,
`LMSTUDIO_MODEL_REF`, `HARNESS_USER_ID`.

### Step 7 — Live run + findings

Run the harness against live lmstudio. Record tool-use success, token counts, cost
vs TMP_008b §12. Write findings into `TMP_008b` §12 + `tilemap-service/DESIGN.md` §8.

## Verification gate (VERIFY phase)

- `cargo build --workspace` + `cargo test --workspace` green.
- `go test ./...` in provider-registry-service green.
- Python SDK tests green.
- `swagger`/`openapi` lint on the YAML (or a structural check).
- Live harness run produces a measurement report (or an honest failure record per R-A).

## Risks (from spec §6)

- R-A lmstudio model may not support forced tool-use — harness records honestly.
- R-C `infra` stack bring-up may surface unrelated breakage — bring up minimum subset.
