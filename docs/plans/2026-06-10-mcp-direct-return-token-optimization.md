# Plan — MCP "direct-return" / dual-audience tool results (token + latency optimization)

> **Status:** PLANNED (not started). Captured 2026-06-10 from a user observation during the glossary-assistant live-smoke.
> **Origin:** while testing `glossary_list_kinds` through the real chain (browser → chat → ai-gateway → glossary MCP), the round-trip is:
> `agent calls MCP → MCP returns to agent → agent reads response → agent "cooks" a reply → responds to user`.
> For tools whose result IS the user's end goal (pure display/listing), the final model turn is wasted tokens + latency.
> **Owning service for the fix:** `chat-service` (it owns the agent loop). The Go/TS MCP tools only *annotate intent*; they cannot skip the loop themselves.

---

## Problem

In the standard agentic loop (Anthropic Messages API / OpenAI tool-use), **after every `tool_result` the loop re-invokes the model** to produce the next turn. For a tool like `glossary_list_kinds` that just returns data the user asked to see, that extra model turn:

- burns output tokens re-narrating data the tool already produced, and
- adds a full model round-trip of latency,

with no added value — the model only paraphrases what the tool returned.

The user proposed two ideas to optimize this:
1. **Direct-return** — some tool calls should return straight to the user, the agent does not analyze/cook the response.
2. **Dual-channel response** — a tool returns (a) a short status for the agent to read (ok / failed / message), and (b) the payload meant for the user.

---

## Research findings (2026-06-10) — what MCP gives us vs. what we must build

The idea is **real and exists in the ecosystem**, but it splits into two parts and **only one part is in the MCP SDK**.

### Part (b) — dual-audience response → **IS in the MCP spec**

MCP defines `annotations.audience` on *every* content block (text / image / resource). `audience` ∈ `["user"]`, `["assistant"]`, or both, plus `priority` (0–1):

```jsonc
{
  "content": [
    { "type": "text", "text": "Found 12 kinds",
      "annotations": { "audience": ["assistant"], "priority": 0.3 } },   // for the model
    { "type": "resource", "resource": { /* ... */ },
      "annotations": { "audience": ["user"], "priority": 0.9 } }          // render to the user
  ]
}
```

**Caveat:** the spec states *"annotations are hints, not guarantees of behavior."* The server only labels content; **the client (chat-service) must implement the logic that honors the label.** MCP does nothing automatically.

Related: `structuredContent` + `outputSchema` (spec rev 2025-06-18) let a tool return compact, machine-readable JSON. This **reduces token bulk** but the result **still passes through the model** — it does not skip the turn.

### Part (a) — direct-return (skip the model) → **NOT in the MCP protocol**

There is **no `returnDirect` flag in MCP**. The "skip the model to save tokens/latency" behavior is a **harness / agent-loop decision**, implemented in our own orchestration code, not provided by the SDK.

Prior art at the framework layer: **LangChain / LangGraph `return_direct=True`** — when set, the tool's output is returned to the caller immediately without going back through the model. Note: even there it is reported as **flaky** (depends on graph/ToolNode structure — the model sometimes still produces a trailing message). So a careful implementation matters.

**Why it can't live in MCP:** MCP only defines the *shape* of a tool result. The decision to loop back to the model belongs to whoever runs the loop — here, `chat-service`.

---

## Design direction (to be refined when the task is picked up)

Implement in **chat-service** (owns `_stream_with_tools` / the tool loop):

1. **Tool classification — "terminal/display" vs "reasoning-input".**
   Mark a subset of tools as *display* tools. When the LLM calls a display tool and there is no further pending tool call, render its `structuredContent` (or `audience:["user"]` content) **directly to the FE and end the turn — do not re-invoke the model.**

2. **Carry intent via MCP annotations.** Have the Go/TS MCP tools tag result content with `annotations.audience` (and optionally `priority`). chat-service reads the annotation through ai-gateway and uses it as the signal for what to render to the user vs. feed back to the model. (Keeps the policy declarative + close to the tool, while honoring stays in chat-service.)

3. **Adopt `structuredContent` + `outputSchema`** on the relevant Go MCP tools so display results are compact JSON the FE can render without a model paraphrase.

### Critical guardrail — direct-return is NOT a blanket optimization

`glossary_list_kinds` is most often a **means to an end**, not the end itself. In the "propose entity" flow the model **must** read the kinds, then reason further (search → get_entity → propose). Direct-returning there would **break the flow**.

Direct-return is only correct when the tool-call **is the user's actual end goal** (e.g. "list the kinds for me to see"). Therefore the trigger must be **conditional**, not per-tool-blanket. Options to evaluate:
- direct-return only when the display tool is the **last** tool call of the turn AND the model emitted no accompanying reasoning/next-step;
- or expose a **separate "display variant"** of the tool used only on explicit user-facing list/show intents;
- or let the model itself signal terminal intent.

This decision (the trigger condition) is the main design risk and should be settled in CLARIFY/DESIGN before BUILD.

---

## Scope / files (anticipated — confirm at PLAN)

- `chat-service` — agent loop (`_stream_with_tools`, `_emit_chat_turn`): terminal-tool detection + skip-model + render path; tool classification config.
- Go MCP tools (`glossary-service`) — add `annotations.audience` + `structuredContent`/`outputSchema` to display-oriented read tools (`glossary_list_kinds`, possibly `glossary_search`/`glossary_get_entity`).
- `ai-gateway` — verify annotations + structuredContent pass through the federation envelope (INV-7) unmodified.
- FE chat — render direct-return display payloads (a card/list component) instead of an assistant text bubble.

## Verification (anticipated)

- Unit: terminal-tool path skips the model turn; reasoning-input tools still loop.
- Token/latency measurement: before/after on a "list kinds" turn — this task only earns its keep if measured (avoid mock-only green; do a real-provider live-smoke per the cross-service evidence rule).
- Regression: the propose-entity flow (which depends on the model reading `list_kinds`) must NOT be short-circuited.

## Open questions for CLARIFY

1. What is the trigger condition for direct-return (last-tool-call heuristic vs separate display variant vs model-signaled)?
2. Do we need streaming for direct-return payloads, or is a single rendered block enough?
3. Which existing tools are genuinely "display" vs always reasoning-input?

---

## Sources

- MCP Tools spec (2025-06-18) — annotations & audience: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- SEP-1624 — `structuredContent` vs `content` guidance: https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1624
- LangGraph discussion — return tool output directly, skip agent LLM: https://github.com/langchain-ai/langgraph/discussions/5995
- LangChain tools docs — `return_direct`: https://docs.langchain.com/oss/python/langchain/tools
