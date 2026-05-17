# Spec — Tilemap Phase 0b: Gateway tool-use contract + SSE parser + L3 harness

> **Status:** DESIGN 2026-05-15. AMAW XL task. Branch `mmo-rpg/zone-map-amaw`.
> **Workflow:** v2.2 + `/amaw` (XL — full AMAW, subagent dispatch allowed).
> **Source:** handoff "NEXT SESSION SETUP — Phase 0b"; `services/tilemap-service/DESIGN.md` §9; `TMP_008b` §3/§4/§9/§12.

---

## 1. Problem

Phase 0b's goal is to empirically validate the TMP_008b L3 zone-classifier LLM
contract against real lmstudio. The original handoff scoped it as L (SSE parser
+ one prompt). Investigation found the LLM gateway **cannot transmit tool-use**:

- `ChatStreamRequest` (openapi + Go `streamRequest`) has **no `tool_choice` field** — the
  caller cannot force a tool call (TMP_008b §3.2 requires `tool_choice: {type:tool,...}`).
- The canonical SSE envelope (`StreamEventEnvelope`) has **no tool-call event** —
  only `token / reasoning / usage / done / error / audio-chunk`.
- Both Go streamers **drop tool-call deltas on the floor**:
  - `streamOpenAICompat` parses `choices[].delta` for only `content` + `reasoning_content`;
    `delta.tool_calls[]` is not in the parsed struct.
  - `streamAnthropicSSE` handles `text_delta` + `thinking_delta`; its own comment says
    `input_json_delta` (tool use) is an unmapped "future follow-up cycle".

Net: a forced tool call through the gateway today yields an empty token stream +
`done(finish_reason="tool_calls")` with the arguments JSON lost.

**User decision (CLARIFY):** extend the gateway contract first, run as one XL `/amaw` batch.

## 2. Scope

In scope (one XL batch):

1. **openapi** — add `tool_choice` to `ChatStreamRequest`; add `ToolCallEvent` to
   `StreamEventEnvelope`. Adding the event requires **three** YAML edits (Adversary
   r4 WARN-2): the new `ToolCallEvent` schema, its entry in the `oneOf` list, AND a
   `tool_call: '#/components/schemas/ToolCallEvent'` line in `discriminator.mapping`
   — omitting the mapping line breaks discriminator-aware parsers.
2. **provider-registry-service (Go)** — pass `tool_choice` through; re-frame provider
   tool-call deltas into canonical `tool_call` events (openai-compat + Anthropic).
3. **`sdks/rust/loreweave_llm`** — add `tool_choice` field + `StreamEvent::ToolCall` variant;
   implement the real `GatewayClient::stream()` SSE parser; add a tool-call accumulator.
4. **`sdks/python/loreweave_llm`** — mirror the contract (`tool_choice`, `ToolCallEvent`).
5. **`services/tilemap-service`** — hardcoded L3 zone-classifier harness (CLI mode).
6. **Infra** — bring up the `infra` stack (postgres + provider-registry + deps);
   gitignored creds file; live measurement run vs TMP_008b §12.

Out of scope: TMP_008b §5 retry loop, §6 fallback, §10 key-phrase extraction
(Phase 2); the zone-placement engine (Phase 1); **Anthropic request-side tool
support** — confirmed during DESIGN that `anthropicAdapter.Stream` sends no `tools`
field at all today (only model/messages/max_tokens/temperature/system), and
Anthropic-shaped tools differ from OpenAI-shaped — wiring that is a separate
translation job, deferred (lmstudio, the PoC target, is OpenAI-compatible).

## 3. Design decisions

### D1 — Canonical tool-call event = streaming deltas (not aggregated)

Both providers stream tool-call **arguments** as partial-JSON fragments:
- OpenAI: `delta.tool_calls[]` — `index`, plus `id`+`function.name` on the first
  fragment for that index, then `function.arguments` string fragments.
- Anthropic: `content_block_start{type:"tool_use", id, name}` →
  `content_block_delta{delta:{type:"input_json_delta", partial_json}}` → `content_block_stop`.

New canonical event mirrors that — keeps the gateway a **stateless re-framer** (same
property `token`/`reasoning` have today; no per-stream buffering):

```
ToolCallEvent {
  event:            "tool_call"
  index:            integer   // which tool call in the turn (0-based)
  id:               string?   // present on the first delta for this index
  name:             string?   // present on the first delta for this index
  arguments_delta:  string     // incremental JSON fragment (may be "")
}
```

Rejected: a single aggregated event with the full arguments string — forces the
gateway to buffer per-index tool-call state and breaks the dumb-re-framer property.
Reassembly is the SDK's job (a small accumulator helper), not the gateway's.

**Emit rule (Adversary r1 BLOCK-1):** OpenAI sends `id` + `function.name` on the
*first* `delta.tool_calls[i]` fragment, usually with `arguments == ""`. The streamer
MUST emit a `tool_call` event whenever `id` OR `name` OR a non-empty `arguments_delta`
is present — it must NOT mirror the `content != ""` non-empty guard used for token
deltas, or the first fragment (carrying `id`/`name`) is suppressed and, with D1's
no-buffer rule, unrecoverable. Only a fully-empty fragment (no id, no name, empty
args) is skipped. `arguments_delta` is therefore an allowed-empty string in the schema.

### D2 — `tool_choice` field

Add `tool_choice` to `ChatStreamRequest` — freeform (OpenAI-shaped: `"auto"` /
`"none"` / `"required"` / `{"type":"function","function":{"name":...}}`). The gateway
copies it into the upstream body verbatim for openai-compat providers (lmstudio path).
`tools` stays OpenAI-shaped per the existing contract.

### D3 — Go gateway changes

- `streamRequest`: add `ToolChoice any json:"tool_choice,omitempty"`.
- `streamChat`: `if in.ToolChoice != nil { input["tool_choice"] = in.ToolChoice }`.
- `StreamChunkKind`: add `StreamChunkToolCall = "tool_call"`.
- `StreamChunk`: **reuse the existing `Index` field** for the tool-call index — do NOT
  add a second field tagged `json:"index"` (that produces a duplicate JSON key).
  **Dual-meaning note (Adversary r4 WARN-1):** for `token`/`reasoning` the streamer
  sets `Index` from a monotonic local counter (`tokenIdx++`); for `tool_call` it must
  instead set `Index` directly from the provider's own `tool_calls[].index` (OpenAI) /
  `content_block` index (Anthropic) — a semantic call identifier, NOT a counter. The
  tool-call emit path must never `++` a local counter for `Index`. Add
  `ToolCallID string json:"id,omitempty"`, `ToolName string json:"name,omitempty"`,
  `ArgumentsDelta string json:"arguments_delta,omitempty"` — all three `omitempty`.
  **BUILD correction to Adversary r2 BLOCK-1:** `StreamChunk` is the *shared* event
  struct; a non-`omitempty` `arguments_delta` would emit `"arguments_delta":""` on
  every `token`/`usage`/`done` event too. `omitempty` does NOT undo the D1 emit rule —
  the `event:tool_call` SSE frame plus `id`+`name` still serialize on the first
  fragment; only an information-free empty string is dropped. The contract stays
  consistent by making `arguments_delta` **optional** in the openapi `ToolCallEvent`
  (`required: [event]` only) and having every SDK consumer **default an absent
  `arguments_delta` to `""`** (Rust `#[serde(default)]`, Python `str = ""`).
- **Parity rule for the tool-call `index`:** the wire MAY omit `index` when 0 (Go's
  shared `Index` is `omitempty`; openapi `ToolCallEvent.index` is optional, default 0).
  All three SDKs treat an absent `index` as `0`. To keep serialize-symmetry across
  SDKs (Adversary r2 WARN-3): Rust models it `index: u32` with
  `#[serde(default, skip_serializing_if = "is_zero")]` (a tiny `fn is_zero(n:&u32)->bool`
  helper — matches Go's omit-when-0); Python `index: int = 0` (consumer-side; the rare
  serialize path may emit `index:0`, documented as benign). It is a plain `u32`/`int`,
  NOT `Option`/nullable, so the accumulator always keys on a concrete value.
- `streamOpenAICompat`: extend the parsed struct with
  `delta.tool_calls[]{index,id,function{name,arguments}}`; emit one `StreamChunkToolCall`
  per fragment.
- `streamAnthropicSSE`: track `content_block_start` of `type:"tool_use"` (capture
  index→id/name); map `input_json_delta.partial_json` → `StreamChunkToolCall`. This is
  **parse-side only** — symmetric, low-cost, and the streamer's own comment invites it;
  Anthropic *request*-side tool support stays deferred (see §2 out-of-scope).
- **Adapter `Stream` body builders are NOT uniform (Adversary r3 BLOCK-1):** only
  `openaiAdapter.Stream` forwards `input["tools"]` today (adapters.go:398-400).
  `lmStudioAdapter.Stream` and `ollamaAdapter.Stream` build their body from
  model/messages/temperature/max_tokens only — they read **neither** `tools` nor
  `tool_choice`. Since lmstudio is the PoC target (AC-5 runs through
  `lmStudioAdapter.Stream`), this batch must add **both** `tools` **and** `tool_choice`
  pass-through to `lmStudioAdapter.Stream` + `ollamaAdapter.Stream`, and `tool_choice`
  to `openaiAdapter.Stream` (which already forwards `tools`). `anthropicAdapter.Stream`
  is untouched (sends no tools today — §2).

### D4 — Rust SDK

- `models.rs`: `ChatStreamRequest.tool_choice: Option<serde_json::Value>`
  (`skip_serializing_if = "Option::is_none"`); `StreamEvent::ToolCall { index, id, name, arguments_delta }`.
- `client.rs`: implement `GatewayClient::stream()` — `reqwest` POST → `bytes_stream()`
  → line-buffered SSE parser → `impl Stream<Item = Result<StreamEvent, LlmError>>`.
  `StreamHandle` wraps it. Handle: `data:` lines, `event:` lines, `:` keep-alive
  comments, multi-line buffering across chunk boundaries, `error` event → `LlmError`.
- New `tool.rs`: `ToolCallAccumulator` (Adversary r3 WARN-3). The canonical
  `tool_call` event has **no per-index terminal marker** — Anthropic's
  `content_block_stop` is intentionally not re-emitted, and OpenAI has no per-call
  terminator. The accumulator therefore: (a) is an **index-keyed map**
  (`BTreeMap<u32, PartialToolCall>`), NOT a monotonic list — OpenAI may stream
  multiple tool calls with interleaved / non-monotonic / out-of-order `index` values;
  (b) for each `ToolCall` delta, upserts the entry at `index`, sets `id`/`name` if the
  delta carries them (first-write-wins; later deltas usually omit them), and appends
  `arguments_delta`; (c) **finalizes only at `Done`** (or stream end) — `finish()`
  drains the map into `Vec<CompletedToolCall { index, id, name, arguments: String }>`
  sorted by index. A still-empty `arguments` at `Done` is surfaced to the caller (the
  harness treats it as a tool-use failure to record, not a panic).
- **Error-path contract (Adversary r4 WARN-3):** "stream end" includes an
  error-terminated stream. If `GatewayClient::stream()` yields `Err(LlmError)` (e.g. an
  `error` event, or transport failure) with no preceding `Done`, the consumer still
  calls `accumulator.finish()` to salvage any partial tool call. The D6 harness, on a
  stream error, records `tool_use_success = false` plus whatever partial
  `CompletedToolCall`s were accumulated — it never panics or discards the measurement.

### D5 — Python SDK

`models.py`: new `ToolCallEvent(_BaseEvent)` — **must follow the existing discriminator
idiom** (Adversary r1 WARN-3): `event_type: Literal["tool_call"] = Field("tool_call",
alias="event")`, then `index: int = 0`, `id: str | None = None`,
`name: str | None = None`, `arguments_delta: str`; add it to the
`StreamEvent = Annotated[Union[...], Field(discriminator="event_type")]` union. `tool_choice: list[dict] | dict | str | None`
on `StreamRequest`. `client.py`: `_dispatch_event` handles `"tool_call"`.

**Cross-SDK `index` consistency (Adversary r1 WARN-3):** `index` is semantically
load-bearing for `tool_call` (it identifies which call). All three SDKs treat an
absent `index` as `0`: Rust `index: u32` with `#[serde(default)]` (NOT `Option`),
Python `index: int = 0`, Go reuses the shared `omitempty` `Index` field (absent ⇒ 0).
The accumulator therefore always keys on a concrete `u32`/`int`. See D3 parity rule.

### D6 — tilemap-service L3 harness

`main.rs` CLI mode `classify` (or a new `harness` module): builds the TMP_008b §3
tool definition (`submit_zone_classifications`, OpenAI-shaped) + §9 few-shot system
prompt + a small hardcoded tilemap payload (1 zone, ~3 placeholder objects);
constructs `ChatStreamRequest` with `tools` + `tool_choice` forced; calls the gateway;
accumulates the `tool_call` stream; parses arguments JSON; runs the §4.1 R1–R5
validators; prints a report (usage tokens, tool-use success, cost vs §12 estimate).

### D8 — Fail loud on tools for a non-supporting provider (Adversary r1 BLOCK-2)

`tool_choice`/`tools` live on the contract-level `ChatStreamRequest`, but only
openai-compat adapters wire them through (D3). Without a guard, a request that
resolves to an Anthropic model would accept `tool_choice`, return 200, and silently
drop it — a contract hole.

**Capability lives on the adapter, not a hand-maintained list (Adversary r2 BLOCK-2):**
add `SupportsTools() bool` to the `provider.Adapter` interface. `openaiAdapter`,
`lmStudioAdapter`, `ollamaAdapter` return `true`; `anthropicAdapter` returns `false`
(request-side tools deferred — §2). The capability is co-located with each adapter so
it cannot drift from `ResolveAdapter`; a new openai-compat adapter declares its own
support and is never spuriously rejected.

Fix in `doLlmStream`: after `provider.ResolveAdapter(...)` returns the adapter and
**before** the SSE prelude (`w.WriteHeader(200)`), if
`(in.Tools != nil || in.ToolChoice != nil) && !adapter.SupportsTools()`, return
`400 LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER` naming the provider kind. This also closes
the **pre-existing** silent-drop of `tools` for Anthropic, not just the new
`tool_choice`. (The guard runs only on the `chat` op path — `tts` has no tools.)

**Open-set note (Adversary r3 WARN-2):** `ResolveAdapter`'s `default:` case routes any
unknown/custom provider kind to `openaiAdapter`, which returns `SupportsTools()==true`.
So unknown kinds permit tools by inheritance — the safe default (the upstream itself
surfaces an `error` event if it genuinely can't do tools). The Go test for AC-7 covers
both an explicit Anthropic-kind reject and an unknown-kind allow, to lock this path.

### D7 — Infra + creds

Bring up `infra` compose: `postgres`, `provider-registry-service`, `usage-billing-service`,
`auth-service` (minimum for the internal stream path + billing). Resolve the lmstudio
`platform_model` UUID from the `loreweave_provider_registry` DB. Write
`.local/phase0b.env` (gitignored) holding `LOREWEAVE_GATEWAY_URL`,
`LOREWEAVE_INTERNAL_TOKEN`, `LMSTUDIO_MODEL_REF`, `HARNESS_USER_ID`.

## 4. Wire-format parity & determinism

- openapi YAML is the source of truth; Rust `tests/wire_format.rs` + new Go streamer
  tests + Python tests must all assert the `tool_call` discriminator + field names.
- The SSE parser is correctness-critical — `/review-impl` after POST-REVIEW will
  target it (multi-line buffering across `bytes_stream()` chunk boundaries, partial
  `data:` lines, keep-alive comments, the `tool_call` accumulator).

## 5. Acceptance criteria

- AC-1: openapi validates; `tool_choice` + `ToolCallEvent` present with the §3 shape,
  AND the `discriminator.mapping` carries the `tool_call` line (r4 WARN-2).
- AC-2: Go — `streamOpenAICompat` emits `tool_call` events for an OpenAI tool-call
  fixture; unit test covers multi-fragment reassembly order. Anthropic ditto.
- AC-3: Rust — `GatewayClient::stream()` parses a mock-gateway SSE stream into
  `StreamEvent`s incl. `ToolCall`; `wire_format.rs` locks the new event;
  `ToolCallAccumulator` reassembles fragmented deltas — **including a test with two
  tool calls streamed with interleaved / out-of-order `index` values** (r3 WARN-3) and
  a test where `id`/`name` arrive only on the first fragment. `cargo test --workspace` green.
- AC-4: Python — `ToolCallEvent` round-trips; `_dispatch_event` handles it; tests green.
- AC-5: harness builds the L3 request, runs against **live lmstudio**, gets a parsed
  tool call, validates it, prints a token/cost report.
- AC-6: findings (tool-use success rate, token cost vs §12) written back into
  `TMP_008b` §12 + `services/tilemap-service/DESIGN.md` §8.
- AC-7 (D8): the D8 guard rejects `tools`/`tool_choice` for a non-supporting provider.
  Capability component unit-tested now (`TestAdapterSupportsTools` — openai/lmstudio/
  ollama true, anthropic false). The full handler-level reject path (DB cred
  resolution → `ResolveAdapter` → guard) needs the live-DB + fake-adapter integration
  harness the project already defers as `D-PHASE5A-STREAM-INTEGRATION-TESTS` — the D8
  case joins that deferred suite; the live measurement run exercises the no-reject path.

## 6. Risks

- R-A: lmstudio's loaded model may not support tool-calling / forced `tool_choice` —
  the harness measures and reports this honestly; not a code defect.
- R-B: RESOLVED in DESIGN — `anthropicAdapter.Stream` sends no `tools` today, so
  Anthropic request-side tool support is deferred; only the Anthropic streamer
  parse-side `tool_call` mapping lands this batch.
- R-C: bringing up the `infra` stack may surface unrelated breakage (worker-ai /
  knowledge-service are already crash-looping) — bring up only the minimum subset.
