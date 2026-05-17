# Scope Guard post-review — phase-0b-sse-parser

**Verdict: CLEAR**
Cold-start conservative final gate before SESSION. Task: tilemap gateway tool-use
contract + SSE parser + L3 harness (XL / AMAW).

- Spec: `docs/specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md`
- Plan: `docs/plans/2026-05-15-tilemap-phase-0b-gateway-tooluse.md`
- Date: 2026-05-15

## Step 0 — captured-rules check

| Check | Result |
|---|---|
| `check_guardrails "ready-to-commit"` | **pass:true**, 3 rules checked, 0 violated |
| `search_lessons "llm gateway tool-use SSE" type=guardrail` | 3 guardrails (git push / force-push / DB-migration) — none touches SSE/tool-use |
| `search_lessons "tilemap gateway tool-use"` | 3 lessons (AMAW design decisions, guardrail seeding, review-layer note) — no blocker |

No guardrail blocks this task area.

## Acceptance criteria (spec §5 AC-1..AC-7)

| AC | Status | Evidence |
|---|---|---|
| **AC-1** openapi validates; `tool_choice` + `ToolCallEvent` present with §3 shape; `discriminator.mapping` carries `tool_call` | **COVERED** | `openapi.yaml`: `ChatStreamRequest.tool_choice` (l.419-434, oneOf string/object); `ToolCallEvent` schema (l.576-615, `required:[event]`, `index` default 0, `arguments_delta` default ""); `StreamEventEnvelope.oneOf` includes `ToolCallEvent` (l.520) AND `discriminator.mapping` has `tool_call: '#/components/schemas/ToolCallEvent'` (l.530) — r4 WARN-2 three-edit requirement met. |
| **AC-2** Go `streamOpenAICompat` + `streamAnthropicSSE` emit `tool_call` events; multi-fragment reassembly | **COVERED** | `streamer.go:249-262` — emit per fragment, `Index` from `tc.Index` verbatim (no `++`), D1 emit rule honored (skip only fully-empty fragment l.250). `anthropic_streamer.go:128-142` (content_block_start tool_use → first fragment) + `:169-179` (input_json_delta → arguments). VERIFY evidence: Go tests green. |
| **AC-3** Rust `GatewayClient::stream()` parses mock SSE incl. `ToolCall`; `wire_format.rs` locks event; `ToolCallAccumulator` reassembles incl. interleaved indices + first-fragment id/name | **COVERED** | `client.rs` real `stream()` + `StreamHandle`; `sse.rs` `SseDecoder` (chunk-boundary buffering, CRLF, keep-alive, `[DONE]` skip, 8 unit tests); `tool.rs` `ToolCallAccumulator` BTreeMap-keyed — tests `handles_interleaved_out_of_order_indices`, `id_name_first_write_wins`, `salvages_partial_call_with_empty_arguments`. VERIFY: `cargo test --workspace` green (loreweave_llm 45 + tilemap 17). |
| **AC-4** Python `ToolCallEvent` round-trips; `_dispatch_event` handles it; tests green | **COVERED** | `models.py:78-92` `ToolCallEvent(_BaseEvent)` — discriminator idiom `event_type: Literal["tool_call"] = Field("tool_call", alias="event")`, `index:int=0`, `id`/`name` optional, `arguments_delta:str=""`; added to `StreamEvent` union (l.104); `StreamRequest.tool_choice` (l.128). VERIFY: Python 20 tests green. |
| **AC-5** harness builds L3 request, runs against live lmstudio, gets parsed tool call, validates, prints token/cost report | **COVERED** | `harness/mod.rs` `run_l3_measurement` + `render_report`; `prompt.rs` TMP_008b §3 tool + §9.1 prompt; `validate.rs` R1-R5. VERIFY: live lmstudio (qwen3-14b) run tool_use_success=YES, 3/3 classifications, R1-R5 clean, input≈890/output≈215 tokens, ~64s. |
| **AC-6** findings written into TMP_008b §12 + tilemap-service/DESIGN.md §8 | **COVERED** | `TMP_008b_llm_contract_spec.md` §12.8 (l.699-728) — 5 empirical findings incl. measured cost + lmstudio string-only `tool_choice` discovery. `tilemap-service/DESIGN.md` §8.1 (l.300-320) — Phase 0b resolution, Item 7 RESOLVED + new findings. |
| **AC-7** D8 guard rejects tools/tool_choice for non-supporting provider | **PARTIAL (acknowledged by spec)** | Capability component unit-tested (`TestAdapterSupportsTools` — openai/lmstudio/ollama true, anthropic false per `SupportsTools()`). `stream_handler.go:216` D8 guard wired (`hasToolDefinitions && !SupportsTools()` → 400 `LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER` before SSE prelude). Full handler-level reject path (DB cred → ResolveAdapter → guard) explicitly joins the project's pre-existing deferred `D-PHASE5A-STREAM-INTEGRATION-TESTS` suite. **This is acknowledged drift, not a miss** — spec §5 AC-7 documents it. |

**Tally: 6 COVERED, 0 UNCOVERED, 1 PARTIAL-by-design.** AC-7 partial is spec-sanctioned (capability tested; live run exercises the no-reject path).

## Prior-finding resolution (AUDIT_LOG REVIEW events)

| Round | Status | Findings | Resolution |
|---|---|---|---|
| design r1 | REJECTED | 2 BLOCK + 1 WARN | BLOCK-1 empty-args first fragment → D1 emit rule (`streamer.go:250` skip-guard only fully-empty); BLOCK-2 tool_choice silent-drop → D8 guard; WARN-3 Python event_type alias → D5 idiom. Verified in spec D1/D5/D8. |
| design r2 | REJECTED | 1 BLOCK + 2 WARN | BLOCK-1 omitempty re-introduces wire issue → resolved via openapi `arguments_delta` optional + SDK defaults (Rust `#[serde(default)]`, Python `str=""`); WARN-2 closed allowlist → `SupportsTools()` on adapter; WARN-3 Rust index asymmetry → `u32` + `is_zero` helper. Verified. |
| design r3 | REJECTED | 1 BLOCK + 2 WARN | BLOCK-1 adapter-uniformity factual error → D3 corrected: `lmStudioAdapter`/`ollamaAdapter.Stream` now wire both `tools`+`tool_choice`. Verified (spec D3 §134-142). |
| design r4 | APPROVED_WW | 3 WARN | WARN-1 Index dual-semantics → documented `streamer.go:53-61`; WARN-2 discriminator.mapping → spec §2.1 + openapi l.530; WARN-3 error-terminated accumulator → D4 error-path contract + `tool.rs finish()` salvages. Verified. |
| code r1 | APPROVED_WW | 3 WARN | WARN-1 unbounded SSE buffer → `sse.rs MAX_BUFFER_BYTES=16MiB` + test `unbounded_line_terminates_instead_of_growing`. WARN-2 empty `tools:[]` false 400 → `stream_handler.go hasToolDefinitions()` checks non-empty slice. WARN-3 multi-call honesty → `harness/mod.rs:187-194` `tool_calls_seen>1` NOTE in `render_report`. All 3 verified in code. |

**15/15 findings resolved** (8 design BLOCKs/WARNs across r1-r3 + 3 r4 WARNs + 3 code-r1 WARNs, allowing that r4/code-r1 are the surviving rounds; every BLOCK fixed, every WARN fixed-or-documented).

## Spec-vs-code drift (D1-D8)

No drift. D1 (streaming deltas + emit rule), D2 (`tool_choice` freeform), D3 (Go: `StreamChunkToolCall`, shared `Index`, `omitempty` fields, adapter pass-through), D4 (Rust `StreamEvent::ToolCall`, real `stream()`, `ToolCallAccumulator`), D5 (Python discriminator idiom), D6 (harness), D8 (`SupportsTools()` + guard) — all match the code read. The harness `forced_tool_choice()` returning `"required"` rather than the object form is a documented Phase 0b empirical correction (prompt.rs l.142-153 + TMP_008b §12.8 finding 2) — that is recorded drift, not silent.

## Open deferred items

- `D-PHASE5A-STREAM-INTEGRATION-TESTS` — AC-7 full handler reject path joins this pre-existing deferred suite. Spec-acknowledged.
- Anthropic request-side tool support — deferred per spec §2 out-of-scope (R-B resolved in DESIGN).
- No new deferred items introduced by the code-review fixes.

## Conclusion

**CLEAR.** All acceptance criteria covered (AC-7 partial is spec-sanctioned); all 4 design-review rounds + 1 code-review round findings resolved; `check_guardrails` pass:true; no spec drift; live lmstudio run succeeded with clean R1-R5 validation. Cleared for SESSION.
