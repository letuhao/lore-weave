# ARCH-1 (AG-UI) + ARCH-2 (MCP) — design & delta assessment

- Date: 2026-06-01
- Branch: `arch-unify-chat-rag`
- Companion to: `2026-06-01-platform-landscape-gap-analysis.md` (why adopt MCP + AG-UI + A2A)
- Question this answers (PO): *"go deep into the design — is it a lot to change? I think not much,
  because we don't really have agentic AI yet."*
- **Answer: NOT much.** Not (only) because the agent is simple, but because the pieces we already
  built **accidentally already match the standard shapes**. The work is *conforming wire formats +
  packaging a component*, not redesigning logic. Evidence below.

---

## 1. The surprising finding — we're already ~80% shaped like the standards

### MCP (ARCH-2) — our tool layer is already client-server "list + call + envelope"
Verified in-repo:
- `knowledge-service/app/routers/internal_tools.py`:
  - `GET /internal/tools/definitions` → serves the tool schemas (single-sourced in
    `app/tools/definitions.py`). **≙ MCP `tools/list`.**
  - `POST /internal/tools/execute` → runs one tool, returns envelope `{success, result, error}`
    (always HTTP 200). **≙ MCP `tools/call`.**
- `chat-service/app/client/knowledge_client.py`: `get_tool_definitions()` (cached) + `execute_tool()`
  → **already an MCP-style client** (list, then call).
- `chat-service/app/services/stream_service.py` `_stream_with_tools` (K21-B): bounded loop
  (`MAX_TOOL_ITERATIONS=5`, final pass tool-free), reassembles tool calls, executes, feeds results
  back. **≙ a standard MCP tool-use loop.**

→ **Adopting MCP = re-skinning the existing list/execute endpoints as MCP JSON-RPC** (`tools/list`,
`tools/call`) and pointing the chat client at it. Schemas, executor, result envelope, client caching,
the bounded loop — all already exist and are unchanged.

### AG-UI (ARCH-1) — our stream is already the protocol AG-UI bridges
Verified in-repo:
- `chat-service/app/routers/messages.py` sets header **`x-vercel-ai-ui-message-stream: v1`**,
  `media_type=text/event-stream` — i.e. we already emit the **Vercel AI SDK data-stream protocol v1**
  (`stream_service.py` docstring line 1 says so explicitly).
- Backend already emits structured chunks: text delta, `reasoning_content` delta, `{"tool_call": …}`,
  finish/usage.
- Frontend `features/chat/hooks/useChatMessages.ts` consumes it with a **hand-rolled** reader
  (`res.body.getReader()` + `TextDecoder`) — **no `ai` / `@ag-ui` / `copilotkit` dependency.**

→ AG-UI is the agent↔UI layer that **bridges to/from the AI-SDK data-stream protocol** (official
adapters; AWS Bedrock AgentCore + CopilotKit do exactly this). We're already on the base format; the
delta is (a) map our chunk types → AG-UI event types, (b) replace the FE hand-rolled parser with an
AG-UI/AI-SDK client, (c) package `ChatView` as a reusable component.

---

## 2. Delta — what changes, what doesn't

### Unchanged (the hard, already-built layers)
- ✅ provider-registry gateway (model layer, BYOK, billing) — below the agent; untouched.
- ✅ knowledge-service RAG / context / memory / graph logic — only the tool *transport* is re-skinned.
- ✅ The bounded tool-use loop *logic* — only its client transport changes.
- ✅ Model adapters, pricing, usage-billing — untouched.

### Changes, by component (with rough size)

| # | Component | Change | Size |
|---|---|---|---|
| C1 | **knowledge-service** | Add an **MCP server facade** over the existing `tools/definitions.py` + `executor.py` (JSON-RPC `tools/list`/`tools/call`; reuse the official MCP Python SDK). Keep the internal HTTP endpoints during transition. | **S–M** |
| C2 | **chat-service** | Tool loop calls an **MCP client** instead of bespoke `knowledge_client.execute_tool`. Same loop, same bounded guard. | **S** |
| C3 | **chat-service** | Emit **AG-UI events** (map existing chunk types → AG-UI `TEXT_MESSAGE_*` / `TOOL_CALL_*` / `STATE_DELTA` / `RUN_FINISHED`). Keep the SSE transport. | **M** |
| C4 | **frontend** | Replace `useChatMessages` hand-rolled parser with an **AG-UI client** (`@ag-ui/client`) or Vercel AI SDK `useChat`. | **M** |
| C5 | **frontend** | Package `features/chat` as a **reusable `<Chat>` component** (providers + view + context-attach + write-back) and **wire the editor AI panel** (the disabled tab). = the visible half of ARCH-1. | **M** |
| C6 | **frontend/editor** | `STATE_DELTA` / frontend-tool-calls → editor write-back (insert/replace block) — this is also assisted-creation (WA-4). | **M** |
| C7 | **A2A seam (design-only, no MVP code)** | Give the chat agent an **agent-card** shape so it's A2A-addressable later (game multi-agent). | **design only** |

**Net: ~4 moderate + 2 small changes, concentrated in 2 seams (the tool transport, the stream
transport) + 1 packaging job. No rewrite of agent logic, RAG, gateway, or billing.**

### Why "we don't really have agentic AI yet" *helps*
- Single agent, single bounded loop, no multi-agent / handoffs / background jobs → **nothing complex
  to untangle**; the standards' simple path is enough.
- Tools are a small fixed domain set → the MCP server is small.
- One chat surface today → one component to package + one panel to wire.

---

## 3. MVP scope vs deferred

**MVP (this ARCH track):**
- C1–C2: MCP server (knowledge tools) + chat agent as MCP client. *Scope tools to the 3 verticals.*
- C3–C5: AG-UI events + FE AG-UI client + reusable `<Chat>` + editor panel wired.
- C6: minimal editor write-back (insert/replace at cursor) → unblocks assisted-creation.

**Deferred (design the seam, don't ship):**
- Power-user-registered MCP servers/tools (registry surface exists internally; not exposed).
- Exposing LoreWeave as an external MCP *server* (distribution).
- A2A multi-agent (game) — C7 seam only.
- Realtime-voice-with-tools beyond current voice.

---

## 4. Design decisions — ✅ LOCKED (PO-approved 2026-06-01)

> **Locked decisions (summary):** adopt the LF-governed 3-layer standard stack —
> **MCP** (tool contract, ARCH-2) over **Streamable HTTP**; **AG-UI** as the agent↔UI *contract*
> for ARCH-1, implemented on the wire via **Vercel AI SDK** (`ai`/`@ai-sdk/react`), **no CopilotKit**;
> **editor write-back via AG-UI frontend-tool-calls**; **A2A** = design the agent-card seam only, ship
> later (game multi-agent). **Session scope = bind to a knowledge `project`** (already built);
> project-tree + cross-project sharing are a future additive schema extension (seam now, ship later).
> Transition is **dual-run** then retire the bespoke path.

1. **MCP transport for internal tools → Streamable HTTP.** The current MCP transport is "Streamable
   HTTP" (JSON-RPC over a single HTTP endpoint, SSE for server→client streaming; superseded the old
   HTTP+SSE pair). It fits our service mesh (knowledge-service is already an HTTP service); stdio is for
   local subprocess tools (not our case). **Recommend Streamable HTTP**, chat-service = MCP client,
   knowledge-service = MCP server.
2. **AG-UI adoption depth on FE → adopt AG-UI as the *contract*; implement via Vercel AI SDK on the
   wire; skip CopilotKit for MVP.** We already emit the Vercel AI-SDK data-stream protocol v1, so using
   `ai` + `@ai-sdk/react` (`useChat`) for transport is the lowest-churn path. Shape the agent↔UI events
   to **AG-UI event types** (TEXT_MESSAGE_*, TOOL_CALL_*, STATE_DELTA, RUN_*) via the official
   AG-UI↔AI-SDK bridge so the contract is standard + future-proof. **Don't pull in CopilotKit** (heavy,
   opinionated UI — we already have a mature `ChatView`).
3. **Editor write-back → AG-UI frontend-tool-calls.** The agent calls editor-side tools the frontend
   registers (`insert_text(range,text)`, `replace_range`, `apply_patch`). Cleaner "apply this edit"
   semantics than STATE_DELTA, and it's exactly the assisted-creation (WA-4) mechanism. Reserve
   STATE_DELTA for syncing structured UI widgets (later).
4. **Session scoping → bind a chat session to a knowledge `project` (already the design!).** See §4a.
5. **Transition → dual-run.** Stand up the MCP server facade *alongside* the existing
   `/internal/tools/{definitions,execute}` endpoints, migrate chat-service to the MCP client, verify,
   then retire the bespoke path. Low-risk, incremental.

### 4a. Session scope = knowledge `project` (PO was right — it's largely already built)

Verified in-repo:
- **`knowledge_projects`** (project_id, user_id, **`project_type ∈ {book, translation, code, general}`**,
  nullable **`book_id`** cross-DB ref). → a "project" can scope **anything** (a book, a translation, code,
  or a free-form general project). ✅ matches the PO model "scope is anything".
- **Hierarchical context scope** — `knowledge_summaries.scope_type ∈ {global, project, session, entity}`
  (L0 global → L1 project → session → entity). ✅ matches "a project has large→small levels".
- **`chat_sessions.project_id`** already exists (nullable, cross-DB). chat-service `build_context(project_id=…)`
  passes it to knowledge-service; "a no-project chat is valid". → **chat sessions are already
  project-scoped.**

**So the session-scope question dissolves:** we do NOT invent per-chapter / per-book / shared session
*types*. A chat session **binds to a knowledge project**; granularity (chapter / scene) is handled by
the context-scope hierarchy *inside* the project, not by a new session type. Concretely:
- Editor AI panel (classic-novel) → chat session bound to the book's knowledge project; the current
  chapter/selection is passed as session/entity-scope context (+ via AG-UI context-attach).
- VN / game → the same: a project of the appropriate type, same session→project binding.

**One correction to the PO recollection:** "a project is *shared across many projects*" is **NOT yet in
the schema.** Today projects are **flat + per-user** (no `parent_id`, no project↔project share/membership
table). The hierarchy that exists is the *context-scope* hierarchy (global→project→session→entity),
**within** a project — not a project tree, and not cross-project sharing.
- ✅ Built: typed projects (scope = anything), book-linkage, within-project scope hierarchy, session→project binding.
- ❌ Not built (future): **project tree** (parent/child projects, e.g. a shared world/universe spanning
  multiple books) and **cross-project sharing** (one project's knowledge reused by others). These are a
  natural, additive schema extension (`parent_project_id` + a `project_shares` membership table) — design
  the seam, ship later. This matters for the **game** vertical (a game world built from many books/projects).

---

## 5. Recommendation

The refactor is **conforming, contained, and low-risk** — concentrated in two transports (tool +
stream) and one component-packaging job, with the heavy layers (gateway, RAG, memory, billing)
untouched. The PO's instinct holds: **not much to change.**

**Status: design + decisions LOCKED (§4, 2026-06-01).** Next session → a per-component BUILD plan
(C1–C6 in §2) with sequencing, contracts (exact MCP tool list, AG-UI event mapping, editor-tool
schemas), and tests. Suggested order: **C1+C2 (MCP, dual-run) → C3 (AG-UI events) → C4 (FE client) →
C5 (`<Chat>` + editor panel) → C6 (write-back/WA-4).** A2A agent-card seam + project-tree/sharing
seam are designed-but-deferred.
