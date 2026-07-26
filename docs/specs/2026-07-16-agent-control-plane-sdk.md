# Spec — Agent Control Plane as a consumable SDK (every agent-runtime, not chat-only)

> **Status:** 🔒 SEALED — 2026-07-16 (PO-approved). Authored after the Practice/roleplay boundary review
> exposed that the agent control/governance substrate is **welded into chat-service** and cannot be reused
> by a second agent-runtime without duplication.
> **Sealed sequencing (PO):** **EXTRACT-FIRST** — A0→A3 (contracts+SDK+chat-dogfood+Rust crate) land
> *before* A4 Practice, so the first non-chat consumer is built on the clean boundary, never on the
> coupling this spec removes (OQ-3). **Autonomous drive (ACP-10): interface + a unit-proven park path NOW**
> (OQ-4) — locks the boundary for the future background/game runtimes. **OQ-1 → new pkg**
> `sdks/python/loreweave_agent_control`. **OQ-2 → hand-write Rust types + validate-in-test** (mirror
> `contracts-ws`; codegen later only if churn warrants). Build board: [`docs/plans/2026-07-16-agent-control-plane-RUN-STATE.md`](../plans/2026-07-16-agent-control-plane-RUN-STATE.md).
> **Type:** FS · cross-cutting (chat-service · knowledge-service · roleplay-service · a new shared
> contract + per-language SDK). **Decision prefix:** **ACP-\*** (Agent Control Plane).
> **Builds on — does NOT duplicate:**
> - [`2026-07-15-agent-task-governance.md`](2026-07-15-agent-task-governance.md) (SEALED) — that spec
>   defines **WHAT** the control does (DEFINE·PLAN·MONITOR·CONTROL, the rail, the effect-probes, the hook
>   lifecycle). **This spec defines HOW any runtime CONSUMES it** — the boundary + SDK. Governance = the
>   engine; ACP = the standard socket every consumer plugs into.
> - [`contracts/interview/working_memory.schema.json`](../../contracts/interview/working_memory.schema.json)
>   — the charter/state contract that ALREADY EXISTS (this spec generalises + enforces it fleet-wide).
> - [`2026-06-23-interview-roleplay.md`](2026-06-23-interview-roleplay.md) — the executive + anchoring.

---

## 1 · The problem, proven by the roleplay build

We are adding a **second** agent-runtime (interview Practice, on roleplay-service) and immediately hit the
wall: the control/governance layer is **not a layer, it is chat-service source.**

- The **executive** IS service-exposed (knowledge-service `POST /internal/working-memory/{init,tick}`) —
  good. But **the cadence that drives it is inline chat code**: `stream_service.py:5375-5384` decides
  "this is a roleplay session, every N turns, fire a tick" in the middle of chat's post-turn block.
- The **rail** (`rail_progress.py` verdict machine + `_maybe_redrive_rail` drive) lives inside chat's
  loop; the DRIVE (hold-the-turn, re-prompt) is woven into chat's streaming generator.
- The **charter contract** (`working_memory.schema.json`) is machine-checked on **exactly one** of its
  three code sites (chat-service `test_working_memory.py`); the **producer** (roleplay `charter::freeze`,
  Rust) and the **executive owner** (knowledge `WorkingMemoryCharter`) mirror it **by hand**.

⇒ A new consumer must **re-implement the orchestration** (when to tick, when to drive, the hook
lifecycle) and **hand-mirror the contract** — the exact "duplicated code and role for nothing" this spec
exists to kill. And two more consumers are coming: **background multi-agent workflow runners** and
**game-server agent logic** (PRR-20 plane). Neither can live inside chat-service's turn loop.

**The goal:** the control plane becomes a **standard with a thin SDK** — contracts + per-language client +
service surfaces + an embeddable loop-harness — that **any** agent-runtime integrates in a few calls,
instead of forking chat-service.

---

## 2 · The model — three planes + one SDK

```
   CONSUMERS (agent-runtimes — a loop where an LLM decides + acts over steps)
   ┌───────────┬───────────────┬────────────────────┬───────────────────┐
   │ chat-svc  │ roleplay      │ background          │ game-server       │
   │ (today)   │ /interview    │ task-agent runner   │ agent logic       │
   │ interactive│ (via chat)   │ (future, autonomous)│ (future, PRR-20)  │
   └─────┬─────┴───────┬───────┴─────────┬──────────┴─────────┬─────────┘
         │  integrate via the SAME SDK — never fork chat-service          │
         ▼                                                                ▼
   ┌────────────────────── THE AGENT CONTROL PLANE ─────────────────────────┐
   │ A · CONTRACTS (the SoT boundary)   contracts/agent-control/*.schema.json │
   │     working_memory · WorkflowDefinition · EffectRef · Verdict           │
   │ B · COMPUTE (stateless, library)   verdict machine · predicate parse ·  │
   │     plan/todo state ops · the hook-lifecycle harness                    │
   │ C · SERVICES (stateful, HTTP)      knowledge: working-memory SSOT +      │
   │     executive · domain effect-probes (/internal reads)                  │
   └────────────────────────────────────────────────────────────────────────┘
```

**The SDK is not a monolith and not a new god-service.** It is the union of A (contracts) + B (a thin
per-language client/harness) + the ALREADY-EXISTING C (service routes). A consumer embeds B and calls C,
speaking A. Nothing imports chat-service.

---

## 3 · Sealed decisions (draft — for PO review)

| # | Decision |
|---|---|
| **ACP-1** | **The control plane is a named ARCHITECTURAL LAYER, not chat-service internals.** It owns: the working-memory/charter SSOT + executive (knowledge-service), the rail verdict-machine + governance-drive *semantics*, and the effect-probe catalog. Chat-service becomes **a consumer of it**, not its home. |
| **ACP-2** | **A "consumer" is any agent-runtime** — a loop that lets an LLM decide and act over multiple steps. Enumerated: chat-service (interactive), interview/Practice (rides chat today), a future background task-agent runner, future game-server agent logic. Each **consumes**; none re-implements. A deterministic code pipeline is NOT an agent-runtime and does not consume the plane (governance §15 boundary — govern agent-driven, exempt pipelines). |
| **ACP-3** | **The coupling surface is CONTRACTS + a thin SDK, never shared code reach-in.** A consumer speaks the plane through (a) versioned schemas, (b) service HTTP, (c) a thin per-language client — and MAY NOT import another service's modules. This is the microservice-governance consensus GOV-10 already adopted (central catalog, distributed enforcement), applied to the whole plane. |
| **ACP-4** | **Split the plane by STATEFULNESS, and put each part in its right home.** (i) **Stateless compute** — verdict machine, contract types, `done_when`/predicate parsing, plan-state ops — is a **library** (embeddable, cheap, no network). (ii) **Stateful** — working-memory SSOT + executive + effect-probes — stays **service-side** (already HTTP). (iii) **The loop-harness** — the hook lifecycle (Pre/PostToolUse/Stop) + cadence + drive — is an **embeddable SDK** each runtime wraps its own loop in. |
| **ACP-5** | **Polyglot by CONTRACT, not by one library** (language rule I3). Consumers are Python (chat, knowledge), Rust (roleplay), **TypeScript (`game-server` — per `contracts/language-rule.yaml`, realtime transport PRR-20; NOT Rust)**, TS (gateway). So the SDK is: the shared `contracts/agent-control/*` schemas + a **Python package** (`sdks/python/loreweave_agent_control`, mirroring `loreweave_llm`) + a **Rust crate** (`crates/contracts-agent-control`, mirroring `crates/contracts-ws`). **The `game-server` (TS) consumer gets the language-neutral HTTP surface + a demand-pulled TS adapter (ACP-13), NOT the Rust crate** — do not ship a native client for it ahead of need. The stateful surfaces (executive, probes) are language-neutral HTTP so a non-Python runtime needs no Python. *(Corrected at review — the original text mis-mapped `game-server` to Rust, contradicting the LOCKED language rule.)* |
| **ACP-6** | **The contract is MACHINE-CHECKED on EVERY side** (the refactor). Every producer/consumer of a control contract validates against the schema in its own test suite (the `frontend-tools.contract.json` + governance-D4 discipline). Today only chat does; roleplay (producer) and knowledge (executive) get the same gate. A field added on one side reds the others until aligned. |
| **ACP-7** | **NO new monolithic "control-service."** The plane is deliberately hybrid (GOV-10): STATE + executive stay in **knowledge-service** (it owns working-memory), probes stay **domain-distributed**, compute + harness are **libraries**. "Extract from chat" means → into contracts + libs + the existing services, **not** into a second god-service. This is the literal answer to "don't hardcode + stick it in chat." |
| **ACP-8** | **Chat-service is REFACTORED to be the FIRST consumer of the harness — the boundary's acceptance test.** Its inline `_fire_executive_tick` cadence + `_maybe_redrive_rail` drive move **behind the SDK harness interface**. If chat cannot cleanly consume the SDK, the boundary is wrong and we fix the SDK, not chat. Dogfood-or-it-isn't-real. |
| **ACP-9** | **The SDK integration surface is a SMALL, explicit hook interface.** A consumer provides {an LLM loop that emits tool-calls, a context-inject point, a yield point}; the harness provides four calls: `on_session_start()→rehydrate plan`, `on_user_turn()→pending-step nag`, `on_tool_result(tool,result)→advance|feedback` (runs the effect-probe), `on_yield()→hold|release` (the drive verdict). Exactly the governance §8 lifecycle, as an embeddable API. |
| **ACP-10** | **The verdict machine is SHARED; the ENFORCEMENT POLICY is per-runtime-MODE.** `next_actionable_step` (STOP_ASYNC/UNKNOWN/USER) is one shared function. But the DRIVE differs: an **interactive** runtime (chat) maps a hold to *re-prompt the user-facing turn + the deterministic escape hatch* (GOV-13); an **autonomous** runtime (background task-agent, game logic) has no user to re-prompt, so a hold maps to *re-inject + retry to N → then PARK + escalate* (no user-gate; the `blocked≠stopped` autonomous discipline). STOP_USER is meaningless to an autonomous runtime → it becomes a park-with-reason. The consumer declares its mode; the harness picks the policy. |
| **ACP-11** | **The plane cannot let a consumer bypass the invariants.** Effect-probes are `/internal` reads (NOT ai-gateway agent-logic — governance §14 correction). Tenancy scope-keys (owner/book) ride the plan + probe args (a consumer cannot probe cross-tenant). Models resolve per-user via provider-registry (the executive already does). The SDK surfaces these as required args, not optional. |
| **ACP-12** | **Versioned + additively evolved.** Each control contract carries a `version`; changes are additive; the both-sides test (ACP-6) reds on a breaking drift. A consumer pins a contract major; the plane supports N-1 during a migration. `question_target` (Practice) is the first additive field exercised end-to-end. |
| **ACP-13** | **Framework-AGNOSTIC port + adapters — never a dependency on, nor a rebuild ON, an external agent framework.** The integration surface (ACP-9's four hooks + the contracts) is a **port**: any runtime binds via a thin **adapter** — our chat loop (A1/A2) is the first; a future LangGraph / LangChain / CrewAI / Claude-Agent-SDK runtime would be *one adapter onto the same port*, not a re-arch. **Two hard limits:** (i) we do NOT rebuild our runtime on an external framework — it would violate the **provider-gateway** invariant (LLM calls MUST go through provider-registry, not a framework's own provider SDK) and **MCP-first** (tools federate through ai-gateway); an external framework that consumes ACP is *subject to those invariants*, not exempt from them. (ii) we do NOT build any external adapter until a real consumer exists (no speculative binding — the `don't-build-for-an-absent-consumer` discipline). The SDK is **designed** adapter-ready (the port is clean, framework-neutral); adapters are demand-pulled. |
| **ACP-14** | **Memory interface = two deliberately-separate contracts: `MemoryStore` + `CheckpointSaver`** (the LangGraph split — proven across Letta/Mem0/Zep/LangGraph; §16.1). `MemoryStore` is `BaseStore`-shaped (`get/put/search/delete/list_namespaces` + async twins) over **namespace tuples that ENCODE tenancy** `(scope_tier, owner_user_id|book_id, tier_name)` — so the System→user→book cascade (User-Boundaries law) is a namespace-prefix walk, and cross-tenant is structurally impossible. **`tier` is a closed enum** `{working, episodic, semantic, procedural}` (Frontend-Tool-Contract enum discipline) routing to the EXISTING backends (KG→semantic/episodic, `working_memory`→working, file-memory→procedural). `CheckpointSaver` (`put/put_writes/get_tuple/list/next_version`) owns the **plan/charter/state**, keyed `(thread_id, checkpoint_ns, checkpoint_id)`. **No data moves** — this is one uniform interface over our dense stores. |
| **ACP-15** | **Tiers differ by WRITE-PATH → name the writes; recall is budget-aware.** The SDK exposes `log`(→episodic, auto), **`consolidate`**(episodic→semantic — *our executive-every-N-turns IS this*, now a named/auditable/throttleable verb with Zep bi-temporal supersede on conflict, not blind append), `promote`(pattern→procedural rule — the RUN-STATE→ContextHub-lesson move). Plus **`recall(query, tiers, budget)→context_block`** that fuses+reranks across tiers under a token budget — the memory-side counterpart of the **Context Budget Law kernel**. Out-of-band CRUD is reachable without the chat loop (Letta-REST lesson), through the same tenancy namespace + E0 grant-checks (`/internal must grant-check`). |
| **ACP-16** | **Durable execution = SNAPSHOT-per-step on our OWN substrate — closes W1 by WIRING, no new engine** (§16.2). `CheckpointSaver` + a `durable_step(step_id, fn, idempotency_key)` wrapper give resume-at-step + replay. **Snapshot model, NOT event-log** (reload state + skip completed steps by recorded write; event-log replay would force the whole LLM loop to be replay-deterministic — a non-starter). **Local side-effects: DBOS-piggyback** — commit the step's durability record in the SAME txn as the business write + the outbox row (reuses the transactional-outbox invariant ⇒ exactly-once). **Remote/tool: at-least-once + idempotency key** `(thread_id, checkpoint_id, step_id)`, deduped by the saga. **Pause/resume/timers → WFQ + RabbitMQ delayed** (a durable pause releases the worker; resume re-enqueues + reloads the checkpoint) — what makes crash-prone background/game agents safe. Full impl gated on the first autonomous consumer (**D-ACP-DURABLE**); the INTERFACE lands now so we don't design it out. |
| **ACP-17** | **The enforcement surface is 4-PART, not hooks-only** (2026 best practice — OpenAI Agents SDK / ADK / LangChain-1.0 / MAF all converged; §16.3). (i) **positional hooks** (`on_session_start/user_turn/tool_result/yield` — have); (ii) **wrap interceptors** `wrap_tool_call/wrap_model_call(ctx, handler)` — call the handler 0/1/N× → timeout/retry/short-circuit/replace-result in one frame (a bare before+after hook can't); (iii) a **declarative guardrail/tripwire layer, SEPARATE from hooks** — input/output phase, `on_fail ∈ {block, reask, fix, filter, refrain, escalate}` (OpenAI tripwire ∪ Guardrails-AI OnFailAction); (iv) a **typed `AgentRunContext`** threaded through all of them (session/turn ids · the invariant/policy set · DI'd services · a mutable state bag), **mapped onto OTel span attributes so context == telemetry**. Hooks return a **control-flow protocol** `Continue \| Halt(reason) \| Override(result) \| JumpTo(target)` with **layer-precedence** (which adapter wins — ADK Plugin > object-callback). Our current hook lifecycle is the right *skeleton* but ~1 of these 4 — the other three are the ADD. |
| **ACP-18** | **Effect-verification IS the platform's flagship GUARDRAIL — the validated moat.** 2026 research (proxy-state verifiable reward, GroundEval, AJ-Bench) ranks **grounded state-diff verification ABOVE LLM-as-judge** as a correctness signal, and the LangSmith/Langfuse/Phoenix tier mostly LACKS it. So probing the real effect is not "a check" buried in a hook — it is a first-class **output guardrail** (ACP-17-iii): a turn cannot complete until the `effect_verified` guardrail passes (`silent-success-is-a-bug` made a typed tripwire). This is the honesty axis, now named as the differentiator and modelled as the standard's own guardrail concept. |
| **ACP-19** | **Observability = adopt OpenTelemetry GenAI `gen_ai.*` spans + `gen_ai.evaluation.result` events — do NOT invent a schema** (§16.4). Emit the operation-name tree (`invoke_agent`/`invoke_workflow` root → `chat` → `execute_tool` carrying `gen_ai.tool.call.arguments/result`); the step transitions (`planned→in_progress→effect_checked→done`) as **span EVENTS**; and BOTH the separate-judge score AND the effect-verification as **`gen_ai.evaluation.result`** events parented to the step span. Encode effect-verification under a clearly-namespaced **`effect.*` extension** (`effect.probe.target/expected/observed/match/probe.query/verifier.kind ∈ {state_diff,code_assert,llm_judge,hybrid}`) — recording the probe QUERY makes runs replayable and the "model-claimed-success-but-probe-disagreed" case greppable across all runs. Model = **trace → span → score** (Langfuse-clean). Runs with effect labels become a **self-labeling, grounded regression corpus** (not judge-opinion). Full trace/eval-studio gated (**D-ACP-TRACE**); the SCHEMA lands now so every run is standard-shaped from day one. |
| **ACP-20** | **Speak the emerging standards; do not invent a 4th.** There is no single agent-control standard — governance assembles from **MCP** (tools — have) + **A2A** (agent-to-agent: Agent-Card discovery + task/message semantics — Linux Foundation, 150+ orgs; the port to govern cross-agent handoffs when a multi-agent consumer lands — W3) + **OTel GenAI** (observability→enforcement; the **GAOP** "policy engine in an OTel collector" pattern IS our monitor+enforce thesis). A neutral control plane is a legitimate unclaimed niche, but must CONSUME these three. The A2A adapter is gated on the first multi-agent consumer (**D-ACP-MULTIAGENT**). |

---

## 4 · The boundary — who owns what (the disposition all consumers share)

| Concern | Layer | Home | A consumer… |
|---|---|---|---|
| Author scripts / freeze a **charter** (the goal) | Definition (consumer-domain) | roleplay-svc (interview); a future world-model (game) | PRODUCES a charter conforming to the contract |
| **charter/state SSOT** + the **executive** (rewrites state) | Control · stateful | knowledge-service (HTTP) | CALLS `init`/`tick`; never stores its own copy |
| **Anchor render** (inject goal/progress into the prompt) | Control · compute | SDK library (from the contract) | EMBEDS it in its own prompt-build |
| **Verdict machine** (`next_actionable_step`) | Control · compute | SDK library | CALLS it with plan+effects → a verdict |
| **Effect-probes** (`linked_structure`, `entities_extracted`, …) | Control · stateful | domain services (`/internal`) | CALLS a probe by NAME from the catalog |
| **The drive** (hold/re-prompt/park) | Control · harness | SDK harness, **policy per mode** (ACP-10) | wraps its loop's yield point in `on_yield()` |
| **Plan/todo state** (ActivePlan) | Control · stateful | `working_memory` seam (GOV-2) | READS/writes via the SDK, tenancy-scoped |

**Nothing in this table lives in chat-service** except chat's own consumer glue. That is the whole point.

---

## 5 · What the refactor actually touches (grounded, not abstract)

| # | Change | Size | Note |
|---|---|---|---|
| **R1** | Promote `contracts/interview/working_memory.schema.json` → `contracts/agent-control/` + add `WorkflowDefinition`, `EffectRef`, `Verdict` schemas (the governance data-model §9, currently prose/Pydantic-only) | S | move + 3 new schema files; keep a redirect for the old path |
| **R2** | **Enforce the contract on the two unchecked sides** — a Rust schema-validation test in roleplay-service + a `jsonschema` test in knowledge-service (mirror chat's) | S | the SDK becomes *real* here |
| **R3** | Extract the verdict machine + anchor render + predicate parse into `sdks/python/loreweave_agent_control` (Python) ; refactor chat-service to import it (dogfood, ACP-8) | M | pure move + re-point; behavior-identical, proven by chat's existing tests staying green |
| **R4** | Extract the **cadence + drive harness** (`on_session_start/user_turn/tool_result/yield`) into the same package; chat's inline `_fire_executive_tick` + `_maybe_redrive_rail` call it | M | this is what makes a 2nd consumer cheap |
| **R5** | A **Rust SDK crate** `crates/contracts-agent-control` — charter/state types (checked against R1) + a thin executive/probe HTTP client — so roleplay (and future game) produce+consume without hand-JSON | M | mirrors `crates/contracts-ws` |
| **R6** | `docs/standards/` entry "Agent Control Plane" + a row in `docs/standards/README.md` (it is a cross-cutting standard now) | XS | discoverability |

Everything else (chat's actual behavior, the executive logic, the grading) is **untouched** — this is an **extraction + enforcement** refactor, not a rewrite.

---

## 6 · Practice as the FIRST cross-consumer validation (why this spec is not academic)

The interview Practice feature becomes the **proof** the boundary works — it exercises every layer as a
*second* consumer, additively:

1. **Contract (R1/R2):** add `question_target` to the charter schema → roleplay (producer) + chat/knowledge (consumers) all red until aligned → the SDK's both-sides check earns its keep on day one.
2. **Definition layer:** roleplay `charter::freeze` + the 3 interview presets add `question_target` (default 5) — the **only** roleplay change. It stays a pure producer.
3. **Control layer (via the SDK):** the deterministic executive extension — `question_count` (from `message_count`), real `elapsed_min` (from session `created_at`), and the **wrap directive** injected by the anchor when `count ≥ target` or `elapsed ≥ budget`. Lives in the SDK/knowledge-executive, consumed identically by chat.
4. **Mobile FE:** entry point + phone `PersonaPicker`/timed-session/`ScorecardView` — consumes the existing `/start` + `/evaluate` + scorecard read.

If Practice can be built **without adding one line of control logic to roleplay-service**, the boundary is
correct. That is the acceptance criterion.

---

## 7 · Phases

| Phase | Deliverable | DoD (effect test — PASTED) |
|---|---|---|
| **A0** | R1 + R2 — contracts moved/added + **machine-checked on all 3 sides** (chat, knowledge, roleplay) | a renamed charter field REDs the Rust test AND both Python tests |
| **A1** | R3 — Python SDK (`loreweave_agent_control`) extracted; chat-service consumes it | chat's full existing working-memory + rail tests green **importing the SDK**, not local copies |
| **A2** | R4 — the cadence+drive harness; chat's inline tick/drive re-pointed to `on_tool_result`/`on_yield` | a live chat turn drives identically (S06-style hold/release) through the harness |
| **A3** | R5 — the Rust SDK crate; roleplay produces its charter through it (no hand-JSON) | roleplay `/start` round-trips a charter the crate validated against the shared schema |
| **A4** | **Practice** (spec §6) — the 2nd consumer, incl. `question_target` + the mobile FE | Practice works with **zero** control logic added to roleplay; a live interview wraps at 5 / at budget (in-container, pasted) |
| **A5** | R6 — the `docs/standards` entry + README row; the autonomous-mode drive policy (ACP-10) stubbed for the future background/game runruntimes | the standard is discoverable; an autonomous-mode hold PARKs (unit-proven), never waits on a user |

---

## 8 · Edge cases

| # | Edge case | Handling |
|---|---|---|
| **EC-1** | A **Rust** runtime can't run the Python executive in-process | it doesn't need to — the executive is HTTP (`/internal/working-memory/tick`); the Rust crate is a thin client (ACP-5). |
| **EC-2** | An **autonomous** consumer hits a hold but has no user to re-prompt | ACP-10: the drive maps to re-inject→retry-N→**park+escalate**; STOP_USER → park-with-reason. Never blocks forever, never waits on a human that isn't there. |
| **EC-3** | Contract **drift** between polyglot consumers | ACP-6/12: every side validates against the one schema in its own suite; a breaking change is additive + versioned; the both-sides test reds. |
| **EC-4** | A consumer tries to **bypass tenancy** (probe another owner's book) | ACP-11: scope-keys are REQUIRED args on plan+probe; the `/internal` probe grant-checks the caller-derived identity (`internal-route-must-grant-check`). |
| **EC-5** | Chat-service can't cleanly consume the extracted SDK (hidden coupling) | ACP-8: that's the signal the boundary is wrong — fix the SDK interface, not paper over it in chat. The dogfood IS the gate. |
| **EC-6** | A deterministic **pipeline** author thinks it needs the plane | ACP-2 + governance §15: it doesn't — code-driven chains are governed by their control-flow; the plane is for agent-driven loops only. |
| **EC-7** | The executive tick and the rail drive **both** run per turn for one session | they share the `working_memory` seam (GOV-2 puts ActivePlan there); one read, two consumers — not duplication. The harness sequences them (`on_tool_result` then `on_yield`). |
| **EC-8** | A team wants to run a **LangGraph / LangChain / external-framework** agent on the platform | ACP-13: it integrates as an **adapter onto the hook port**, NOT by us adopting the framework. It remains bound by provider-gateway (its LLM backend = provider-registry) + MCP-first (its tools = ai-gateway federation) + tenancy. Built only when that consumer is real — designed-for, not built-ahead. |

---

## 9 · Relationship to the sealed governance spec (the division of labour)

| | Governance spec (2026-07-15, SEALED) | THIS spec (ACP) |
|---|---|---|
| Question | **What** should control an agent? | **How** does any runtime consume that control? |
| Delivers | DEFINE·PLAN·MONITOR·CONTROL semantics; the rail; effect-probes; the hook lifecycle; the drive | the LAYER boundary; the contracts; the per-language SDK; the embeddable harness; the per-mode drive policy |
| Owns | the *engine* (rail_progress, executive, probes, the G0–G5 build) | the *socket* (contracts/agent-control, the SDKs, chat-as-first-consumer, roleplay/game as future consumers) |

ACP does **not** re-decide any GOV-\* rule; it makes the GOV engine **consumable**. Governance's Phase G
builds the engine inside chat; ACP's phases **extract it into a standard** so roleplay, background
task-agents, and game logic reuse it. Practice is the first non-chat consumer and the joint acceptance
test.

---

## 10b · Competitive teardown — where ACP is WEAKER (the find-the-weakness pass)

Benchmarked against LangGraph, LangChain, CrewAI, AutoGen, OpenAI Agents SDK, Temporal/Inngest
(durable-execution), the Claude Agent SDK, and DSPy. Honest gaps first; our moat is noted only so the gaps
sit in context.

**Our moat (keep — most frameworks lack these):** (1) **Effect-verified completion** — we probe the durable
truth (a real DB row), not the model's *"done ✓"*; nearly every framework trusts the model's claim. (2) The
**DRIVE** — refuse-to-yield until the effect is met (enforcement, not just orchestration). (3) **Multi-tenant
+ provider/ MCP governance BY CONSTRUCTION** (LangGraph/LangChain are libraries — you build tenancy yourself).
(4) **Separate-judge grading** (SD-7 quarantine).

**The weaknesses, ranked by impact on the roadmap:**

| # | Gap (ours) | Who does it better | Impact | Verdict |
|---|---|---|---|---|
| **W1** | **No durable execution / checkpoint / replay / time-travel.** `ActivePlan` is a state BLOB on `working_memory`; no event-sourced, resume-at-exact-step log, no time-travel debug. A crashed background agent can't resume deterministically. **The repo OWNS a durable substrate (outbox/saga/WFQ) — it is NOT wired to the agent-control plane.** | LangGraph (checkpointer), Temporal/Inngest | **HIGH** for the future autonomous/background + game consumers (long-running, crash-prone) | **Wire ACP plan-state onto the EXISTING durable substrate — wiring, not greenfield.** Parked D-ACP-DURABLE, gated on the first autonomous consumer. |
| **W2** | **No graph topology.** `WorkflowDefinition` = step-list + `depends_on`; no conditional edges, loops, or parallel fan-out/map-reduce as first-class. | LangGraph (explicit graph) | MED — fine for LINEAR governed flows (S06); thin for branchy background/game flows | Track: `WorkflowDefinition` v2 (a DAG) IF a real branchy consumer appears. Don't pre-build. |
| **W3** | **Thin multi-agent orchestration.** We govern ONE loop; `subagent_runtime` is nested-exec (read-only clamp), not first-class handoff / delegation / role-teams / group-chat. `SubagentStop` rolls effects up, but there's no *governed handoff* primitive. | CrewAI, AutoGen, OpenAI Swarm (handoffs) | MED-HIGH for future | Track: a governed-handoff primitive when a multi-agent consumer is real. |
| **W4** | **HIL is a specialized gate, not a general interrupt/resume.** The drive = hold + skip-phrase; no "interrupt at any step, collect arbitrary human input, resume with an injected value." | LangGraph `interrupt()` | LOW-MED | Adequate now; generalize if the product needs richer HIL. |
| **W5** | **No replayable execution-trace / eval studio.** GOV-8 traces step transitions, but there's no LangSmith-grade replayable run-trace/inspector over agent executions. | LangSmith / LangGraph Studio | MED (debugging + the S06-style eval) | Track: a structured run-trace as a first-class artifact (also strengthens the S06 eval signal). |
| **W6** | **Bespoke; small ecosystem / no community components.** Onboarding cost; no off-the-shelf chains. | LangChain ecosystem | LOW — mitigated by MCP tools + **ACP-13** framework-agnostic port | Accept. |
| **W7** | **No automated prompt/flow optimization.** | DSPy | LOW (different concern) | Out of scope. |

**The one that actually matters next: W1.** Your named future consumers — **background task-agents** and
**game logic** — are long-running and crash-prone, exactly where LangGraph/Temporal win and we don't. But we
already OWN the durable substrate (outbox / saga / WFQ); the fix is **wiring the ACP `ActivePlan` onto it**
(resume-at-step, replay), folded into ACP-10's autonomous path — **not** adopting a new framework. W2/W3/W5
are demand-pulled by a real branchy / multi-agent / eval-heavy consumer; building them now would be the
`build-for-an-absent-consumer` anti-pattern.

## 10 · Open questions — RESOLVED at seal (2026-07-16, PO)

- ~~**OQ-1**~~ → **new pkg** `sdks/python/loreweave_agent_control` (mirrors `loreweave_llm`; clean dep boundary).
- ~~**OQ-2**~~ → **hand-write Rust types + validate-in-test** (ACP-6; matches `contracts-ws`). Codegen later only if churn warrants.
- ~~**OQ-3**~~ → **EXTRACT-FIRST**. A0→A3 land before A4 Practice — the second consumer is built on the clean boundary, not on the coupling this spec removes.
- ~~**OQ-4**~~ → **interface + a unit-proven park path NOW** (A5). Full autonomous impl ships with the first background/game runtime.

---

## 16 · Interface reference (research-grounded — folded in at seal, 2026-07-16)

A parallel 4-agent web-research pass (memory · durable-execution · control-SDK-standards · observability)
confirmed one thing repeatedly: **our systems already implement the hard parts; we lack the standard
INTERFACE shapes.** Below are the shapes we adopt (signatures illustrative — the A0 contracts are the SoT;
the point is the *shape*, taken from patterns proven across LangGraph / Letta / OpenAI-Agents-SDK / ADK /
Temporal / OTel-GenAI).

### 16.1 Memory (ACP-14/15) — `MemoryStore` + `CheckpointSaver`, over our EXISTING stores
```
# long-term, cross-run — namespace ENCODES tenancy; tier is a closed enum
MemoryStore.put(ns=(scope, owner_id|book_id, tier), key, value, index?)   # tier ∈ {working,episodic,semantic,procedural}
MemoryStore.get(ns,key) · search(ns_prefix, query?, filter?, limit?, offset?) · delete(ns,key) · list_namespaces(...)
# short-term, resumable — owns plan/charter/state (the CHECKPOINT tier)
CheckpointSaver.put(key=(thread_id,ns,ckpt_id), snapshot, meta) · put_writes(key, task_id, writes)
CheckpointSaver.get_tuple(key) -> (snapshot, meta, pending_writes) · list(key, before?, limit?) · next_version(cur,chan)
# named write-paths + budget-aware assembly
log(episode)   consolidate(episodes -> facts)   promote(pattern -> rule)   recall(query, tiers, budget) -> context_block
```
Maps to what exists: `semantic/episodic`→KG (PG+Neo4j, bi-temporal supersede) · `working`+plan/charter/state→`working_memory` · `procedural`→file agent-memory · `consolidate`→the executive pass (now named) · `recall`→the Context-Budget kernel, memory-side.

### 16.2 Durable step (ACP-16) — snapshot-per-step on outbox/saga/WFQ
```
durable_step(step_id, fn, *, idempotency_key)  # completed write exists? return recorded : run fn then put_writes
interrupt(payload) / await_signal(step_id)      # durable pause: checkpoint + RELEASE worker; resume re-enters
sleep_until(step_id, ts)                         # durable timer -> RabbitMQ delayed message
```
Local effect ⇒ commit `put_writes` + business write + outbox row in ONE txn (DBOS-piggyback ⇒ exactly-once).
Remote effect ⇒ at-least-once + `idempotency_key=(thread_id,ckpt_id,step_id)`, saga-deduped. Resume = reload latest
checkpoint, skip steps whose write landed — the LLM is never re-run for completed turns.

### 16.3 Enforcement surface (ACP-17) — the 4 parts
```
# (i) positional hooks (have)                         # (ii) wrap interceptors — enforce in ONE frame
on_session_start/on_user_turn/on_tool_result/on_yield   wrap_tool_call(ctx, handler) / wrap_model_call(ctx, handler)
# (iii) declarative guardrails — HALT                 # (iv) typed run-context — threaded, == OTel span attrs
Guardrail(phase=input|output) -> {tripwire, on_fail ∈ {block,reask,fix,filter,refrain,escalate}}   AgentRunContext{ids,policy,deps,state}
# hooks return a control-flow verdict:  Continue | Halt(reason) | Override(result) | JumpTo(target)   (+ layer precedence)
```
`effect_verified` is an **output Guardrail** (ACP-18), not a hook — a turn cannot complete until it passes.

### 16.4 Trace + eval (ACP-19) — OTel GenAI, effect as a first-class score
```
span tree:  invoke_agent{gen_ai.agent.*} > chat{gen_ai.request.model, usage} > execute_tool{gen_ai.tool.call.arguments/result}
span events: planned -> in_progress -> effect_checked -> done
scores (gen_ai.evaluation.result events, parented to the step span):
  { name:"llm_judge.<criterion>", score.value, score.label, explanation, provenance: separate-model }
  { name:"effect_verified", score.label: verified|unverified|drifted, explanation:<state-diff>,
    effect.probe.target, effect.expected, effect.observed, effect.match, effect.probe.query,
    effect.verifier.kind ∈ {state_diff, code_assert, llm_judge, hybrid} }     # effect.* = our namespaced extension
```
Model = trace → span → score (Langfuse-clean, OTel-native; portable to Datadog/Phoenix/Langfuse unchanged). Runs
carrying `effect_verified:unverified` are a **self-labeling grounded regression corpus** — no human/judge annotation.
This is the signal the observability tier lacks; recording `effect.probe.query` makes it replayable.

### 16.5 What this changes about the build (still EXTRACT-FIRST)
Interface SHAPES land in A0–A2 (contracts + Python SDK + harness) so nothing is designed out; HEAVY impls stay
demand-gated (durable-step full → D-ACP-DURABLE; A2A → D-ACP-MULTIAGENT; trace/eval studio → D-ACP-TRACE; graph
WorkflowDefinition → D-ACP-GRAPH). Cheap high-value adds land NOW: the memory two-contract split, the guardrail
layer with `effect_verified` as flagship, and OTel `gen_ai.*` + `effect.*` emission (schema only). **Verdict on
our design: right skeleton · validated moat (effect-verified > LLM-judge) · a concrete standards-based path to
close W1/W5 as wiring, not rewrites.**

## 17 · Extraction & re-wire edge cases (the load-bearing risks — grounded against code 2026-07-16)

This is not a greenfield build; it is **extracting a standard out of chat-service + re-wiring two live
services.** The risks are in behavior-preservation, the contract move, and the port boundary — each below is
grounded against the actual code and carries its resolution + which phase owns it.

| # | Edge case (VERIFIED) | Resolution | Phase |
|---|---|---|---|
| **RW-1** | **The contract move is test-only-safe.** Grep confirmed NO service reads `contracts/interview/working_memory.schema.json` at runtime — only chat's `test_working_memory.py` (hard-coded path) + doc comments reference it. | `git mv` → `contracts/agent-control/` + update the test path + a stub redirect at the old path, **in ONE commit**. No runtime risk; the both-sides test reds if a ref is missed. | A0 |
| **RW-2** | **Behavior-preserving extraction needs a CHARACTERIZATION baseline BEFORE the move.** Extracting `next_actionable_step` / `render_pinned/tail` / `resolve_anchor` / `merge_state` risks silent drift (closures over chat state, import side-effects). Dogfood-green is necessary but NOT sufficient. | Capture golden outputs on a fixture corpus FIRST; the extracted SDK must reproduce them **byte-identically** (a characterization test running old+new until old is deleted). | A1 |
| **RW-3** | **The port boundary — the harness returns a VERDICT; the consumer owns loop mechanics.** The drive (`_maybe_redrive_rail`) is woven into chat's SSE generator (it yields lines, re-enters the LLM loop). If the SDK owns streaming, roleplay/background/game can't reuse it. | `on_yield()` returns a pure decision `{hold\|release, reprompt_text?, escape_hatch?}`; the CONSUMER executes the re-prompt in its own loop. The SDK owns **no** streaming/loop mechanics. **THE most important extraction boundary.** | A2 |
| **RW-4** | **Two distinct control programs must not conflate.** VERIFIED separate: `_compute_rail_drive_context`/`_maybe_redrive_rail` (book-building — `book_id` + grants + `rail_specs` + `RAIL_REDRIVE_CAP`) vs `_fire_executive_tick` (interview `working_memory`). | The harness carries a `control_program ∈ {book_rail, interview_executive, none}` per session; hooks dispatch to the ACTIVE one. An interview session is NEVER subject to book-rail verdicts, and vice versa. The `ActivePlan` names its program. | A2 |
| **RW-5** | **Voice/text parity asymmetry (EC-3 risk).** VERIFIED: `voice_stream_service` reads the anchor (`resolve_anchor:365`) but the executive-tick + rail-drive appear **text-only**. | The extraction is where this is FIXED or CONSCIOUSLY decided: the harness is shared by text + voice (the `working_memory.py` EC-3 rule). A2 DoD asserts BOTH paths route through the harness — or a tracked, reasoned "voice anchor-only for now" row. Silent asymmetry = a regression. | A2 |
| **RW-6** | **The executive HTTP contract is MISSING from `contracts/` — an A0 gap.** VERIFIED: only the *state* schema is in `contracts/`; the `init`/`tick` request+response bodies live only in knowledge-service code — yet BOTH the Python SDK and the Rust crate will call them over HTTP. | A0 ALSO adds `contracts/agent-control/executive.{init,tick}.schema.json` + the probe-eval contract, machine-checked on knowledge (producer) + both SDK clients. **Add to A0 scope.** | A0 |
| **RW-7** | **`question_target` must be OPTIONAL + defaulted, never required (rolling-deploy safety).** During A4 rollout, chat/knowledge (new) and roleplay (maybe old) deploy at different times; a charter WITHOUT it must stay valid. | Schema adds `question_target` as OPTIONAL; the CONSUMER applies `default 5`, the schema does not require it (ACP-12 made concrete). Migration order: **schema → consumers (default-apply) → producer (emit)** — never producer-first. | A4 |
| **RW-8** | **The both-sides test must validate REAL producer output, not a hand fixture** (`inject-at-chokepoint-proves-nothing`). A hand-authored charter passing the schema hides a drifted `freeze()`. | A0's Rust test validates the OUTPUT of `charter::freeze()` on the real presets; the Python tests validate a real executive `tick` round-trip — real producer output, not fixtures. | A0 |
| **RW-9** | **Checkpoint/memory access must grant-check on the LOADED session's owner** (`gate-must-derive-scope-from-the-loaded-row`). `CheckpointSaver` keyed by `thread_id=session_id`; a consumer must not load another user's checkpoint by guessing a session_id. | Every checkpoint/memory op derives tenancy scope from the session row's `owner_user_id` (or E0 grant), never a client field; the `/internal` executive + probe routes grant-check the caller-derived identity. | A1/A2 |
| **RW-10** | **Concurrent turns on one session clobber `working_memory.state`.** Double-submit → two ticks; `merge_state` is monotonic for `covered` but last-writer-wins for `phase`. | The executive `update_state` is a monotonic merge under a per-session advisory lock (or an OCC version on the row) — `decouple-loop-chain-under-producer-lock`. Read-modify-write atomically, never blind-overwrite. | A2 |
| **RW-11** | **The SDK library must not hard-code knowledge-service's URL + must be mockable.** The Python SDK (a library) calls the executive over HTTP; a unit test can't hit a live service. | The SDK takes executive/probe endpoints + auth via **injected config** (no module-level URL); a test double satisfies the client interface. Provider-registry model resolution flows from the CONSUMER (per-user), never an SDK default (ACP-11). | A1 |
| **RW-12** | **Rollback plan for the re-wire.** If A2 regresses live behavior, revert must not need a data migration. | A0–A4 add **NO schema/DB migration** (contract move + code move only; durable tables are gated to D-ACP-DURABLE; FR adds only a pref key). A revert is a pure code revert. Keep A0–A4 migration-free. | all |

**Meta-resolution — this is an L/XL extraction, so the DISCIPLINE is:** (1) **characterize before you move** (RW-2); (2) **the harness is a decision-maker, not a loop** (RW-3 — the boundary that makes it reusable); (3) **no migration in the extract phases** (RW-12 — trivial rollback); (4) **prove the boundary by dogfood** (ACP-8 — chat green through the SDK) **plus** the golden (RW-2). If any of these four can't hold for a slice, stop and re-scope that slice — don't push a leaky extraction live.

## 18 · Cold-start review findings — folded in as BUILD REQUIREMENTS (2026-07-16)

Three independent cold-start adversaries (extraction-correctness · invariants/tenancy · boundary/reusability)
red-teamed this spec against the code. **PO decision: keep EXTRACT-FIRST full scope + fix the voice executive
now.** Therefore every confirmed finding below is a **mandatory requirement**, not a defer-justification. Each
is grounded in code and assigned to a slice. (The boundary lens argued to *defer* the SDK internals; the PO chose
to keep them — so those findings become "publish the contract CORRECTLY," + a truth-in-labeling note that the
N=1 dogfood proves behavior-preservation, not reusability, until a 2nd runtime lands.)

### HIGH — must be handled or the build breaks / drifts silently
| ID | Finding (VERIFIED in code) | Requirement | Slice |
|---|---|---|---|
| **RV-H1** | **`merge_state` lives in knowledge-service** (`executive.py:74`), NOT chat — but A1's DoD lists its golden alongside chat's `next_actionable_step`/`render_pinned`. Chat never calls `merge_state`; its golden can't run in chat's suite. | **knowledge-service is ALSO an A1 SDK consumer** (`knowledge-service → loreweave_agent_control`), with its own `merge_state` characterization golden. A1 scope + §4 boundary table updated: `merge_state` is a stateless LIB function; the *stateful* executive wrapper (`run_executive`, `repo.*`) stays in knowledge. | A1 |
| **RV-H2** | **The two control programs are NOT mutually exclusive.** Executive tick fires on `is_roleplay` (`stream_service.py:5377`); rail drive fires on `rail_specs and book_id and grant_ok` (`:1781`) — independent gates, no suppression. A session with a `working_memory_seed` AND a write-mode book rail fires **both today**. RW-4's single-`control_program` model silently NARROWS this. | Replace the single-active model: the harness runs the **SET of active programs, SEQUENCED** (executive tick → rail drive), **preserving today's behavior**; define precedence only where they'd contend. Add a **both-eligible-session test** proving both still fire. | A2 |
| **RV-H3** | **`on_yield` is far more entangled than "hold\|release."** The drive (`stream_service.py:1771-1861`) does a **fresh async book-state re-probe**, consumes **cross-turn nudge counters** (`rail_nudge_counts`/`rail_twice_nudged`/`rail_redrive_count`), applies enforcement caps, and drives chat-generator mechanics (synthetic `role=user` directive; **drop stateful chain head** `response_id=None`). A single happy-path live-smoke won't catch counter/enforcement drift. | The `on_yield` contract carries the real inputs (probe client, nudge counters, enforcement, escape-hatch, identity) and returns `{hold\|release, directive_text, giving_up, drove_flag}`; the CONSUMER owns the generator mechanics (RW-3 holds). A2 adds a **multi-turn drive characterization** (nudge→nudge→give-up + the escape phrase), not just one smoke. | A2 |
| **RV-H4 (tenancy)** | **The checkpoint WRITE is not owner-scoped.** `update_state` (`working_memory.py:77`) is `WHERE session_id=$1`, `user_id` a non-key column (the "UNIQUE without a scope key" smell); `get(user_id=None)` has an unscoped branch. The `CheckpointSaver` key `(thread_id,ns,ckpt_id)` would institutionalize it. | `update_state` gets **`AND user_id = $2`**; the `get(user_id=None)` branch is removed; **owner is a non-optional param** of the CheckpointSaver/repo signature. Owner-scope is a CONSTRAINT, not an upstream-read convention. | A1/A2 |

### MED — design-precision that becomes a violation if built as worded
| ID | Finding | Requirement | Slice |
|---|---|---|---|
| **RV-M4** | **`question_target` silently dropped** — chat's `WorkingMemory*` Pydantic models declare no `model_config` ⇒ `extra='ignore'` (`models.py:16-44`); `parse_working_memory` drops unknown fields. The anchor never sees it. (The repo's own `REST-mirror-drops-fields` class.) | A4 adds `question_target` to `WorkingMemoryCharter` + a **round-trip test** (present value survives `parse_working_memory` into the anchor), not only the absence direction. | A4 |
| **RV-M5** | **The wrap directive can't be "injected by the anchor"** — `render_pinned(wm)` sees only `WorkingMemory`, not `message_count`/`created_at`/`question_target`; `elapsed_min` is never computed (`merge_state:95` only preserves it). | The executive (or a deterministic pre-render step) **computes `question_count`/`elapsed_min`/`wrap` INTO `state`**; `render_pinned` reads them from `wm.state` and stays **pure** (A1 golden signature unchanged). New `state` fields ⇒ **schema.json update first** (JSONB `state`, so no DB migration — RW-12 holds). | A4 |
| **RV-M6** | **Concurrency: OCC is impossible under RW-12.** `update_state` is a blind read-modify-write; tick is fire-and-forget (`asyncio.create_task`, `:5382`). RW-10 offered "advisory lock OR OCC" — but OCC needs a `version` column = a migration RW-12 forbids. | The migration-free fix is the **advisory lock** (per-session); strike OCC from RW-10. Add a **concurrent-double-submit test** (A2's single-turn smoke doesn't exercise it). | A2 |
| **RV-M7 (voice — PO: FIX NOW)** | **The voice path has a DEAD executive** — `voice_stream_service.py` calls `resolve_anchor` (`:365`) but has **no tick, no drive**; a voice-only roleplay never advances `state` (frozen at seed), and the code calls the 2-hr voice session *"the real use"* (`:364`). | **PO chose to fix it:** wire the voice path through the executive tick (+ drive) via the shared harness, so voice sessions advance state and voice Practice enforces 5Q/timer/wrap. A2 adds a **voice live-smoke**. (No longer an "anchor-only" waiver.) | A2 |
| **RV-M1** | **`llm_judge`/`hybrid` effect-verifiers are LLM calls** — ACP-11 blanket-classified all probes as non-LLM `/internal` reads. | ACP-11/ACP-18 amended: **any `llm_judge`/`hybrid` verifier resolves its model per-user via provider-registry** (no literal), same as the executive. (Impl gated to D-ACP-TRACE; this is the design instruction now.) | spec (A0 note) |
| **RV-M3** | **Out-of-band `MemoryStore` CRUD** (ACP-15) is a NEW user-reachable surface; "cross-tenant structurally impossible" holds ONLY if the owner prefix is server-pinned. | ACP-14/15 amended: the `(scope, owner_id\|book_id, tier)` **owner prefix is SERVER-DERIVED from the authenticated caller + E0 grants, never client-asserted/spoofable**. | spec |
| **RV-M8 (trust model)** | **The executive `/internal` routes trust a body `user_id`** (`working_memory.py:41-67`); knowledge has **no cross-DB FK** to the chat session owner (`migrate.py:1452`), so RW-9's "derive from the loaded row" is **unsatisfiable there**. | Honest trust model: **internal-token + the caller asserts a SERVER-AUTHENTICATED `user_id`** (chat/roleplay derive owner from THEIR own session rows). Every future `executive.tick` consumer (RW-6's Rust/TS clients) MUST pass a server-authenticated user_id, never a request field. RW-9 reworded to this. | A0/A2 |
| **RV-M2** | ACP-5 mis-mapped `game-server` to Rust; it is **TypeScript** (`language-rule.yaml:77`). | Fixed inline in ACP-5. | done |

### LOW / truth-in-labeling (kept, under the PO's full-scope decision)
- **RV-L1** — the `CheckpointSaver` namespace has **no book tier** (`session_working_memory` carries `user_id` only). Don't advertise a book-tier cascade the checkpoint backend can't honor; the System→user→book cascade is real for the KG/glossary stores, NOT the checkpoint store.
- **RV-L2 (truth-in-labeling)** — with N=1 runtime (chat), the A1/A2 "dogfood" proves **behavior-preservation** (via the RW-2 golden), **NOT reusability**. The verdict machine (`rail_progress.py`) is book-building-specific and has one importer. State this honestly in the DoD; reusability is validated only when a genuinely-separate 2nd runtime lands.
- **RV-L3** — Practice (A4) is **independently buildable on today's seams** (charter field + executive extension + anchor). Under EXTRACT-FIRST it still follows A0–A3, but note it is not *blocked* by them — if the extraction stalls, Practice can proceed, de-risking the sequence.
- **Confirmed CLEAN by review:** executive provider-gateway (per-user model, no literal) · MCP-first exemption (non-agentic summarizer, state-write-only) · secrets (`internal_service_token`, not `JWT_SECRET`) · roleplay tenancy (per-tier partial-unique indexes, no `UNIQUE(code)` smell) · SDK placement (`contracts-ws`/`loreweave_llm` mirrors) · RW-1 move-safety · RW-8 real-`freeze()`-output test · RW-6 executive-contract gap.

## Appendix — research sources (2026-07-16 4-agent pass)
- **Memory:** LangGraph BaseStore/BaseCheckpointSaver; Letta/MemGPT memory-blocks; Mem0 add/search; Zep/Graphiti bi-temporal KG; Cognee ECL; SOAR/ACT-R lineage.
- **Durable execution:** LangGraph checkpoint (`put_writes`/`get_tuple`, pending-writes sentinels, `interrupt()`); Temporal (event-sourced replay, SideEffect); Restate/Inngest (journaling/step-memoization); DBOS (transactional piggyback exactly-once); Vanlightly determinism (control-flow deterministic, side-effects journaled).
- **Control-SDK standards:** OpenAI Agents SDK (guardrails+hooks, tripwire-halts); Google ADK (callbacks+plugins, None=observe/value=override, plugin precedence); Microsoft Agent Framework / SK (middleware pipeline); LangChain 1.0 (middleware wrap_model/tool_call, jump_to); Pydantic-AI (typed RunContext); Vercel AI SDK (stopWhen/prepareStep/wrapLanguageModel). Standards: MCP + A2A (LF, 150+ orgs) + OTel-GenAI; GAOP (policy-in-collector).
- **Observability/eval:** OTel GenAI semconv (`gen_ai.*` spans + `gen_ai.evaluation.result` event); trace→span→score model (Langfuse OSS reference, OpenInference/Phoenix); trajectory > outcome eval; grounded state-diff > LLM-judge (proxy-state reward, GroundEval, AJ-Bench).
