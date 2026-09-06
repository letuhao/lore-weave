# S2 — the PLAN, as a first-class data structure

**Module:** `ARCHITECTURE.md` §0.4 (PLAN / EXECUTE separation) and §0.5 (recovery).
**Mandate:** coverage, not critique. Two questions: what situation does the plan module exist to
solve, and what situations will certainly occur that it has **no defined answer for**.
**Method:** the live `loreweave_agent_registry` DB, the shipped rail driver
(`sdks/python/loreweave_agent_control/rail.py`, 729 lines), the Go authoring contract, PlanForge's
pass registry, and the `authoring_runs` FSM. Every claim below carries a `file:line` or a query.

---

## 1 · What the plan module exists to solve

### 1.1 The situation, stated

> A novelist's session is long, multi-turn, and interleaved. The work that matters —
> *"set up my world, save my cast, plan the arcs, draft the chapters"* — is a **sequence whose
> steps are separated by many turns of ordinary conversation**. The model has to hold that
> sequence across those turns while also doing the emotional work of co-writing, and it drops it.

That is not a hypothesis. It is the opening docstring of the shipped rail driver
(`sdks/python/loreweave_agent_control/rail.py:8-22`), written after four identical measured runs:

> *"the flagship STILL does not ship — measured across four identical S06 runs: kinds 5/12/0/5 ·
> **cast 0/0/0/0** · plan 0/1/0/0. Nothing DRIVES the rail. The model is handed a 12-step recipe and
> asked to hold it across a 17-turn conversation … and it drops it. The old rail header literally
> said 'look back at what you have already called, and continue from the first step still
> outstanding': it asked the model to REMEMBER, and remembering is the thing it is worst at."*

### 1.2 Three independent proofs from this repo that the situation occurs

| # | evidence | where |
|---|---|---|
| **E1** | **The plan already exists as data and has never run.** 12 seeded workflows, 45 steps, with `done_when`, `gate`, `inputs_map`, `repeat`, `async_job`. `SELECT slug, used_count, last_run_at FROM workflows` returns **`used_count = 0` and `last_run_at = NULL` for all twelve** — and both columns are **dead: no Go code writes either**. `workflow_revisions` / `workflow_proposals` are **0 rows**. There is no `POST /workflows/{id}/run`, no `workflow_runs` table, and **no execution state of any kind** in the registry service (RT2 §A11) | live DB; `services/agent-registry-service/internal/migrate/migrate.go:497-766` |
| **E2** | **The real plan is in prose, not in the structure.** `notes_md` totals **21,952 characters across the twelve (mean 1,829)** against 45 steps of `{id, tool, gate}`. `vision-to-book` carries **4,673 characters** of notes over 9 thin steps — and those notes contain the *ordering constraint* (*"ORDER IS LOAD-BEARING — categories BEFORE cast. Proposing a character before its category exists fails with 'unknown kind' and you will loop"*), the *prerequisite branch*, the *hand-off to another agent*, and the *negative constraints* (*"do NOT call `plan_compile`"*). **None of that is expressible in `{declaration, accepts, emits, done_when}`.** The structure holds ~5% of the plan | live DB `notes_md` |
| **E3** | **Where a plan was expressed only as a restriction, it produced a deadlock — twice, in code comments.** `rail.py:167-176`: a plan run proposed on 2026-07-29 made `done_when: "plan > 0"` true *forever*, so `done_suppress` dropped `plan_propose_spec` from every later session; the author could never plan a second arc, and the model — shown `plan_compile` but not the tool that mints a run id — **invented `run_id="arc_1_setup_001"`**. `rail.py:222-233`: `max(any TRUE artifact)` jumped over a proven-absent step and forbade the very step that produces the `confirm_token` the next step needs | `rail.py:167-176`, `:222-233` |

E3 is the §0.4 thesis restated by the code that suffered it: **when a plan can only be expressed by
narrowing the action space, a stale plan permanently confiscates a capability.**

### 1.3 What the module therefore exists to do — three jobs, all information-space

1. **Be the durable carrier the conversation is not.** RT3 F2/F3/F5 measured the carrier: a pin-blind
   `LIMIT 50` window (`stream_service.py:5063-5084`), sequence-based compaction with **no pin path**
   (`compaction.py:266-268` — the only `_is_pinned` returns `False` for anything the persistence
   layer can store), tool results evicted beyond the newest 3, and **tool-call arguments dropped at
   two independent layers** (the cross-turn `SELECT role, content` never reads `chat_messages.tool_calls`;
   `compact_service.py:66-81` renders a tool turn as `(called tool_a, tool_b)` with arguments discarded).
   That is the mechanism behind the 61.8%.
2. **Let the model see, disagree with, and rewrite the sequence** — which rails, intent regexes and
   F18 auto-load all structurally forbid (§0.4's table).
3. **Give failure a level to be classified at.** §0.5's four plan-level scopes are not derivable from
   the call alone: the same `terminal_permanent` is *binding-invalid* when the argument came from a
   prior step and *needs-human* when it came from the user.

### 1.4 What already works, and must not be re-derived

The design should treat these as solved and inherit them:

- **Grounding a step's doneness in the artifact, not the call log** — `compute_rail_progress`
  (`rail.py:189`) reads the book's own counters and lets *absent artifact* override *successful call*.
  This is the only thing in the repo that refuses the "succeeded and wrote nothing" signal.
- **The durable/session split** — `done` (is it in the book?) orients; `session_done` (did *this chat*
  do it?) is the only honest basis for removing anything (`rail.py:156-178`).
- **Own WHERE, never WHEN** — `render_progress_block`'s docstring records two live failures from
  trying to own WHEN (`rail.py:358-397`): cut 1 fired the opening step while the user was still
  talking; cut 2 deadlocked. Cast 0 both times.
- **A real dependency DAG with human checkpoints** — PlanForge's `PASS_REGISTRY`
  (`services/composition-service/app/services/plan_pass_service.py:55-89`): `depends_on` tuples,
  `checkpoint="blocking"` where a human is the only oracle (who the characters ARE; what shape the
  story takes), inputs resolved **by pointer**.
- **A durable, crash-recoverable, budgeted run** — `authoring_runs`
  (`services/composition-service/app/db/migrate.py:1741-1781`): `current_unit` cursor, `driver_id` +
  `driver_heartbeat_at` with stale-sweep re-claim (`authoring_run_service.py:1146-1171`),
  `budget_usd`/`spent_usd`, `breaker_state` recording *why* it stopped, `pause_after_each_unit`
  defaulting true, and `uq_authoring_runs_active_book` — **one active run per book, across users,
  409 on violation**.
- **Staleness derived, never stored** — PlanForge's `is_fresh()`
  (`plan_pass_service.py:187-210`) recomputes `sha256(ordered input artifact_ids + params)` against a
  recorded `input_fingerprint`, so re-running any pass invalidates everything downstream with **zero
  invalidation writes**. The file's own words: *"This is `make`."* `pass_cursor`, `blocked_at` and
  `runnable_now` are all **computed at serialization** (`:259-354`), never persisted. This is the
  single most reusable idea in the repo for a plan executor, and §0.4 does not mention it.
- **Three durable resume patterns already in production**, in increasing weight:
  **resting-state + client pull** (`intent_run.slot_cursor`; PlanForge blocking checkpoints — no
  sweeper needed because no work is in flight), **heartbeat + sweep** (`authoring_runs`), and
  **lease + reconcile-against-downstream-truth** (`campaigns.driver_leased_until`,
  `campaign-service/app/saga/reconcile.py:42-63`, driver stateless between ticks by construction).
- **The only real fan-out** — `campaign-service`'s `next_dispatches()`
  (`app/saga/gating.py:91-143`) returns a *batch* bounded by `max_inflight`, under a
  `gating_mode ∈ {phase_barrier, cold_start}` barrier. Its stages, however, are **code**, not data.

---

## 2 · Situations with no defined answer

Ranked by likelihood of occurring in **this** product — a novel-writing assistant with long,
interleaved, multi-turn sessions. Each entry states the situation, the repo evidence that it occurs,
what the design says (usually nothing), the **cheapest way to settle it**, and the **Ceiling Test**
(§0.3) verdict on the proposal.

---

### F1 · The plan has no home, so it evaporates between turns — **certain, every session**

**Situation.** The user is mid-plan at step 4 of 9. On the next turn they ask *"wait, what's Lin
Yao's mother called again?"* Then they come back. Where did the plan go?

**Evidence it occurs.** Today the answer is: **nowhere, because nothing stores it.** There is no rail
table, no session column, no Redis key. The plan is *re-derived from scratch every turn* from two
sources — a mode binding, and a **regex over the current user message**
(`stream_service.py:5427-5438` → `intent_workflows.py:112`, 10 slugs, keyword match, no LLM). An
off-topic turn matches nothing, so the rail is simply **not pinned that turn** and the plan is absent
from the prompt entirely. Worse, on a **suspend → resume** — the product's own approval-card path —
`_compute_rail_drive_context` (`stream_service.py:611-615`) re-derives **only the mode-binding pin**.
Every intent-pinned plan (entity-triage, canon-check, kg-build, chapter-compose, translation-pass,
draw-a-map, populate-from-notes) is **lost at the confirm card** — the exact moment the plan was
working.

**What the design says.** §0.4 calls the plan "data — inspectable, revisable, cheap to re-present"
and never names its **owner, lifetime, or storage**. A plan can be per-turn, per-session, per-book,
or per-user, and every one of those is a different product.

**Cheapest way to settle.** One decision, one column, one query. Declare the plan's scope key (the
evidence points at **session-owned, book-scoped**, matching `authoring_runs`), then the falsifier is
already runnable against production data:

```sql
-- how often does a live plan disappear because the turn's words did not match?
SELECT count(*) FROM chat_messages WHERE role='user' AND session_id IN (…);
```
run the existing 10 intent regexes over each user message of a real multi-turn dogfood session and
count the turns that match none. **Every such turn is a turn where today's plan is invisible.** No
new code; ~20 lines of script against `chat_messages`.

**Ceiling Test.** ✅ enabler — a stored plan adds information across turns and removes no option.

---

### F2 · Where the plan sits in the request — §0.4's central cost claim is **false as built**

**Situation.** The plan must be re-presented every turn. Every turn, its cursor and its state counts
have changed. Where does it go?

**Evidence it occurs.** Today the plan block is **tail block #14 of the system message**
(`stream_service.py:5597`, `pinned_rail_text`), i.e. **inside** the BP2-cached region
(`sdks/python/loreweave_context/system_message.py:73` stamps `cache_control` on the *last* element of
the persona+tail region; Anthropic caches the **cumulative prefix**). And its bytes change on every
turn by construction — `render_progress_block` embeds live counters
(*"world categories: 31 · characters/places saved: 3187"*) plus *"YOUR PLACE IN THE RECIPE: step N of
M"*. RT3 F9 prices it: the tool-block/prefix change measured **+65% uncached / hit-rate 1 in 6**
(`poc/P1-P2-findings.md:639-644`). §0.4 asserts the opposite without a mechanism:

> *"small, structured, and cheap enough to re-present every turn **without touching the cache prefix**"*

There is no position in the request where that is true *and* the plan is durable: the prefix is
cached (so a mutating plan is expensive there), and the message tail is **lossy** (RT3 F2/F3 — the
`LIMIT 50` window and `persist_auto_compact` both delete without a pin, and `_is_pinned` cannot be
reached by anything the persistence layer can write).

**What the design says.** Nothing. §0.4 names the requirement and skips the placement.

**Cheapest way to settle.** Decide the position (the only cache-safe one is **after the last cached
breakpoint, adjacent to the newest user turn** — the same slot `wm_tail` already uses at
`stream_service.py:5620`), then measure with data that already exists: `chat_messages.context_breakdown`
(`migrate.py:198-199`) records per-category token counts per turn. Group consecutive turns of one
session by whether the plan block's bytes changed and compare cache-read vs cache-write tokens.
**One query, zero new instrumentation** (this is RT3 Part 3's F8 row with one extra grouping column).

**Ceiling Test.** ✅ neutral — placement is invisible to the model's action space.

---

### F3 · `done_when` has a closed 9-word vocabulary, and a model-authored plan cannot use it

**Situation.** §0.4 says the plan is *"produced by the model itself"*. The model writes a step:
*"rename Lin Yao to Lin Yaoxue everywhere — done when no old surface form remains."* What is that
step's `done_when`?

**Evidence it occurs.** The grammar is **`<key> <op> <int>` with `key` in a hard-wired set of nine**:
`categories · cast · connections · plan · structure · structure_fresh · chapters · prose · suggestions`
(`contracts/book-state-keys.contract.json`; `rail.py:49-76`; enforced at authoring time by
`services/agent-registry-service/internal/api/workflows.go:76`). Each key is a **hardcoded internal
route in a named service** — adding a tenth means a new endpoint, the contract file, `BOOK_STATE_KEYS`,
the labels map, the `BookState` dataclass, the Go regex, and two lockstep tests. **A model cannot mint
one at run time, and neither can a user-authored plan.** All nine are also **book-global counters**,
so they cannot express anything scoped to a chapter, a character, or a scene — which is most of what
a novelist asks for.

The failure is not loud. An unparseable or unknown-key predicate logs a warning and **falls back to
the call log** (`rail.py:116-129`, `:301-306`) — i.e. it silently degrades to *"the tool ran"*, the
exact signal the whole mechanism exists to distrust (§1.4).

**What the design says.** C-8 requires *"a workflow's `done_when` is a predicate over real state"* and
stops there. It never says what a step whose completion is **not observable** does.

**Cheapest way to settle.** Choose between two, and only two, positions:
(a) `done_when` binds to the step's own **`emits`** (C-6) rather than a global counter — which makes
it extensible for free and unifies the two clauses §0.4 already says are "the same mechanism seen
twice"; or (b) `done_when` stays a closed set and **absence is a first-class, visible value**
(`observable: false`), never a silent fall-through to the call log.
Falsifier, one unit test on the shipped kernel: author a step with `done_when: "seams < 1"`, assert
the plan reports **not-observable**, not **done-because-the-tool-ran**.

**Ceiling Test.** ✅ enabler under (a) — it *adds* an expressible predicate; the "silent fall-through
to the call log" it replaces is a lie, and C-5's argument applies verbatim.

---

### F4 · A plan resumed days later — a binding can be stale, and there is no such error class

**Situation.** The user starts a plan on Monday, approves the confirm card, and comes back Thursday.
The plan's step 3 is bound to `adopt.confirm_token`.

**Evidence it occurs.** The seeds bind expiring credentials **by name**:
`glossary-bootstrap` step `apply` has `inputs_map: {"confirm_token": "adopt.confirm_token"}`;
`vision-to-book` step `apply-categories` the same. A confirm token is a P6 credential with a TTL, and
`chat_suspended_runs` is swept by `expires_at` (`app/db/suspended_runs.py:187-191`). And the
staleness class has **already caused a production deadlock**, recorded in the code: a plan run
proposed on **2026-07-29** made `done_when: "plan > 0"` read true forever, disarming
`plan_propose_spec` in every later session (`rail.py:167-176`). The repo's fix was to **invent a
second key** — `structure_fresh`, *"latest plan run only; a re-plan reads 0 until ITS compile lands"*
(`contracts/book-state-keys.contract.json`) — a per-key patch for what is a **general** property.

**What the design says.** §0.5 has four plan-level scopes: `step-local`, `binding-invalid`,
`plan-invalid`, `needs-human`. **None of them is "stale".** `binding-invalid` covers *wrong or stale*
in one phrase and prescribes *re-run the producing step* — but nothing in the structure records **when**
a value was emitted, or that a given emit is **volatile** (a confirm token, a proposal id, a presigned
URL) versus durable (an `entity_id`). Without that the executor cannot tell a value that is fine from
one that expired at 3am on Tuesday, so it will either re-run everything or trust everything.

**Cheapest way to settle.** Do **not** invent a mechanism — adopt PlanForge's, which already solves
the harder half. `is_fresh()` (`plan_pass_service.py:187-210`) makes staleness **derived**:
`sha256(ordered input artifact_ids + params)` vs a recorded `input_fingerprint`, so an upstream change
invalidates everything downstream with zero invalidation writes. That covers *"an earlier step was
re-run"*. It does **not** cover *"the world moved while nobody ran anything"* — the confirm-token
case — so add exactly one field for that: `volatile: true` on an `emits` entry (plus its
`emitted_at`). The repo already ships both live examples: a confirm token (expires; even
`workflow_proposals.expires_at` defaults to `now() + 7 days`) and an `entity_id` (does not). Test:
build a plan with both bindings, advance the clock past the token TTL, assert the executor re-runs
*only* the token's producing step.

**Ceiling Test.** ✅ enabler — it adds provenance-in-time; it removes no option and lets a strong
model reason about freshness it currently cannot see.

---

### F5 · The user edits the plan, or changes the goal — there is no edit operation, and the abandon channel is an English regex

**Situation.** *"Actually do the map first."* / *"Forget the cast, just start writing."* /
*"Thôi, viết luôn đi."*

**Evidence it occurs.** The **only** defined channel today is `_ABANDON_RE` (`rail.py:600-607`) — a
literal alternation over `skip|forget|drop|abandon|never mind|nevermind|leave|ditch` near
`plan|step|setup|it|this|that`, plus `just (write|draft|move on|keep going)`. It is deliberately not
an LLM call, which is right; but this product's dogfood book is **Vietnamese/Chinese**, and a CJK or
Vietnamese abandon phrase matches **none** of it. The fallback is the bounded auto-release after 3
nudges — and those nudge counters are **per-turn locals reset on every user message**
(`stream_service.py:1932-1951`), so a user who wants out gets nudged again on the next turn, forever.

And there is **no edit path at all** — a plan today can be *abandoned*, never *amended*. The
versioning that exists is nominal: `workflow_revisions` has **0 rows**, **no version or sequence
number**, is snapshotted from exactly one call site whose error is discarded
(`workflows.go:699`, `:758-762`), is never written on `create`, has **no restore endpoint**, and its
read endpoint **does not even return `steps`** (`workflows_rest.go:174-210`). No `revision_id`
foreign key exists anywhere, so **a workflow edited mid-run mutates under any in-flight execution**.

The one place in the repo where a mid-run plan edit is done *correctly* is PlanForge:
`plan_review_checkpoint(pass_id, edits)` (`plan_forge_service.py:1011`, `_review_pass:1053`) writes a
**new artifact** for that pass, and because downstream inputs resolve by pointer + fingerprint,
everything dependent goes stale **by derivation**. A narrower second case exists in glossary-build,
which accepts an overridden `worklist` in the `plan_ready → building` window
(`glossary_build/service.py:243-255`). Everything else in the repo freezes its scope at launch.

**What the design says.** §0.4 says the plan is *"revisable"* and names **no revise operation**, no
revision identity, and no rule for what happens to values already emitted by steps the edit touches.
§0.5's `plan-invalid` → *replan* covers the model deciding to replan; it does not cover **the human
editing a live plan**, which is the product's whole promise ("a plan they can see and adjust" —
`vision-to-book.notes_md`).

**Cheapest way to settle.** Declare the plan **append-only with a revision id**, and state the one
rule that matters: **emitted values are keyed by step id and survive a revision that does not delete
their step.** Falsifier: a 5-step plan; edit step 5; assert step 2's emitted `entity_id` is still
bound. Separately, make abandonment **language-independent** by giving it a UI affordance rather than
a regex — the repo's own lesson is on file (`feedback_e2e_that_types_a_ui_string_is_language_coupled`,
`feedback_space_tokenizer_degrades_on_cjk`).

**Ceiling Test.** ✅ enabler — a revise op adds an action *for the human*, not a restriction on the
model; the model's action space is unchanged.

---

### F6 · A step whose output is a JUDGEMENT — the structure has no place for "the answer is no"

**Situation.** *"Is chapter 7 good enough to keep?"* *"Is this seam clean?"* *"Are these two the same
character?"* In a novel-writing assistant this is the **most common** kind of step.

**Evidence it occurs.** The judging step **is missing from the plans that need it, because it cannot
be written.** `canon-check` — the workflow whose entire purpose is finding contradictions — has three
steps, all reads (`composition_list_canon_rules`, `book_list`, `book_read`), **none with a
`done_when`**. The judgement lives nowhere in the structure; it is implied by prose. Meanwhile the
`done_when` grammar admits only integer comparisons on nine counters (F3), so a verdict cannot be a
completion predicate, and the four §0.5 scopes have no slot for **"the step succeeded and the verdict
is NO"** — which is neither a failure nor a done.

**What the design says.** Nothing. §0.5 classifies *failures*; a negative verdict is a success.

**Cheapest way to settle.** Decide once whether a verdict step (a) `emits` a typed verdict that the
plan may branch on (which forces F7's branching decision), or (b) always transitions to
`needs-human` — the §0.5 state the design already declares a **success**. Option (b) is nearly free
and matches PlanForge's own answer: `checkpoint="blocking"` on exactly the two passes where *"the
human is the only oracle"* (`plan_pass_service.py:60-70`). Falsifier: encode `canon-check` as a plan
with a verdict step and see whether either option renders it.

**Ceiling Test.** ⚖️ (b) is a legitimate human-in-the-loop stop, not a capability ceiling — it removes
no tool and the model can still act; (a) is a pure enabler.

---

### F7 · The plan a weak model writes is simply WRONG — nothing checks order

**Situation.** A 26B model writes a 6-step plan that saves the cast before creating the categories.

**Evidence it occurs.** This exact ordering error is the one the seeds shout about in capitals:
*"ORDER IS LOAD-BEARING — categories BEFORE cast. Proposing a character before its category exists
fails with 'unknown kind' and **you will loop**"* (`vision-to-book.notes_md`). And weak-model
plan-following is already measured at **S03 entity-triage 0/3 · S04 kg-build 1/3 · S09 canon-check
improvises** (`intent_workflows.py:8-13`) — that measurement is *why* the regex-pin exists.

**What the design says.** C-6 is the check that would catch it — *"a workflow step's `accepts` must be
satisfiable from a prior step's `emits` — checked at **generation**"*. But §0.4's whole point is that
a plan may be **produced by the model at run time**, and nothing says the same satisfiability check
runs then. M5/C-11 check only that step names resolve to *admitted* declarations — a referential
check, not an ordering one. So a model-authored plan is the **one plan the contract never validates**.

**Cheapest way to settle.** Say that the C-6 satisfiability check runs at **plan-accept** time, not
only at generation, and that its output is a **finding attached to the plan** (which steps are
unsatisfiable and why) rather than a rejection. Falsifier: feed the checker `vision-to-book` with
steps 1–3 removed; it must name `save-cast` as unsatisfiable.

**Ceiling Test.** ✅ enabler **only if it reports rather than blocks** — a rejection would be a
ceiling (the strong model may know an order we do not). Report the finding; let the model overrule it.

---

### F8 · A binding resolves by KIND or by STEP-INSTANCE — undefined, and this repo already got it wrong

**Situation.** A plan drafts chapter 7, judges it, then redrafts it. Step 5 binds "the draft". Which
draft?

**Evidence it occurs.** PlanForge hit this and left the post-mortem in the source
(`plan_pass_service.py:81-85`): the `self_heal` pass **emits a new `scene_plan` and depends on
`scenes`** —

> *"which is exactly why inputs must resolve by POINTER: under a latest-by-kind rule it would read
> its own output as its input."*

Novel-writing plans re-run the same declaration many times by nature (draft → judge → redraft;
propose → merge → propose). A kind-keyed binding is therefore wrong here **by default**, not in a
corner case.

**What the design says.** §0.4 says the plan *"binds emitted values into later steps' arguments"* and
does not say what the binding key is. The prior art is split down the middle: `inputs_map` uses
`"<step-id>.<field>"` (an instance pointer — `glossary-bootstrap`, `autonomous-drafting`), while
`done_when` uses a bare global noun (a kind).

**Cheapest way to settle.** Write the one sentence — *a binding is `<step_id>.<emit_name>`, always an
instance pointer, never a type* — and add the three-step regression: step 3 binds step 1's emit while
step 2 emits the same kind; assert step 3 receives step 1's value. `inputs_map`'s existing string
format already is this; nothing needs to be invented, only decided.

**Ceiling Test.** ✅ neutral/enabler — it makes an existing reference unambiguous.

---

### F9 · A plan that cannot be written until a lookup runs — no notion of a partial plan

**Situation.** *"Clean up my suggestion pile."* You cannot know how many merge steps there are until
`glossary_curation_list` has run. Same for *"fix the timeline"*, *"tidy the duplicate characters"*.

**Evidence it occurs.** `entity-triage` is exactly this workflow, and the seed's answer is to **not
enumerate the steps at all**: four generic steps, `repeat`, and a *drain* predicate
`done_when: "suggestions < 1"`. The drain operators (`<`, `<=`, `==`) were added to the grammar for
precisely this rail, because *"a triage step could never be marked done from the book"* under a
build-only grammar (`rail.py:57-64`).

The repo also already ships the *other* answer, in a different service: `glossary_build_runs.worklist`
is a **JSONB step list generated by an LLM at run time**, after a `planning` phase, with resumable
per-item rows carrying an `ordinal` (`composition-service/app/db/migrate.py:2169-2213`). That is a
model-authored plan, executed, today — the closest live precedent §0.4 has. Its registered gap is the
one F1 also names: *"a service restart mid-build leaves the run in `building`; the authoring-run
heartbeat/sweep pattern is the planned follow-up"* (`glossary_build/service.py:9-11`).

**What the design says.** §0.4's plan is a fixed `steps[]`. There is no notion of a step that
**expands into steps**, of a plan that is **partially written**, or of a *"plan the planning"* first
step. §0.5's `replan` transition fires on *failure*; discovering that the plan needs more steps is
**not a failure**.

**Cheapest way to settle.** State that a plan is **append-only and may be extended by the executor
after any step**, which the replan path already needs mechanically. Falsifier: a 2-step plan whose
step 2 appends 3 steps; assert the cursor and every existing binding stay valid.

**Ceiling Test.** ✅ enabler — the model gains the ability to write less plan up front.

---

### F10 · Two plans at once — the repo holds two contradictory precedents and the design picks neither

**Situation.** *"Keep drafting chapters 5–12 in the background"* — and, three turns later, *"while
that's going, clean up the suggestion pile."*

**Evidence it occurs.** Rails already run N-at-a-time: `_rail_specs` / `_rail_progress_objs` are
parallel **lists** (`stream_service.py:5414-5420`), `pinned_rail_block` renders all of them up to a
12,000-char cap, and `rail_gate_suppressions` **unions the suppression set across all rails**
(`rail.py:702-729`). But the drive **breaks on the first drivable rail**
(`sdks/python/loreweave_agent_control/harness.py:106-113`) — so the second plan is *displayed and
never advanced*, with nothing telling the user which one is live. Composition made the **opposite**
decision for the same product: `uq_authoring_runs_active_book` — **one active run per book, across
users, 409 on violation** (`composition-service/app/db/migrate.py:1783-1786`).

**What the design says.** Nothing — §0.4 is written throughout in the singular ("the plan").

**Cheapest way to settle.** Separate the two questions and answer both in one line each:
*how many plans may EXIST* (evidence says: many — they are cheap data) and *how many may hold the
TURN* (evidence says: one). Falsifier is already writable against the shipped kernel: pin two rails,
assert exactly one is driven **and** that the other is rendered as *waiting*, not as *in progress*.

**Ceiling Test.** ✅ enabler if the non-driving plans stay **visible** — the harm today is that a
silently un-advanced plan is indistinguishable from a stalled one.

---

### F11 · Branching — the field exists in the shipped contract and **is evaluated by nobody**

**Situation.** *"If the book already has a compiled plan, skip to drafting; if not, build it first."*

**Evidence it occurs.** The authoring contract already ships the field:
`services/agent-registry-service/internal/api/workflows.go:44` —

```go
When string `json:"when,omitempty" jsonschema:"optional predicate over prior step results / inputs (evaluated by the runner)"`
```

**There is no runner and no consumer.** Grep finds the struct field, and nothing else — and `when`
appears in **zero of the 45 seeded steps**. So the schema tells an author (and any model reading the
tool schema) that branching works, while nothing anywhere can honour it. Meanwhile the branch it
would express is written in prose in the notes: `autonomous-drafting.notes_md` — *"PREREQUISITE: this
drafts from a COMPILED story plan. If the book has no compiled plan yet, **STOP and offer to build/
compile the plan first**"*. Nine of the twelve seeds contain at least one prose conditional.

**What the design says.** §0.4's step shape is `{declaration, accepts-bindings, emits-bindings,
done_when}` — it **drops** a field the current contract already advertises, without saying whether
branching is deliberately the model's job (replan on the result) or an omission.

**Cheapest way to settle.** Pick one and make it non-silent: either **delete `when`** from the
contract and state that branching is expressed by re-planning (which §0.5's `plan-invalid` path
already supports), or define its grammar the way `done_when`'s was defined. The one thing that must
not survive is a schema field the runner ignores — the repo's own rule
(`feedback_a_freeform_contract_schema_is_the_root_cause_of_shape_drift`). Falsifier: seed a workflow
with a `when` and assert the runner **honours or rejects** it, never ignores it.

**Ceiling Test.** ✅ neutral — either resolution changes what the author can express, not what the
model may do.

---

### F12 · Parallel / fan-out — the one primitive for it is unreachable, and its name is already taken

**Situation.** *"Extract entities from all twelve chapters."* Independent, parallelisable steps.

**Evidence it occurs.** The contract has a fan-out field —
`workflows.go:45`, `Repeat string`, *"none | per_item:<inputs key> — fan the step over a list input"* —
validated against the workflow's declared `inputs` (`validateRepeat`, `:205-219`). But **all twelve
seeded workflows declare `inputs = {}`** (verified in the live DB), so `per_item:` can never validate
on any shipped workflow. And the seeds store **`"repeat": true`** — a *boolean* into a `string` field —
which the runtime reads with an entirely different meaning: `bool(st.get("repeat"))` = *"this step is
legitimately re-runnable, never action-gate it as done"* (`rail.py:154-155`, `:722-726`). One field
name, two incompatible types and two incompatible semantics, either side of a Go typed struct whose
unmarshal errors are discarded (`workflows.go:348`, `_ = json.Unmarshal(...)`) — the repo's own
`feedback_typed_struct_drops_field_before_forward_allowlist` failure, live.

**What the design says.** §0.4's `steps[]` is an **ordered list**; nothing addresses independence,
concurrency, or fan-out. The Go step struct has **no `parallel`, no `branch`, no `next`, no
`on_error`** — ordering is array position and nothing else. The two shapes the product actually needs
both exist elsewhere and neither is plan data: PlanForge's `depends_on` DAG
(`plan_pass_service.py:55-89`) computes `runnable_now` (`:350-353`) but **nothing orchestrates it**,
and campaign-service's `next_dispatches()` (`app/saga/gating.py:91-143`) is the only true batch
fan-out in the repo — bounded by `max_inflight`, under a `phase_barrier`/`cold_start` gating mode —
with its stages **hardcoded**.

**Cheapest way to settle.** Two cheap decisions, taken together: (1) is a plan a **list** or a
**DAG** — PlanForge says DAG, and `depends_on` is the same information `accepts`-bindings already
carry, so the DAG is *derivable for free* from the bindings and needs no new field; (2) rename one of
the two `repeat` meanings, and add the round-trip test (author `repeat` through the Go API, read it
back, assert the value survives) — this one is a live bug regardless of the redesign.

**Ceiling Test.** ✅ enabler — deriving the DAG from bindings adds parallelism the model can exploit
and constrains nothing.

---

### F13 · The word "plan" is already triple-booked in this product — **naming, but load-bearing**

`permission_mode = "plan"` is a shipped per-turn UI mode with its own system nudge (*"research the
book with read-only tools and build/refine the plan via the `plan_*` tools. Do NOT write prose"* —
`stream_service.py:703-709`); the `plan_*` tools are **PlanForge**, the *story-arc* planner
(`_is_plan_tool`, `:724-726`); and `done_when: "plan > 0"` means *"an arc-plan proposal exists"*
(`contracts/book-state-keys.contract.json`). To the user, **"the plan" is their novel's arc plan** —
`vision-to-book.notes_md` instructs the agent to say *"your story plan"* and forbids the words
*workflow* and *PlanForge*. A fourth "plan" that means *the agent's own step list* will collide in
prompts, in tool names, in telemetry, and in the user's own sentences. **Cheapest settle:** name it
now, once, in §0.4 (the repo's existing internal word is **rail**, or **recipe** in user-facing
prose), before it is written into a contract file.

---

## 3 · Summary table

| # | situation | design defines it? | cheapest settle |
|---|---|---|---|
| F1 | plan evaporates between turns; lost on suspend→resume | ❌ no owner/lifetime/storage | run the 10 intent regexes over one dogfood session's user messages; count non-matching turns |
| F2 | where the plan sits vs the cache prefix | ❌ claim asserted, mechanism absent | group `context_breakdown` by "did the plan block change"; one query |
| F3 | `done_when` closed 9-key vocabulary; silent fall-through | ⚠️ C-8 stops at "over real state" | bind `done_when` to the step's own `emits`, or make non-observable explicit |
| F4 | resume days later; a binding went stale | ⚠️ `binding-invalid` exists, no staleness/TTL | `emitted_at` + `volatile:true` on `emits`; test the confirm-token case |
| F5 | user edits the plan / changes the goal | ❌ no revise op; abandon is an English regex | append-only + revision id; emitted values keyed by step id |
| F6 | a step whose output is a judgement | ❌ no verdict, no "answer is NO" | verdict → `needs-human` (free), or a typed verdict emit |
| F7 | a weak model's plan is simply wrong | ⚠️ C-6 checks at *generation* only | run C-6 satisfiability at plan-accept; **report**, never block |
| F8 | binding by kind vs by step instance | ❌ unstated | one sentence: `<step_id>.<emit_name>`; 3-step regression |
| F9 | plan needs a lookup before it can be written | ❌ fixed `steps[]` | append-only plan; step 2 appends steps, cursor stays valid |
| F10 | two plans at once | ❌ singular throughout | split "may exist" from "may hold the turn"; render the other as *waiting* |
| F11 | branching | ❌ dropped; `when` ships and is ignored | define `when`'s grammar **or** delete it — never ignore it |
| F12 | parallel / fan-out | ❌ ordered list only | derive the DAG from bindings (free); fix the `repeat` type collision |
| F13 | "plan" is triple-booked | ❌ | name it in §0.4 before it reaches a contract file |

**The cross-cutting one.** F1, F2, F4, F5 and F10 are all the same missing decision seen five times:
**the plan's identity and lifetime.** Until the plan has an owner, a scope key, a revision, and a
defined position in the request, none of the five can be answered, and each will be answered ad hoc
by whoever hits it first — which is precisely how `structure_fresh` was born (F4).

**The build-or-buy note this produces.** Every capability §0.4 needs is already implemented
*somewhere in this repo* — and **nothing combines them**:

| capability | who has it | why it cannot be lifted |
|---|---|---|
| branching (a real DAG) | PlanForge `depends_on` | step list is a hardcoded Python dict |
| parallel fan-out | campaign-service `next_dispatches` | stages are code, unrevisable |
| resume after days | `authoring_runs` heartbeat+sweep · `campaigns` lease+reconcile | scope frozen at launch, no mutation path |
| mid-run plan revision | PlanForge `plan_review_checkpoint` + derived freshness | one job only; no driver of its own |
| an **authorable** step schema | agent-registry `workflows` | no run table, no revision pinning, and a live type bug (F12) |

The plan module's actual job is therefore **not** to invent these four mechanisms. It is to be the
first place they are expressed as *data* over one substrate — and the risk to name in §0.4 is that a
sixth partial implementation is the default outcome.
