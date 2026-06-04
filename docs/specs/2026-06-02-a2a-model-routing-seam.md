# A2A Model-Routing Seam — orchestrator (tool model) + reasoning sub-agent

> **Status:** Design sketch / roadmap (NOT a Track-1 build). Forward-looking
> follow-on to ARCH-1 (MCP + AG-UI + frontend tools) and the ARCH-2 A2A seam.
> Author: session 104 (2026-06-02), branch `arch-unify-chat-rag`.
> Prerequisite shipped this session: **editor "Compose" mode** (`disable_tools`)
> — the cheap, single-model stepping stone described in §6.

---

## 1. Problem

Two model strengths are in tension for assisted creation (WA-4):

| Need | Best served by | Weakness |
|---|---|---|
| **Reliable tool-calling** (propose_edit, memory_*) | instruct/coder models (e.g. `qwen3-coder-30b`) | prose is serviceable, not great |
| **High-quality prose** (sáng tác) | reasoning models (`qwen3.5`, `qwen3.6`) | heavy/slow on tool emission; `qwen3.6-35b` got stuck in `<think>` and never emitted a tool call in the C6 live smoke |

Empirically (session 104): tool-calling is **not** broken for Qwen 3.5 — it emits
clean OpenAI tool calls raw, streamed, and end-to-end through chat-service (1.8s).
The real issue is **reasoning models spend their budget reasoning before/around the
tool call**, and some heavier ones stall. So we don't want a reasoning model
driving a tool loop; we want it to do what it's best at — write — while a
tool-capable model handles orchestration.

Big platforms solve this with **model routing** (a fast router/orchestrator model
dispatches to specialists). We are **resource-constrained** (local LM Studio,
typically one model resident in VRAM at a time) so a full ML router is out. This
doc specifies the *minimal* routing seam that fits our stack and the standard
**A2A (Agent-to-Agent)** direction already on the ARCH roadmap.

---

## 2. The seam — where it lives

The chat-service tool loop (`_stream_with_tools` in
`services/chat-service/app/services/stream_service.py`) is already the
orchestration point: it runs the LLM, sees tool calls, executes them, loops. We
add **one more "tool" the orchestrator can call**: a *prose-generation capability*
delegated to a different (reasoning) model.

```
Orchestrator model  = the session's tool-capable model (coder/instruct)
Sub-agent           = a reasoning model, invoked for ONE turn as a pure generator
Seam                = a server-side capability "compose_prose" that the
                      orchestrator calls; chat-service fulfils it by streaming a
                      SECOND model, then returns the text as the tool result
```

Crucially the sub-agent call is **server-side and synchronous within the loop** —
unlike the C6 *frontend* tool (propose_edit) which suspends to the browser. So it
reuses the existing inline-tool-execution path, not the suspend/resume path.

---

## 3. Concrete flow (one turn)

```
User: "Rewrite this paragraph to be more atmospheric, keep the lore."

Request 1 (orchestrator = qwen3-coder-30b, tools = [memory_*, compose_prose, propose_edit]):
  pass 0: model calls memory_recall_entity("the city")      → executed inline (existing)
  pass 1: model calls compose_prose({                       → NEW seam
            instructions: "rewrite atmospherically, keep lore X/Y",
            source_text: "<the paragraph>",
            context_refs: [recalled lore]
          })
     └─ chat-service resolves a REASONING model (provider-registry) and streams it
        with a writer system prompt; collects the prose. Returns it as the tool
        result. (AG-UI: emit TOOL_CALL_START/ARGS + a CUSTOM "sub-agent:compose"
        progress event so the FE can show "✍️ Drafting with <reasoning model>".)
  pass 2: model calls propose_edit({operation:"replace_selection", text:<prose>})
     └─ SUSPENDS to the browser (C6 path) → user Apply → resume → done.
```

The reasoning model never touches the tool loop — it only generates text. The
coder model never has to write great prose — it orchestrates and packages. Each
does what it's good at.

---

## 4. Mapping to existing code

| Concern | Reuse |
|---|---|
| Add `compose_prose` schema | new entry alongside `frontend_tools.py` (but server-executed, like memory tools) — advertise only when a reasoning sub-agent model is configured |
| Resolve the sub-agent model | `provider_client.resolve(model_source, model_ref, user_id)` — needs a per-session/per-project "writer model" ref (new session field, e.g. `composer_model_ref`) |
| Stream the sub-agent | a second `loreweave_llm.Client.stream()` inside the tool handler; same SDK |
| Surface progress | AG-UI `CUSTOM` event (`stream_events.py`) — "sub-agent active" so the UI isn't silent during the (slow) reasoning pass |
| Usage/billing | sum sub-agent tokens into the turn usage (the `seed_usage`/`total_*` accumulation pattern from C6 already sums across passes) |
| A2A protocol framing | when knowledge-service / a future writer-service becomes a separate agent, `compose_prose` becomes a real **A2A task** over the A2A seam instead of an in-process second `Client` |

---

## 5. Relationship to A2A / MCP standards

- **In-process (phase 1):** `compose_prose` is just a second model call inside
  chat-service. No protocol needed. Cheapest.
- **A2A (phase 2):** the prose generator is exposed as an **A2A agent** (Agent
  Card + task endpoint). chat-service's orchestrator sends an A2A `task` and
  streams the result. This is the "router multiple model" pattern big platforms
  use — but driven by an *explicit capability call*, not an opaque ML router.
- **MCP** stays the transport for *tools/memory* (knowledge-service); **A2A** is
  the transport for *agent delegation* (orchestrator ↔ generator). They compose:
  the sub-agent can itself use MCP memory tools if needed.

---

## 6. MVP stepping stones (what's done / what's next)

1. **DONE (this session): editor "Compose" mode** — `disable_tools` per turn
   (`SendMessageRequest.disable_tools` → `stream_response`). The user manually
   routes: Agent (tool model, tools on) vs Compose (any model, prose-only, Apply
   by hand). Zero extra models, zero protocol. This already lets a reasoning
   model draft cleanly today. *This is the 80/20 — ship and learn.*
2. **NEXT-LIGHT: per-session `composer_model_ref`** + a `compose_prose`
   server-tool that streams the chosen writer model in-process (phase 1 above).
   Single feature, no A2A protocol, but auto-routes within one turn.
3. **LATER: true A2A** — promote the generator to an A2A agent once there's a
   reason (separate scaling, a dedicated writer-service, or a cloud writer model).

---

## 7. Resource constraints (the hard part on local hardware)

- **LM Studio typically keeps one model resident.** Swapping orchestrator ↔
  reasoning mid-turn can trigger **model load/unload thrashing** (tens of seconds
  per swap) — which would make phase-2 in-process routing *slower than helpful*.
  Mitigations, in order of preference:
  1. **Co-resident models** — load both a small coder (orchestrator) and a
     reasoning model at once (needs enough VRAM; a 30B-a3b MoE + a small coder may
     fit; otherwise a 7-8B orchestrator).
  2. **One role in the cloud** — orchestrator = small/cheap cloud model (fast tool
     calls), writer = local reasoning model (or vice-versa). BYOK already supports
     mixed providers via provider-registry.
  3. **Defer** — keep Compose mode (manual routing) until hardware/budget allows.
- **Latency budget:** the reasoning pass dominates; always stream a progress event
  so the editor shows "drafting…" rather than a frozen panel.
- **Usage:** two model calls = two billings; sum them (already supported) and make
  it visible so the cost is not a surprise.

---

## 8. Open questions

- Where does the **writer system prompt** live — per-project (lore voice), per-user
  preset, or a fixed "novelist" prompt? (Session already has `system_prompt`;
  Compose could reuse it, A2A needs its own.)
- Should `compose_prose` return **plain text** (MVP) or **structured Tiptap JSON**
  for richer inserts? (C6 is plain-text insert today.)
- Selection semantics: replace-selection vs insert — the orchestrator must pass
  the live selection range (FE already exposes `getSelection()` from C6).
- Failure mode: sub-agent stalls/empties → orchestrator should fall back to its
  own prose or surface an error, not hang the turn.

---

## 9. Decision

Ship **Compose mode** now (done) as the resource-appropriate answer. Treat the
in-process `compose_prose` seam (phase 1) as the next increment *only when* there's
a co-resident or cloud writer model available — otherwise model-swap thrashing
makes it a net loss. Full A2A is a Track-2 item, unblocked by the same hardware
condition. The seam is designed so each phase is additive and reuses the existing
tool loop, model resolution, AG-UI events, and usage summation.

**Status update (session 104):** phase-1 `compose_prose` is SHIPPED (the seam,
the per-session `composer_model_ref`, the Session-Settings dropdown, and the
"✍️ Drafting…" indicator). What remains is purely operational — pointing the
composer at a model that won't thrash. See §10.

---

## 10. Operational setup — configuring the composer writer (no code, infra)

`compose_prose` works with ANY model the user registers in provider-registry
(BYOK). The ONLY operational concern is the model-swap thrash on a single-GPU
local stack (§7). Pick the option matching the hardware:

### Option A — Cloud writer (recommended for production)
1. **Register a cloud chat model** (BYOK) in provider-registry: Settings →
   Providers → add an Anthropic / OpenAI / etc. credential, then a user-model
   (e.g. `claude-sonnet-4-x`, a strong prose model).
2. **Set it as the session's composer**: editor AI panel → Session Settings →
   *Composer model (optional)* → pick the cloud model. (Orchestrator stays the
   local/tool-capable model.)
3. No thrash — the writer runs remotely; the local orchestrator stays resident.
   Cost = two billed calls per delegated turn (orchestrator + writer); usage is
   summed and shown.

### Option B — Local co-resident (enough VRAM for two models)
1. In **LM Studio → Settings**: set **Max loaded models ≥ 2** (or enable JIT
   loading) and a generous model-idle TTL so both stay resident.
2. Load a small **orchestrator** (e.g. `qwen3-coder-30b` / a 7–8B instruct) +
   the **writer** (a reasoning model). Confirm both fit in VRAM simultaneously.
3. Register both as user-models; set the writer as the session composer.
4. Verify no thrash: a delegated turn should complete in seconds (the
   "✍️ Drafting…" pill flicks on/off quickly), not the ~minutes a cold model
   load takes. The composer pass streams a `composing` CUSTOM event so latency
   is visible.

### Option C — Single-GPU, one model only (default; no extra setup)
Leave **Composer model = None**. `compose_prose` is then NOT advertised, and the
editor's **Compose mode** toggle is the routing tool: switch a session to a
reasoning model for prose (no tools) vs. the tool-capable model for agentic
edits. This is the resource-appropriate path until cloud/VRAM is available.

> **Anti-pattern:** setting a *different local* composer on a single-GPU stack.
> Every delegated turn unloads the orchestrator, loads the writer, then reloads
> the orchestrator — tens of seconds each way. Use Compose mode (Option C) or a
> cloud writer (Option A) instead.

### Verify (any option)
A delegated turn's SSE should show: `TOOL_CALL_START compose_prose` →
`composing active=true` → (writer streams) → `composing active=false` →
`TOOL_CALL_RESULT {ok:true, result:{prose}}` → closing assistant text. If the
gap between the two `composing` events is tens of seconds on a local stack, the
writer is cold-loading (thrash) — revisit the option above.
