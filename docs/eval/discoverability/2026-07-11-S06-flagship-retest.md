# S06 FLAGSHIP re-test — the go/no-go · gemma-4-26b-a4b-qat

**Date:** 2026-07-11 · HEAD `30a1fdb1a` (all of: silent-success fix, book_id injection, WS-5 workflow rail
+ steering directive, cross-turn activation fix, review-impl fixes) · services rebuilt.
**Fixture:** a **fresh, empty** book `019f51ae-…` (0 kinds / 0 entities / 0 chapters — origin from nothing).
**Pass:** warm + `QG_SIM_AUTORENDER=1` (real-GUI faithful). **Run:** [`runs/2026-07-11-S06-flagship-retest/`](runs/2026-07-11-S06-flagship-retest/).

## Verdict: ❌ — the flagship still does not ship. But the failure MOVED again, and it says exactly what to build next.

**Ground truth after all 17 turns** (the flagship's own test: open the book and look):

| The flagship promises | Exists? |
|---|---|
| world structure (categories) | **0 kinds** ❌ |
| the cast + key terms | **0 entities** ❌ |
| how everyone connects | **0 knowledge projects** ❌ |
| a readable chapter/arc plan | **1 plan_run → 5 artifacts** (a real 6.3 KB NovelSystemSpec) ✅ |
| a drafted + revised opening | **0 chapters** ❌ |

One of five. **16 of 17 turns called ZERO tools.** The single tool-calling turn produced the plan.

## What actually happened (and why it matters)

At **turn 7** the user says **"yeah do it"** — assenting to the *assistant's own offer* to "set up your world so
I keep all this straight for you — categories like Characters, Sects, Cultivation Systems…". The agent then:

```
find_tools(intent="plan_propose_spec")      → found the planner by name
plan_propose_spec(book_id, mode="llm", …)   → fired PlanForge, async job
```

It **never called `workflow_list` / `workflow_load`** — even though `glossary-bootstrap` was advertised, the
steering directive was injected, and that workflow is *exactly* the rail for the thing it had just offered.
It reached past the rail for a flashier tool it found by name, and skipped the world, the cast, the
connections, and the draft entirely.

### The root cause: the rail fires on a REQUEST, not on an ASSENT to the agent's own offer

- **S01 passes** because the user says it outright: *"Help me set up the world info for this book."* → the
  agent matches the request to `glossary-bootstrap` and follows it.
- **S06 fails** because the user only says *"yeah do it."* The assent refers to an offer **the assistant made
  in its own words** several turns earlier. To use the rail the agent must (a) still be holding its own offer
  and (b) map the assent onto a workflow. It does neither — it improvises.

**This is the flagship's core shape** (the assistant proposes, the user says yes), so the rail misses precisely
where the flagship needs it most. Authoring more workflows will not fix this by itself.

### A NEW failure the baseline never had: the machinery leaks

Because the agent reached a tool **without a rail owning the vocabulary**, it narrated the internals to the
user. Counted in the transcript, said *to the user*:

> **PlanForge ×27 · Spec ×24 · glossary ×16 · ontology ×5 · NovelSystemSpec ×4**

e.g. turn 7: *"I've kicked off the **PlanForge** engine… running a deep analysis to turn your words into a
formal, structured **NovelSystemSpec**."* — and turn 16: *"Since you've approved the **PlanForge Spec**, we are
moving into the **Worldbuilding/Ontology** phase. We need to build the **Glossary**."*

Every one of those is a §1 word the persona must **never** be required to know — an automatic scenario failure.
The baseline never leaked them **because it never called a tool**. This is strong, concrete confirmation of the
WS-5 thesis: **`notes_md` on a workflow is what keeps the machinery out of the user's face.** No rail ⇒ the
agent describes its own plumbing.

## Per-movement checkpoint (§11)

| Movement | goal-achieved | no-rescue | no-thrash | honest | canon-intact |
|---|---|---|---|---|---|
| **A** find the wound | ✅ (conversational) | ✅ | ✅ | ✅ | ✅ |
| **B** find the spine | ✅ (conversational) | ✅ | ✅ | ✅ | ✅ |
| **C** world structure | ❌ 0 kinds — fired the *planner* instead | ❌ **jargon** (PlanForge/NovelSystemSpec) | ✅ | ⚠️ async job never polled | ✅ |
| **D** cast + connections | ❌ 0 entities, 0 projects | ✅ | ✅ | ✅ (claims nothing) | ✅ |
| **E** arc plan | ✅ **a real spec exists** | ❌ jargon ("Spec", "PlanForge") | ✅ | ⚠️ never polled the job | ✅ |
| **F** draft + revise | ❌ 0 chapters (prose only in chat) | ✅ | ✅ | ✅ | ✅ |

**Story-craft remains excellent.** It caught the specifics (the "Tragedy of Erasure", the same-soul callback,
"he loved her and spent her anyway"), never flattened the premise, and canon held across all 17 turns.

## Instrumented (§10)

| Metric | Value |
|---|---|
| empty-intent `find_tools` | **0** ✅ |
| discovery calls | **1** ✅ (no loop — the original north-star failure is dead) |
| thrash / silent-success / commit-failed / unresolved | **0 / 0 / 0 / 0** ✅ |
| effectful (persisting) calls | **1** |
| **async jobs without a status-read** | **1** ❌ (fired the plan, never polled it) |
| false-persistence claims | 0 ✅ |
| wall-clock | 202 s (max turn 21 s) — fast, never stalled |

## Delta vs the 2026-07-09 baseline

| | baseline | now |
|---|---|---|
| tools called | **0** | 2 (find_tools → plan_propose_spec) |
| anything persisted | **nothing** | a real arc-plan spec (5 artifacts) |
| false-"done" claims | **2** | 0 |
| discovery loop | none | none |
| jargon to the user | none *(it did nothing)* | **severe** (PlanForge ×27, …) |

Real progress — it now persists something and stopped lying — but it is **further from shippable than the
one-artifact score suggests**, because the jargon leak alone fails the persona.

## What must be built next (ranked, evidence-backed)

1. **Bind the assistant's own offer to a workflow (the assent gap).** The single highest-leverage fix. When the
   agent offers to do something a workflow covers, it must *run that workflow on assent* — not improvise. Two
   candidate mechanisms: (a) extend the steering directive so an OFFER must name the workflow it will run, and a
   user's assent triggers `workflow_load(slug)`; (b) **WS-3 mode→capability binding** — pin the co-writer
   workflow set for a `write`-mode book session so the whole flagship runs on one rail. WS-3 is the umbrella's
   own answer and now has direct evidence.
2. **A `vision-to-book` flagship workflow (W6)** whose steps ARE movements C→F, so one rail covers world → cast →
   connections → plan → draft, with `notes_md` owning the vocabulary (which also kills the jargon leak).
3. **Async honesty as a structural guard.** The plan job was fired and never polled (it happened to succeed).
   The runner must mark an async step pending and gate any completion claim on an observed terminal status.
4. **W2 (cast capture) and W4 (connections)** — still unauthored; movements D/C′ cannot land without them.

## Bottom line

The mechanism now works when the user *asks* (S01 ✅, S02 ✅, S03 ✅). The flagship fails because a user who is
just *talking about their story* never asks — they assent. **The next unlock is not another tool; it is binding
the rail to the conversation** (WS-3 / a flagship workflow), so the assistant's own offer is a workflow it then
runs.
