# A2A Phase-3 — real protocol: deep analysis

> **Status:** Analysis / design (Track-2, no MVP code yet). Follow-on to
> `2026-06-02-a2a-model-routing-seam.md` (phases 1–2, shipped) and the locked
> ARCH decision (`2026-06-01-arch-1-2-design-agui-mcp.md` §C7: "A2A = design the
> agent-card seam, ship later — game multi-agent").
> Author: session 104 cont.8 (2026-06-03), branch `arch-unify-chat-rag`.

---

## 0. TL;DR

1. **Two different things hide under "A2A phase-3".** (a) A2A-ifying the
   *internal* compose_prose delegation, and (b) the *game multi-agent* mesh
   (the original driver). They have opposite cost/benefit.
2. **Do NOT A2A-ify compose_prose now.** In-process delegation (phase-2) is
   simpler and faster; A2A there is pure overhead until the writer is a separate
   scaling unit/team/vendor. (§4)
3. **The real A2A payoff is the game vertical** (world-gen, NPC, director agents
   coordinating) — and external interop (other frameworks calling LoreWeave
   agents). That's Track-2, build when the game vertical is active. (§5, §7)
4. **LoreWeave is already A2A-shaped.** AG-UI events ≈ A2A `TaskStatusUpdate`/
   `TaskArtifactUpdate`; the C6 suspend/resume ≈ A2A `input-required` +
   resubscribe; suspended-run persistence ≈ A2A `TaskStore`. Phase-3 is mostly a
   **protocol adapter**, not new semantics. (§6) ← key finding
5. **Cheap seam now (phase-3a): publish a static Agent Card** at
   `/.well-known/agent-card.json` for the chat agent — discovery only, zero
   behavior change. Satisfies the locked C7 "design the seam". (§7)
6. **Invariants hold:** every model call inside an A2A task still goes through
   provider-registry (provider-gateway invariant) + usage-billing; external A2A
   traffic still enters via api-gateway-bff. A2A changes the *agent↔agent* edge,
   not those. (§8)

---

## 1. What A2A is (precise, from the v0.3/1.0 spec)

A2A (Agent2Agent, Google → Linux Foundation 2025) is the **agent↔agent** peer
protocol: how one agent *discovers* and *delegates work to* another **opaque**
agent across frameworks/vendors.

- **Discovery — Agent Card** at `/.well-known/agent-card.json`: `name`,
  `description`, `provider`, `interfaces[]` (transport + url), `capabilities`
  (`streaming`, `pushNotifications`, `extendedAgentCard`), `skills[]`
  (`id`/`name`/`description`), `securitySchemes` + `security`.
- **Transports (functionally equivalent):** JSON-RPC 2.0 over HTTP POST, gRPC,
  or HTTP+REST. (We'd pick **JSON-RPC over HTTP** — same shape as our MCP
  streamable-HTTP transport.)
- **Core methods:** `SendMessage`, `SendStreamingMessage` (SSE),
  `SubscribeToTask` (resubscribe), `GetTask`, `ListTasks`, `CancelTask`, push-
  notification config CRUD, `GetExtendedAgentCard`.
- **Unit of work = Task** (server-generated id, `contextId` groups a
  conversation). Lifecycle: `submitted → working → (input-required | auth-
  required) → completed | failed | canceled | rejected`.
- **Message** = a turn (`role` user/agent, `parts[]`); **Artifact** = an output
  (`parts[]`); **Part** = `text | data(JSON) | raw(bytes) | url` + `mediaType`.
- **Streaming:** SSE emitting `TaskStatusUpdateEvent` / `TaskArtifactUpdateEvent`
  (ordered).
- **Auth:** declared in the card — `http`(bearer/basic), `apiKey`, `oauth2`,
  `openIdConnect`, `mutualTls`. Servers MUST scope task access.
- **Versioning:** `A2A-Version` header (defaults `0.3`); `A2A-Extensions`.
- **Python SDK** (`a2a-sdk`): `AgentExecutor` (your logic) + `DefaultRequestHandler`
  (+ a `TaskStore`) + `A2AStarletteApplication(agent_card, handler)`; client
  `A2AClient`. Mounts like our FastMCP `/mcp` app.

## 2. The three-protocol stack — keep them straight

| Edge | Protocol | LoreWeave status |
|---|---|---|
| agent → **tools/memory** | **MCP** | shipped (knowledge-service `/mcp`, default on) |
| agent → **UI** | **AG-UI** | shipped (chat-service AG-UI events, FE consumes) |
| agent ↔ **agent** | **A2A** | this doc — seam only |

A2A does NOT replace MCP or AG-UI. An A2A agent can *itself* be an AG-UI streamer
to a UI and an MCP client to tools. A2A is strictly the peer-delegation edge.

## 3. Where would A2A actually be used in LoreWeave?

Per the scope correction (gap analysis): **classic novel · visual novel · game**.
Candidate agent↔agent edges:

1. **compose_prose** (orchestrator → writer) — *internal, same box today.*
2. **Game multi-agent** — world-gen agent, lore/continuity agent, NPC/character
   agents, a "director/orchestrator" agent coordinating them; possibly a
   separate `game-server`/`world-gen` process. **← the real A2A case.**
3. **External interop** — a third-party/framework agent calling a LoreWeave
   agent (e.g. "draft a chapter using this book's lore") via the Agent Card.
4. **Cross-service domain agents** — e.g. a translation agent, an
   extraction/knowledge agent as addressable peers (vs today's bespoke internal
   HTTP + MCP tools).

## 4. Critical analysis — do NOT A2A-ify compose_prose now

Phase-2 runs the writer in-process inside `_stream_with_tools`. Replacing that
with an A2A `SendMessage` task buys nothing at current scale and costs:

- **Latency/overhead:** task create + SSE subscribe + serialize parts, vs a
  direct second `client.stream()`.
- **State:** a `TaskStore` to persist task lifecycle (we'd reuse the suspended-
  run pattern, but it's more moving parts).
- **Same thrash:** A2A doesn't fix the single-VRAM model-swap problem (§ writer
  setup in the phase-1/2 doc); it just moves the call across a socket.

**A2A earns its keep only at a real boundary:** the writer is a *separate
deployable* (own scaling/GPU), a *different team/vendor* agent, or must be
*discoverable*. Until then, in-process is the correct design. (Use the existing
`composer_model_ref` + Compose-mode for routing.)

## 5. The real driver — game multi-agent (Track-2)

When the game vertical is built, several agents must coordinate: e.g. a
**Director** orchestrates a **WorldGen** agent (terrain/lore), **NPC** agents
(dialogue/behavior), a **Continuity** agent (canon checks). A2A is the right fit
because:

- they may run as **separate processes** (the sibling `game-server` /
  `world-gen` / `local-image-generator-service` already exist);
- they benefit from **discovery** (a Director finds available agents via cards);
- they're **opaque** (each owns its own model/loop/state) — exactly A2A's model;
- it future-proofs **external** framework interop (150+ orgs speak A2A).

This is where to spend A2A effort — not on the chat compose path.

## 6. Key finding — LoreWeave is already A2A-shaped

The existing seams map almost 1:1 onto A2A, so phase-3 is an **adapter**, not a
re-architecture:

| LoreWeave today | A2A concept |
|---|---|
| chat turn (one request→stream) | a **Task** (`submitted→working→completed`) |
| `session_id` / chat session | `contextId` (groups turns) |
| AG-UI `TEXT_MESSAGE_*` / `REASONING_*` deltas | `TaskStatusUpdateEvent` stream |
| AG-UI final message / outputs / `propose_edit` result | `Artifact` (`parts[]`) |
| **C6 suspend (`RUN_FINISHED status:suspended`)** | **`input-required` state** |
| **C6 resume (`POST /tool-results`)** | **`SubscribeToTask` / send to same task** |
| `chat_suspended_runs` table | **`TaskStore`** (persisted task state) |
| `X-Internal-Token` (MCP/internal) | A2A `apiKey`/`http` security scheme |
| usage summed across passes (D10) | task-scoped usage metering |

Implication: an A2A server facade over chat-service can be built by **mapping the
existing `_emit_chat_turn` event stream** to A2A events — the hardest parts
(streaming, human-in-loop pause/resume, persisted task state, usage) already
exist from ARCH-1 C3–C6.

## 7. Incremental phase-3 plan (additive, each shippable alone)

- **3a — Static Agent Card (cheap seam, satisfies locked C7).** Serve
  `/.well-known/agent-card.json` describing the chat agent (skills: chat,
  memory-aware Q&A, propose_edit/compose; capabilities: `streaming:true`,
  `pushNotifications:false`; security: bearer/internal). **Discovery only, no
  behavior change.** Lets external/game agents *see* LoreWeave agents. ~S.
- **3b — A2A server facade over the chat agent (internal first).** Mount an
  `A2AStarletteApplication` (via `a2a-sdk`) that wraps a turn as a Task: an
  `AgentExecutor` that drives `_emit_chat_turn` and maps its events → A2A
  `TaskStatusUpdate`/`TaskArtifactUpdate`; `input-required` ⇄ C6 suspend;
  `TaskStore` backed by (or reusing) `chat_suspended_runs`. Behind the gateway +
  internal token. ~L.
- **3c — compose_prose via A2A (only if writer becomes a separate service).**
  Swap `_run_composer`'s in-process `client.stream()` for an `A2AClient`
  `SendMessage` to a composer agent. Gate like `USE_MCP_TOOLS`. ~M, **deferred
  until there's a real boundary**.
- **3d — Game multi-agent mesh (the payoff).** WorldGen/NPC/Continuity agents
  each an A2A server; a Director orchestrates via `A2AClient` + discovery.
  Track-2, when the game vertical starts. ~XL.

**Recommendation:** ship **3a** when convenient (cheap, unblocks discovery,
honors the locked seam decision); design 3b's adapter (this doc); **defer 3c/3d**
to when a real cross-process boundary or the game vertical exists.

## 8. Invariants & constraints (must hold in every phase)

- **Provider-gateway invariant:** any model call inside an A2A task still resolves
  + runs via provider-registry (BYOK), never a direct SDK call. A2A is transport
  between agents; model access stays gated.
- **Gateway invariant:** external A2A traffic enters through api-gateway-bff
  (proxy `/.well-known/agent-card.json` + the A2A endpoint). Internal
  service-to-service A2A uses `X-Internal-Token` (same as MCP), and — learned
  from D-ARCH2-MCP-LIVE-SMOKE — **disable DNS-rebind host checks** for the
  internal transport.
- **Billing:** each A2A task that consumes models meters usage to usage-billing,
  task-scoped (reuse the per-turn summation).
- **Auth scoping:** A2A servers MUST prevent cross-tenant task access — map to
  our `owner_user_id` + project scope (same as suspended-run loading).
- **No platform lock-in / no hardcoded models** (CLAUDE.md) — Agent Card skills
  describe capabilities, not specific model names.

## 9. Risks / open questions

- **Dependency coexistence:** add `a2a-sdk` alongside `mcp` (both pydantic-v2,
  both Starlette/anyio). Check version pins before adopting; isolate to the
  service that hosts the A2A server.
- **Spec churn:** A2A is at 0.3/1.0 with active evolution under LF; pin
  `A2A-Version` and treat the card/transport as a versioned contract.
- **Task persistence:** prefer a Postgres-backed `TaskStore` (we already persist
  suspended runs) over in-memory, for multi-instance + restart safety.
- **Discovery exposure:** a public Agent Card advertises capabilities — keep the
  extended (authenticated) card for sensitive skills; public card minimal.
- **Cost surprise:** multi-agent fan-out multiplies model calls; per-task budget
  + visible metering (like the turn usage we already sum).
- **Don't hand-roll the protocol** — use `a2a-sdk`; only the `AgentExecutor`
  (mapping to `_emit_chat_turn`) and `TaskStore` are ours.

## 10. Decision

A2A's value for LoreWeave is the **game multi-agent vertical** and **external
interop**, not the internal compose path. The architecture is already A2A-shaped
(§6), so the remaining work is a protocol adapter, deferrable until the game
vertical is active. **Now:** optionally ship **3a** (static Agent Card seam) to
honor the locked C7 decision and unblock discovery. **Defer** 3b (facade), 3c
(compose-via-A2A), and 3d (game mesh) until a real cross-process boundary or the
game vertical exists. Keep MCP (tools) and AG-UI (UI) as the shipped edges; A2A
joins them only at genuine agent↔agent boundaries.

---

## 11. Benchmark — does the design actually work? (empirical, session 104 cont.9)

The §6 claim ("already A2A-shaped → phase-3 is an adapter") was **validated
empirically**, not just asserted. A PoC (`poc/a2a_phase3_bench.py`) implements
the A2A **wire spec** (Agent Card + JSON-RPC `message/send` / `message/stream`
SSE + `tasks/get` + task lifecycle + artifacts + apiKey auth) as the proposed
adapter, with three LoreWeave-shaped agents (composer, approver, director) driven
in-process via httpx `ASGITransport`. Agent logic is deterministic on purpose —
the benchmark tests the A2A **plumbing/mappings**, not model quality (the model
call plugs into the executor; it was validated live in the compose_prose smoke).

**Result: 7/7 scenarios PASS** —

| # | Scenario | Validates the mapping |
|---|---|---|
| 1 | Discovery (Agent Card @ well-known) | agent advertises skills/capabilities/security |
| 2 | `message/send` → Task + Artifact | **chat turn ↔ Task** (§6) |
| 3 | `message/stream` SSE (`task→status→artifact→completed`, ordered) | **AG-UI deltas ↔ TaskStatus/Artifact events** (§6) |
| 4 | Human-in-loop: `input-required` → resume same task → `completed` | **C6 suspend/resume ↔ input-required** (§6, the load-bearing claim) |
| 5 | Multi-agent: Director → (A2A) → Composer | **game mesh delegation** (§5) |
| 6 | Auth: 401 (no token), 403 (cross-tenant task read) | §8 auth scoping |
| 7 | `tasks/get` retrieval | task store round-trip |

**Findings:**
- The proposed **adapter mappings hold** — especially the two hardest (human-in-
  loop pause/resume and agent→agent delegation). The design is implementable on
  the stable wire contract.
- **`a2a-sdk` coexists cleanly** with `mcp` + pydantic 2.13.4 in the chat-service
  image (risk #9 cleared — installs, imports, no conflict).
- **`a2a-sdk` is at 1.1.0 and protobuf-based** with a churned server API (no
  `a2a.server.apps`; `add_a2a_routes_to_fastapi(...)` + `AgentExecutor` +
  `TaskUpdater` + `*TaskStore`; `AgentCard` uses `interfaces`, not `url`).
  Integration is **heavier than FastMCP** → pin the version, isolate to the
  hosting service, and budget more glue for 3b than C1's MCP mount took.
- Implementing the **wire spec directly** (as the PoC does) is a valid impl path
  if the SDK's churn/protobuf is undesirable — the interop contract is the wire,
  not the SDK.

**Verdict:** the phase-3 design is sound and buildable; the open question is
**when** (game vertical / real boundary), not **whether**. Recommendation in §10
stands: cheap 3a now if desired, defer 3b–3d.
