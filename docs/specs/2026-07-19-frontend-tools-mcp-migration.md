# Spec — Migrate "frontend tools" onto MCP (Tasks + Elicitation pattern)

- **Date:** 2026-07-19
- **Status:** SEALED — all decisions (D1–D6) resolved; ready to decompose into a build plan (starts with the SP-0 beta spike). No code yet.
- **Trigger:** a lost, un-appliable proposal card (chat session `019f771a`) exposed that frontend tools bypass MCP's arg validation.
- **Size:** XL — cross-service (chat-service · ai-gateway · domain services · frontend), phased.
- **Related:** `docs/standards/mcp-tool-io.md` (Frontend-Tool Contract) · CLAUDE.md **MCP-first invariant** ("legacy agentic logic … tracked for migration, never silently grandfathered").
- **External research:** MCP spec — Tasks extension, Elicitation, Multi-Round-Trip Requests (MRTR), the 2026-07-28 Release Candidate, MCP Apps (sources at foot).

---

## 1. Problem — a symptom that exposed architectural debt

In session `019f771a` the agent emitted `propose_edit(domain, changes, base_version, resource_ref)` — those are **`propose_record_edit`'s** arguments, invalid for `propose_edit` (which requires `operation`+`text`, `additionalProperties:false`). **Nothing rejected it:** the turn suspended and rendered an Apply card that could never apply.

The tempting fix — a bespoke validator on the suspend path — **doubles down on the legacy design**. The real root cause: **frontend tools are a pre-MCP "sample" construct that was never migrated onto MCP**, so they re-implement (and drift from) schema, discovery, and — the thing that bit us — **input validation**, all of which MCP already standardizes. The missing validation is one symptom; the parallel discovery/advertisement path and the separate build-time contract are others.

> **Thesis (endorsed):** MCP is the LLM tool-calling core and is already built and mature here. Frontend tools should *use* it, not maintain a parallel implementation. **MCP-centralized-and-standard is correct.**

---

## 2. Current architecture (evidence)

### 2.1 MCP path — real MCP; validation centralized in the domain service
```
chat-service (MCP Python SDK client)  knowledge_client.py:679 → POST /mcp
  → ai-gateway (MCP proxy Server, @modelcontextprotocol/sdk)  proxy-server.factory.ts:49
      federates by tool→provider map; forwards args VERBATIM (no validation)
  → domain service (Go go-sdk / Python FastMCP MCP server)
      ⮕ inputSchema VALIDATION here, in the SDK handler:
        go-sdk mcp/server.go:322-325 → jsonschema-go validate.go:566
        ("validating \"arguments\": … required: missing properties: [...]")
```
- Real MCP end-to-end (official SDKs, `tools/list`/`tools/call`, streamable-HTTP, stateless).
- **Validation is inherited only by being a real MCP tool on a domain service.** ai-gateway and chat-service do not validate. The resolved validator is a reusable object, but it only fires automatically via `RegisterTool`/`AddTool`.
- Human-in-the-loop today = the **tier/`confirm_token`** convention (Tier-W/S tools mint a token instead of writing; the agent replays it through `confirm_action`). No native elicitation/tasks in use.

### 2.2 Frontend-tool construct — a chat-service-local parallel
- `services/chat-service/app/services/frontend_tools.py` — 12 tools as OpenAI function dicts; membership in `FRONTEND_TOOL_NAMES` is the only marker.
- Suspend/resume: `is_frontend_tool` (`stream_service.py:2494`) → **unwrap args only, NO validation** → `break` → `save_suspended_run()` persists the whole working conversation in `chat_suspended_runs` (owner-scoped, TTL-swept). Client executes; the human's **outcome** POSTs to `/tool-results` → `resume_stream_response` appends a `role:tool` outcome and runs a 2nd LLM pass.
- Validation deferred to the client; closed-set enums enforced only at **build time** (`contracts/frontend-tools.contract.json` + two test suites).

### 2.3 Execution-kind taxonomy (decides the MCP mapping)
| Kind | Tools | Browser execution | Write target | Human gate |
|---|---|---|---|---|
| **A · UI/nav** | `ui_navigate`, `ui_open_book/chapter`, `ui_show_panel`, `ui_watch_job`, `ui_open_studio_panel`, `ui_focus_manuscript_unit` | router nav / open dock panel (headless) | **none** | no (resolve-immediately) |
| **B · editor write** | `propose_edit` | apply prose into the open Tiptap doc | **client editor state** | yes (Apply) |
| **C1 · version PATCH** | `propose_record_edit`, `glossary_propose_entity_edit` | client `PATCH /v1/<domain>/actions/apply-record-edit` (If-Match) | **domain service** | yes (Apply) |
| **C2 · mint→confirm** | `confirm_action`, `glossary_confirm_action` | client `POST /v1/<domain>/actions/confirm` | **domain service** (already MCP-minted token) | yes (Confirm) |

The incident was a **B↔C1 confusion**. Two distinct validated MCP schemas would have rejected it at the source.

---

## 3. What MCP already provides (spec research — the design basis)

The migration is **not** an invention; MCP has native primitives for every piece. Key facts (2025-11-25 + 2026-07-28 RC):

- **Tools are server-side only.** *There is no "client-executed tool" in MCP* (confirmed in the RC). The client-facing primitives are elicitation (and the now-deprecated sampling/roots). → An earlier draft's "client-executed MCP tool" concept is **dropped.**
- **Tasks extension** (`io.modelcontextprotocol/tasks`, experimental) = **durable, resumable tool calls**: the server returns a durable **`taskId`** instead of blocking; the client **polls (`tasks/get`) and retrieves the result after reconnecting**; **task IDs survive disconnects** and are **durably stored**. Statuses: **`working | input_required | completed | failed | cancelled`**. It explicitly names **"human-in-the-loop / approval gates"** as a use case: the task enters **`input_required`** carrying `inputRequests` (elicitations); the client answers via **`tasks/update`**. *This is our durable suspend/resume, standardized.* (`tasks/list` was removed in the RC.)
- **Elicitation** = server requests input from the human via the client. **Two modes:** **form** (structured, flat objects, **primitives only** — string/number/boolean/enum, **no nesting or arrays-of-objects**) and **url** (out-of-band for sensitive data: auth/payment/OAuth — must not pass through the client). **Three-action response model:** **`accept`** (with `content`), **`decline`**, **`cancel`**. Client MUST let the user review/modify/decline/cancel; server MUST NOT request secrets via form mode.
- **MRTR (Multi-Round-Trip Requests, RC)** makes elicitation **stateless**: the server returns `InputRequiredResult` + an echoed `requestState`; the client re-issues the original call with `inputResponses`. No persistent connection needed — "any server instance can pick the retry up."
- **MCP Apps** (roadmap) = **server-rendered UIs** — the emerging mechanism for a server to ship a rich interactive component (e.g. a diff card) that the client renders. Candidate home for our rich proposal payloads.
- **Validation stays server-side** (inputSchema, now JSON Schema 2020-12). **Sampling & Roots are deprecated.**
- **Version/SDK reality (as of 2026-07-19 — decided: adopt beta):** the latest *stable* spec is **2025-11-25** (elicitation form+url + 3-action stable; Tasks experimental-core). The **2026-07-28 spec is still a Release Candidate** (finalizes 2026-07-28, ~9 days out). Because this repo is in **dev phase**, we **adopt the beta v2 SDKs now** and move to stable when it ships. Concrete betas for our stack:
  - **Python** (chat-service client, knowledge/AI FastMCP servers): `mcp[cli]==2.0.0b1` (v2 is a major rework; alpha was `2.0.0a1`).
  - **Go** (domain MCP servers, currently `go-sdk v1.6.1`): `github.com/modelcontextprotocol/go-sdk@v1.7.0-pre.1` — **same module path, no API rework** (gentlest migration).
  - **TypeScript** (ai-gateway, currently `@modelcontextprotocol/sdk`): v2 **splits into two new packages** `@modelcontextprotocol/server` + `@modelcontextprotocol/client`, both `2.0.0-beta.1` — a real repackaging migration for ai-gateway.
  - **Stable** for all: targeted **2026-07-28** (pin exact beta versions until then; "public APIs may change between beta and stable").
- **What the betas confirm vs. what needs a spike:** the beta blog lists **stateless core, MRTR, routable headers, auth hardening, standard error codes**. It does **NOT** confirm the **Tasks extension**, **server-side elicitation send**, or **MCP Apps** are in the beta core SDKs (Tasks is a separate `ext-tasks` extension). ⇒ **Phase-0 spike (SP-0):** verify against the actual beta SDK APIs which of {Tasks, server-initiated elicitation via MRTR, MCP Apps} are usable today; the plan branches on the result (see §4/§7).

### 3.1 The three-action model maps onto our cards 1:1
| Card action | Elicitation action | Current outcome enum |
|---|---|---|
| Apply / Confirm | `accept` (+ content) | `applied_saved` / `action_done` |
| Dismiss / Reject | `decline` | `dismissed` |
| Close / Esc / drop | `cancel` | `cancelled` |

---

## 4. Target architecture

**Principle:** every agent-invocable capability is a **server-side MCP tool** → it inherits **schema + validation + discovery + contract** for free (fixing the incident's root cause). Human-in-the-loop and durability use **the native Tasks + Elicitation pattern**, not a bespoke suspend.

**Adoption strategy — adopt the beta v2 SDKs now (dev phase), pin, move to stable at 2026-07-28.** We build directly on the native primitives that the betas confirm — **stateless core + MRTR + elicitation** — for the human gate. **Durability** (a card that sits for hours across a closed connection) needs the **Tasks** extension, whose beta availability is unconfirmed → until SP-0 confirms native Tasks, our existing **`chat_suspended_runs`** durable store bridges it (it already IS a durable, owner-scoped, resumable handle). Two clarifications from the research:
- **MRTR ≠ durable polling.** MRTR is the *round-trip* (server returns `InputRequiredResult`; client re-issues with `inputResponses`) — great for the elicitation exchange, but it does not by itself provide a durable handle that survives a long pause. **Tasks** is the durability layer. So: **elicitation-over-MRTR for the exchange + Tasks (or our store) for durability.**
- The **stateless core** aligns with us: ai-gateway already stands up a **stateless proxy Server per request** — so the v2 stateless model is a natural fit, not a fight.

Our existing seams already mirror the standard:

| Our current mechanism | MCP-standard equivalent | Migration |
|---|---|---|
| `chat_suspended_runs` (durable, owner-scoped, TTL) | Tasks durable store (`taskId`, survives disconnect) | keep as the Task store; add a `taskId`/status field |
| the suspend chunk | task status `input_required` | relabel; carry `inputRequests` |
| `POST /tool-results` resume (run_id, outcome) | `tasks/update` (inputResponses) / MRTR retry | keep endpoint; align payload |
| outcome enum (`applied/dismissed/…`) | `accept/decline/cancel` | map (§3.1) |
| agui-only + surface-gated advertisement | per-request **capability negotiation** (`elicitation`/`tasks` extension) | replace surface flags with a client capability |
| `frontend_tools.py` schemas | domain-service MCP tool `inputSchema` | move; validation becomes inherent |
| `frontend-tools.contract.json` + 2 tests | MCP `tools/list` (the single contract) | retire / bridge |

### 4.1 Per-kind end state
- **KIND C (domain writes) → native MCP tools with a server-side gate.** The write already runs through the domain service, and C2 already mints its token via a domain MCP tool. End state: the **propose + confirm are real MCP tools on the owning domain service**, run **task-shaped** (durable) and enter **`input_required`** for the human gate. **Validation is inherent** (this is where the incident lived). The rich diff payload rides as **task content / an MCP App**, *not* the elicitation `requestedSchema` (flat-primitive limit). The elicitation captures the **decision** (accept/decline/cancel) + any edited scalar. Highest value, cleanest fit.
- **KIND B (`propose_edit`) → MCP tool, task-shaped + elicitation.** The proposed text rides as task content; `accept` applies it to the editor (client effect), `decline`/`cancel` otherwise. If the human may edit before applying, an elicitation `string` field captures the edited text (a primitive — allowed).
- **KIND A (`ui_*`) → validated MCP tools that return a directive synchronously.** No task, no elicitation (matches today's resolve-immediately). The tool **validates the enum/allowlist** (fixes the `panel_id` out-of-enum silent-no-op) and returns `{path|panel|…}`; the **client acts on the tool result**. Requires a lightweight host (a small nav/UI MCP provider, or an ai-gateway-local tool set) — *decision D3*.

### 4.2 Why this closes the root cause at one seam
Once a tool is a server-side MCP tool, its args are validated by the SDK's inputSchema handler **before** any suspend/`input_required` — the exact enforcement backend tools already get, producing the same `required: missing properties` signal the model already knows how to repair. A `propose_edit`-with-`propose_record_edit`-args call is rejected at the source, in one place, for **all** tools.

---

## 5. Edge cases (cleared)
1. **Durable pause across a closed connection** → Tasks (durable `taskId`, resume by poll). ✔
2. **Human gate** → elicitation `input_required` + 3-action model. ✔ (§3.1)
3. **Arg validation** → server-side inputSchema (JSON Schema 2020-12) — the fix, inherent. ✔
4. **"Don't hang a UI-less client"** → per-request capability negotiation (client declares `elicitation`/`tasks`); server never tasks a client that didn't opt in. ✔ (replaces surface flags)
5. **Rich proposal payload (multi-field diff, `changes[]`)** → **cannot** be an elicitation form schema (flat-primitive limit). Convey as **task content** or an **MCP App**; elicitation carries only the decision (+ scalar edits). ⚠ constrains the UI mechanism → *decision D4*.
6. **Sensitive confirms (e.g. BYOK credential entry)** → **url-mode elicitation** (out-of-band, never through the client/LLM). ✔ available if needed.
7. **Concurrency/staleness** (the existing `base_version`/If-Match, 409/412) → the domain MCP tool keeps its optimistic-lock; `accept` can still fail → surfaces as `applied_conflict`, model self-corrects. ✔ unchanged.
8. **Batch confirms** (N tokens → one card) → one task with multiple `inputRequests`, or a batch tool. ✔ representable.
9. **Experimental risk** → Tasks/elicitation are RC/experimental on beta SDKs → **adopt the shape on stable SDKs now**, native extension on stabilization. ✔ (§4)
10. **Deprecations** → do NOT build on **sampling** or **roots** (deprecated). ✔

---

## 6. Migration plan (phased; each independently shippable)
- **SP-0 — beta spike (blocks nothing else; informs everything).** On the beta v2 SDKs, verify which of {**Tasks** extension, **server-initiated elicitation** via MRTR, **MCP Apps**} are usable today, in Go (`v1.7.0-pre.1`) and Python (`2.0.0b1`). Output: a capability matrix that fixes D3/D4 and whether Tasks is native yet or `chat_suspended_runs` bridges. *(Also: pin the beta SDK versions across chat-service, ai-gateway (the `sdk`→`server`+`client` split), and the Go domain services; confirm the stateless-core migration is a no-op for ai-gateway's per-request proxy.)*
- **Phase 0 — validation seam (root-cause fix).** Give every frontend tool a server-owned `inputSchema` and validate args with the MCP validator **before** suspend; on invalid, feed the standard `required: missing properties` signal back to the model. No execution change. *Closes the bug class; makes later phases additive.* (For a KIND-C tool this can already be its domain-service schema; for A/B, a schema registered at the chat-service seam using the same validator.)
- **Phase 1 — KIND C → native MCP + task-shaped gate.** Domain-service propose/confirm become real MCP tools (validated, discoverable) run task-shaped with an `input_required` gate; cards become renderers. Retire the bespoke C schemas.
- **Phase 2 — KIND B (`propose_edit`) → MCP tool, task-shaped + elicitation.** Proposed text as task content; accept/decline/cancel; optional scalar edit.
- **Phase 3 — KIND A (`ui_*`) → validated directive tools** on a nav/UI MCP host; client acts on the result.
- **Phase 4 — retire duplication.** Remove `frontend_tools.py` schemas, the parallel advertisement, and `frontend-tools.contract.json`; MCP `tools/list` is the single contract. Update `docs/standards/mcp-tool-io.md`.
- **(Later) native Tasks/elicitation** once Tier-1 SDKs ship it and our services upgrade past pre-v2 SDKs.

---

## 7. Decisions (RESOLVED)
- **D1 — Pattern → DECIDED.** Server-side MCP tools + **Tasks (durability) + Elicitation (gate)**. No client-executed tool (does not exist in MCP); no bespoke suspend semantics. Research-mandated.
- **D2 — Adoption → FINAL 2026-07-19 (SP-0 evidence + scope-correction).** **Build Phases 1-2 on current STABLE SDKs; DEFER the beta v2 adoption.** SP-0 spiked each SDK: the human-gate primitive (**elicitation**) already ships in ALL current **stable** SDKs (Python `mcp` **1.28.1** — already installed & running; Go `go-sdk` **v1.6.1**; TS `@modelcontextprotocol/sdk` **1.29.0**); the **Tasks** extension ships in Python stable; `chat_suspended_runs` covers durability. So the betas give **zero gate-capability gain**. A beta v2 **does** exist (Python `mcp==2.0.0b2` via `--pre`, TS `server/client/core@2.0.0-beta.4`, Go `go-sdk@v1.7.0-pre.3`) — my earlier "no Python v2" was a `pip index --pre` methodology error — **but adopting it is a major rewrite**: v2 **removes `mcp.server.fastmcp`**, on which the shared `loreweave_mcp` kit + 6 Python services depend (~9.3k lines), plus a TS gateway-proxy redesign. Given zero gain + stable v2 landing **2026-07-28**, we defer. **When adopted (best post-stable): via a FastMCP→MCPServer ADAPTER in the `loreweave_mcp` kit** (single chokepoint → 6 services untouched). Stable pins in place: Python `mcp==1.28.1`, Go `v1.7.0-pre.3` (harmless), ai-gateway `sdk@1.29.0`. Full detail: build-plan doc §"SP-0 CAPABILITY MATRIX" + "CORRECTION".
- **D3 — `ui_*` host → DECIDED: ai-gateway-local.** Reuse ai-gateway's existing **consumer-local tool** precedent (`tool_list`/`tool_load`/`find_tools` never hit a provider). `ui_*` validate the enum/allowlist with the shared JSON-Schema resolver and return a directive; the client acts on the result. No new service.
- **D4 — Rich card rendering → DECIDED: task-content + existing FE cards.** The existing `ProposeEditCard`/`RecordDiffCard`/`ConfirmActionCard`/etc. become renderers of MCP-delivered proposal data (carried as task/tool-result content). **MCP Apps deferred** to a Phase-4 evaluation (unproven; unconfirmed in the betas) — not a dependency.
- **D5 — First increment → DECIDED: (a) MCP-native validation seam.** Phase 0 validates frontend-tool args at the chat-service seam using the **standard JSON-Schema-2020-12 validator** against each tool's **canonical inputSchema** (the same schema Phases 1–3 reuse), emitting the standard `required: missing properties` signal. This is the migration's first increment (schema + validation centralized on the MCP standard), **distinct from the reverted hotfix** (a hand-rolled check): standard validator, canonical schema, non-throwaway. Chosen over "(b) straight to Phase 1" because it closes **all three kinds' validation immediately** and the persistence fix already prevents loss.
- **D6 — Interim guard → DECIDED.** Folded **into Phase 0** as the MCP-native seam (D5); no standalone legacy-shaped validator.

> **Status: SEALED.** All decisions resolved; only SP-0 (the beta capability spike) can still branch implementation details (native Tasks now vs `chat_suspended_runs` bridge; MCP-Apps viability) — it does not reopen the design.

---

## 8. Non-goals
- Rewriting the durable pause store (`chat_suspended_runs` stays — it becomes the Task store).
- Changing the domain write endpoints (`/v1/<domain>/actions/*`) — Phase 1 relocates the *gate + schema* onto MCP, not the writes.
- The persistence fix (done on `fix/chat-persist-checkpoints`).
- Waiting for the stable 2026-07-28 spec before starting — we adopt the beta now (dev phase) and pin; stable is a version bump later, not a blocker.

---

## Sources
- MCP Tasks extension — https://modelcontextprotocol.io/extensions/tasks/overview
- MCP Elicitation — https://modelcontextprotocol.io/specification/draft/client/elicitation
- 2026-07-28 Release Candidate — https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/
- Beta SDKs for the RC — https://blog.modelcontextprotocol.io/posts/sdk-betas-2026-07-28/
- Async/long-running (SEP-1391/1686) — https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1391
