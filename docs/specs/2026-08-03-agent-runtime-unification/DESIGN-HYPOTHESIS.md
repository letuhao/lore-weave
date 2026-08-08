# Design hypothesis — what we are betting on, and what would prove it wrong

**Status:** UNPROVEN. This document exists because the PO stated the correct objection:

> *"I cannot approve an architecture when I don't know whether it works."*

That objection cannot be answered by more argument. It is answered by naming the **bet**, naming the
**falsifier**, and running it. This file is the input to the red team and the contract the live run is
measured against. It is deliberately written so that it can **lose**.

---

## 0 · The one-paragraph statement of the idea

> **The model does not fail at *using* tools. It fails at *choosing* one from a set that is silently
> mutated under it, and at *naming* the arguments a tool demands.** So: stop mutating the set, and stop
> demanding the names. Give a **small, fixed, always-true** surface — one search per domain, plus a
> handful of coarse capabilities that take a **plain-text instruction** and run a whole job through a
> sub-agent — and let everything else arrive **in the conversation**, where new information is supposed
> to arrive, rather than by rewriting the system prompt behind the model's back.

Shorthand: **shape 1 + shape 4, with shape 3 as an override.** Shape 2 (today) is retired.

**How it is assumed to solve the reported symptom.** The infinite loop is a chain of four links, and
the design claims to cut each one at a *different* place:

| link in the loop | today | where the design cuts it |
|---|---|---|
| the right tool is not on the wire | budget silently deletes it (measured: arm E, 0/3) | there is no budget — the set is small and fixed (**A1, A2**) |
| the model must invent an identifier | 57% of the surface demands a caller-supplied id | capabilities take text; reads return references (**A3, A5**) |
| the failure does not say what to do | 58% of "errors" are our own breakers | R10 error contract, 4 classes at the raise site |
| the model writes prose instead of calling | measured 0/3 without a directive | anti-prose enforced as a gate (**A8**) |

**Every one of those four is an assumption, not a result.** They are enumerated below with the
evidence that exists today and the evidence that does not.

---

## 1 · The assumption register

Legend — **evidence**: 🟢 measured in this repo · 🟡 measured but narrowly (one model / one prompt /
small N) · 🔴 asserted, never measured.

### A1 — Selection failure is a property of the *set*, not of the model
**Claim.** A weak model picks correctly whenever the correct tool is present and honestly described;
it fails when the set has been mutated to exclude the answer.
**Mechanism.** Remove all dynamic filtering ⇒ the failure mode cannot occur.
**Evidence.** 🟢 Arms A/B/C/D 3/3 vs arm E 0/3, single variable. 🟡 one model (`gemma-4-26b-a4b-qat`),
one task family.
**Falsifier.** A task where the correct tool *is* present, the set is ≤20, and the model still picks
wrong at a material rate. **If A1 is false, shrinking the surface buys nothing** and the whole shape
collapses back to a model-tier problem.
**Blast radius if false:** total.

### A2 — The product fits in ~20 advertised tools
**Claim.** 198 current tools collapse to one search per domain plus ~8 coarse capabilities.
**Mechanism.** 118 of 198 are writes that are steps of a larger job; those jobs are the capabilities.
**Evidence.** 🟡 the 118 count is 🟢, the *collapse* is 🔴 — no capability boundary has been drawn.
**Falsifier.** An honest decomposition that lands at 60+, or a capability whose text interface cannot
express a real user request without becoming a DSL.
**Blast radius if false:** the surface is not cache-stable and shape 1 is not reachable; falls back to
shape 3 (user-curated) as the primary, not the override.

### A3 — Text-in capabilities eliminate id-resolution failure *by construction*
**Claim.** A capability that takes `"rename the second chapter of book X to Y"` cannot fail with
"invalid chapter_id", because the caller never supplies one.
**Mechanism.** Resolution moves inside, where the code has the catalog.
**Evidence.** 🟢 57% of real errors are id-resolution; 57% of tools demand an id. 🔴 that the failure
*disappears* rather than *relocates*.
**Falsifier.** The sub-agent's internal resolution fails at a comparable rate — i.e. the ambiguity was
never in the interface, it was in the request. **This is the single most likely way the design merely
moves the problem behind a wall where it is harder to see.**
**Blast radius if false:** severe, and *worse than today* — the failure becomes unobservable.

### A4 — A sub-agent handed free text preserves the correctness the ordered sequence gave
**Claim.** Running PlanForge / world-setup / glossary-build end-to-end inside one call is at least as
correct as the model driving the steps.
**Evidence.** 🟢 the boundary exists (`subagent_runtime.py::tool_scope` — the only real tool whitelist
in the repo). 🔴 correctness under free text is unmeasured. This is open question **N2**.
**Falsifier.** Measured quality regression vs the current stepwise path on the same input.
**Blast radius if false:** the write half of the surface; reads still hold.

### A5 — Reads collapse to text-in / references-out without choking the context
**Claim.** One universal search per domain replaces 39 id-requiring reads; results are references
(id + title + snippet), and the model fetches only what it needs.
**Mechanism.** grep/glob pattern — search returns *locations*, not content.
**Evidence.** 🟡 p50 result size 171 tokens; 🟢 18 of 36 read tools have **no `limit` parameter**
(the choke hazard is concentrated and already has a written, gated rule, OUT-2, with 14 grandfathered).
🔴 no cross-store search exists — the corpus is Postgres + Neo4j + object storage + vector.
**Falsifier.** A reference that is not actionable without a second id-requiring call — which
**reintroduces the 57% class one hop later**.
**Blast radius if false:** the read half; and it takes A3 with it.

### A6 — A static tool block restores prompt-cache stability
**Claim.** Tools are the first cache block; freezing them makes the prefix stable across a session.
**Evidence.** 🟢 a changed tool block costs +65% uncached tokens.
**Falsifier.** The residual variation — mode (ask/write/plan), per-surface differences, shape-3 user
curation — mutates the block often enough that stability is not achieved in practice.
**Blast radius if false:** cost and latency, not correctness. **Non-fatal.**

### A7 — Capability and guidance delivered *in the conversation* stay effective
**Claim.** Announcing a tool as a message (the Claude Code / curl-from-docs pattern) works as well as
declaring it in the system prompt, and keeps working N turns later.
**Evidence.** 🟡 arm B (schema in conversation) 1/1, single turn.
**Falsifier.** Effectiveness decays with conversation depth, or **compaction/projection deletes the
announcement** while the model still believes the capability exists. This repo already runs a chat
projection — an announcement that survives turn 3 but not compaction is a *new* silent deletion, i.e.
the exact defect this spec exists to kill, relocated.
**Blast radius if false:** the long-tail half of the design; the fixed core survives.

### A8 — "Call a tool, do not write prose" can be enforced as a gate
**Claim.** The native failure mode of a coarse text-in surface (prose instead of action) is
suppressible.
**Evidence.** 🟡 0/3 without directive, 3/3 with one — one model, one prompt. 🟢 the `co_write`
incident (6,948 characters, zero tool calls) is the production instance.
**Falsifier.** A prompt-level directive that holds for one model and not the next, with no
*mechanical* enforcement available. Open question **N3**: what is the gate, as opposed to the hope?
**Blast radius if false:** the whole coarse-capability idea degrades into a chatbot.

### A9 — Deprecating everything and rebuilding beats migrating in place
**Claim (PO).** Retire all current MCP/skills/workflows, keep only the new architecture, re-admit
tools one at a time under the stricter definition. No noise, and every tool measurable.
**Mechanism.** The 13 accumulated mechanisms make any measurement confounded; a clean floor removes
the confound.
**Evidence.** 🔴 asserted. Counter-evidence available: this repo's tools are **live in a product with
a dogfood book**, and the frontend-tools MCP migration is mid-flight on this very branch.
**Falsifier.** A dependency that cannot be dark — an FE surface, an in-flight job, a seeded workflow —
that makes "deprecate all" mean "break the product", or the loss of the **baseline we need to prove
the new shape is better**.
**Blast radius if false:** schedule and product risk, not design correctness.

### A10 — Per-tool live verification is a valid acceptance signal
**Claim.** Stack one brick at a time; when the tower falls, adjust.
**Evidence.** 🔴 and this is the assumption with the worst track record here: **all thirteen previous
mechanisms were also "verified"**. Context telemetry currently covers **35%** of messages and **nothing
before July 2026**; a freshly driven turn wrote **none**.
**Falsifier.** We cannot tell a fallen tower from a standing one. **If A10 is false, nothing else in
this document can be settled** — including whether A1–A9 are true.
**Blast radius if false:** total, and silent.

### A11 — The FSM lane absorbs the ordered multi-step jobs
**Claim.** Chat never has to drive a fixed-order sequence, because the sequence lane exists.
**Evidence.** 🟢 12 seeded workflows assert steps + `done_when`. 🟢 **and none of them is runnable** —
the rack has no click handler.
**Falsifier.** The FSM lane cannot be reached by a user, so chat drives the sequence anyway and A2's
capability count is wrong.
**Blast radius if false:** A2 and A4.

### A12 — Codegen does not grow the prompt
**Claim.** An EF-style generated manifest and migration chain add build-time cost only.
**Evidence.** 🟡 R13.6 forbids generating prose; R13.6.1 asserts a token budget in CI.
**Falsifier.** Any generated artifact that reaches a prompt and is more verbose than the hand-written
prose it replaced. Already flagged 🔴 in §7 as the most likely way this spec does net harm.
**Blast radius if false:** per-turn, permanent cost regression.

---

## 2 · The dependency structure — what is load-bearing

```
A10 (can we measure?) ──── if false, everything below is unknowable
   │
   └── A1 (set, not model) ──── if false, the shape is wrong outright
          │
          ├── A2 (~20 fits) ──┬── A4 (sub-agent correctness)
          │                   └── A11 (FSM lane reachable)
          ├── A3 (id failure gone) ── A5 (reads → references)
          ├── A7 (conversation delivery durable)
          └── A8 (anti-prose gate)

A6, A9, A12 are cost/schedule assumptions — expensive if wrong, not fatal.
```

**Order of falsification is therefore fixed: A10, then A1, then A3/A5 together, then A2/A4.**
Anything that tests A2 before A1 is testing the wrong thing.

---

## 3 · Red-team mandate

The red team's job is **not** to grade this document. It is to produce **concrete scenarios in which a
stated assumption is false**, grounded in this repository's real code and real data, and to say what
observation would distinguish its scenario from the design's claim.

A finding is worth reporting only if it names:

1. the assumption it attacks (A1–A12),
2. a **specific** scenario — a real request, a real store, a real file path,
3. why the design's stated mitigation does not cover it,
4. **the cheapest observation that would settle it** — this is the part that becomes the POC.

Explicitly in scope: attacking the **rival shapes** too. If a cheaper option (for example: fix only
the error contract and the `book_id` resolution, change nothing structural) captures most of the value,
that is the most damaging finding available and it must be made.

---

## 4 · Red-team verdict (2026-08-04, seven parallel attacks)

**Nine of twelve assumptions are dead. Two are wounded. One survives by fiat.**
Every verdict below was re-verified in the main session against the live database or the source — the
red team's claims are cited, not trusted. Two agent claims were corrected in the process and are
marked ⚠.

| # | assumption | verdict | the fact that settled it |
|---|---|---|---|
| **A1** | set, not model | 🔴 **DEAD as stated** | **2,477 / 4,010 failures (61.8%) are on a tool that already SUCCEEDED in that same session.** Arms A–E all ran one zero-arg lookup (*"List my books."*); the spec's multi-step citation `eval/glossary_build_poc.py:57-59` sends **no `tools`** at all. Proven for single-step lookup only |
| **A2** | ~20 advertised | 🔴 **DEAD** | honest decomposition using §2.2's own four-part test = **76** (13 capabilities + **51 writes that refuse** + 12 searches) |
| **A3** | text-in kills id failure | 🔴 **DEAD as stated** | it already shipped for `book_id` (a 22-line schema projection), and where resolution relocated it **fails silently**: a non-UUID `chapter_id` is overwritten with the turn's id and the call **succeeds on the wrong object** (`stream_service.py:1619-1623`). The one internal resolver **mints duplicates** rather than erroring (`entity_resolver.py:216-219`) |
| **A4** | sub-agent holds correctness | 🔴 **DEAD** | ⚠ `subagent_defs` holds **1 row** — `lore-scout`, `tool_scope:["glossary_search","glossary_get_entity"]` (RT2 said zero). Two read tools. **It has never held a write.** And production says the opposite in a comment: *"NEVER mixing kinds in a call (that is the E2 collapse)"* (`glossary_build/service.py:444-447`) |
| **A5** | universal search | 🔴 **DEAD as named** | **already shipped, already retracted in writing 2026-07-24** (K26, `knowledge-service/app/mcp/server.py:368-379`) for precisely the failure A5 would rebuild. Both search candidates take `book_id` as a **required** path UUID; the search path folds **no** CJK/honorifics while the write path folds 60 |
| A6 | cache stability | 🟠 wounded, non-fatal | 60 distinct tool-block variants; `permission_mode` is per-turn behind a one-keystroke toggle |
| **A7** | delivery in conversation | 🔴 **DEAD — not implementable** | history load is `SELECT role, content … LIMIT 50`, **pin-blind**; writers persist only `user`/`assistant`; **`invoke_tool` does not exist in chat-service**. An announcement at turn 3 is gone by turn ~28 *before compaction sees it* — a **new** silent deletion |
| A8 | anti-prose as a gate | 🟠 wounded | `tool_choice` is plumbed to LM Studio but chat hardcodes `"auto"`; `commit-service` shows `"required"` is **advisory** — its real gate is a deterministic non-LLM fallback |
| **A9** | big-bang deprecation | 🔴 **DEAD as a big bang** | public MCP edge = **170 `TOOL_POLICY` entries** + published OAuth scopes + **issued third-party keys**. Cannot be dark. **Steel-man is real though:** of 315 registered tools, **123 ever called, 90 ever succeeded** |
| **A10** | we can measure | 🔴 **FALSE TODAY** | **no column records which tools a turn advertised** — arm-E silent deletion is *structurally invisible* in production. `message_feedback` = **3 rows**. `finish_reason` covers **249/2,653 = 9.4%**. ⚠ `context_breakdown` is **83.4%**, not the 35% this register claimed — my denominator was wrong |
| **A11** | FSM lane absorbs jobs | 🔴 **DEAD** | `grep workflow_run` → **one hit, in a test comment.** No run endpoint, no `workflow_runs` table, no runner in any language, no `onPick`/`onRun` in `ExtensionsPage.tsx`. The 12 workflows have never been runnable |
| A12 | codegen won't grow prompts | 🟡 survives by fiat | true only because R13.6 forbids generating prose; 20,500 tokens of skill prose sit outside the gate |

### 4.1 The finding that matters more than the verdicts

**Seven independent attacks converged on the same alternative.** Not one of them was asked to find it:

> The mechanism A3 proposes **already shipped once**, for `book_id`, as a schema projection plus a meta
> flag. **613 of the 960 id errors are `entity_id` and `chapter_id`** — the two arguments it was never
> extended to. `book_chapter_save_draft` already takes text and resolves internally (*"pick the chapter
> by NUMBER or TITLE"*). This is a **per-tool argument-resolution fix**, and it is what four separate
> red teams independently ranked first.

**And a failure class nobody was tracking.** Both the proposal *and* the cheap rival convert loud
failures into quiet ones — wrong-object success, silent under-return, most-recently-edited fallback on
a zero-hit query. **This repo counts only loud failures.** Any acceptance criterion built on an error
rate will therefore improve while correctness degrades.

### 4.2 Acceptance arithmetic — the reason "3/3" must never be cited again

```
3 / 3 successes  ⇒  95% upper bound on failure rate = 63.2%
production failure rate, decontaminated             = 54.2%
```

**54.2% sits inside every 3/3 interval.** Arms C and D — used in §1.0 as evidence — bound nothing.
To assert ≤10% failure for one capability requires **29 consecutive successes**; at 20 capabilities
that is ~580 instrumented turns. Either that is budgeted, or instrumented production traffic becomes
the acceptance channel — which is what §4.3 items 1–4 exist to enable.

### 4.3 What must exist before the first brick

Ordered. Nothing below line 3 is knowable until lines 1–3 are done.

1. **`chat_messages.advertised_tools`** — written at the existing chokepoint `stream_service.py:2143`,
   persisted in the UPSERT. *Without this, the root cause this spec was written for has no field it
   could ever appear in.*
2. **`chat_messages.withheld_tools`** — make `budget_names_by_tokens` return `(kept, dropped)` exactly
   as its sibling `budget_rail_tools` already does **twenty lines below it**; every filter contributes
   `{tool, stage, reason}`.
3. **`tool_calls[].source ∈ {tool, breaker, meta}`** — no migration needed (JSONB). Until this exists,
   **65.7% of the error signal is our own prose**.
4. **A wrong-object counter** (§4.1) and mandatory `finish_reason`.
5. **Freeze the baseline before anything is retired** — snapshot `tools/list` into `contracts/`, script
   arms A–E. Today they were built from a live catalog and are **not reproducible**; after a retirement
   only arms A and B survive, and those are the two that agree with the design.

### 4.3a Constraint C3 (PO, 2026-08-04) — **MCP is the agent surface; the FE goes through the API**

Measured against the live tree the same hour it was stated. **It is already ~99% true**, and the
residue is a known, countable list rather than a systemic constraint:

| lane | who decides the call | transport | recorded in `chat_messages.tool_calls`? | C3 |
|---|---|---|---|---|
| chat agent | the model | MCP | ✅ 7,447 calls | ✅ |
| **browser-executed agent tools** — `FRONTEND_TOOL_NAMES` (`ui_*`, `propose_edit`) | **the model** | MCP; the *executor* is the browser | ✅ | ✅ — the marker *"describes WHERE A TOOL EXECUTES, not where it is decided"* (`frontend_tools.py:57`) |
| third-party keys | an external agent | MCP via `mcp-public-gateway` | ❌ — separate `audit-client` | ✅ still the agent surface |
| **FE bridge** | **the FE, no agent in the loop** | REST `/v1/ai/tools/execute` → BFF → ai-gateway, carrying an **MCP tool name** | ❌ | ❌ **the exception** |

**The exception is 8 call sites in 2 files** (`composition/motif/api.ts`, `composition/arcImport/api.ts`)
against a **`FE_BRIDGE_TOOL_ALLOWLIST` of 8 tools, all composition** — `composition_conformance_run`,
`composition_arc_import_analyze`, `composition_motif_{mine,bind,adopt}`, `composition_library_translate`,
`composition_get_mine_job`. Its own header states the intent: *"the FE's path to a Tier-W propose …
**WITHOUT a chat agent in the loop**."* The rest of the frontend uses `/v1/*` REST throughout
(53 × `/v1/books`, 17 × `/v1/chat`, …) and **never speaks MCP**.

**Two different things in this repo are both called "frontend tools", and the audit conflated them.**
One is agent-decided with a browser executor (in-lane); the other is FE-decided (out-of-lane). Every
statement about "FE tools" in `AUDIT.md` and `SPEC.md` must name which.

**What C3 changes in the verdict above:**

- **RT4-6 collapses.** Its objection — *"chat telemetry covers one lane, so `never called ⇒ dead` would
  silently kill shipped FE tools"* — was the reason A9's retire-by-data was scheduled *after* the R9.6
  counters. Under C3 the unrecorded non-agent lane is **a fixed list of 8 names**, not an unknown
  population. Retire-by-data needs only: chat telemetry **+ those 8 + the public-gateway audit log**.
  **That un-blocks it by an entire phase.**
- **A9's steel-man strengthens.** If MCP exists for agents, then **192 of 315 tools have never been
  called by their only intended consumer.** That is no longer a partial-visibility artefact.
- **The 170-entry public policy stands unchanged** as a deprecation-window constraint — third-party
  keys *are* the agent surface under C3, so a sunset window is required, not optional.
- **A new, bounded question:** give those 8 real REST endpoints and MCP becomes exactly one lane with
  exactly one telemetry table. Small, and it makes the denominator exact.

### 4.4 Status of this document

**The architecture in `SPEC.md` §1.4 does not survive its own red team and must not be built as
specified.** That is the finding, and it was obtained for the cost of one session rather than one
quarter. The spec is not withdrawn — R10 (error contract), R5 (guards register), R1 (manifest) and
R9.6 (usage counters) are untouched by every attack above, and items 1–4 here are R5 made concrete.

What is withdrawn is the claim that **1 + 4** is ready to decide. It is not, and the correct next act
is instrumentation plus two SQL-sized POCs, not a rebuild.
