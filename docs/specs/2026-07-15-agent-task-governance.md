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

## 7 · Open questions (for CLARIFY)

- **OQ-1** Where does CONTROL run — a `PostToolUse`-style hook after each tool, a per-turn checkpoint,
  or a `Stop`-style gate before the agent yields the turn? (Industry uses all three; likely per-turn
  checkpoint + a yield gate. `agent-gui-loop-needs-live-browser-smoke` cousin: prove by effect.)
- **OQ-2** The effect-probe registry's home — chat-service (calls composition/book) vs. a probe MCP each
  domain owns. Leaning: **domain owns its probes** (composition owns `linked_structure`), chat-service
  federates — mirrors the MCP-first + provider-gateway invariants.
- **OQ-3** Agent-self-defined effects: how tightly closed is the set? A pure enum is safest; a
  parameterised probe (`linked_structure(book_id)`) needs typed args (IN-3 enum discipline).
- **OQ-4** Interaction with the existing `/goal` + workflow-gate (this repo's OWN governance for the
  human-agent loop) — is the agent-governance a scaled-down sibling? Reuse vocabulary.
- **OQ-5** Cost: MONITOR re-inject + CONTROL probes add per-turn work. Budget it (07S §1); the probe is
  one cheap query, the nag is a few tokens — but measure, don't assume (`m3-pullmode-measured-nogo`).

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
