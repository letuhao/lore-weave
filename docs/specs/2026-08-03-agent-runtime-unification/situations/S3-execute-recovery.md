# S3 · EXECUTION + RECOVERY — coverage interrogation

**Module:** running a plan's steps, and what happens when one fails.
**Against:** `ARCHITECTURE.md` §0.5 (recovery) · §0.4 (plan ≠ execution) · §0.3 (Ceiling Test) · §0.1 (narrow-never-invent).
**Mode:** coverage, not critique. Two questions: *what does each scope exist to solve* and *what will certainly
occur that recovery has no defined answer for.*

**Method.** Read the real machinery, not the design's description of it:
`services/chat-service/app/services/stream_service.py` (7818 lines — the six breakers, the tool loop, the
suspend/resume path, cancellation), `app/db/suspended_runs.py`, `app/db/tool_call_history.py`,
`app/services/reasoning_loop_detector.py`, `app/services/workflow_runner.py`, `app/services/tool_plan.py`,
`app/services/subagent_runtime.py`, `sdks/python/loreweave_agent_control/rail.py`,
`services/glossary-service/internal/api/action_confirm.go`, `services/book-service/internal/api/mcp_tools_write.go`,
`services/chat-service/app/routers/messages.py`.

---

## 1 · What each recovery scope exists to solve, with repo evidence

### The baseline this is measured against

The repo's workflow primitive — the one place a plan exists as data — has exactly **one** recovery policy,
and it is a prose sentence emitted into every rail:

> `workflow_runner.py:206-208` — *"If a step fails, STOP — report which steps completed and which did not; do
> not claim the workflow finished."*

That is a **stop**, shipped, in every pinned rail, which is precisely what §0.5 forbids
(*"a guardrail's output must be a PLAN STATE TRANSITION, not a stop"*). The four scopes exist to replace this
one sentence. Everything below is the evidence that each of the four is a real, occurring situation.

---

### 1.1 `step-local` — the call failed; the step is still right

**Exists to solve:** a transient or repairable call failure where re-issuing with *different* arguments is the
correct next act, and blind identical re-issue is the pathology.

**Evidence it occurs, and that the distinction is already load-bearing:**

| evidence | where | what it shows |
|---|---|---|
| `REPEATED_FAILURE_CAP = 2` | `stream_service.py:536-546` | measured live: `book_get_chapter` ×13 on one identical error; `book_update_details` ×16 on *"no fields to update"* |
| the key is `(tool, EXACT args)` | same | *"a failed call with FIXED args is legitimate… only an IDENTICAL repeat is the loop; a retry with different args gets a fresh key and runs"* — the repo **already implements** step-local-retry-if-modified. It just has no name for it |
| `book_get_chapter` ×19, nineteen invented ids | `ARCHITECTURE.md` §0.5 table | the model *was* doing step-local retry. It could not do it correctly because it was told *"wrong"* and never *"wrong where"* (C-12) |
| 74% byte-identical repeat calls | §0.5 | the failure mode step-local exists to bound |

**Verdict: well-evidenced.** The scope is real and half-built.

---

### 1.2 `binding-invalid` — a value bound from an earlier step's `emits` is wrong or stale

**Exists to solve:** the 61.8% class. The model is asked to re-supply an identifier it already received, the
conversation is a lossy carrier, and it invents one.

**Evidence it occurs:**

- §2's measurement: **2,477 / 4,010 failures (61.8%) on a tool that already SUCCEEDED in the same session**.
  Session `019faf5b`: `glossary_propose_entities` returns `entity_id:019fafa2-…` at step 12; at step 16 the
  model sends `entity_id:"0"`.
- RT3 measured the carrier: pin-blind `LIMIT 50` window, tool results evicted beyond the newest 3, arguments
  dropped by the transcript renderer.
- The repo already reconstructs "what actually completed" from the **server's** record rather than the model's:
  `tool_call_history.succeeded_tool_counts()` (a COUNT, not a set — *"a set would mark the later step done the
  moment the earlier one succeeded"*) and `rail.compute_rail_progress()` which outranks the call log with the
  **book-state artifact** wherever one exists. That is ~80% of the replan input §0.5 asks for, already built.

**Verdict: the strongest-evidenced scope, and the one with the most existing scaffolding.** See M2 — the
prescribed *remedy* is where the gap is.

---

### 1.3 `plan-invalid` — the plan's premise is false

**Exists to solve:** the world does not match the plan. The thing does not exist, permission is refused, or the
plan was authored against a surface that has changed.

**Evidence it occurs:**

- **12 rails point at 30 dead tools, behind a gate that fails open** (§4 C-11, §3 M5). A plan whose steps name
  unresolvable declarations is plan-invalid *at load time*, and today it loads.
- `workflow_load_result()` returns `{"not_found": slug, "reason": "no workflow '…'"}`
  (`workflow_runner.py:170-175`) — a plan-invalid outcome with no transition attached; the model gets prose.
- `pinned_rail_block()` silently `continue`s past a slug that resolves to nothing (`workflow_runner.py:294-295`).
  The rail block renders *without* that rail and says nothing — a plan-invalid condition delivered as an absence.
- Rail-notes truncation at `NOTES_CHAR_CAP`: measured 2026-07-11, the flagship rail's tail was cut and the tail
  was the honesty rules (`workflow_runner.py:241-246`). A plan can be *partially* invalid and still look whole.

**Verdict: well-evidenced,** and notably the evidence is mostly about plan-invalidity that is never *detected*,
not plan-invalidity that is mishandled.

---

### 1.4 `needs-human` — the ambiguity cannot be resolved from anything available

**Exists to solve:** the model has nothing left to reason from, and the correct behaviour is to ask.

**Evidence the machinery exists and the reason to enter it does not** (§0.5's own claim, verified):

- `chat_suspended_runs` (`db/migrate.py:308-333`): full `working` conversation, `pending_tool_call`, usage,
  `permission_mode`, `pinned_step_tools`, `book_id`, 6h `expires_at`. Owner-scoped load/delete.
- `finish_reason='awaiting_input'` is persisted as a **visible, non-badged** message
  (`stream_service.py:6670-6678`): *"shows NO failure badge (the card itself is the affordance)"*. The design's
  *"asking the user is a SUCCESS state"* is already true in the persistence layer.
- Entry points, exhaustively: a frontend-tool call, a `tool_approval` card, and an ext-task durable gate
  (`stream_service.py:7237-7247`). **Confirmed: no path from "the model is stuck" to a suspend, and no MCP
  `elicitation` anywhere in the repo.**

**Verdict: the expensive half is built; §0.5's reading is correct.** The gaps are in *expiry* (M4) and in
*what the human is told about work already committed* (M1).

---

## 2 · What the design DOES answer

Recorded so the findings below are not read as a claim that nothing is covered.

| situation | answered by | note |
|---|---|---|
| replan loses completed work | §0.5: replan input = plan + completed steps + emitted values + failure | and `succeeded_tool_counts` + `compute_rail_progress` already produce it server-side |
| contaminated retry | same (R11) — the failed *conversation* is not the replan input | consequence of the structure, not a bolted-on rule |
| the model can't tell *where* it went wrong | C-12 fault locus + the drop-then-blame corollary | closes the `book_get_chapter` ×19 shape |
| our prose counted as tool failure | §5.3 `source ∈ {tool, breaker, meta}` | closes the 65.7% |
| a plan dying silently | the invariant: *no plan may terminate except by `done_when` or a human* | the strongest sentence in §0.5 |
| simple replan runaway | replan budget stated **in the plan**, visible, exhausting → needs-human | see M5 for the shape it does not cover |

---

## 3 · MISSING — situations that will certainly occur with no defined answer

Ranked: **data corruption > lost work > loop > cost.** Each carries a Ceiling Test verdict, because a recovery
mechanism is exactly the kind of thing that becomes a ceiling by accident.

---

### M1 · The side effect already happened, and no scope mentions the world *(data corruption)*

**The situation.** Step 3 of 5 wrote to the database. Step 4 fails, scope is `plan-invalid`, we replan. Who
un-does step 3? §0.5's four transitions are *retry / re-run the producer / replan / suspend*. **Not one of them
says anything about state already committed.** "Replan" is defined purely as a control-flow act.

**Why it is certain.** Every rail in the repo is a write sequence. The flagship `vision-to-book` rail is 11-12
steps: adopt categories → **apply** (creates glossary kinds) → capture cast → **save cast** (creates entities) →
**create the connections project** → propose a plan. A failure at "arc-plan" leaves a book with categories,
entities and a KG project already live. Measured stalls at exactly this shape: *"S06 stalling at 2/5 (categories
+ cast land, connections/plan/chapters never do)"* (`suspended_runs.py:47-52`).

**The primitive exists, and it is pointed the wrong way.** `_meta.undo_hint = {tool, args}` is emitted by every
Tier-A write in book-service (`mcp_tools_write.go:25-32`) and composition-service (`mcp/server.py:451`), naming
the exact reverse call. The runtime reads it at `stream_service.py:4492-4502` — and hands it to the **frontend**
as a user-clickable "agent did X · Undo" strip (`stream_events.py:404-405`). **The executor never reads it.**
Coverage is also partial: only book-service and composition-service emit it; glossary, knowledge and jobs emit
none, so even the human-driven path covers a minority of writes.

**Cheapest way to settle it.** Do **not** build a saga/rollback engine. Make the plan carry a
**completed-effects ledger**: each completed step appends `{step_id, emitted, undo_hint | null}`. Two uses, both
cheap:
1. the ledger is an **input to the replan** — "these effects are live; step 3 created X" — alongside the
   completed steps §0.5 already prescribes;
2. a declaration with no `undo_hint` declares `reversible: false` **at admission** (a C-2-adjacent clause,
   checkable mechanically), so a plan can *know* before it starts that step 3 is a one-way door.

**Gate (red-able):** a plan that replans past a completed step whose effects are not in the replan input is a
runtime contract violation — the same construction as §5's *"a withholding that does not register is a defect"*.

**Ceiling Test: ✅ enabler.** It **adds** information (what is live, what is reversible) and removes no action.
Note the near-miss: *automatic* rollback would be a **🔴 ceiling** — it confiscates a decision a strong model
makes better than we can, and it is unappealable. Ledger + option passes; auto-undo does not.

---

### M2 · `binding-invalid` prescribes re-running a step that may not be re-runnable *(data corruption)*

**The situation.** §0.5 states the transition unconditionally: *"invalidate the binding and **re-run the
producing step** — never ask the model to retype it."* There is no idempotency condition on that sentence, and
**no clause in C-1…C-12 requires a declaration to state whether re-running it duplicates.**

**Why it is certain — three distinct shapes, all present in the repo:**

1. **The producer duplicates.** The producing step in the design's own worked example is
   `glossary_propose_entities` (§2). It is a *create*. Re-running it makes a second draft of every entity.
   `kg_project_create` was measured at **×57 in one turn** (`rail.py:627`).
2. **The runtime already knows the distinction exists but has no declared one.**
   `IDEMPOTENT_NOOP_WRITE_CAP = 1` (`stream_service.py:524-534`) fires on `created: False` — i.e. the runtime
   discovers idempotency *empirically, from the result, after the call*. `ONESHOT_CREATE_TOOLS` is a hardcoded
   registry of exactly one tool (`stream_service.py:555`). Both are stand-ins for a missing contract clause.
3. **Some producers are re-run-*impossible* by construction.** `glossary-service/internal/api/action_confirm.go:175-186`
   claims the JTI **before** running the effect and is explicitly fail-closed: *"once claimed, a failed effect
   does NOT release it; the human re-proposes."* A `binding-invalid` re-run of a confirm step returns
   `422 already confirmed — propose again`. **The correct recovery is to walk back TWO steps, to the proposer** —
   and §0.5's transition can only walk back one.

**Cheapest way to settle it.** One new contract clause, **C-13 `re_runnable`**, a closed three-value enum every
declaration already knows the answer to:

| value | `binding-invalid` may | why |
|---|---|---|
| `idempotent` | auto-re-run | safe; this is the case §0.5 assumes |
| `duplicates` | re-run **only after telling the model**, which chooses | the model may prefer a read-back |
| `single_use` | **not** re-run — escalate to `plan-invalid`, replan from the producer's producer | the confirm-token case |

This also gives §0.5's "walk back one step" the general form it needs: `single_use` is the signal to walk back
further. Cost: a mechanical boot-time check (M4-class), no runtime machinery.

**Ceiling Test: ✅ enabler.** Pure information; it removes no option and **adds** one (`duplicates` hands the
model a choice it does not have today).

---

### M3 · A step times out but its effect commits later *(data corruption)*

**The situation.** Every MCP tool call has a hard client-side deadline: `knowledge_client.py` `tool_timeout_s =
30.0`, bound to `sse_read_timeout` as well (`:773-783`). The call is abandoned; the server-side write lands two
seconds later.

**Why the four scopes get it wrong.** A timeout is the archetypal `retryable_transient` under C-7 — set *where
the failure is raised*, which is the **client**, which by definition does not know whether the effect landed.
That maps to **step-local → retry**, and the write runs twice. And C-8's post-condition is the *opposite*
check — it catches *"a call that changed nothing reported success"*, i.e. the no-op, not the double-commit.

This is a known class in this codebase, not a hypothetical: *"latency + short timeout + best-effort degrade =
data corruption — a size-gated 'random' corruption is a timeout suspect first."*

**Cheapest way to settle it.** A timeout is **not** step-local. Name the state the model currently cannot see:
**`indeterminate`** — the call's outcome is unknown, which is a *third* thing from success and failure. Its
permitted transitions are exactly three, and all three reuse machinery already required elsewhere:
(a) re-run **iff** C-13 says `idempotent` (M2, free); (b) run the step's **read-back** and let the C-8
post-condition decide; (c) `needs-human`. Default is (c), never (a).

**Ceiling Test: ✅ enabler.** It names a state that exists in the world and is currently invisible to the model.
Today the model is *told* "failed" about a call that succeeded — that is the §0.5 shape-1 defect (failure
disguised as success) with the sign flipped, and it is unrecoverable for the same reason.

---

### M4 · Concurrency — a second request while a plan is mid-flight *(data corruption)*

**The situation.** The user sends a new message while a plan is running, or answers a *stale* card after a newer
plan has already changed the same objects.

**Why it is certain.** `routers/messages.py:348` — `POST /{session_id}/messages` has **no in-flight check and no
lock**. The only 409 in the handler is `session is archived` (`:366`). Two concurrent POSTs on one session both
run a full tool loop. They do not collide on the message row (the checkpoint upserts by `msg_id`) — **they
collide on the world.**

The sharper case is plan-specific: a session holding a live `awaiting_input` suspend **accepts a brand-new
turn**. `load_suspended_run` gates on `owner_user_id` and `expires_at > now()` (`suspended_runs.py:109-119`) and
on nothing else — never *"is this still this session's live plan?"* So the old card stays resumable for 6 hours
(and, per M5, forever), and resuming it replays a plan authored against a world that has since moved. Its
carried `pinned_step_tools` and `book_id` are re-applied verbatim.

**Cheapest way to settle it.** Make **the plan the unit of concurrency**: one live plan per session. A second
request while a plan is non-terminal is **routed INTO the live plan as new information** (the enabler form), not
run beside it. And a resume must re-check that its plan is still the session's live plan; if not, the resume's
scope is `plan-invalid`, not "expired".

**Ceiling Test: ⚠️ needs the right form.** A hard *reject* of the second request is a 🔴 ceiling — it removes an
action the user legitimately has. Routing the message into the live plan as input is ✅ an enabler and is what a
strong model wants anyway (it is how it learns the user changed their mind mid-plan). **Choose (a); (b) reject
is only the degraded fallback and must say what the live plan is.**

---

### M5 · `needs-human`, but the human never answers — the expiry sweeper is dead code *(lost work)*

**The situation.** §0.5 elevates suspend-and-ask to a first-class success state. It inherits a machine whose
expiry is a **predicate, not an action**.

**Verified, repo-wide:**

- `suspended_runs.sweep_expired_runs()` (`:187-196`) carries the docstring *"Called periodically from the
  lifespan."* **It has zero callers.** A repo-wide grep for the symbol returns exactly one hit — its own
  definition. Rows accumulate past `expires_at` indefinitely.
- The recovery path that *does* exist — `_mark_suspend_abandoned` → flip `awaiting_input` to `interrupted`
  (`stream_service.py:7207-7226`) — fires **only when the FE attempts a resume of a dead run**. A user who
  simply never comes back triggers nothing.
- So the terminal state of an unanswered ask is: an assistant message frozen at `awaiting_input` forever, a
  suspended-run row that never expires in practice, and **the completed steps' effects live in the database with
  nothing anywhere saying so.**

**Cheapest way to settle it.** Give `needs-human` an expiry **transition**, not a TTL. On expiry: materialize
the trapped turn (already written — reuse `_mark_suspend_abandoned`), attach the **completed-effects ledger**
(M1) so the user is told what is live, then terminate. And wire the sweep — the fix is the missing *caller*, and
the red-able gate is *"a 6h-old row is gone after one sweep tick"*, which is one test.

**Ceiling Test: ✅ neutral.** Invisible to the model; it is a runtime lifecycle property.

---

### M6 · The process dies mid-plan — checkpointed, never reconciled *(lost work)*

**The situation.** Deploy, OOM, SIGKILL mid-plan.

**Half-built, and the missing half is the readback.** The turn *does* checkpoint at every tool boundary:
`stream_service.py:6535-6560`, throttled by `_CHECKPOINT_MIN_INTERVAL_S = 1.5`, upserting the assistant row with
the full `tool_calls_history` at `finish_reason='streaming'`. Its comment names the exact motivating incident:
*"a long tool-loop turn that produced a card, then died before the clean finish."* So the record of completed
steps **is durable**.

**But nothing ever reads a `'streaming'` row back.** Grepping the literal across chat-service returns only the
two *write* sites. There is no boot-time reconciliation, no sweeper, no expiry. A crashed plan leaves a row
stuck at `'streaming'` **forever** — it does not even reach `interrupted`, which §0.5 already classifies as a
defect. The plan terminated by neither `done_when` nor a human, silently, which is the precise thing the §0.5
invariant forbids.

**Cheapest way to settle it.** The plan is data and it is already persisted. On boot: any plan in a non-terminal
state with no live runner → transition to **`needs-human`** (*"this run was interrupted by a restart; N steps
completed; resume or abandon?"*). One boot sweep, one transition, and it reuses M5's sweeper and M1's ledger —
three findings, one mechanism.

**Ceiling Test: ✅ neutral.** Invisible to the model.

---

### M7 · A failure inside a sub-agent — the parent sees a wrapped string, not a scope *(lost work)*

**The situation.** A sub-plan hits `needs-human`. What does the parent plan do?

**Why it is certain.** The sub-run's outcome reaches the parent as prose with no structure:

- `stream_service.py:3310-3330` — the parent's success flag is `_sub_ok = not payload.get("error")`. Boolean.
- the synthesized result is truncated at `SUBAGENT_RESULT_CHAR_CAP = 4000` with an appended note
  (`subagent_runtime.py:71, 172-182`) — **a truncation that can cut the error off the end of the payload.**
- the scope-violation path returns a bare English sentence as `error` (`stream_service.py:3335-3352`).
- a sub-run **cannot surface a suspend at all**: `clamp_permission_mode`'s docstring records that Tier-W/S
  writes *"return a `result.error` instead of executing"* because *"the subagent cannot surface an approval
  suspend"* (`subagent_runtime.py:37-55`).

So a child that needed a human returns an error string; the parent classifies it `step-local` and **retries the
entire sub-run** — burning `min(caller_cap, SUBAGENT_MAX_ITERATIONS=4)` iterations to reach the same wall.

**Cheapest way to settle it.** One rule: **a sub-plan's terminal state is structured and `needs-human`
propagates.** `needs-human` is the only scope a child cannot handle locally, so it suspends the *parent*; every
other scope is the child's own business and the parent sees pass/fail plus the child's emitted values. This also
makes `cap_result` truncation harmless — the state is a field, not the tail of a prose blob.

**Ceiling Test: ✅ enabler.** Replaces an opaque string with a classification; removes nothing.

---

### M8 · The user cancels mid-plan — not one of the four scopes *(lost work)*

**The situation.** The user hits Stop at step 3 of 5.

**Why the design has no answer.** §0.5's four scopes are **all failure scopes**. Cancel is neither a failure nor
`done_when` — so under the invariant (*"no plan may terminate except by satisfying `done_when` or by reaching a
human"*) **a cancelled plan cannot legally terminate at all.**

**What happens today.** `stream_service.py:7049-7075` catches `CancelledError`/`GeneratorExit`, shield-persists
the partial with `finish_reason='interrupted'`, and re-raises without swallowing. Completed effects are visible
via `tool_calls_history`. But the badge is `interrupted` — which §0.5 defines as *a defect, not an outcome*. So
**every deliberate user Stop is recorded as a defect**, and the baseline metric §0.5 proposes (*"an immediate
baseline against today's telemetry, where `interrupted` is common"*) is uninterpretable: it cannot separate
"we broke" from "the user chose to stop."

**Cheapest way to settle it.** A fifth scope, **`abandoned-by-user`** — a legitimate terminal state, the same
shape as `awaiting_input` (a success-shaped end, not badged as failure). It must carry the completed-effects
ledger (M1) so the user is told what is live. The deterministic detector already exists:
`rail.user_abandoned_rail()` is a literal-phrase matcher, explicitly *"not an intent-guess"*. Cost: one enum
value and one badge rule.

**Ceiling Test: ✅ neutral,** and it is a prerequisite for the §0.5 metric being readable at all.

---

### M9 · A replan loop that *changes* every time *(loop / cost)*

**The situation.** replan A → fail → replan B → fail → replan A. The design answers the *simple* runaway (the
replan budget is in the plan, visible, and exhausting it → `needs-human`). It does not answer the **oscillating**
one, and the oscillating one is this repo's measured shape.

**Why it is certain.** Every breaker in the repo keys on an **identical** artifact — `(tool, EXACT args)`,
byte-identical read results, same category. `ReasoningLoopDetector` exists *specifically* because a model
oscillating between two **different** choices trips none of them: *"Actually, I'll try book_update_meta / Wait,
I'll try propose_record_edit"* ×30+, zero tool calls, hung until the user hit Stop
(`reasoning_loop_detector.py:3-15`) — a period-2 cycle. Lifted to plan level, that is replan-A/replan-B, and
§0.5's guardrail property 1 (*fires only on deterministic evidence — an identical call repeated*) explicitly
will not see it.

**Second, unbudgeted axis:** a sub-agent replans inside **its own** plan. Depth is capped at 1 and
`SUBAGENT_MAX_ITERATIONS = 4`, but nothing states that a sub-plan's replans debit the parent's replan budget.
The real bound is *N steps × 4*, not the number the plan shows the model — which breaks §0.3's *visible and
appealable* rule, because the visible number is wrong.

**Cheapest way to settle it.** Two one-line rules, no new machinery:
1. the replan budget is a **plan-tree** budget, decremented at the **root**;
2. the guardrail keys on **plan identity, not call identity** — hash the `(step declaration, binding)` tuple set;
   a replan producing a previously-seen plan-hash **is** the deterministic evidence. This is literally the
   existing `(tool, EXACT args)` rule lifted one level, so guardrail property 1 is preserved intact.

**Ceiling Test: ✅ enabler.** The transition adds information — *"you have proposed this plan before; here is
what failed last time"* — which is the §0.5 replan input, applied to itself.

---

### M10 · Two failures at once — the four scopes are a flat enum with no precedence *(loop)*

**The situation.** A step fails **and** the budget exhausts. Or, harder: a call has two bound arguments, one
stale (`binding-invalid`) and one user-supplied and ambiguous (`needs-human`) — **simultaneously**.

**Why it is certain.** §0.5's table is four unordered rows. And §0.5 itself establishes that the mapping from
C-7 to scope is *not* one-to-one — *"the same `terminal_permanent` means binding-invalid when the argument was
bound from a prior step, and needs-human when it came from the user"* — which is a **per-argument** rule. A call
with arguments of both provenances therefore has two correct scopes, and the design does not say which wins.

The runtime's precedent is not encouraging: six breakers run as a fall-through chain in one loop
(`stream_service.py:4037-4146` — repeated-read, idempotent-no-op-write, repeated-failure, blank-args, plus
tool_list and the reasoning detector elsewhere), each with its own counter and cap, and **precedence is an
accident of source order.**

**Cheapest way to settle it.** State the lattice; build nothing. **`needs-human` > `plan-invalid` >
`binding-invalid` > `step-local`** — the most conservative scope always wins. One table, one test. C-12's
per-field fault locus makes the multi-argument case *decidable*, because it names which field was rejected, and
`accepts` provenance (C-4) says where that field came from.

**Ceiling Test: ✅ neutral.** A tie-break rule, not a constraint.

---

### M11 · The guardrail fires but the model was right *(cost / ceiling)*

**The situation.** The guardrail issues a transition the model did not need and should not obey.

**Why the design has no answer.** §0.5 gives the guardrail three properties, and property 3 (*a strong model
reaches the transition before the guardrail fires*) is a **metric**, not a mechanism. There is no defined
transition for *"the guardrail's transition was wrong."*

**Why it is certain — it has already happened, twice, in this repo, and only a human could fix it.** The F18
`tool_list` breaker's own comment records two **reverted** fixes where the breaker's intervention made behaviour
strictly worse (`stream_service.py:557-570`): returning an error *"framed the repeat as a failure the model
'fixes' by retrying HARDER (28→311 calls)"*, and charging budget to force finalization *"made it HALLUCINATE a
tool-call as text."* The recovery path in both cases was a developer reverting code. Similarly
`REPEATED_FAILURE_CAP` short-circuits the 3rd identical call — and if those two failures were 30-second timeouts
(M3), the model is now **permanently blocked from a call that would have worked**, with no appeal.

**Cheapest way to settle it.** §0.3 already requires every constraint to be *visible **and appealable***. Make
that literal: a guardrail-issued transition carries `appealable: true`, and the model may **override it once** by
stating a reason, which is recorded. The override rate is then the denominator that turns property 3 from an
aspiration into a number you can read per model — *"guardrail fire-rate must fall toward zero as model strength
rises"* becomes measurable as *fires minus sustained overrides*.

**Ceiling Test: ✅ this is what makes the guardrail pass at all.** Without an appeal, a guardrail is an
*invisible, unappealable bound* — §0.3's own named 🔴 archetype (*"a bound is fine; an invisible, unappealable
bound is not"*). Property 3 without an appeal path is an unfalsifiable claim, and §0.3 warns exactly that:
*"if it does not, we built a ceiling and mislabelled it."*

---

## 4 · Summary

| # | missing situation | class | cheapest settlement |
|---|---|---|---|
| **M1** | side effect committed, then replan — no ledger, no compensation concept | data corruption | completed-effects ledger in the plan; `reversible` at admission from `undo_hint` |
| **M2** | `binding-invalid` re-runs a non-idempotent / single-use producer | data corruption | **C-13 `re_runnable`**: `idempotent` \| `duplicates` \| `single_use` |
| **M3** | step times out, effect commits late | data corruption | **`indeterminate`** outcome; never auto-retry; read-back or human |
| **M4** | second request / stale resume against a live plan | data corruption | one live plan per session; route the new message **into** it; resume re-checks liveness |
| **M5** | needs-human never answered — `sweep_expired_runs` has **zero callers** | lost work | expiry **transition** + wire the sweeper (one caller, one test) |
| **M6** | process dies mid-plan — `'streaming'` rows never read back | lost work | boot reconciliation → `needs-human` |
| **M7** | sub-agent failure arrives as a truncatable string | lost work | structured sub-plan terminal state; `needs-human` propagates to the parent |
| **M8** | user cancel is not one of the four scopes | lost work | fifth scope **`abandoned-by-user`**, a success-shaped terminal |
| **M9** | oscillating replan (A→B→A) trips no identical-artifact breaker | loop | plan-tree budget at the root; guardrail keys on **plan hash** |
| **M10** | two scopes at once — flat enum, no precedence | loop | lattice: needs-human > plan-invalid > binding-invalid > step-local |
| **M11** | guardrail fires and is wrong — no appeal, no recovery | cost / ceiling | `appealable: true` + one recorded model override; the override rate **is** property 3's metric |

**One mechanism settles four.** M1's completed-effects ledger, M5's expiry transition, M6's boot reconciliation
and M8's cancel scope are all *"a plan reached a non-`done_when` end — say what is live and hand it to a human."*
Built once, they close the §0.5 invariant's only real hole: today a plan can end without satisfying `done_when`
**and** without reaching a human, in four distinct ways, silently.

**One finding is a prescribed corruption, not an omission.** M2 is the only entry where the design *actively
tells the runtime to do the wrong thing* — §0.5's *"re-run the producing step"* is stated with no idempotency
condition, and `action_confirm.go` proves the repo already contains producers where that re-run is impossible by
construction. It should be settled before any brick-4 (`emits`→`accepts` pair) is built, because brick 4 is the
first place a producing step gets re-run.
