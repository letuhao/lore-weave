# Spec — Agent Task/Process Governance (DEFINE · PLAN · MONITOR · CONTROL)

> **Status:** 📐 CLARIFY draft — 2026-07-15. Authored after a live S06 flagship replay proved the gap
> and a web-research pass (BPM process governance + 2026 AI-agent governance + the todo-list pattern
> across Claude Code / Cursor / Codex / Antigravity). **Highest priority** (PO-directed).
> **Type:** FS · cross-cutting (chat-service agent loop + a small composition/book effect-check surface).
> **Decision prefix:** **GOV-\***.
> **Builds on (does NOT duplicate):** [`2026-07-09-agent-discoverability-and-workflow`](2026-07-09-agent-discoverability-and-workflow/) (the *workflow definitions* + discoverability). **Distinct from** [`2026-07-03-ai-task-standard.md`](2026-07-03-ai-task-standard.md) (that governs **single-shot NON-agentic** LLM generation; this governs **multi-step AGENTIC workflows**).

---

## 1 · The problem, proven live

A workflow **definition** without **governance** is almost useless — this is an industry consensus, and
we measured it. The S06 flagship replay (gemma-4-26b, in-container, 2026-07-15):

- The agent had the tools (it called `plan_propose_spec`), had the instruction (the new `co_write`
  skill teaches *"propose AND compile"*, injected + unit-proven), and used a **synchronous** propose
  (rules mode — the spec was ready immediately).
- It **still proposed and stopped.** `structure_node=0`, `outline_node=0`. The planning feature never
  produced the linked structure it exists to produce. **A feature that never works is not deliverable.**

**Root cause (not tool-missing, not instruction-missing):** *plan salience decay.* The research names it
exactly — *"as tool results accumulate, the original plan fades in salience; a ten-step task drifts after
steps 1–3 because 4–10 are no longer prominent."* The agent did steps 1–3 (orient, propose), the user
pushed drafting (turns 12–16), and **"compile" fell out of salience.** No mechanism held it there.

**What we have vs. what we lack.** We have *definitions* (`co_write`, `plan_forge`, the workflow spec) and
*task-specific* rule-logic (glossary extraction, lore-enrichment quality checks) — but no **framework**.
The task-specific enforcers are hardcoded, per-task, and un-generalised; the workflows have no PLAN /
MONITOR / CONTROL pillars around them. The agent cannot self-define a workflow's checklist, nor its own
enforcer.

---

## 2 · The model — a 4-pillar governance loop (PDCA for agents)

BPM, 2026 AI-agent-governance stacks, and every agentic IDE converge on the same control loop. Named for
our system:

| # | Pillar | What it does | The failure it prevents |
|---|---|---|---|
| **1 · DEFINE** | A workflow states its **steps, dependencies, and each step's REQUIRED EFFECT** (the observable it must produce) + optional enforcer rules. Platform-authored (`co_write`, `plan_forge`) **or agent-self-defined** at plan time. | undefined / implicit process |
| **2 · PLAN** | When a workflow starts, the agent **instantiates** the definition as a concrete, **persistent todo list** for THIS task (on the `working_memory` seam). One-in-progress. | no plan; ad-hoc drift |
| **3 · MONITOR** | Track each step done/pending; **re-inject the pending steps every turn (the "nag")** so they stay salient; detect drift/thrash (repeat-read, empty-intent). | **salience decay** (the S06 failure) |
| **4 · CONTROL** | **Enforce**: a step cannot be marked *done* until its REQUIRED EFFECT is verified — a cheap **rule-based effect-check** (+ optional LLM check for nuance). On deviation, **re-prompt**; on repeated failure, **escalate/replan**. | **false-done** (weak model claims a step it never did) |

The loop: **DEFINE (Plan)** → agent **PLAN/EXECUTE (Do)** → **MONITOR (Check)** → **CONTROL (Act)** → repeat
until every step's effect is real. This is **PDCA**, applied per-agent-task.

### Why all four, not one

- **DEFINE alone** = a steering file. The agent reads it and still drifts (S06 proved it).
- **PLAN alone** (todo list) = keeps steps salient, but a weak model can **mark a step done without
  doing it** (false-done — the bug class this repo bans). Needs CONTROL.
- **CONTROL alone** (a verifier) = catches the miss, but re-deriving "what should have happened" every
  turn is heavy and un-anchored. Needs a DEFINE + a PLAN to check against.
- **Together** they are cheap and robust: the todo keeps the step visible (MONITOR/nag), and a one-query
  effect-check gates its completion (CONTROL) so it can neither fade nor be faked.

---

## 3 · Sealed decisions (draft — for PO review)

| # | Decision |
|---|---|
| **GOV-1** | **A workflow definition is DATA, not prose.** Each step declares `{id, intent, required_effect, enforcer?}`. `required_effect` is a **named, cheaply-checkable observable** (e.g. `composition.linked_structure(book_id) > 0`), resolved by a small registry of effect-probes — NOT free text. This is what makes CONTROL possible and generic. |
| **GOV-2** | **The agent PLANS a workflow into a persistent todo list** on the existing `working_memory` seam (one home — do NOT invent a second plan store). Steps carry their `required_effect` from the definition. One-in-progress. Survives compaction (the seam already does). |
| **GOV-3** | **MONITOR re-injects PENDING steps every turn (the nag), not the whole plan.** Tight (tokens are taxed every turn — 07S §1). A step whose effect is already satisfied drops off; a pending one stays salient. Mirrors the industry "nag reminder after N idle rounds", but effect-driven, not round-counting. |
| **GOV-4** | **CONTROL gates step-completion on the effect-check — a step is `done` ONLY when its `required_effect` probe returns true.** A model claiming *"compiled ✓"* while `linked_structure=0` is **overridden to still-pending** + re-prompted (*"the plan still has no linked structure — call plan_compile"*). This is the `silent-success-is-a-bug` law made mechanical. Rule-based first (cheap, deterministic); an LLM check is opt-in per step for genuinely semantic effects. |
| **GOV-5** | **Both platform-defined AND agent-self-defined.** Platform ships governed workflows (`co_write`, `plan_forge`, and — generalised — glossary-extraction / lore-enrichment). The agent may ALSO define an ad-hoc workflow at plan time (its todo list) and **declare a step's effect** for self-enforcement. Agent-declared effects draw from the SAME probe registry (a closed set — the agent can't invent an unverifiable effect; `Frontend-Tool-Contract` enum discipline). |
| **GOV-6** | **Generalise the existing task-specific enforcers INTO this framework, don't fork it.** glossary-extraction and lore-enrichment already have rule-based quality logic; they become **governed workflows** with declared effects, retiring their bespoke enforcement. One framework, many workflows. Legacy per-task logic is tracked for migration, never grandfathered silently. |
| **GOV-7** | **Escalation is bounded.** N consecutive CONTROL failures on one step → stop re-prompting, surface honestly to the user (*"I couldn't complete X"*), never loop forever (the `hard-stop after 3 attempts` discipline). Enforcement re-prompts are capped + counted; a runaway enforcer is itself a bug. |
| **GOV-8** | **Governance is OBSERVABLE.** Every step transition (planned → in-progress → effect-checked → done/re-prompted) is traced (the 2026 AI-governance "observability layer"). This is the audit trail + the eval signal (the S06 gate reads it). |
| **GOV-9** | **The enforcement surface is a COPIED hook lifecycle** (OQ-1 sealed — Claude Code + Kiro converge identically; we do not invent one). The governance loop attaches to four lifecycle events: `UserPromptSubmit` (MONITOR — inject the pending-step nag), `PreToolUse` (CONTROL — block a step that violates a dependency; exit-2 semantics = block + reason to the model), `PostToolUse` (CONTROL — run the just-completed step's effect-probe, mark done / re-prompt), and **`Stop`** (CONTROL — the completion gate: **refuse to yield the turn** while a pending step's effect is unmet, sending control back with the re-prompt). §8 details the mapping. |
| **GOV-10** | **The effect-probe registry is HYBRID: central CATALOG, distributed IMPL** (OQ-2 sealed — the microservices-governance consensus: *centralize the policy source of truth, distribute enforcement close to the workload*). The **catalog** (probe names + typed contracts + the closed set) has ONE home (a governance module in chat-service); each **probe implementation** is owned by its domain as an MCP tool (composition owns `linked_structure`, glossary owns `entities_extracted`) — MCP-first + provider-gateway invariants. No bottleneck (a probe is one cheap query); consistent contract (one catalog). §10 details it. |
| **GOV-11** | **This is the SESSION-governance pattern ported from meta to product, and STRONGER in the honesty axis** (OQ-4 resolved by brainstorm). The repo already runs agent-governance on itself (Claude Code ↔ the human): `/goal` (a Stop-gate condition), `workflow-gate.py` (an effect-gated phase state-machine), the RUN-STATE file (a persistent todo), the pre-commit hook (rule-probes), the TodoWrite nag. We reuse that vocabulary (*condition · evidence · gate · nag*). Crucial difference: `/goal`'s evaluator reads the **transcript only** — it enforces persistence, NOT honesty (a model *claiming* a check passed satisfies it). The product agent-governance **runs the effect-probe (a real query)**, so it verifies the EFFECT, not the claim — it can do what `/goal` structurally cannot. §11 details the symmetry. |

---

## 4 · How it maps to what exists (the seams — build on, don't duplicate)

| Pillar | Existing seam | What GOV adds |
|---|---|---|
| DEFINE | `co_write_skill.py`, `plan_forge_skill.py`, the workflow-definition spec | a **data schema** for steps+effects (today they are prose) |
| PLAN | `working_memory.py` (persistent cross-turn anchor), `workflow_runner` (`workflow_list/load_result`) | the **todo instantiation** of a workflow onto working-memory |
| MONITOR | `book_context_note` re-injection, the async-honesty signal, empty-intent / repeat-read detectors | **effect-driven pending re-inject** (the nag) |
| CONTROL | glossary/lore rule-checks (task-specific); `silent-success-is-a-bug` law | a generic **effect-probe registry** + the completion gate + re-prompt |

**Effect-probe registry (the new core piece).** A closed set of cheap probes, one per governable effect:
`composition.linked_structure(book_id)`, `glossary.entities_extracted(...)`, `book.chapter_published(...)`,
… Each is a single fast query returning a boolean/count. Platform + agent both reference probes **by
name from this registry** (GOV-5's closed set). This is the smallest new surface that makes CONTROL
generic — and it reuses the exact query patterns the task-specific enforcers already run.

---

## 5 · The S06 case, governed (the acceptance walk-through)

1. **DEFINE**: `co_write` declares the *lay-out-a-story* workflow: `[propose → compile(effect: linked_structure>0) → draft]`.
2. **PLAN**: the author says *"lay a story out"* → the agent writes the todo on working-memory, steps carry their effects.
3. Agent proposes (step 1) → its effect (`plan_run exists`) satisfied → step 1 `done`.
4. Author pushes drafting (turn 12). **MONITOR re-injects the pending `compile` step** — it does not fade.
5. Agent tries to move on / claim setup done. **CONTROL** checks `linked_structure(book) > 0` → **false** →
   overrides to pending + re-prompts *"compile the plan first."*
6. Agent calls `plan_compile` → probe returns true → step 2 `done` → drafting proceeds.
7. **Gate GREEN by mechanism, not by hoping the weak model self-regulates.**

---

## 6 · Phases (draft)

| Phase | Deliverable | DoD (effect test) |
|---|---|---|
| **P0** | The **effect-probe registry** + the step/effect **data schema** (GOV-1). Seed with `linked_structure` + the 2 legacy task probes. | a probe returns the right boolean on a live book; schema round-trips |
| **P1** | **PLAN**: workflow → todo on `working_memory` (GOV-2), one-in-progress. | a workflow start writes the todo; survives a compaction |
| **P2** | **MONITOR**: effect-driven pending re-inject (GOV-3). | pending `compile` re-appears each turn until its effect is true |
| **P3** | **CONTROL**: the completion gate + re-prompt + bounded escalation (GOV-4/7). | a false-done `compile` is overridden + re-prompted; caps at N |
| **P4** | **Generalise** glossary-extraction + lore-enrichment into governed workflows (GOV-6); retire bespoke enforcement. | both run through the framework; old per-task logic deleted |
| **P5** | **Observability** (GOV-8) + **the S06 flagship replay GREEN** — `structure_node > 0`, driven by governance. | the pasted S06 metrics + DB rows; 23-D7 / 27-H4 / 28-D3 satisfied |

---

## 7 · Open questions

**RESOLVED (folded into §3 + detailed below):**
- ~~**OQ-1**~~ → **GOV-9 / §8** — copy the Claude Code + Kiro hook lifecycle (they hook before/after/stop).
- ~~**OQ-2**~~ → **GOV-10 / §10** — hybrid: central catalog, domain-distributed probe impl.
- ~~**OQ-4**~~ → **GOV-11 / §11** — port the `/goal`+`workflow-gate` pattern; stronger in honesty (effect-probe > transcript).

**STILL OPEN (for the detail pass + edge-case review):**
- **OQ-3** Agent-self-defined effects — how closed is the set? (§9.3 proposes typed-parameterised probes
  from a closed name-registry; confirm the arg-typing + who can register a new probe name.)
- **OQ-5** Per-turn cost of MONITOR re-inject + CONTROL probes — measure, don't assume
  (`m3-pullmode-measured-nogo`, 07S §1 budget). §12 EC-9.
- **OQ-6** (new) Async effects — a `mode="llm"` propose returns a *job*; its effect (`spec_ready`) is not
  immediate. Does CONTROL wait, poll, or treat "job in flight" as a distinct pending sub-state? §12 EC-2.
- **OQ-7** (new) Who owns the WORKFLOW-DEFINITION catalog vs. the skill that teaches it? Today the prose
  lives in `co_write_skill.py`; the governed definition is data. One home — do they merge? §9.1.

---

## 8 · The enforcement surface — the copied hook lifecycle (GOV-9)

Claude Code and Kiro converge on the same events; we adopt them verbatim and place each governance
pillar on the right one. Exit-code semantics are copied too: a **block** (PreToolUse exit-2) stops the
action and hands the reason to the model; a **refuse-to-stop** (Stop) sends control back with a reason.

| Lifecycle event | Fires | Governance action | Block / feedback |
|---|---|---|---|
| `SessionStart` / resume | session/agent start | rehydrate the active workflow's plan from `working_memory` | — |
| **`UserPromptSubmit`** | user turn, before the model sees it | **MONITOR**: append the PENDING-steps nag to context (only the not-yet-satisfied steps) | context inject |
| **`PreToolUse`** | before a tool runs | **CONTROL (guard)**: if the tool would violate a step dependency (e.g. drafting before the plan compiled, when the workflow requires it), block with the reason | **exit-2 block** |
| **`PostToolUse`** | after a tool returns | **CONTROL (advance)**: if this tool was a step's action, run that step's **effect-probe**; true → mark `done`; false → keep pending + inject feedback (*"you called plan_compile but linked_structure is still 0 — check the result"*) | feedback inject |
| **`Stop`** ⭐ | model about to yield the turn | **CONTROL (gate)**: if any REQUIRED (non-optional) pending step has an unmet effect AND the user's intent still implies the workflow, **refuse to yield** — re-prompt the model to complete it | **refuse-to-stop** (bounded, GOV-7) |
| `PreCompact` | before compaction | ensure the plan is durably on `working_memory` (survives the compaction) | — |
| `SubagentStop` | a sub-agent finishes | roll its step effects up into the parent plan | — |

**The S06 fix is the `Stop` gate + the `PostToolUse` advance:** the agent proposes (PostToolUse marks
step-1 done), tries to move to drafting, hits `Stop` with `compile` still pending + `linked_structure=0`
→ refused, re-prompted → compiles → probe true → `Stop` allows the yield. No reliance on self-regulation.

⚠ **The `Stop` gate must not trap a user who changed their mind.** It fires only while the user's intent
still implies the workflow (a lightweight intent check) and is bounded (GOV-7: N refusals → surface
honestly, release). A user who says *"forget the plan, just write"* releases the gate — governance
serves the author, it does not imprison them (the `blocked ≠ imprisoned` principle).

---

## 9 · Data model

### 9.1 WorkflowDefinition (the DEFINE artifact — OQ-7)
```
WorkflowDefinition {
  id: str                     # "co_write.lay_out_story"
  trigger: intent-descriptor  # when it applies (author lays out their story)
  steps: [ Step {
    id: str                   # "compile"
    intent: str               # one line, human + model readable
    action_hint: str          # the tool(s) that advance it (advisory, not a hard bind)
    required_effect: EffectRef | null   # null ⇒ advisory step (no gate)
    optional: bool            # a non-required step never blocks Stop
    depends_on: [step_id]     # ordering for the PreToolUse guard
  } ]
}
```
The **skill prose** (`co_write_skill.py`) and the **governed definition** are ONE concept in two forms;
GOV resolves OQ-7 by making the definition the source and the skill prose a *rendering* of it (so they
cannot drift — the `css-var-duplicated-across-two-consumers-drifts` lesson).

### 9.2 EffectRef + the probe contract
```
EffectRef { probe: ProbeName; args: {typed} }        # e.g. { probe: "composition.linked_structure", args: { book_id } }
Probe (impl, domain-owned MCP) : (args) -> { satisfied: bool, observed: <cheap value>, cost_ms }
```
`observed` lets the re-prompt be specific (*"linked_structure = 0"*), not just "not done".

### 9.3 The plan/todo state (on `working_memory`, GOV-2)
```
ActivePlan {
  workflow_id: str
  steps: [ { step_id, state: planned|in_progress|done|blocked, last_probe: {satisfied, observed, at}, attempts: int } ]
  # one-in-progress invariant; survives compaction; re-injected (pending only) by MONITOR
}
```
**OQ-3** (agent-self-defined): the agent may author an `ActivePlan` ad-hoc, but each `required_effect`
must reference a **probe NAME from the closed catalog** (it cannot invent an unverifiable effect) — the
`Frontend-Tool-Contract` closed-set-⇒-enum discipline applied to effects. It MAY parameterise
(`linked_structure(book_id=X)`) with typed args; it may NOT register a new probe name (that is a
platform/def-time act, §10).

---

## 10 · The effect-probe registry (GOV-10 — hybrid)

- **Central catalog** (one home, chat-service governance module): the closed set of `ProbeName`s, each
  with its typed arg-schema + which domain owns it + a description. Versioned. This is the SoT the agent
  and the definitions reference by name — the `contracts/frontend-tools.contract.json` pattern, for
  effects.
- **Distributed impl**: each probe is an MCP tool on its owning domain (`composition_probe_linked_structure`
  on composition-service, reading `structure_node`/`outline_node`; `glossary_probe_entities_extracted` on
  glossary-service). MCP-first; a probe never reaches into another service's DB (provider-gateway /
  scope-separation invariants).
- **Seeded probes (P0):** `composition.linked_structure(book_id)`, plus the two that generalise the
  existing task-specific enforcers — `glossary.entities_extracted(...)`, `lore.enrichment_complete(...)`
  — so GOV-6 lands with real subjects, not a toy.
- **Cost discipline:** a probe is ONE cheap query (`EXISTS`/`count`), cached within a turn. The catalog
  records each probe's measured `cost_ms`; a probe that is not cheap is a design smell (CONTROL runs it
  often). This answers OQ-5 by construction — but it is MEASURED at P0, not assumed.

---

## 11 · Symmetry with the session-governance (`/goal` + `workflow-gate`) — GOV-11

The repo already governs the **Claude-Code ↔ human** loop; the product governs the **studio-agent ↔
novelist** loop. Same four pillars, same vocabulary, one is the reference for the other:

| Pillar | SESSION (this repo, on itself) | PRODUCT (the studio agent) |
|---|---|---|
| DEFINE | 12-phase `WORKFLOW.md` + the `/goal` condition | `WorkflowDefinition` (co_write, plan_forge) |
| PLAN | size-class → phase plan | agent `ActivePlan` on `working_memory` |
| MONITOR | RUN-STATE file · the *"TodoWrite hasn't been used recently"* nag | pending-step re-inject (the nag), §8 |
| CONTROL | `workflow-gate.py` state-machine · pre-commit rule-hooks · the `/goal` Stop-gate | effect-probe gate · the `Stop` refuse-to-yield, §8 |

**The insight that makes the product version STRONGER:** `/goal`'s evaluator *"reads the transcript
only — it cannot run commands or read files"* (WORKFLOW.md, verbatim), so it enforces **persistence,
not honesty** — a model *claiming* a check passed satisfies it. The product agent-governance **runs the
effect-probe** (a real DB query), so it verifies the **effect**, not the claim. S06 is exactly the case
`/goal` would wave through (*"I've set up the plan"* with `structure_node=0`) and the effect-probe
catches. ⇒ We port the vocabulary and the mental model, and we CLOSE the honesty gap the meta-level
tool cannot. (Conversely: the SESSION tooling could adopt effect-probes too — a future cross-pollination
row, out of scope here.)

---

## 12 · Edge cases (for the review + plan)

| # | Edge case | Handling |
|---|---|---|
| **EC-1** | **False-done** — model marks `compile` done, effect=0 | GOV-4: `PostToolUse`/`Stop` probe overrides to pending. THE core case. |
| **EC-2** | **Async effect** — `mode="llm"` propose returns a job; `spec_ready` not immediate (OQ-6) | A distinct `in_flight` sub-state: the step is not done AND not re-promptable-as-skipped; MONITOR shows *"waiting for the propose job"*; CONTROL gates on the job's terminal state, not wall-clock. Do NOT re-prompt a step that is legitimately in flight (that is the `worker-loop-cancel-clobber` class). |
| **EC-3** | **User abandons the workflow** (*"forget the plan, just write"*) | §8: the `Stop` gate checks residual intent; an explicit abandon RELEASES it. Governance serves, not imprisons. |
| **EC-4** | **Re-prompt loop** — the model can't complete a step (a real backend error) | GOV-7: N attempts → stop, surface honestly (*"I couldn't compile — <observed error>"*), release. A runaway enforcer is itself a bug (`hard-stop after 3`). |
| **EC-5** | **Probe flakiness** — the effect-probe itself errors (service down) | Absent ≠ unsatisfied. A probe that cannot RUN returns `unknown`, not `false` — CONTROL does NOT re-prompt on `unknown` (that would punish a book-service outage), it degrades to advisory + warns. The `silent-success-is-a-bug` law's mirror: a silent FAILURE-to-verify must not read as "not done". |
| **EC-6** | **Compaction mid-workflow** | `PreCompact` + GOV-2: the `ActivePlan` is on `working_memory`, which survives; the nag rehydrates it on the next turn. |
| **EC-7** | **Concurrent / nested workflows** — the agent plans B while A is pending | one-in-progress is per-STEP, not per-workflow; the ActivePlan holds a small stack; MONITOR nags the top-of-stack. (Deep nesting is a smell — cap it.) |
| **EC-8** | **A step with no cheap effect** (genuinely semantic — "the prose matches the author's voice") | `required_effect: null` (advisory) OR an opt-in LLM-check effect (GOV-4) — used sparingly, since it costs a turn. Most steps have a cheap structural effect; reserve the LLM check. |
| **EC-9** | **Per-turn cost** (OQ-5) | MONITOR nag = only pending steps (tens of tokens); CONTROL probe = one cached cheap query per advanced step. Measured at P0; budgeted (07S §1). |
| **EC-10** | **Agent games the probe** — calls a no-op that flips the effect without real work | The probe reads the REAL effect (structure_node rows), which a no-op cannot fabricate — that is the whole point of effect-over-claim. A probe that CAN be gamed is a mis-designed probe (probe the durable truth, not a transient flag — `reconcile-by-truth-mirror-producer-predicate`). |

---

## 13 · Where this sits in the AI-native platform

The platform already has the **generative** and **grounding** layers — session management, prompt
engineering, context engineering, session compaction, knowledge grounding, LLM-as-judge. Those make the
agent *capable* and *informed*. **What was missing is the layer that makes a multi-step capability
actually COMPLETE reliably** — the control loop that turns a workflow *definition* into a workflow
*outcome*. That is this governance layer. In the 2026 AI-agent-governance stack's terms, the platform had
the *policy/context* and *observability* pieces; this adds the **runtime-enforcement** piece and the
**plan-lifecycle** piece — the two that, per Gartner, half of 2030's agent failures will trace back to.
It is the missing pillar, and it is why a strong model *and* a weak model both need it.

---

## Appendix A — industry sources (the research this spec rests on)

- **Todo-list / plan-persistence** (the MONITOR pillar): Claude Code Todos/Tasks (persist across
  compaction, multi-session), *"How agents plan with to-do lists"* (salience decay / lost-in-the-middle),
  Spring-AI *"why your agent forgets tasks"*, LangChain deepagents todo.
- **Enforcement / verifier** (the CONTROL pillar): Claude Code hooks (PostToolUse feedback-inject, Stop
  exit-2 completion gate), Kiro steering-files + agent-hooks, PolicyGuard (dialogue-grounded sub-agent
  verifier), the deep-research Verifier (rule-based + LLM, replan-on-fail).
- **Governance model** (the 4 pillars): BPM process-governance lifecycle (model→execute→monitor→
  control/improve), 2026 AI-agent-governance stacks (policy · lifecycle · runtime-enforcement ·
  observability), agentic-workflow governance checklists.
