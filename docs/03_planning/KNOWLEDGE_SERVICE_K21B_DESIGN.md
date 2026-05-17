---
name: KNOWLEDGE_SERVICE_K21B_DESIGN
description: Phase K21 Cycle B design — chat-service tool-calling loop + tool-call persistence + max-iteration + capability fallback + K21.12 tool_calling_enabled plumbing
type: design
---

# Phase K21-B — Tool Calling: chat-service tool-calling loop

> **Status:** DESIGN (2026-05-17, session 57 cycle 14)
> **Authorized by:** PO at CLARIFY — original 3-cycle split kept; Cycle B
> includes K21.12's BE half; tool-call history stored in a new
> `chat_messages.tool_calls` column.
> **Closes-on-BUILD:** the chat-service slice of K21 — tasks K21.4, K21.6,
> K21.10, K21.11, and the BE half of K21.12.
> **Size:** XL+ — three services (chat-service + knowledge-service +
> provider-registry), 2 migrations, the tool-calling loop, and Anthropic
> request-side tool support. ~18 files.

---

## 1. Scope

**Cycle B** wires Cycle A's memory tools into the chat turn so the LLM can
call them mid-response.

| In scope | Task |
|---|---|
| chat-service tool-calling loop | K21.4 |
| tool-call persistence — new `chat_messages.tool_calls` column | K21.6 |
| max-iteration safety (5) | K21.10 |
| provider capability fallback | K21.11 |
| `tool_calling_enabled` per-project setting — BE half | K21.12-BE |
| Anthropic request-side tool support in the gateway | R1 / D12 |

REVIEW-DESIGN (R1) found the gateway forwards `messages` raw and
`anthropicAdapter.SupportsTools()` is `false` — Anthropic can't receive
OpenAI-shaped tool-result messages. Per the PO call, Cycle B **expands
into provider-registry** to add that conversion (D12), so tool-calling
works on Anthropic-backed chats too.

**NOT in Cycle B** → Cycle C: the FE tool-call indicator (K21.5), the
`memory_remember` user-confirmation flow (K21.7 safeguard 4 — needs an
interactive FE round-trip), and the `tool_calling_enabled` settings
**toggle UI** (K21.12-FE). Voice chat stays tool-free (D-K21B-02).

---

## 2. What exists (audit, 2026-05-17)

- [`stream_service.py`](../../services/chat-service/app/services/stream_service.py):
  `stream_response` builds `messages` → `_stream_via_gateway` runs **one**
  `client.stream()` pass → persists the assistant message + the
  `chat.turn_completed` outbox event in one transaction. `chat_messages`
  has a `content_parts` JSONB column (reasoning, timing).
- The `loreweave_llm` SDK already has `StreamRequest.tools` / `tool_choice`
  and emits `ToolCallEvent`; the gateway rejects tools for a non-supporting
  provider with `LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER` (Cycle A audit).
- chat-service [`knowledge_client.py`](../../services/chat-service/app/client/knowledge_client.py)
  — `build_context` → `KnowledgeContext` (`extra="ignore"`); every failure
  path degrades, never raises.
- chat-service [`migrate.py`](../../services/chat-service/app/db/migrate.py)
  is a single idempotent `DDL` string (`DO $$ … ALTER TABLE … $$` blocks) —
  there is **no** `app/migrations/` dir, so the K21 plan's
  `app/migrations/NNN_tool_calls.py` path is stale.
- knowledge-service [`context.py`](../../services/knowledge-service/app/routers/context.py)
  — `ContextBuildResponse` is `model_validate`'d from the builder's
  `BuiltContext` (`from_attributes=True`); `app/db/migrate.py` uses the same
  idempotent-DDL pattern. Cycle A's `internal_tools.py` + `definitions.py`
  (`TOOL_DEFINITIONS`) are in place.

---

## 3. Decisions

### D1 — Tool-schema distribution: knowledge-service serves them

chat-service must send `tools=[…]` to the gateway, but `TOOL_DEFINITIONS`
lives in knowledge-service (`app/tools/definitions.py`) and the two are
separate Python services. **Decision:** knowledge-service exposes
`GET /internal/tools/definitions` (added to Cycle A's `internal_tools.py`
router) returning `{"tools": TOOL_DEFINITIONS}`; chat-service fetches it
once and process-caches it (lazy, on the first tool-enabled turn). The
schemas stay single-sourced — no drift, no Cycle A refactor. A fetch
failure → chat-service caches "no tools" for that process and the turn
proceeds tool-free (degrade, never block). *Alternative considered* —
move `definitions.py` into a shared `sdks/python` package; cleaner
long-term but disturbs shipped Cycle A code + needs a packaging touch →
**D-K21B-01**.

### D2 — The loop: a new `_stream_with_tools`

NEW `_stream_with_tools(...)` in `stream_service.py` wraps the iteration;
the existing `_stream_via_gateway` stays as the no-tools path.
`stream_response` picks `_stream_with_tools` when tool defs are available
**and** `kctx.tool_calling_enabled` is true, else `_stream_via_gateway`.
`_stream_with_tools` yields the **same chunk-dict shape** as
`_stream_via_gateway` (`content` / `reasoning_content` / `finish_reason` /
`usage`) plus a `tool_call` key for the SSE indicator — so
`stream_response`'s consume loop barely changes.

### D3 — Streaming UX: stream every pass live + emit `tool-call` events

Every pass's `TokenEvent`s stream live as `text-delta` — no buffering, no
suppression. The model's natural "Let me check what we know about Kai…"
preamble is good UX, and live streaming is preserved. A structured
`tool-call` SSE event (`{type:"tool-call", tool, status}`) is emitted per
tool call so Cycle C's indicator can render it. This is the
Claude/ChatGPT pattern; the K21 plan's "behind the scenes, thinking
indicator" was one option — live-with-indicators is simpler (no buffering)
and better.

### D4 — `ToolCallEvent` reassembly

The gateway emits incremental `ToolCallEvent` fragments. Reassemble by
`index`: the first fragment for an index carries `id` + `name`, later
fragments carry `arguments_delta`; concatenate the deltas → a JSON string
→ parse to the args dict. The `DoneEvent` terminates the pass; if any
index was seen, the pass made tool calls.

### D5 — Tool-result message format (OpenAI shape on the wire)

After a tool-calling pass, chat-service appends to `messages`: one
`{role:"assistant", content:<preamble or "">, tool_calls:[{id, type:"function", function:{name, arguments}}]}`
then one `{role:"tool", tool_call_id:<id>, content:<JSON result>}` per
call. chat-service always speaks the **OpenAI shape**; per-provider
translation is the gateway's job (D12) — OpenAI-compatible adapters
forward it raw, the Anthropic adapter converts it.

### D6 — K21.6 persistence: new `chat_messages.tool_calls` column

Append a `DO $$ … ALTER TABLE chat_messages ADD COLUMN tool_calls JSONB … $$`
block to chat-service `migrate.py`'s `DDL` (matches the existing
column-add idiom; the plan's separate-migration-file path is stale). The
column stores the per-turn tool-call history — a list of
`{iteration, tool, args, ok, result|error}` — for Cycle C UI replay.
`NULL` when the turn made no tool calls. The assistant message's
`content` column stays the full concatenated assistant text the user saw
(preambles + final answer); `tool_calls` is the parallel ordered history.
Precise interleaving of text and tool chips at render time is Cycle C's
concern (REVIEW-DESIGN R2).

### D7 — K21.10 max iterations: 5, last pass forced text-only

`MAX_TOOL_ITERATIONS = 5`. Iterations 0–3 stream with the `tools` array +
`tool_choice="auto"`; **the final iteration streams with no `tools` array
at all** so the model physically cannot emit a tool call and must answer
in text. That makes the loop self-terminating — the final pass falls
through to the text-answer return. A defensive post-loop `yield` covers
the case where a misbehaving gateway emits tool calls anyway. (The
implementation omits `tools` rather than sending `tool_choice="none"` —
functionally stronger, and it saves the tool-schema tokens.)

### D8 — K21.11 provider capability fallback

If the first pass raises `LLMError` with code
`LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER`, retry that pass **once without
`tools`** (plain stream) and log the model ref. The turn completes
tool-free. Only the first pass needs this check — once a pass succeeds
with tools, the provider supports them.

### D9 — K21.12-BE: `tool_calling_enabled` plumbed via `build_context`

knowledge-service: `projects.tool_calling_enabled BOOLEAN NOT NULL DEFAULT
true` (a `migrate.py` `DO`-block) → `Project` + `ProjectUpdate` models →
the projects repo `SELECT`/`UPDATE` → `BuiltContext` →
`ContextBuildResponse.tool_calling_enabled`. chat-service:
`KnowledgeContext.tool_calling_enabled: bool = True` (the `extra="ignore"`
default keeps an older knowledge-service working) — `stream_response`
gates `_stream_with_tools` on it. No-project (Mode 1) chats have no
project row → the field defaults true → tools still offered (the executor
handles a null project per Cycle A D3). `build_context` already runs
every turn, so no extra round-trip. The settings **toggle UI** is
Cycle C; `ProjectUpdate` accepting the field now lets that be FE-only.

### D10 — Billing across iterations

Each `client.stream()` pass is a separate gateway job and is billed.
`_stream_with_tools` accumulates `input_tokens` / `output_tokens` across
passes and emits one trailing `usage` chunk with the summed totals;
`stream_response`'s single `billing.log_usage` call is unchanged — it just
receives the summed usage.

### D11 — Untouched

`_auto_generate_title` (no tools — title-gen is a fixed short prompt) and
`voice_stream_service.py` (voice chat stays tool-free → **D-K21B-02**).

### D12 — provider-registry: Anthropic request-side tool support

REVIEW-DESIGN R1 — the gateway's `extractMessages`
([adapters.go:565](../../services/provider-registry-service/internal/provider/adapters.go#L565))
forwards `messages` raw, and `anthropicAdapter.SupportsTools()` is
currently `false` (the handler rejects `tools`/`tool_choice` for
Anthropic). Per the PO call, Cycle B closes that gap. The
`anthropicAdapter` gains:
- **tools conversion** — the OpenAI-shaped `tools` array
  (`{type:"function", function:{name, description, parameters}}`) →
  Anthropic's `{name, description, input_schema}`; `tool_choice` →
  Anthropic's `{type:"auto"|"any"|"tool"}` (`"none"` → omit tools).
- **inbound message conversion** — `{role:"assistant", tool_calls:[…]}`
  → an assistant message with `tool_use` content blocks; each
  `{role:"tool", tool_call_id, content}` → `{role:"user",
  content:[{type:"tool_result", tool_use_id, content}]}`.
- `SupportsTools()` → `true`.

The output side (`anthropic_streamer.go` already maps `tool_use` blocks →
`ToolCallEvent`) is unchanged; OpenAI-compatible adapters are untouched.
After D12, no first-class provider rejects tools, so K21.11's
capability-fallback (D8) becomes a pure backstop.

---

## 4. The loop (pseudocode)

```
async def _stream_with_tools(..., messages, tool_defs, knowledge_client, ctx):
    working = list(messages)
    total_in = total_out = 0
    for i in range(MAX_TOOL_ITERATIONS):          # 5
        last = i == MAX_TOOL_ITERATIONS - 1
        # final pass: omit `tools` entirely so the model must answer in text
        req = StreamRequest(..., messages=working,
                            **({} if last else {"tools": tool_defs,
                                                "tool_choice": "auto"}))
        text, tool_frags, finish = [], {}, None
        async for ev in client.stream(req):       # D8: 1st pass guards LLMError
            TokenEvent     -> text.append(ev.delta); yield {content: ev.delta}
            ReasoningEvent -> yield {reasoning_content: ev.delta}
            ToolCallEvent  -> reassemble into tool_frags[ev.index]   # D4
            UsageEvent     -> total_in += ev.input_tokens; total_out += ev.output_tokens
            DoneEvent      -> finish = ev.finish_reason
        if not tool_frags:                        # final text answer
            yield {finish_reason: finish or "stop",
                   usage: _Usage(total_in, total_out)}
            return
        calls = reassemble(tool_frags)            # [{id, name, args}]
        working.append({role:"assistant", content:"".join(text), tool_calls:[...]})
        for c in calls:
            yield {"tool_call": {"tool": c.name, "status": "running"}}    # D3
            res = await knowledge_client.execute_tool(ctx, c.name, c.args) # degrades
            working.append({role:"tool", tool_call_id: c.id,
                            content: json.dumps(res)})
            record c into tool_history
            yield {"tool_call": {"tool": c.name, "status": "ok"|"error"}}
    yield {content: "(I reached my tool-call limit.)", finish_reason: "stop",
           usage: _Usage(total_in, total_out)}    # defensive — unreachable via D7
```

---

## 5. Test plan

- **knowledge-service** — `GET /internal/tools/definitions` returns all 5
  schemas + is internal-token-gated; `projects.tool_calling_enabled`
  round-trips through the repo + `ProjectUpdate`; `build_context` surfaces
  it; default `true` for a project that predates the column.
- **chat-service `knowledge_client`** — `execute_tool` success / tool-error
  / transport-failure-degrades; `get_tool_definitions` fetch + cache + a
  fetch failure caches empty; `KnowledgeContext.tool_calling_enabled`
  default when absent.
- **chat-service `_stream_with_tools`** (the core) — mock `client.stream`
  to script passes: a no-tool pass streams text and returns; a one-tool
  pass executes + re-streams; `ToolCallEvent` fragment reassembly across
  `index`; the 5-iteration cap forces a `tool_choice="none"` final pass;
  `LLM_TOOLS_NOT_SUPPORTED` → one tool-free retry; usage sums across
  passes; `tool-call` SSE events emitted; `tool_calls` persisted; a tool
  failure (knowledge-service down) doesn't crash the turn.
- **`stream_response`** — gating on `tool_calling_enabled`; the no-tools
  path still works (regression).

---

## 6. Files

**knowledge-service (MOD):** `app/routers/internal_tools.py` (definitions
endpoint), `app/db/migrate.py` (`projects` column), `app/db/models.py`
(`Project` + `ProjectUpdate`), `app/db/repositories/projects.py`,
`app/context/builder.py` (`BuiltContext`), `app/routers/context.py`
(`ContextBuildResponse`). Tests: `test_internal_tools.py` (extend) +
projects/context coverage.

**chat-service (MOD):** `app/client/knowledge_client.py` (`execute_tool`,
`get_tool_definitions`, `KnowledgeContext` field), `app/db/migrate.py`
(`chat_messages.tool_calls`), `app/services/stream_service.py`
(`_stream_with_tools` + `stream_response` integration). Tests: a new
`test_stream_tools.py` + `knowledge_client` coverage.

**provider-registry (MOD):** `internal/provider/adapters.go` —
`anthropicAdapter` gains OpenAI→Anthropic `tools` / `tool_choice` /
`messages` conversion and `SupportsTools()` → `true`. Tests:
`adapters` tool-conversion coverage (Go).

---

## 7. Deferred / out of scope

| ID | Note | Target |
|---|---|---|
| D-K21B-01 | Move `definitions.py` to a shared `sdks/python` package instead of the `GET /internal/tools/definitions` endpoint (D1). | knowledge-service/SDK cleanup |
| D-K21B-02 | Voice chat (`voice_stream_service.py`) stays tool-free — wiring the loop into the voice path is a follow-up. | K21 follow-up |
| K21.5 / K21.7-sf4 / K21.12-FE | FE tool-call indicator, `memory_remember` user-confirmation flow, settings toggle. | K21 Cycle C |
