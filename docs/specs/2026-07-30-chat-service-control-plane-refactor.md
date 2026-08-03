# chat-service: the control plane needs an architecture (D-CHAT-CONTROL-PLANE)

**Status:** DEFERRED — gate #2 (large / structural). Written 2026-07-30 from a live dogfood.
**Trigger to do it:** before the next feature that adds a *control* mechanism to the turn loop.
**Debt tracked in:** [`2026-08-03-glossary-kg-entity-refactor/DEBT-REGISTER.md` §B](2026-08-03-glossary-kg-entity-refactor/DEBT-REGISTER.md#b--chat-service-control-plane--d-chat-control-plane)
— 7 open items, ids `2026-07-30-01` … `2026-08-03-07`. Nothing in §3 has been built; the trigger
above has **not** fired (verified 2026-08-03), and it is **prose-only** — no gate can see it.

---

## 1. What happened, exactly

A real-user run of the co-writer on a brand-new book. The author asks it to set up the book's
categories. The model reasons **correctly**, identifies **the right tool**, and then emits
**40,597 characters of one repeated paragraph** until the author hits Stop.

The tool it wanted was `glossary_adopt_standards`. Two mechanisms, each individually correct,
had made that impossible:

| Mechanism | What it does | Why it's right |
|---|---|---|
| **N5a-FULL capability floor** (`filter_intent_gated_setup_tools`) | removes high-impact ontology tools from the turn catalog — *"un-seeded, un-findable, AND un-loadable"* | stops the co-writer rebuilding a newcomer's world on an unrelated "write chapter 1" turn |
| **`vision-to-book` rail** | renders an ordered recipe into the prompt, **by tool name**, and computes `next=glossary_adopt_standards` | a mid-tier model cannot reconstruct the right order unaided |

One says *"call this tool"*. The other says *"this tool does not exist"*. Nothing in the system
noticed they disagreed, because **nothing in the system is responsible for noticing**.

Three more mechanisms that exist to catch exactly this all missed:

- **`D-RAIL-NEXT-STEP-EXEMPT`** — budget-exempts the rail's next-step tool. Computed **once, at
  turn start**. The rail advanced mid-turn (0/9 → 1/9); the exemption still pointed at the
  finished step.
- **The step-runner** (`decide_rail_drive` + `[SYSTEM DIRECTIVE]` injection) — the thing that
  would have re-steered the model. It only fires once *"a rail step tool actually succeeded this
  turn — the model chose to start it"*, so it cannot rescue a model that **cannot** start.
- **`ReasoningLoopDetector`** — `max_period=4` segments. The repeating block was ~10 segments, so
  a period-10 cycle is out of range. It is tuned for the short *"Actually…/Wait…"* oscillation.

## 2. The shape of the problem

`stream_service.py` is **7,074 lines**, 42 functions, and carries **at least 16 independent
caps/breakers/gates**:

```
BLANK_TOOL_ARGS_CAP · IDEMPOTENT_NOOP_WRITE_CAP · MAX_TOOL_ITERATIONS
PLANNER_CALLS_PER_TURN_CAP · RAIL_REDRIVE_CAP · REASONING_LOOP_INTERVENTION_CAP
REPEAT_READ_CAP · REPEATED_FAILURE_CAP · TIER_A_AGGREGATE_CAP · TIER_A_SAME_OP_CAP
TOOL_LIST_CATEGORY_CAP · TOOL_LIST_TOTAL_CAP · GLOSSARY_TOOL_ITERATIONS
UNIVERSAL_TOOL_ITERATIONS · EXECUTIVE_EVERY_N_TURNS · EXECUTIVE_TURN_WINDOW
```
plus four Gemma-specific wire-repair regexes.

**Size is not the defect.** Every one of these was added for a real, measured incident — the
comments say so (*"live incident"*, *"measured"*, *"the S06 fix"*, *"Mị Đế dogfood"*). Each is
individually justified and individually tested.

The defect is that they were **accreted, never composed**. There is no shared lifecycle, so:

- each guard reads its own slice of state, **at its own moment** (turn start vs. mid-turn);
- precedence between guards is implicit in *code order across 7,000 lines*;
- no guard declares what it removes, so the next one cannot know what it broke.

That is the honest answer to *"is the architecture broken, or did it never exist?"* — for the
turn loop specifically, **it never existed**. What exists is a very well-documented pile of
correct patches.

## 3. What to build

### A. A tool-availability SSOT — *the one the author asked for first*

Today, "is this tool available, and if not, why?" is answered independently by **eight** places:
`hot_tool_names`, `filter_intent_gated_setup_tools`, `budget_rail_tools`,
`budget_names_by_tokens`, `merge_activated_tools`, the action gate (`done_suppress`), the
repeated-failure de-advertiser, and (as of tonight) the auto-load guard.

Nobody can answer *"why is tool X not on the wire?"* without reading all eight — which is
literally how this investigation was spent.

```
availability(name, turn) -> Available
                          | Withheld(stage="capability_floor", reason=…, unlock=…)
                          | Budgeted(stage="rail_budget", …)
                          | NotFound
```

Every filter registers as a **named stage**. Three things fall out immediately:

1. the model's error message can say **why**, and what would unlock it (tonight's fix hand-rolls
   exactly this for one case);
2. a test can assert a cross-mechanism invariant — *"for every step of a pinned rail,
   availability is never `Withheld`"* — which is the check that would have caught this class on
   the day it was introduced;
3. debugging is one call instead of eight greps.

### B. A `TurnState` — one owner of "what is true right now"

A single record: rail progress + step cursor, active tool names, breaker counters, iteration
budget, permission mode. Recomputed at **defined lifecycle points** (turn start; after each tool
result), never ad hoc. The mid-turn staleness bug is not fixable by patching
`D-RAIL-NEXT-STEP-EXEMPT` — it is structural, and it will come back under a different name until
there is one place that knows the rail moved.

### C. Guards become policies over `TurnState`

`policy(state) -> Decision(allow | block | steer(directive))`, evaluated in **one** place with
**logged precedence**. The 16 caps stay — they are earned — but they stop being 16 `if` blocks
scattered through a 7,000-line function.

### D. Cross-mechanism invariant tests — the actually-missing net

Every mechanism has unit tests **for itself**. Nothing tests the mechanisms **against each
other**, which is why a contradiction survived. Minimum set:

- every pinned rail's step tools are reachable (not withheld, not budgeted out) — **this is the
  test that fails today**;
- no gate removes a tool another gate requires;
- an unsatisfiable state always yields an honest message, never a silent retry.

### E. The anti-rot rule (the answer to *"how do we stop this recurring?"*)

> **A new control mechanism must declare what it blocks, register as an availability stage, and
> add the invariant it must not violate.**

This is the same rule this repo already applies elsewhere and that works: *rule + SSOT + gate +
test*. The provider-gateway invariant holds because `ai-provider-gate.py` fails the commit. The
reasoning wire-fields SSOT holds because an AST gate reds on a re-introduced copy. The turn loop
has the rules written in comments and **no gate at all** — so each new feature silently pays for
the last one.

## 4. Scope note

This is a refactor of `chat-service`'s turn loop only. It touches no contract, no schema, and no
other service. It is deferred because it is genuinely structural — not because it is optional:
every hour spent chasing "why did the agent do nothing" is paid out of this debt.

**Interim (shipped 2026-07-30, not a substitute):** the rail's step tools are exempt from the
capability floor; an off-surface-but-real tool auto-loads; a withheld tool and an invented tool
get *different*, honest messages; the rail re-arms its step tools when it advances mid-turn.

## 5. Second confirmation, unrelated trigger (same day)

§1 said the step-runner *"cannot rescue a model that cannot start"*. That sentence described a
capability-floor collision. Hours later the identical hole fired on a **wire-level** fault with
nothing to do with the control plane: Gemma concatenated two tool calls into one `arguments`
payload, `repair_json` absorbed the control tokens into a string value and returned
**parseable-but-wrong** JSON, the tool rejected an enum value the model never wrote, every call
in the iteration failed — so `turn_succeeded` stayed empty, the driver stayed silent, and the
turn became 10,882 characters of prose.

Fixed at the wire (`D-TOOLCALL-GEMMA-INTERIOR-LEAK`: split instead of swallow, a post-condition
that refuses a disguised repair, an honest decoder-fault error before the frontend/backend fork)
and at the seam (`D-RAIL-INFLIGHT-ON-ATTEMPT`: an *attempted* step tool counts as in flight,
extracted into a named `_rail_is_in_flight` policy rather than an inline expression — a small
down-payment on §C).

Two things this sharpens for whoever does the refactor:

1. **`in_flight` was the single highest-leverage predicate in the loop.** Two incidents, two
   layers, one wrong definition. Under §B it becomes a `TurnState` field with one owner instead
   of an expression re-derived at one call site.
2. **A repair layer needs a post-condition, not just a best effort.** §A/§C are about *gates*
   that remove things; this is a *transform* that can silently produce a wrong result. The
   anti-rot rule in §E should cover both: **a mechanism that transforms a payload must be able
   to say it failed** — "repaired into something that parses" is not success.

The three incidents were in three different layers (gate contradiction · tool surface · wire
corruption) and presented identically, because the turn loop has exactly one way to fail
outward: the model talks in circles. Until §A/§B/§D exist, *every* defect anywhere upstream
arrives wearing that costume, and each one costs a live debugging session to un-mask.
