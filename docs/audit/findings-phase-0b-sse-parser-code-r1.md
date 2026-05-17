# Adversary findings — phase-0b-sse-parser — review-code — round 1

Status: **APPROVED_WITH_WARNINGS** (0 BLOCK, 3 WARN)

Cold-start CODE review of the Phase 0b implementation against
`docs/specs/2026-05-15-tilemap-phase-0b-gateway-tooluse.md` (D1-D8).
All 3 findings framed as questions, no fixes proposed beyond what the flaw reveals.

---

## WARN-1 — `SseDecoder.buf` has no size cap; Go's SSE scanner does

`sdks/rust/loreweave_llm/src/sse.rs` `feed()` does
`self.buf.extend_from_slice(bytes)` then scans for `\n`. Incomplete lines are
*retained* until a newline arrives — correct for chunk-boundary buffering. But
there is **no upper bound** on `buf`. The Go side deliberately caps the
equivalent: `streamer.go:112` — `scanner.Buffer(make([]byte,0,64*1024),
1024*1024)` — a 1 MiB line cap, after which `scanner.Err()` surfaces
`bufio.ErrTooLong`.

The Rust decoder is the SDK that talks to a possibly-misbehaving or
genuinely-malicious upstream re-framed stream. A response body that streams
many MiB with **no `\n`** (a broken provider, a hung proxy emitting garbage, a
content-length-less chunked body that never frames) makes `buf` grow until the
process OOMs. `read_timeout` in `client.rs` does NOT help — bytes *are*
arriving, just never newline-terminated, so the idle timer never fires.

The spec (§4) explicitly calls the SSE parser "correctness-critical" and lists
"multi-line buffering across `bytes_stream()` chunk boundaries" as the
`/review-impl` target. An unbounded buffer is the failure mode of exactly that
mechanism.

- Question: what stops `SseDecoder.buf` from growing without limit when an
  upstream streams a large body containing no newline byte, and why is the Go
  streamer's explicit 1 MiB cap intentionally absent from the Rust mirror that
  faces the same untrusted-upstream surface?

Severity: **WARN** — requires a misbehaving upstream to trigger; not reachable
from a well-behaved gateway. But it is a genuine unbounded-memory path with no
guard, and the sibling Go code shows the project already decided this needs a
cap.

---

## WARN-2 — D8 guard treats an empty `tools: []` array as "has tools"

`stream_handler.go` `streamRequest.Tools` is typed `any`. The D8 reject at
`stream_handler.go:205` is:

```go
if (in.Tools != nil || in.ToolChoice != nil) && !adapter.SupportsTools() {
```

A JSON body containing `"tools": []` (an empty array — a plausible default a
caller emits when it has no tools to send) decodes via `encoding/json` into a
**non-nil** `[]interface{}{}`. `in.Tools != nil` is therefore `true`, and a
request that carries *zero actual tool definitions* to an Anthropic-resolved
model is rejected with `400 LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER`.

Spec D8 frames the guard's purpose as closing the silent-drop of *real* tool
definitions — "a request that resolves to an Anthropic model would accept
`tool_choice`, return 200, and silently drop it." An empty `tools` array drops
nothing; rejecting it is a spurious 400 a previously-working Anthropic caller
would suddenly hit if it started sending `tools: []`. The Rust SDK avoids this
(`tools: Option<Vec>` with `skip_serializing_if`), but the gateway contract is
not Rust-SDK-only — any caller posting raw JSON hits this.

- Question: is rejecting a request whose `tools` is an empty array (no tool
  definitions, nothing actually dropped) the intended behavior of the D8
  guard, or should the guard test "non-empty tools OR tool_choice present"
  rather than "tools field present"?

Severity: **WARN** — the live PoC path (lmstudio, `SupportsTools()==true`) is
unaffected, and AC-7's component test only covers `nil` tools, not `[]`. Real
contract-surface drift, low live-path blast radius.

---

## WARN-3 — harness validates only `calls.first()` but reports `tool_calls_seen` for all

`services/tilemap-service/src/harness/mod.rs` reassembles every streamed tool
call via `ToolCallAccumulator`, then:

```rust
let calls = acc.finish();
let tool_calls_seen = calls.len();
let raw_arguments = calls.first().map(...).unwrap_or_default();
match calls.first() { ... }
```

Everything after `acc.finish()` operates on `calls.first()` **only**. If the
model emits two or more tool calls (the accumulator is explicitly built for
interleaved multi-call streams — D4, AC-3), `tool_calls_seen` reports e.g. `2`
but `classifications_parsed`, `validation_errors`, `raw_arguments`, and
`tool_use_success` all derive from index 0 alone. The report then shows
`tool_calls_seen: 2` next to a validation summary computed from one call — a
silently misleading measurement.

D6 scopes the harness to "call exactly once" and `forced_tool_choice()` returns
`"required"` with a single tool, so a well-behaved model emits one call. But
the harness is a *measurement* tool whose entire job (R-A) is to "measure and
report honestly" what lmstudio actually does — and an LLM ignoring "call
exactly once" and emitting a second call is precisely the kind of contract
deviation Phase 0b exists to catch. The report swallows it: a reader sees
`tool_calls_seen: 2` with no indication the extra call was never inspected.

- Question: when `acc.finish()` yields more than one `CompletedToolCall`,
  should the harness surface that the calls beyond index 0 were discarded
  (e.g. a `failure` note), rather than letting `tool_calls_seen` and the
  validation summary silently disagree about how many calls were examined?

Severity: **WARN** — does not corrupt the single-call happy path AC-5 verified
green; it is a measurement-honesty gap in the off-nominal branch, which is the
branch a measurement harness most needs to be honest about.

---

Lessons consulted: 6 (3 guardrails + 3 adversary-rejection notes)
Step 0 query strings used: "llm gateway SSE tool-use streaming" (type=guardrail, limit=10); "streamer.go SSE parser" (tags=adversary-rejection, limit=5)
Guardrails relevant: (none — the 3 returned guardrails cover git push / force-push / DB-migration AMAW gating, none touches SSE parsing or tool-use)
Prior REJECTED patterns: phase-0b-sse-parser review-design r1-r3 all REJECTED (r1: empty-args first fragment drops id/name vs no-buffer property — verified addressed: streamer.go:250 skip guard + D1 emit rule honored; r2: arguments_delta omitempty re-introduces BLOCK at wire layer — addressed via openapi optional + SDK defaults; r3: ollama/lm_studio Stream() never wired tools — verified addressed: adapters.go:712-717 + 911-916 now forward tools/tool_choice). r4 APPROVED_WITH_WARNINGS. amaw-task-slug-validation review-code r1 REJECTED (second-entry-point miss) — informed WARN-2's "guard covers one shape, misses a sibling input shape" lens.
