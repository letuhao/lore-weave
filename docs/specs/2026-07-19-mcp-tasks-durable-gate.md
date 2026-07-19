# Spec — Build the MCP **Tasks** durable-gate ourselves (skip the v2 migration)

- **Date:** 2026-07-19
- **Status:** DRAFT — for pressure-testing. No code yet.
- **Owner track:** Frontend-tools → MCP migration ([`2026-07-19-frontend-tools-mcp-migration.md`](2026-07-19-frontend-tools-mcp-migration.md)). This spec is the **keystone** that unblocks that migration's native-gate phases (1-2).
- **Thesis (user-directed):** MCP v2 offers us **near-zero new capability** — we already have v1-era equivalents for everything *except* the **Tasks** extension (durable `input_required`, resume-by-poll). And v2 wouldn't even give us Tasks on our **Go** domains (the Go SDK has no Tasks in v1 *or* the v2 pre-release). So instead of paying the enormous v2 migration debt (FastMCP→MCPServer rewrite of 6 services + TS gateway repackage) for nothing, **we build the one missing piece — Tasks — ourselves, on v1.** Then v2 is *permanently optional* until it stabilizes and we choose to adopt it.

---

## 1. Why this, why now

The reported bug (`019f771a`) was fixed by **Phase 0** (server-side arg validation at the frontend-tool seam). The *rest* of the migration's value is making the **human gate** for high-impact writes (delete book, create glossary kind, publish, destructive ontology ops) a **native MCP primitive** instead of our bespoke `confirm_token` + frontend-tool-suspend construct.

The blocker we found: a **correct** native gate must be **durable** — it survives the human taking minutes, or closing the browser, mid-confirm. Raw MCP **elicitation** (server pushes a request back to the client mid-call) is the *wrong* primitive for that: it needs a held-open connection + bidirectional relay through our stateless proxy, and it dies on disconnect. The **right** primitive is **Tasks**: a durable `taskId`, poll-based, `input_required` for the gate. But Tasks isn't in the Go SDK.

**So: build Tasks ourselves.** It is *more* tractable than raw elicitation (below), reuses our battle-tested durable store, and closes the one real gap between us and MCP v2.

---

## 2. The MCP Tasks protocol (authoritative — from the spec)

Source: [modelcontextprotocol.io/extensions/tasks](https://modelcontextprotocol.io/extensions/tasks/overview) · [ext-tasks repo](https://github.com/modelcontextprotocol/ext-tasks). Extension id: **`io.modelcontextprotocol/tasks`**.

**Lifecycle** (all client→server; **no unsolicited server→client messages**):
1. **Capability negotiation.** Client declares the extension in *per-request* capabilities:
   `params._meta["io.modelcontextprotocol/clientCapabilities"].extensions["io.modelcontextprotocol/tasks"] = {}`.
   Server advertises the same in its `server/discover` capabilities. Server MUST NOT return a task to a client that didn't declare support.
2. **Task creation.** For a supported request (e.g. `tools/call`), instead of the normal result the server returns a **`CreateTaskResult`** (`resultType: "task"`) with `{ taskId, status, ttlMs, pollIntervalMs }`. **The task is durably created before the response is sent.** Server-directed: the *server* decides per-request whether to make a task; the client just handles whichever shape arrives.
3. **Polling.** Client calls **`tasks/get(taskId)`** → current `status` (+ `result`/`error` on terminal states), respecting `pollIntervalMs`.
4. **Mid-flight input (the gate).** When the task needs the human, it moves to **`input_required`**; the `tasks/get` response carries an **`inputRequests`** map (elicitations / server requests). The client presents them and answers via **`tasks/update(taskId, inputResponses)`** → server acks (empty result).
5. **Completion.** `status: completed` → `result` holds what the sync call would have returned. `failed` → `error`. `cancelled` → cooperative stop.
6. **Cancellation.** `tasks/cancel(taskId)` — cooperative; may still reach a non-cancelled terminal.

**Statuses:** `working | input_required | completed | failed | cancelled` (last three terminal).
**Methods:** `tasks/get`, `tasks/update`, `tasks/cancel`. (`tasks/list` removed in the RC; `tasks/result` replaced by `tasks/get` polling.)
**Notifications (optional):** `notifications/tasks` via `subscriptions/listen` — a poll-avoiding optimization. **We start poll-only.**

### 2.1 Why Tasks fits us where elicitation didn't
| | Raw elicitation | **Tasks** |
|---|---|---|
| Direction | server→client **push** mid-call | **all client→server** (poll) |
| Connection | held open until the human answers | none — durable `taskId`, resume by poll |
| Our stateless proxy | needs bidirectional relay + held request (hard, load-bearing) | **forward 3 new methods** (`tasks/get`/`update`/`cancel`) + `taskId→provider` route (**additive**) |
| Durability | dies on disconnect | `taskId` survives disconnect (spec requirement) |

---

## 3. Current state — we already have a *proto-Tasks*

Our `confirm_token` + `chat_suspended_runs` **is** a durable input-required gate, just not in the Tasks protocol shape:

| Our mechanism today | MCP Tasks equivalent |
|---|---|
| domain propose tool **mints a `confirm_token`** (persisted; no write) | `tools/call` → **`CreateTaskResult`** (`taskId`, durable) |
| the token's pending action, awaiting confirm | task **`input_required`** + `inputRequests` (the confirm elicitation) |
| `chat_suspended_runs` (durable, owner-scoped, 6h TTL) | the **durable task store** (`ttlMs`) |
| FE confirm card | client presents `inputRequests` |
| human Confirm → `POST /v1/<domain>/actions/confirm` (token) | **`tasks/update`**(taskId, inputResponses) |
| domain commits the write | task → **`completed`** (`result`) |
| outcome enum (`action_done`/`token_expired`/…) | terminal status + `result`/`error` |

⇒ Building Tasks is **~80% re-shaping working machinery into the standard protocol**, not inventing a durable store. The `chat_suspended_runs`/confirm-token persistence stays; we add the protocol face.

**SDK reality (from SP-0 spike):**
- **Python `mcp` 1.28.1** (chat-service client + composition/translation/jobs/lore-enrichment servers) **already ships the Tasks extension** (experimental: `Task`, `TASK_STATUS_INPUT_REQUIRED`, `tasks/get`, server `task_context`/`task_scope`, client `experimental/tasks`+`task_handlers`). → **leverage natively.** *(SP-0 must confirm the experimental API is usable — see §6.)*
- **Go `go-sdk` v1.6.1 / v1.7.0-pre.3** — **no Tasks.** glossary + book are Go → need our own small Tasks facade (§4.3).
- **TS `@modelcontextprotocol/sdk` 1.29.0** (ai-gateway) — must forward the new task methods (§4.4). No v2 needed.

---

## 4. Target architecture

**Principle:** the `taskId` binds to a durable **suspended-run / task row** we own; the gate is `input_required`; the client drives it by poll + `tasks/update`. Reuse `chat_suspended_runs` as the store. Keep `confirm_token` as the **capability-absent fallback** (a client that doesn't declare tasks support still gets today's behavior — never a regression).

```
LLM (chat-service, MCP client, declares tasks cap per-request)
  → ai-gateway proxy  (forwards tools/call; NEW: forwards tasks/get|update|cancel by taskId→provider)
    → domain service (owns the write + the task)
        Python domains: native Tasks (mcp 1.28.1 task_context)
        Go domains (glossary/book): our Tasks facade (§4.3)
        durable task row (reuses / mirrors chat_suspended_runs)
```

### 4.1 The gate flow (KIND-C, e.g. `glossary_book_delete`)
1. LLM calls `glossary_book_delete(book_id)` **with the tasks capability** in `_meta`.
2. Domain **durably creates a task** (persist intended action + `taskId`), returns `CreateTaskResult{ taskId, status: input_required, ttlMs, pollIntervalMs }` carrying `inputRequests` = the confirm descriptor (title, preview, what will happen).
3. chat-service sees `resultType:"task"` + `input_required` → **suspends** (reuse `chat_suspended_runs`, keyed by `taskId`), streams the confirm card to the FE. Turn parks exactly like today.
4. Human Confirms → chat-service calls **`tasks/update(taskId, inputResponses={confirmed:true})`** → domain executes the delete, task → `completed`.
5. chat-service **`tasks/get(taskId)`** → `completed` + `result` → resumes the turn with the real outcome. (Decline → `tasks/update` with a decline / `tasks/cancel` → `cancelled`.)

### 4.2 Capability negotiation
- chat-service (client) adds the tasks extension to **per-request `_meta`** on every `tools/call` it wants gate-able. (Backward-safe: absent ⇒ domain falls back to `confirm_token`.)
- ai-gateway advertises `io.modelcontextprotocol/tasks` in `server/discover` and **passes the client capability through** to the domain (it already forwards `_meta`, see `federation.executeTool` `params._meta`).
- Each task-capable domain advertises the extension in its capabilities.

> **⚠ SAFETY-CRITICAL (T1c(2) finding, 2026-07-19): the tool flip MUST be capability-gated, never unconditional.**
> If a KIND-C tool returns `open_gate(...)` (a task) to a client that did NOT declare tasks support (today's
> chat-service, the public edge, external agents), that client gets a durable task it cannot drive → the real
> action is stranded forever. So a task-capable domain tool does: **`if <client declared tasks>: return await
> open_gate(...) else: return {confirm_token, descriptor, …}` (today's path)**. The gating read + the chat-service
> DRIVER (T1c(3)) must land TOGETHER — flipping a tool before its client can drive tasks is a broken deploy.
> Reading the per-request client capability inside a FastMCP tool (from `ctx`/the request `_meta`) is the small
> unbuilt piece T1c(2) needs; until then, the facade stays proven-but-unwired (no live domain tool is flipped).

### 4.3 The Go Tasks facade (glossary, book)
A small reusable Go helper (candidate home: `sdks/go/` MCP layer, mirroring `loreweave_mcp`): persist a task row, implement `tasks/get`/`tasks/update`/`tasks/cancel` handlers, map `taskId`→the pending action. The propose tools return `CreateTaskResult{input_required}` instead of minting a `confirm_token`; the existing `/actions/confirm` commit logic moves behind `tasks/update`. **The write path and optimistic-lock (If-Match / base_version → 409/412) are unchanged** — a stale confirm still surfaces as `failed`/conflict, model self-corrects.

### 4.4 ai-gateway forwarding (additive, no rewrite)
Add `tasks/get` / `tasks/update` / `tasks/cancel` request handlers to the proxy Server that route by **`taskId`→owning provider** (a new routing dimension alongside tool→provider). Reuse the per-call envelope-header client (`buildEnvelopeHeaders`, INV-7). No held-open connection, no server→client relay — these are ordinary forward calls. Governance note (rate-limit/audit at the edge) applies the same as tools/call.

### 4.5 chat-service client
Wire the mcp 1.28.1 client task handlers (or a thin equivalent): detect `resultType:"task"`, persist `taskId` into `chat_suspended_runs`, poll `tasks/get` (respect `pollIntervalMs`), submit `tasks/update` on the human decision. **Reuses the whole existing suspend/resume + persistence path** (incl. the Phase-0 persistence fix).

### 4.6 Frontend
Reuse existing cards (`ConfirmActionCard`, `RecordDiffCard`, `GlossaryDiffCard`) to render `inputRequests`; Confirm/Dismiss/Close → the `tasks/update` accept/decline/cancel. **No new FE protocol** — the confirm card already exists; only the resolve endpoint shape changes.

---

## 5. Edge cases
1. **Client without tasks capability** (legacy, public edge) → domain returns the **`confirm_token`** result exactly as today. No regression; dual-path during migration. ✔
2. **TTL expiry** (`ttlMs`) → maps to today's token-expired (`token_expired` outcome). Reuse `chat_suspended_runs` TTL sweep. ✔
3. **Optimistic-lock / staleness** (base_version → 409/412) → task `failed` with the conflict; model re-reads + re-proposes. ✔ unchanged.
4. **Batch confirm** (N items, one card) → one task with a multi-part `inputRequests` / a batch descriptor. ✔ representable.
5. **taskId routing after a gateway restart** → taskId must encode/resolve its provider durably (persist taskId→provider, or make provider derivable from the taskId). ⚠ design detail — decide in build.
6. **Sensitive confirm** (BYOK secret) → task `input_required` with a **url-mode** input request (out-of-band), never through the LLM. ✔ available.
7. **Cancellation on turn abort** → `tasks/cancel`; cooperative. Aligns with our disconnect-abort (#19). ✔
8. **Poll load** → respect `pollIntervalMs`; poll-only for v1, add `notifications/tasks` later if needed. ✔

---

## 6. Phased plan (each independently shippable, review-impl + live-E2E)
- **SP-T0 — Tasks spike → DONE** (§6.1): the SDK experimental Tasks is a dead end (removed in 2.0) → hand-roll.
- **T1a — durable-gate CORE → DONE** (`56fba54af`). `loreweave_mcp/tasks.py`: the store + `input_required →
  completed|cancelled|failed` lifecycle, double-confirm guard, TTL, cancel-idempotency. 11 unit tests.
- **T1b — FastMCP WIRE + live E2E → DONE** (`bebd1b2c2`,`84ce42f01`). `loreweave_mcp/tasks_wire.py`:
  `register_task_endpoints` (tasks/get + tasks/cancel handlers on `_mcp_server.request_handlers`; `task_provide_input`
  tool for the input step) + `open_gate`. **Live-proven over a real in-process MCP client↔server session** (accept
  loop: gate → tasks/get input_required → provide_input → executor runs → completed, nothing written until accept;
  decline → cancelled). Learnings: tasks/get carries STATUS only (1.28.1 `GetTaskResult` has no `inputRequests`
  field + `_meta` doesn't round-trip); card payload rides the gate handle, result rides the provide_input response.
- **T1c(1) — `CreateTaskResult` CallTool wrap → DONE** (`4f0724238`). `enable_task_results`; live E2E.
- **T1c(2) — capability-gating primitive + REAL composition flip → DONE** (`517daedcb`, `47badff51`).
  `client_supports_tasks(ctx)` + `gate_or_confirm(ctx, store, …, confirm_fallback)` (9 unit tests) — the guard that
  makes a flip safe. `composition_create_derivative` now calls `gate_or_confirm` (executor = the shared
  `_execute_derive`); composition-service is task-capable (verified in the real container: tasks/get|cancel handlers,
  task_provide_input tool, CallTool wrapped, 100 tools; tool tests green). **Provable no-op for current traffic** (no
  client declares tasks yet → always the `confirm_token` fallback); the task path activates with T1c(3).
- **T1c(3) — chat-service DRIVER + T2 gateway forwarding (NEXT, coordinated — must land together).** chat-service
  declares the tasks extension in its tool-call `_meta`, detects a `CreateTaskResult`, suspends (reuse
  `chat_suspended_runs`), and on the human decision calls `task_provide_input` + polls `tasks/get`; **ai-gateway
  forwards `tasks/get`/`cancel` + passes `CreateTaskResult` through + `taskId→provider` routing**. FE reuses
  existing confirm cards. First FULL live-stack E2E of the durable gate.
  > **COUPLING FINDING (2026-07-19): both client hops need polymorphic-result handling — the pieces can't be
  > split.** `mcp_execute_tool` (chat-service `knowledge_client.py:752`) and the gateway's `federation.executeTool`
  > both call `client.call_tool(...)`, which parses the response as a **`CallToolResult`** — a domain's
  > `CreateTaskResult` would fail/drop. So T1c(3)+T2 = {chat-service client polymorphic handling + caps declaration
  > + `CreateTaskResult` detection + suspend, gateway federation-client polymorphic handling + `tasks/*` forwarding
  > + taskId routing, FE card}, ALL together. Declaring caps without the driver strands a task; forwarding without
  > polymorphic handling drops it. This is why it's one coordinated slice, not four increments — build + live-E2E as
  > a unit (a real agent turn: open the derive gate → hold → accept → commit through the whole stack).
- **(superseded) T1c — wire into a REAL Python domain confirm + `CreateTaskResult` wrap.** Replace the self-contained
  `publish_book` gate with a real KIND-C confirm on a Python domain (composition/translation); emit a wire
  `CreateTaskResult{resultType:"task"}` via a CallTool wrap so a client auto-detects the task; live-prove on a
  stack-up. Then chat-service drives it (reuse `chat_suspended_runs`) + FE renders (reuse existing cards).
  **Concrete wiring pattern (captured from `composition-service/app/mcp/server.py`):** a confirm tool today does
  `payload={…}; confirm_token = mint_confirm_token(secret, user_id, resource_id, descriptor, payload); return
  {confirm_token, descriptor, title, domain}` — and a separate `actions.py` confirm endpoint verifies+executes.
  The ext-tasks form: `return await open_gate(store, descriptor=<same>, executor=<the actions.py execute logic,
  closed over payload>, input_requests={title, preview})`. The executor IS the existing commit logic; the store
  binds to the domain's confirm/consumed-token persistence (durability). `mint_confirm_token` stays for the
  capability-absent fallback (OQ3). **Pinned target for the first cut:** `composition_derive` (descriptor
  `composition.derive`, `server.py:1312`) — its confirm route (`routers/actions.py`) executes via the shared
  **`perform_derive(...)`**, so the executor is a closure `lambda inputs: perform_derive(<payload>)`; add
  `store=InMemoryTaskStore()` (→ persistent later) + `register_task_endpoints` + `enable_task_results` to
  `mcp_server` (`server.py:118`, `make_stateless_fastmcp("composition")`); live-prove by driving the real tool over
  an in-process MCP session (in-container) — avoids a Docker rebuild for the first proof.
- **Phase T2 — ai-gateway task forwarding.** Add `tasks/get|update|cancel` forwarding + `taskId→provider` routing; re-prove T1 **through the gateway** (the real path). Load-bearing → careful + live E2E.
- **Phase T3 — Go Tasks facade** (glossary/book). Build the Go helper; migrate one Go confirm (e.g. `glossary_book_delete`) onto Tasks; live-prove. Keep `confirm_token` fallback.
- **Phase T4 — retire the bespoke gate.** Once all KIND-C confirms are task-shaped: retire the chat-service-local `confirm_action`/`glossary_confirm_action`/`propose_record_edit` **frontend** tools (the parallel construct this whole track exists to remove); `tools/list` + Tasks are the contract. Fold into frontend-tools-migration Phase 4.
- **(Outcome)** We are **feature-complete on v1** — every v2 capability has a v1/native/our-infra equivalent. **v2 becomes optional** cleanup, adoptable post-2026-07-28-stable via the `loreweave_mcp` kit adapter (tracked separately), on our schedule.

---

## 6.1 SP-T0 RESULTS (spiked 2026-07-19 — the SDK experimental Tasks is a DEAD END)
Introspected mcp 1.28.1's Tasks API in the running chat-service container. Findings:
- The Tasks machinery is **complete and functionally present**: `TaskStore` protocol + `InMemoryTaskStore`,
  `TaskResultHandler`, server `ExperimentalServerSessionFeatures.elicit_as_task(message, schema, ttl)` (**this IS
  our confirm gate**), client `ExperimentalClientFeatures.call_tool_as_task` + `poll_until_terminal`, capability
  negotiation helpers.
- **BUT it's experimental + wired at the SESSION layer, not FastMCP** (`FastMCP.Context` exposes zero task methods;
  lowlevel `Server` takes no task params). Using it = integrating the task-message layer into our server stack.
- **DECISIVE: the experimental Tasks API is REMOVED in mcp 2.0** (SEP-1686 was pulled from core; Tasks returns as
  the separate **`ext-tasks`** extension — the `io.modelcontextprotocol/tasks` one this spec targets). Building on
  the 1.28.1 experimental API = a guaranteed rewrite. Also a known streamable-HTTP wrinkle: the SSE stream often
  closes before task polling begins (side-channel/enqueue needed).

⇒ **Do NOT build on the SDK's experimental Tasks.** Hand-roll the small `ext-tasks` **wire protocol** over our own
store. It's the SAME protocol the returning extension will use (future-proof), uniform across Go + Python, and free
of any dependency on the removed experimental API. The `elicit_as_task` *shape* is our reference for the gate
payload; we implement the transport ourselves.

## 7. Decisions (SEALED 2026-07-19; OQ1 REVISED after SP-T0)
- **OQ1 — Facade approach → REVISED & SEALED: one hand-rolled `ext-tasks`-protocol facade for ALL domains.** ~~native-per-domain via the SDK~~ — SP-T0 found the SDK experimental Tasks is removed in 2.0. Instead, implement the **`ext-tasks` wire protocol ourselves** (a small shared helper: `CreateTaskResult` + `tasks/get`/`update`/`cancel` handlers over `chat_suspended_runs`), used **uniformly by Go (`sdks/go`) and Python (`loreweave_mcp` kit)** domains. No SDK experimental dependency; the Go/Python asymmetry disappears. **T1 uses the smallest KIND-C confirm on whichever domain is quickest to wire the shared facade into** (kit chokepoint). The central Tasks↔confirm_token adapter is not needed — the facade IS the standard face over the existing confirm logic.
- **OQ2 — `taskId` identity → SEALED: task-layer id, NOT `confirm_token`.** The `taskId` is issued by the task layer (the Python SDK server-side, or the Go facade). chat-service binds it to a `chat_suspended_runs` row **keyed by `taskId`**. `confirm_token` stays a separate concern on the fallback path only. Routing (§5.5): persist `taskId→provider` (or encode the provider in the id) so a gateway restart still routes `tasks/*`.
- **OQ3 — `confirm_token` fallback → SEALED: keep permanently.** A client that doesn't declare the tasks capability (public edge, external agents, legacy) gets today's `confirm_token` result unchanged. Dual-path is cheap and is the no-regression guarantee.
- **OQ4 — Poll vs notifications → SEALED: poll-only for v1.** Respect `pollIntervalMs`. `notifications/tasks` (`subscriptions/listen`) is a later optimization, only if poll cost bites.
- **OQ5 — Store → SEALED: two layers, reuse what each side already has.** *Domain side* holds the task state (Python SDK's native task store; Go facade's task row) — this is what serves `tasks/get`/`update`. *chat-service side* reuses **`chat_suspended_runs`** for the suspended conversation, keyed by `taskId`. No new chat-side table. (A dedicated domain-side `tasks` table is a Go-facade build detail, decided in T3.)

---

## 8. Non-goals
- Adopting MCP **v2** SDKs (FastMCP→MCPServer rewrite) — explicitly deferred; this spec is the *alternative* to it.
- **MCP Apps** (server-rendered UI) — our FE cards already cover it.
- Replacing the durable store — `chat_suspended_runs` stays; Tasks is a protocol face over it.
- Changing domain write endpoints or the optimistic-lock semantics.

---

## Sources
- MCP Tasks extension (overview + lifecycle + methods) — https://modelcontextprotocol.io/extensions/tasks/overview
- Tasks extension spec repo — https://github.com/modelcontextprotocol/ext-tasks
- Tasks extension site — https://tasks.extensions.modelcontextprotocol.io/
- 2026-07-28 RC (Tasks/Apps as first-class extensions; tasks/list removed; polling replaces tasks/result) — https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- MCP 2026-07-28 spec changes — https://stacktr.ee/blog/mcp-2026-spec-changes
- Governing MCP Apps & Tasks at the gateway — https://www.truefoundry.com/blog/mcp-apps-tasks-gateway-governance
- Architecting the asynchronous agent (Tasks guide) — https://stn1slv.medium.com/architecting-the-asynchronous-agent-a-guide-to-mcp-tasks-7348c6527233
