# FRONTEND JOURNEY LOOP — one journey, driven by a real model, through the real UI

*Successor to [`2026-08-10-toolv2-loop-RUNBOOK.md`](2026-08-10-toolv2-loop-RUNBOOK.md), which closed
2026-08-12 at 319 of 319 tools concluded.*

---

## Why this loop exists, stated as the thing the last one could not do

The tool loop proved each tool works **when called correctly, with correct arguments, in isolation,
by me.** Every LIVE leg was a hand-built JSON-RPC call. That is a real bar and it found real
defects — but it is structurally blind to the four failure classes that dominate the recorded
corpus.

The board's own audit: **4,175 recorded failures, 88.1% are a missing declaration on the tool** —
repeat semantics 48.8%, typed params 16.8%, argument supplier 14.1%, preconditions 8.4%. Not one of
those four can occur when I write the arguments myself. They require a **model** deciding which tool
to call and inventing the arguments from prose.

So this loop changes exactly one thing, and it is the thing that matters:

> **The tool loop asked "does this tool work?". This loop asks "can the product be used?"**

A journey is driven end to end **by the model, through the browser**, with nothing hand-fed.

---

## The iteration unit is a JOURNEY, not a tool

A journey is one natural-language intent a real user would type, carried to a finished outcome. It
is concluded when it is `proven` or `blocked` — never `works mostly`, never `known issue`.

**A journey must cross at least two modules.** A single-module journey is a tool test with extra
steps, and the tool loop already ran 319 of those.

---

## The denominator, derived from SSOT and never typed

The product **declares** its journeys. They are rows, not opinions:

| source | published | where it surfaces |
|---|---|---|
| `workflows` (`loreweave_agent_registry`) | **12** | `{book,editor}` 5 · `{book,editor,studio}` 4 · `{book}` 1 · unrestricted 2 |
| `skills` | **27** | `{chat}` 13 · `{chat,compose}` 5 · unrestricted 9 |
| `slash_commands` · `subagent_defs` · `mode_bindings` | 1 · 1 · 2 | chat surface |

Re-derive these counts at entry with a query, **never from this table.** The tool loop's hardest
recurring lesson was that a self-derived total always reads "done"; a table in a RUNBOOK is a
self-derived total the moment the registry moves.

**Ordering:** a workflow before a skill (a workflow is a multi-step state machine and fails in more
ways), and within each, the surface with the most declared members first — `{book,editor}`.

---

## The three legs, adapted. All three still required.

| leg | tool loop | this loop |
|---|---|---|
| **CODE** | tests + a falsifier proven RED on the original defect | **unchanged** |
| **LIVE** | a hand-built JSON-RPC call through the deployed image | 🔴 **the journey completed through the BROWSER, driven by the model, with no argument I supplied** |
| **DATA** | measured state from SSOT + an explicit falsifier | **unchanged** |

**The LIVE leg is the whole point and it has a hard rule: if I type a tool argument, the journey is
not proven.** The model derives every argument from the prose, or the journey has failed and the
defect is that it could not.

### The run configuration, fixed at entry

| | |
|---|---|
| model | `google/gemma-4-26b-a4b-qat` via `lm_studio` — **already this account's `chat` default and active**, verified in `user_default_models`, not set for the run |
| frontend | `infra-frontend-1` → `http://localhost:5174` |
| driver | Playwright / chrome-devtools MCP — a real browser, not an HTTP client |
| content | **create freely.** This is the dev environment; the throwaway-book rule from the tool loop is explicitly LIFTED here, by decision 2026-08-12. Journeys need books with real history to mean anything |
| account | `019d5e3c-7cc5-7e6a-8b27-1344e148bf7c` |

**Why the model choice is load-bearing:** a weak local model is the point. A journey that only works
on a frontier model is a journey that does not work — the platform's own recorded failures come from
this class of model, and CP-3's V-METRIC already measured where its carrier breaks (d=4).

---

## The six phases of one iteration

1. **READ** the declared journey — the workflow's steps or the skill's body — and state, before
   touching anything, what the model would have to *decide* and what it would have to *derive*.
2. **RUN** it through the browser in natural language. Type what a user would type. Nothing else.
3. **OBSERVE** every seam: which tool was chosen, what arguments were built, what the FE rendered,
   what the state machine did on the step boundary, what the confirm card said.
4. **DIAGNOSE** the first real defect. Fix it where it lives — including in another service, the FE,
   a skill body, a workflow definition, or a tool description.
5. **PROVE** all three legs. The falsifier must be red on the ORIGINAL defect.
6. **CONCLUDE** in the ledger — `proven` or `blocked`, with the evidence and an honest outcome.

---

## 🔴 ONE DEFECT, ONE CYCLE. NEVER BATCH.

**A journey is how a defect is FOUND. It is not the unit of work for fixing one.**

When a journey surfaces three defects across three tools, that is **three cycles**, each run to
completion on its own: test → find → investigate → fix → prove all three legs → conclude → commit.
Not one investigation, not one fix, not one commit covering three.

**I have already broken this rule and it is why the rule is written here.** In tool-loop #311 I was
proving `world_map_get`, found a `world_delete` defect (a cascade dropping map rows and keeping their
blobs), and folded the fix into the same iteration. Both were real and both were proven — but they
went in as **one** commit, under **one** ledger row, for **two** different tools. The second defect
has no row of its own, and the only reason it is findable is a sentence inside the first one's note.

| what batching costs | why it matters here |
|---|---|
| the second defect has no ledger row | the ledger is the progress authority; a defect not in it did not happen |
| one falsifier is asked to cover two mechanisms | the tool loop's most repeated failure was the half-fix — a shared guard is how a half-fix hides |
| a bisect lands on a commit that changed two things | the diagnosis is no longer separable from the fix |
| "investigated together" quietly becomes "assumed the same cause" | two defects in one journey are usually **not** one root cause |

**The rule, stated so it can be checked:** every defect gets its own ledger row, its own falsifier
proven red on **its own** original defect, and its own commit. A journey's row records what the
journey did; each defect it surfaced links to a row of its own.

**The one exception, and it is narrow:** a single mechanism present at several sites is ONE defect
and must be fixed at every site in one cycle — that is the half-fix rule, and splitting it is the
opposite mistake. The test is whether one falsifier, injected at any one site, reds the guard for
all of them. If yes it is one defect at N sites. If no it is N defects.

---

## Rules inherited from the tool loop, each already paid for

These are not restated as advice. Each cost an iteration to learn.

- **Never type a denominator.** Every count comes from a query or a live measurement.
- **A guard never proven RED is decoration.** Inject the original defect and watch it fail.
- **Fix every site of the mechanism, by name.** The half-fix was the tool loop's most repeated
  mistake — five times, twice in the same file.
- **CODE alone is not the bar.** #315: a string-built SQL statement broke every rename while
  `go build`, the full suite, and the new static guards all passed.
- **Read the schema before the first call**, and the column names before the first query.
- **Check the control before filing.** A dozen apparent defects in the tool loop were correct
  behaviour; the check that refutes your own claim is the cheap one.
- **An unverified starting state is not evidence.** Confirm the row before you act on what it means.
- **Defer, record, continue.** A product decision that blocks the current journey lands in the DQ
  list with its evidence, and the loop moves on. An unresolved question is not permission to stop.

---

## What this loop can see that the last one could not

Recorded here so a finding can be classified rather than described:

| class | the question it answers |
|---|---|
| **selection** | did the model pick the right tool from prose? |
| **derivation** | did it build arguments it was never handed? |
| **chaining** | did output A survive as input B across a module boundary? |
| **composition** | do skill + workflow + state machine agree on whose turn it is? |
| **surfacing** | did the FE render the result, and is what it rendered true? |
| **recovery** | after a refusal, did the model have a next move that worked? |

The tool loop could only ever see the last two, and only when I set them up by hand.

---

## Stop condition

**The loop ends when every declared journey — re-derived from the registry at entry — is `proven`
or `blocked`.** Not when the model gets better. Not when the list looks done.

`converted`, `tested`, `investigated`, "mostly works", "known issue" are **not** terminal.

---

## Deferred questions

Carried forward from the tool loop: **DQ-1 → DQ-29**, all but DQ-26 still open, in
[`2026-08-10-toolv2-loop-RUNBOOK.md`](2026-08-10-toolv2-loop-RUNBOOK.md). New ones continue the
numbering from **DQ-30**.

---

## Ledger

`contracts/frontend-journey-ledger.json` — created at first conclusion, same shape as the tool
ledger: one row per journey, `state` ∈ {`proven`, `blocked`}, the note carrying the evidence.
**The ledger is the progress authority. This file is a plan; it is never the record.**
