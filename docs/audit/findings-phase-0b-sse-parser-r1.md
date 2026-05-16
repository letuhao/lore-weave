# Adversary Findings — phase-0b-sse-parser — Round 1

Design under review: `docs/specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md`
Phase: review-design · Agent: adversary · Round: 1
Status: **REJECTED** (1 BLOCK, 2 WARN)

---

## Finding 1 — BLOCK — D1/D3: empty `arguments` fragment carries the only `id`+`name`; the spec's emit guard will drop it

D3 says `streamOpenAICompat` should "emit one `StreamChunkToolCall` per fragment", and D1 makes the gateway a stateless re-framer that does NOT buffer per-index `id`/`name`. But OpenAI's wire reality: the **first** `delta.tool_calls[i]` fragment for an index carries `id` + `function.name` and **usually `function.arguments == ""`**; every subsequent fragment carries only an `arguments` string and **no** `id`/`name`. The existing `streamOpenAICompat` parser guards every emit with non-empty checks (`if choice.Delta.Content != ""`, `if choice.Delta.ReasoningContent != ""`). If the new tool-call branch mirrors that idiom and emits only when `arguments_delta != ""`, the first fragment is suppressed and the `id`+`name` are lost on the floor — exactly the bug Phase 0b exists to fix. Because D1 forbids the gateway from buffering `id`/`name` per index, there is no second chance to recover them: the SDK `ToolCallAccumulator` folds by index and will produce a tool call with empty `id`/`name`.

**Question for the designer:** Where in the design is it stated that the Go streamer MUST emit a `tool_call` event for a fragment whose `arguments_delta` is empty but whose `id`/`name` are present — and that the SSE/openapi `ToolCallEvent.arguments_delta` is explicitly allowed to be `""` (the §3 schema comment says "may be `\"\"`" but D3's emit rule and AC-2's "multi-fragment reassembly order" test do not lock the empty-first-fragment case)? Without that, the gateway's no-buffer property and the empty-args emit guard are mutually contradictory and the design loses the `id`/`name`.

---

## Finding 2 — BLOCK — D2/D3: `tool_choice` is a contract-level field but is silently dropped for Anthropic / non-openai-compat — contract hole

D2 adds `tool_choice` to `ChatStreamRequest` in the openapi — a contract-level, provider-agnostic field. D3 then narrows the implementation: the pass-through "goes in each openai-compat adapter's `Stream` body builder ... `anthropicAdapter.Stream` is untouched (sends no tools today)." The result: a caller can send `ChatStreamRequest{ tool_choice: {...}, model_source: user_model }` resolving to an Anthropic-backed model (or `stream_format: anthropic`), the gateway returns 200, and `tool_choice` is silently discarded. No `error` event, no 400, no documented "ignored on this provider" note. The openapi schema makes a promise the Go implementation does not keep for one whole provider class. This is the same "contract hole" class that the prior `rdy-rejected-test` Adversary round was REJECTED for (2 BLOCK on contract holes — see AUDIT_LOG / lessons).

**Question for the designer:** When `tool_choice` is present on a request that resolves to a provider whose adapter does not consume it (anthropicAdapter today, any future non-openai-compat adapter), what is the defined behavior — a 400 `LLM_INVALID_REQUEST` at `doLlmStream` validation time, a documented openapi note that the field is openai-compat-only, or something else? As designed the field is accepted into the contract but honored by only a subset of providers, with no enumerated side effect for the rest.

---

## Finding 3 — WARN — D5/parity: Python `StreamEvent` discriminator is `event_type` (aliased), not `event` — a new `ToolCallEvent` must replicate the alias exactly or wire-decode breaks

§4 asserts "openapi YAML is the source of truth ... Python tests must all assert the `tool_call` discriminator + field names." But the Python SDK does NOT use `event` as its discriminator — `models.py` uses `event_type` as the Pydantic discriminator with `alias="event"` on every event class, and the `Union` is keyed on `discriminator="event_type"`. D5 only says "`ToolCallEvent` class + add to `StreamEvent` union" without calling out that the new class MUST declare `event_type: Literal["tool_call"] = Field("tool_call", alias="event")` AND that the discriminated `Union` line must include it. Miss the alias and inbound `{"event":"tool_call",...}` frames fail discrimination at runtime; the Rust side (`#[serde(tag = "event")]`) and Go side (`json:"event"`) have no such alias indirection, so a naive "mirror the field names" reading produces a three-way parity mismatch that only the Python wire-roundtrip test (AC-4) would catch — and AC-4 is described only as "round-trips", not "decodes a raw `event:`-keyed payload".

**Question for the designer:** Does the design intend AC-4's `ToolCallEvent` test to decode a raw gateway-shaped payload with the literal `"event":"tool_call"` key (exercising the `alias="event"` path), and is the `index` field's default reconciled across SDKs — Go `StreamChunk.Index` is `omitempty` (0 elided), Rust `ToolCall.index` per D4 is plain `index` (no Option), Python events default `index: int = 0`? A tool-call at wire-index 0 with `omitempty` on the Go side emits no `index` key at all, which an SDK expecting the field present would mis-handle.

---

Lessons consulted: 5 (3 guardrail + 2 adversary-rejection general_note)
Step 0 query strings used:
  - `search_lessons "llm gateway tool-use SSE streaming" --type guardrail --limit 10 --format json`
  - `search_lessons "streamer.go openapi SDK" --tags adversary-rejection --limit 5 --format json`
Guardrails relevant: (none directly — the 3 guardrails returned are git-push / force-push / DB-migration scope rules, not SSE/contract rules; informational context only, not promoted to findings)
Prior REJECTED patterns: `rdy-rejected-test` review-design REJECTED with 2 BLOCK on **contract holes** (directly informs Finding 2 — `tool_choice` accepted by contract, honored by subset of providers); `amaw-task-slug-validation` review-code REJECTED for a fix that closed only one of two entry points (informs Finding 1/2 — a change that covers openai-compat but leaves the Anthropic path is a partial-closure pattern this reviewer flags).
