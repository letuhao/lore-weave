# The new runtime — an empty architecture with a hard membrane

**Status:** DESIGN. Supersedes `SPEC.md` §1.4's shape debate, which the red team closed
(`DESIGN-HYPOTHESIS.md` §4: nine of twelve assumptions dead).

**PO decision, 2026-08-04:**

> Build the new architecture with **no tools on it**. Then admit tools **one at a time**, selectively —
> never in bulk. The architecture's constraints must be strong enough that a tool built for it **can
> only comply**, and **only a tool built to the new architecture can load into it**. It must carry
> enough metrics and logs to be monitored. Tools built on the old architecture must be **invisible to
> the agent**, and invisible to the new `tool_list` as well. **Only a surface with no noise can prove
> the new architecture works** — the old one is too badly damaged for anything admitted from it to
> prove anything.

**PO clarification, 2026-08-04 — the layering:**

> What we are building is a clean architecture, and **only then** are things declared onto it.
> **Tool, skill and workflow are not layers of the architecture. They are derivatives that consume it.**

---

**PO clarification, 2026-08-04 — this is a Framework *and* a Runtime:**

> What we are designing is a **framework + runtime**, not a framework alone.

---

## 0 · Two artifacts, one frozen interface

They are separated because they have **opposite properties**, and every defect this spec exists to
remove came from code that straddled them.

| | **FRAMEWORK** | **RUNTIME** |
|---|---|---|
| runs at | authoring · build · boot | every turn, in the hot path |
| ships as | an SDK + a generator + CI gates | a library inside chat-service and any other host |
| changes | at deploy · **has history, versions, migrations** | per turn · **no history** |
| enforcement | compile-time, generation-time, boot-time — **a violation cannot ship** | per-turn — **a violation must be recorded** |
| failure mode if wrong | the build breaks. Loud, cheap | a silent filter deletes the answer. **This is the entire audit** |
| owns | P1 Identity · P2 Contract · P3 Admission *(the gate)* | P4 Assembly · P5 Observation · P6 Permission |
| **build or buy** | 🔨 **build** — nothing in 2026 has C-4/C-5/C-6, and registry admission is the field's reported gap | ✅ **buy** — Pydantic AI toolsets + FastMCP transformation (P4), OTel GenAI conventions (P5) |

**The interface between them is the manifest, and it is the only one.**
`contracts/agent-runtime-manifest.json` is *produced* by the framework and *consumed* by the runtime.
The runtime has no other catalog input — that is M2, and it is what makes the membrane real rather
than declared.

### 0.1 The invariant that separates them — and kills arm E by construction

> **The runtime may NARROW the surface. It may never INVENT, and it may never do either SILENTLY.
> Only a deploy changes what is admitted.**

Three terms, kept distinct because conflating them is what produced thirteen mechanisms:

| set | owned by | changes | today's defect |
|---|---|---|---|
| **admitted** — what may ever appear on this runtime | framework, manifest | **only by deploy** | no such concept exists; every filter could reach the whole catalog |
| **advertised** — what is on the wire this turn | runtime | per turn, freely, **within admitted** | **not recorded anywhere** — which is why arm-E deletion is invisible |
| **withheld** — admitted but not advertised, with stage and reason | runtime | per turn | 18 filters, **13 of them silent** |

Progressive disclosure is therefore *permitted* — it narrows. `budget_names_by_tokens` dropping
`book_list` was not wrong because it narrowed; **it was wrong because it narrowed silently, and then
the surface told the model the list was complete.** Under this invariant that is not a policy failure
to be tuned, it is a **defect that cannot compile**: an exclusion that does not register is a runtime
contract violation.

---

### 0.13 Disclosure is not determinism — the observation, and the clause that failed on it *(2026-08-05)*

> 🔴 **THE FIRST VERSION OF THIS SECTION IS RETRACTED.** It was written, red-teamed from four angles
> the same day, and did not survive any of them. What follows is what remained. The retraction is
> kept in place rather than deleted because **the failure mode is the one this document keeps
> repeating**, and a section that quietly improved itself would teach nothing.
> Verdicts: [`RT-0.13-falsifiability`](verification/RT-0.13-falsifiability.md) ·
> [`RT-0.13-cost`](verification/RT-0.13-cost.md) ·
> [`RT-0.13-completeness`](verification/RT-0.13-completeness.md) ·
> [`RT-0.13-purpose`](verification/RT-0.13-purpose.md)

#### 0.13.1 What survives — an observation, not a law

**§0.1 and P1–P6 are, without exception, *disclosure* properties.** *Register the narrowing · assign
`source` structurally · write an outcome on every terminal path · bind no constants · bind
`emits`→`accepts` · advertise while the step is current.* Every one says **"tell the truth about what
you did."** None says **"do the same thing twice."**

That asymmetry is real, and it has one concrete consequence worth carrying: **C-13 requires every
*tool* to declare `re_runnable`; the runtime declares nothing.** We ask more of the thing being
anchored than of the anchor.

**It is recorded as an observation and NOT promoted to an invariant**, because every attempt to state
it as one failed — see §0.13.3. An invariant nobody can falsify is worse than an absent one.

#### 0.13.2 What it produced that is worth having — four live defects, none needing the thesis

Found by adversarial review of the retracted clause. **Each stands on its own measurement**; none
depends on any claim in §0.13.3.

| | defect | evidence |
|---|---|---|
| **U-1** | **Unicode normalisation silently deletes tools from the wire.** `estimate_tokens` weights per *codepoint*, and its Vietnamese band spans the combining-mark block — so the same grapheme costs **1.44× more in NFD than NFC**, measured on a real tool description. That number is **both the sort key and the accumulator** in a hard `break` budget cliff. **No `unicodedata` import exists anywhere in chat-service** | `tokens.py:33,41-51`; `tool_surface.py:109-110,192-201` |
| **U-2** | **the catalogue is a 60 s-cached network fetch that degrades to `[]`.** A gateway hiccup yields a turn with no tools and no record of why — the largest silent narrowing available, currently treated as a feature | `knowledge_client.py:571-624` |
| **U-3** | **`_SKILL_VECTOR_CACHE` is keyed without the embedding model**, and populated with whichever chat model ran first after boot — so the surface depends on turn order. Its twin `_TOOL_VECTOR_CACHE` was explicitly patched for both defects | `skill_router.py:75-76,91-92` |
| **U-4** | **`KnowledgeClient._catalog_meta` is an unkeyed process singleton** — one user's provider-outage signal reaches another user's turn | `knowledge_client.py:283,622` |

**U-1 is arm E's mechanism reached through text encoding**, and it is the single most valuable thing
this exercise produced.

#### 0.13.3 What died, and why — kept because the pattern is the point

| retracted claim | why it is dead |
|---|---|
| *"the 87-vs-101 candidate spread proves the baseline was non-deterministic"* | **it proves input UNDER-SPECIFICATION.** `budget_names_by_tokens` is **pure** — its own docstring says so. 87-for-A / 101-for-B is *a function of its input*; the input list omitted the message. **Three independent reviewers converged here** |
| *"below the model call, the same inputs produce the same surface"* | **there are two model calls, and one is ABOVE the surface** — an embedding call in the skill router shapes what is later assembled. The sentence does not describe this system's topology |
| *"CP-0's unsettleable claim was partly a determinism problem"* | the retrospective attributed it to **instrument non-equivalence**, which determinism does not touch. The figure quoted — *548 against 743* — **appears in no round**; round 6 corrected it to 522. And the rate claim had already been withdrawn, so the re-attribution changed no decision |
| *"`seed` appears nowhere on the provider path — checked, not assumed"* | **false.** `adapters.go:678` forwards it. Grepped in one service, asserted about four |
| *"`code_revision` is nearly free — `build-stack.sh` already computes `GIT_SHA`"* | **false.** It becomes an **OCI image label** read from the host. No Dockerfile consumes it; `os.environ.get("GIT_SHA")` is `None` in every scenario, including the happy path |
| *"the purity boundary is enforced by the membrane gate, which already walks the import graph"* | **false, and the fourth instance of this exact shape in this document.** The gate blanket-permits stdlib, and every ambient capability in Python is stdlib — it is green on `os`, `time`, `random`, `uuid`, `open()`. **The tell was the word "already": true of the walk, false of the check** |
| *"P7 — the surface is a function of its recorded inputs, falsifiable at n=1"* | function-ness quantifies over **pairs**; no single record contradicts it. It needs two records with byte-identical inputs, which this corpus is unlikely to contain |
| *"P8 — the record is idempotent"* | **contradicts this same clause**, which prescribed event-sourcing — append-only by definition. `record_pass` appends *deliberately*: a recorder keeping only the latest state cannot show the deletion arm E is made of. Three sites, three defensible semantics, one sentence pretending otherwise |
| *"the gap is bounded, not guessed — ten ways"* | **two more were proven** (U-1, U-2). A list that asserts completeness fails on one omission |
| *"§0.12 conflated two layers by rejecting replay"* | **§0.12 survives unamended.** A drift gate is a *rejector*, which §0.12 already permits in terms. The rule did not need attacking |
| *"the cheap moment is now"* (for the whole proposal) | true for **3 of 9** items. And emitting `manifest_revision` today would hash an **empty** manifest — a constant-valued column at every write, **the exact P4 violation just repaired** |

**The pattern, stated once so it is quotable:** every dead row above is a *capability or a boundary
written as though it already existed*. The diagnosis underneath survived — seven of eight factual
claims held under attack. **What failed was everything built on top of it**, and it failed the way
§6.1 failed three times before.

#### 0.13.4 What is worth building, on its own merits

None of these needs the retracted thesis. Ordered by value per line, measured rather than guessed:

| | why |
|---|---|
| **`prompt_hash`**, chat-service-local | ~10 lines, and it closes a **currently undetectable** failure: a prompt can change today with nobody noticing. Best value per line in the proposal |
| **`NarrowingRule` as data — with pipeline stage kinds** (`order_by`, `take_while_budget`, `top_k`), not keep-predicates | the motivating stage is a *running accumulator over a sort order*, which a `keep(row)` enum **cannot express** — and 6 of 9 existing fixtures are already named `token_budget`. Time-sensitive: **zero production construction sites exist today** |
| **one canonical-serialisation helper** | the repo carries **18 distinct canonical-JSON implementations, 5 flag variants, 0 shared helpers**, with a precedent of digests permanently baselined because a serializer froze. Time-sensitive: **zero persisted digests exist yet** |
| **the purity boundary on the membrane gate** | ~30 lines, and the gate cannot currently see a single ambient import. Ambient reads *are* confined to one module today — **structurally, not by accident** — which is what makes the boundary cheap to hold |

**`code_revision`, `seed` and `block_hashes` are deliberately NOT here.** Their cost does not fall by
doing them early, two are cross-service, and `block_hashes` **cannot be computed correctly in
chat-service at all** — the cache breakpoint is owned by provider-registry *after* a schema
translation, so a chat-service-side hash can be green while the cached bytes changed.

---

### 0.3 The Ceiling Test — every mechanism must pass it *(PO, 2026-08-04)*

> 🔴 **THIS HEADING WAS DELETED 2026-08-05 AND RESTORED THE SAME DAY.** The edit that inserted §0.13
> above consumed this line and did not put it back, so the entire Ceiling Test spent one commit
> living inside `#### 0.13.4` while **68 cross-references** — including §9's own reading order —
> pointed at a section that no longer existed. Found by an adversarial reviewer, not by the author.
>
> **It is the defect §0.1 names, committed by §0.1's twin, in the commit that introduced it:** a
> section narrowed **silently**, with the index still claiming the list was complete. A structural
> edit that matches on a neighbouring heading must restore that heading, and nothing here checked.

**The question:** is what we are about to build an *enabler* for a stronger model, or a *block* that
buys a weak model a few points while capping a strong one?

**Anthropic's own numbers answer it, and the answer is in a detail nobody quotes.** Tool Search took
Opus 4 from 49% → 74% (**+25pp**) and Opus 4.5 from 79.5% → 88.1% (**+8.6pp**). The strong model still
gained. It gained because **Tool Search defers schemas; it does not delete tools** — everything stays
reachable through search. `budget_names_by_tokens` **deleted**, and `book_list` became unreachable.
That single difference is the whole distance between **+8.6pp** and **0/3**.

> **The test: does the mechanism change what the model KNOWS, or what the model CAN DO?**
> Enriching the **information space** is an enabler. Narrowing the **action space** is a ceiling.

**The asymmetry that makes this the deciding rule:**

- an **enabler's** value decays *gracefully* as models improve — it becomes redundant, never harmful
- a **ceiling's** harm *grows* as models improve — the gap between what the model could do and what it
  is permitted to do widens with every release

| mechanism | verdict | why |
|---|---|---|
| **C-4** `accepts` provenance | ✅ enabler | **adds** an option (name/ordinal); removes none |
| **C-6** `emits` | ✅ enabler | pure information |
| **C-7** error contract | ✅ enabler | a stronger model uses it *better* |
| **C-5** no silent substitution | ✅ enabler | removes a **lie** |
| P5 observation · manifest · admission gate | ✅ neutral | invisible to the model |
| **P6** permission | ⚖️ **legitimate ceiling** | a *should not*, not a *cannot know*. The only justified kind |
| coarse text-in capability running a whole job | 🔴 **ceiling, archetypal** | confiscates planning. Weak model gains; **strong model loses**. Our E2 measured it: 7→1 attribute collapse |
| a fixed ~20-tool surface | 🔴 ceiling | a strong model handles 100+; freezing at 20 caps it |
| a `limit` the model cannot raise · a retry budget it cannot see | 🔴 ceiling | a bound is fine; an **invisible, unappealable** bound is not |

**The design rule this forces:**

> Every constraint must be **visible to the model** and **appealable by the model**, unless it is P6.
> The runtime may narrow — it must register the narrowing (§0.1) **and the withheld thing must remain
> reachable on request.** Defer, never delete.

**The risk this exposes in our own plan.** *The membrane can become a ceiling.* If the new runtime
ships with 30 admitted declarations and admission runs one at a time, a stronger model arriving later
is blocked from the other 285 — not by design, but by **throughput**.

> **Admission is a throughput problem, not a gate problem.** If tools are admitted more slowly than
> models improve, the scaffold becomes the ceiling. This is a tracked risk with a number attached:
> **admission rate must be reported per phase**, and a phase that admits fewer than it retires is a red
> flag, not progress.

### 0.4 Plan and execution are separate — the old architecture fused them *(PO, 2026-08-04)*

**The diagnosis.** Every ceiling in §0.3 has the same origin:

> **The old architecture fuses PLAN and EXECUTION into one act, so the only way it can express a plan
> is by narrowing what the model may do next. That is why it blocks a strong model.**

The evidence is that the plan is never a *thing* in this system — it is only ever a *restriction*:

| where a plan exists today | how it is expressed | what the model can do with it |
|---|---|---|
| rails | advance a step, gate what is advertised at that step | **nothing** — it cannot see it, edit it, or disagree |
| 43 intent regexes | keyword → pin a workflow → narrow the surface | nothing; it is not told a plan was chosen |
| F18 auto-load | mutate the tool set mid-turn | nothing |
| `workflows` table | 12 rows of real steps + `done_when` — **genuine plan data** | **nothing: there is no runner** |

The last row is the proof. **The one place the repo stored a plan as data, it could not execute it; the
places it could execute, it stored no plan.** Plan-as-data and plan-as-gate were built as separate
things, and only the gate was ever wired.

**The separation.**

```
   PLAN  (data — inspectable, revisable, cheap to re-present)
     │      produced by: the model itself · a workflow template · a human
     │      steps[] : { declaration, accepts-bindings, emits-bindings, done_when }
     ▼
   EXECUTE  (follows the plan; binds emitted values into later steps' arguments)
            the tool surface is UNCHANGED by the plan — the plan informs, never gates
```

**Why this passes the Ceiling Test where a rail does not:**

| | strong model | weak model |
|---|---|---|
| **rail** (fused) | 🔴 confiscates planning it does better than us | 🟢 helps |
| **plan-as-data** | 🟢 writes its own; the mechanism records and gets out of the way — **or it ignores it** | 🟢 receives a template as scaffolding |

The action space is identical in every case. **Only the information space changes.** That is the
definition of an enabler, and it is the observed difference between Claude Code — which plans for
itself, with plan mode *optional* — and the tools that compensate for a weaker model by **forcing** a
plan before a long action.

**This is not a fourteenth mechanism. It is a split that deletes one.** Rail gating, intent-regex
pinning and mid-turn surface mutation all exist *only* to express a plan by restriction. Once the plan
is data, they have no remaining job.

#### Workflow, redefined

> **A workflow is not a rail. It is a PLAN TEMPLATE — a prior over the plan structure that a model may
> adopt, adapt, or ignore.**

This restores the 12 seeded rows to usefulness (they are already steps + `done_when`) and re-scopes the
dead FSM lane: **build a plan executor, not a rail engine.** A11 died because no runner exists; it is
revived as a smaller thing than the one that died.

#### The part that matters most — the plan is where carry-forward lives

**This closes the 61.8%.** The model receives `entity_id:019fafa2-…` at step 12 and sends `"0"` at
step 16 because the only carrier between them is **the conversation** — and RT3 measured that carrier:
a pin-blind `LIMIT 50` window, tool results evicted beyond the newest 3, arguments dropped entirely by
the transcript renderer. **The conversation is a lossy carrier and we were relying on it to hold
identifiers.**

A plan structure is a *good* carrier: small, structured, and cheap enough to re-present every turn
without touching the cache prefix.

> **C-6 `emits` and the plan are the same mechanism seen twice.** `emits` declares what a step hands
> forward; the plan **binds** it to the step that consumes it. The executor can then verify the
> binding — and, where the binding is unambiguous, **satisfy it directly instead of asking the model to
> retype a UUID it has already seen.**

That is the one part of this design with no prior art in Dify, in the 584-tool routing paper, or in
Tool Search — and it is now the part with the clearest mechanism.

### 0.5 Recovery — what happens when execution fails, and what a guardrail is for *(PO, 2026-08-04)*

**The hole:** the plan is made, execution fails. How does the model know to stop, revise the plan, or
build a new one? A strong model does this well — Opus will **ask the user and wait** when it does not
understand. Our measured behaviour is the opposite: **74% byte-identical repeat calls.**

#### The error must be classified twice, at two different levels

C-7's four classes are **call-level**, set where the failure is raised. The plan asks a *different*
question, and the answer is not derivable from the call alone:

| plan-level scope | means | correct transition |
|---|---|---|
| **step-local** | the call failed; the step is still right | retry, modified, against a **visible** budget |
| **binding-invalid** | the value bound from an earlier step's `emits` is wrong or stale | **invalidate the binding and re-run the producing step** — never ask the model to retype it |
| **plan-invalid** | the plan's premise is false — the thing does not exist, permission is refused, the world moved | **replan** |
| **needs-human** | the ambiguity cannot be resolved from anything available | **suspend and ask** |

**The mapping is not one-to-one, and that is the argument for plan-as-data.** The same
`terminal_permanent` means *binding-invalid* when the argument was bound from a prior step, and
*needs-human* when it came from the user. **Only the plan knows which.** A call-level taxonomy alone
cannot distinguish them — which is why C-7 by itself would not have closed this.

#### What a guardrail is for

> **A guardrail's output must be a PLAN STATE TRANSITION, not a stop.**

Today there are six breakers; every one mints an error-shaped message and hopes the model reads it.
**They are 65.7% of everything the model sees as an error.** That is blocking — the archetypal ceiling.

Redesigned, the guardrail is the **floor for when the model fails to self-diagnose**, and it keeps
three properties that make it an enabler:

1. it fires only on **deterministic** evidence — an identical call repeated, a budget spent — never on
   a judgement about whether the model seems confused;
2. its output **adds information** (the transition, plus what succeeded and what failed). It removes
   no tool;
3. **a strong model reaches the transition before the guardrail fires.**

Property 3 is the test, and it is measurable: **guardrail fire-rate must fall toward zero as model
strength rises.** If it does not, we built a ceiling and mislabelled it.

#### Replan must not lose the completed work

Today a stuck turn ends `interrupted` and everything is lost. With the plan as data, the replan input
is **the plan + the completed steps + their emitted values + the failure** — *not* the failed
conversation. This is R11's "no contaminated retry", and here it is a consequence of the structure
rather than a rule bolted on top.

#### Asking the user is a SUCCESS state

The machinery already exists and is wired to exactly one thing: `suspended_runs` +
`finish_reason='awaiting_input'`, reached only from an approval card. **There is no path from *"the
model is stuck"* to it, and no MCP `elicitation` anywhere in the repo.** The expensive half — suspend,
persist, resume, expire — is built. The missing half is a *reason to enter it*.

> **A model that asks a question is behaving correctly.** `awaiting_input` is a successful terminal
> state, not a failure, and the UI must not badge it as one.

#### 🔴 Correction — `binding-invalid` as first written prescribes data corruption

The table above says *"invalidate the binding and re-run the producing step."* **That is wrong as an
unconditional rule, and it is this design's own defect, not the old architecture's.** If the producing
step is a *create*, re-running it duplicates. The design's own worked example —
`glossary_propose_entities` — is a create; `kg_project_create` was measured at **×57 in one turn**.

Worse, the repo's confirm path burns the JTI **before** the effect and is fail-closed
(`glossary-service/internal/api/action_confirm.go:175-186`), so a re-run returns `422 already
confirmed`. Correct recovery there is walking back **two** steps — which the four-scope transition
cannot express at all.

> **C-13 — `re_runnable` ∈ `idempotent | duplicates | single_use`.** Declared, checked at boot, no
> runtime machinery. Only `idempotent` may be re-run automatically. `duplicates` requires the model
> or a human to choose. `single_use` escalates straight to **plan-invalid**.

**And the world is not mentioned anywhere in the four scopes** — they are pure control flow. A
`undo_hint = {tool, args}` already rides on every Tier-A write in two services and is read at
`stream_service.py:4492` — **but only to render a button for the user.** The executor never reads it.
The replan input must therefore include a **completed-effects ledger** `{step_id, emitted,
undo_hint|null}`. Ceiling test: a ledger plus an option is an enabler; **automatic rollback would be a
ceiling** and is not proposed.

#### A fifth scope, and the four silent exits

**Cancellation is not a failure**, so it fits none of the four scopes — yet today it is badged
`interrupted`, which §0.5 has just declared a defect. **That makes this section's own baseline metric
uninterpretable until cancel has a terminal state of its own:** add **`abandoned-by-user`**. The
deterministic detector already exists (`rail.user_abandoned_rail()`).

**One mechanism settles four measured holes.** A plan can today reach a non-`done_when` end, silently,
in four distinct ways:

| # | silent exit | verified |
|---|---|---|
| 1 | effects committed, then a failure with no ledger | `undo_hint` read only by the FE |
| 2 | `needs-human` never answered | **`sweep_expired_runs` has ZERO callers** — its docstring claims it runs periodically |
| 3 | process death mid-plan | turns checkpoint at `finish_reason='streaming'`; **nothing ever reads a `'streaming'` row back** |
| 4 | user cancels | no scope; badged `interrupted` |

All four are the same rule: **a plan that ends anywhere but `done_when` must name what is live and hand
it to a human.** That is one mechanism, not four.

#### Why this is the argument for rebuilding, and the surface-size argument never was

**PO, 2026-08-04:** *if a step goes wrong, how does the model know it went wrong — and where? The old
logic has no definition of this in the contract, so the model cannot tell, and it loops.*

This is the strongest justification available for a rebuild, and **it is the one the red team never
touched.** The surface-size arguments (A1 "the set, not the model"; A2 "~20 tools") were both killed.
This one is not a matter of degree — **failure is simply not expressible in the current contract**, and
that cannot be retrofitted onto 315 tools each reporting failure in its own private way.

Three distinct ways the model cannot tell, all measured here:

| # | shape | measured | consequence |
|---|---|---|---|
| 1 | **failure disguised as success** — `ok=true` | silent `chapter_id` substitution; **263 no-op writes** | the model does **not** loop. It proceeds on a false premise and produces wrong work. **The worst kind, and invisible to every `ok=false` autopsy** |
| 2 | **our prose disguised as a tool error** | breakers mint the same `{tool_call, ok, error}` shape with **no field marking the source**; **65.7%** of errors | the model retries what was never retryable, and blames the tool |
| 3 | **failure with no locus** | a misspelled key is dropped by the Go typed struct, then reported as *"missing required"* | **the model sent the field. We dropped it. Then we told it the field was missing** |

> With all three live at once, `book_get_chapter` × 19 — nineteen different invented `chapter_id`s
> against one identical error — is not a weak model. It is **correct behaviour from an agent told
> *"wrong"* and never told *"wrong where"*.**

#### C-12 — fault locus *(new contract clause)*

Every rejection must name **the field path it rejected**, the reason, and what would be accepted.
And the corollary the measurement demands:

> **A field the server drops may never be reported as absent.** Dropping-then-blaming is the defect
> that makes a model unrecoverable, because the one repair it can attempt — send the field — is the
> thing it already did.

C-12 is an enabler under §0.3: it adds locus information and removes no option.

#### The invariant this produces

> **No plan may terminate except by satisfying its `done_when` or by reaching a human.
> `interrupted` is a defect, not an outcome.**

The replan budget is stated *in the plan*, so the model can see it and spend it deliberately (§0.3 —
visible and appealable); exhausting it transitions to **needs-human**, never to a silent death. This
gives an immediate baseline metric against today's telemetry, where `interrupted` is common.

---

### 0.6 🔴 Correction — admission cannot score on `ok=true`

**The circular definition.** Every P5 field scores an outcome as `ok=true`. **C-5 exists precisely
because `ok=true` can be a lie** — a silent substitution returns success on the wrong object, and a
no-op write returns success having changed nothing. So §6's *"29 consecutive successes"* gate, as
written, **has no scoreable outcome.**

> **Admission scores on the plan's `done_when`, not on the call's `ok`.**

`done_when` is already required to be *a predicate over real state* (C-8, and §2.2 condition 3). It is
the ground truth this design was missing, and it was already in the contract — unconnected. A step
counts as a success when **the world moved as the plan said it would**, not when the transport
returned 200.

Consequences, each a correction to an earlier section:

- **the wrong-object detector is mis-located.** §5.5 specifies a *counter*; a counter with no detector
  ships reading zero. Only substitution-shaped cases are detectable at the call
  (`stream_service.py:1619`); **the 61.8% carry-forward class is detectable only from plan-binding
  state.** The detector belongs with the plan bindings, not with P5.
- **`advertised_tools` must be `jsonb`, an array per pass — not `text[]`.** A scalar records only the
  last pass and therefore loses the *mid-turn* deletion the field exists to catch.
- **`noop_write_counts` is a per-turn in-memory dict** (`stream_service.py:1895`), never persisted.
  The figure quoted elsewhere in this corpus as *"263 no-op writes"* is **263 breaker cap-hits**,
  counted by matching message text. The underlying population is larger and unmeasured — a lower
  bound, not a count.
- **the guardrail shadow arm must be in v1.** §0.5's property 3 (*fire-rate → 0 as models strengthen*)
  is unobservable if the guardrail blocks: evaluate, record, and do **not** act, for one release.
  It cannot be retrofitted.

### 0.7 Correction to the P5 buy decision

`BUILD-VS-BUY.md` says *"✅ buy — OTel GenAI conventions (P5)"*. Measured against the actual
conventions, **zero of our five fields map cleanly**: `withheld_tools`, `source` and the wrong-object
counter have **no standard attribute at all** (OTel models what happened, never what was suppressed);
`gen_ai.tool.definitions` is opt-in, carries schemas rather than names, and is a span not a column.
The conventions have also **relocated**, with the main-registry `gen_ai.*` entries now marked
deprecated, and they remain at *Development* stability. Locally there are **zero manual spans** in
chat-service and the OTLP endpoint is empty.

> Revised: **⚖️ buy the vocabulary, build the store.** Take `error.type`, `gen_ai.operation.name`,
> `gen_ai.tool.name`, `gen_ai.usage.*`, `gen_ai.execute_tool.duration` (our missing latency) and the
> `gen_ai.evaluation.*` shape for ground truth. Do not expect the store.

**One structural constraint found:** `workflows` lives in `loreweave_agent_registry` and `chat_messages`
in `loreweave_chat` — **different databases.** Plan telemetry cannot join to plan templates in SQL, so
the plan record must carry the template identity by value.

---

### 0.8 🔴 P6 under plans — assent to a job is not representable, and replan launders permission

**The missing middle.** The system expresses exactly two things:

| | scope | binding |
|---|---|---|
| confirm token | **"yes, this one call"** | single-use `jti`, **params frozen inside the HMAC**, 10-minute TTL |
| "Always allow" | **"yes, this tool, forever"** | unbounded in time, count **and amount** |

**There is nothing in between — and `SPEC.md` §2.2 defined the entire FSM lane by condition 4, *"the
user's assent is to the whole job."* The lane was defined by a capability that does not exist.**
Plan/execute separation makes that missing middle the *normal* case, and a friction-minimising UI will
push users to the unbounded option.

**🔴 Replan is a permission-laundering machine as specified.** §0.5 mandates replan; §0.2 keeps P6
unchanged; **neither section mentions the other.** Approve a plan, let it fail, replan — and the
approval carries into a plan the user never saw. The repo has the right instinct twice at call level
(`enabled_ops` is a confirm-*time* input; translation re-prices with a 409 at 1.25× / +$0.50) and
**neither has a plan-level analogue**.

> **An approval binds to a plan hash over its gated steps.** A replan that changes any gated step, or
> raises the estimate past a stated tolerance, **invalidates the approval and must re-ask.** A replan
> that changes only ungated steps does not.

**Two channels are conflated into one that is typed for permission.** `pending_tool_call` is a single
`{id, name, args}` and resume branches on a closed set of consent verbs — unknown answers fail to
denied. There are **zero occurrences of `elicit` in the repo.** But *needs-human* and
*needs-permission* are different in kind: **an answer is DATA that binds into a later step's argument
(a C-6 `emits` source); a permission is a decision only the principal can give.** One mechanism, two
reasons — and today only the permission reason can enter it.

**Verified: "Never allow" is enforced at execute and is invisible at advertise.** Zero references in
the advertise path; the check sits inside the execution loop and its error message asks the model
*"Do not ask to run it again."* **That is prose doing the job the surface should do by construction** —
and the user's own ban, the purest expression of intent in the system, **registers nowhere in the
§0.1 withheld ledger.**

**Ceiling Test verdict — and it is not the one expected.** P6 is the *permitted* ceiling (§0.3), so it
does not fail there. **It fails §0.3's visibility clause**, on three counts the model cannot see
*before it plans*:

1. **which steps will gate** — tier is read per-call inside the loop, after earlier steps commit, and
   one turn allows one suspend, so a 3-gate plan costs 3 round trips. Every input is static: this is
   computable at plan time as a **permission pre-flight**;
2. **which tools are permanently denied** — the "Never allow" finding above;
3. **what the whole job will cost** — budgets exist per-tool, per-user and per-job, and **the sum is
   the one number no surface shows.**

**And the terminal invariant is unsatisfiable for a third-party key** (C3): the gateway returns
`pending_human_approval` and the turn ends — no polling tool in `TOOL_POLICY`, no elicitation, no
suspend. *"Reach a human"* has no human to reach. That lane needs its own terminal state, stated.

---

### 0.9 🔴 Corrections to admission (P3) and identity (P1)

**The throughput arithmetic, computed at last.** §0.3 demanded the number and never produced it:

| | |
|---|---|
| declarations on the wire | **339** (315 tools + 12 skills + 12 workflows) |
| model cadence (§0.3's own Opus 4 → 4.5 reference) | 26 weeks |
| **⇒ admissions needed to not become a ceiling** | **≈13 / week** |
| §6.3's 29-success bar × §6.2's **solo** surface | **377 solo turns / week**, ~754 with §6.4 |
| **the entire product generates** | **≈414 tool calls / week** |

> **As written, admission needs nearly as many synthetic turns as the whole product produces — and
> §6.2's "solo" forbids production traffic from ever counting.** That contradicts the PO's *"prove it
> on a live run."*

**The resolution is that §6.2 misread the requirement. The isolation belongs to the RUNTIME, not the
surface.** The noise the PO ruled out is *old-architecture declarations*, not other compliant ones. A
declaration therefore proves itself **on the new runtime alongside other admitted declarations**, where
production traffic accrues evidence for all of them simultaneously. §6.2 is amended; §6.3's arithmetic
stands.

This also removes the contradiction S4 found between **§6.2 (solo) and §8 Brick 4** (a two-step pair —
*"the one that matters most"*), 130 lines apart in this document.

**🔴 Amending the contract currently invalidates every prior admission.** §6 says *"the failure is the
finding — the contract is what gets amended."* But declarations #1–#30 were admitted against the older
contract: grandfather them and two contract generations coexist (the noiseless premise dies); re-admit
them and the contract can never be amended in practice. **This is the design's intended mode of
operation and it has no mechanism.** Required: a `contract_version`, an `admitted_against` stamp, and
the rule that a **backward-compatible** amendment leaves prior admissions standing while a **breaking**
one moves them to a re-admission queue **without removing them from the runtime**.

**🔴 M4's premise is Python-only — verified.** `NewToolMeta` (`sdks/go/loreweave_mcp/meta.go:184`)
**builds a map and returns it; it validates nothing.** `MustValidateToolMeta` has **14 call sites**
across all Go services while glossary alone calls `NewToolMeta` **58 times**. The repair is to make
construction *be* the validation: an `Admitted[D]` type with a private field, so a bypass is a compile
error rather than a missed lint.

**🔴 §3.1's admission metric cannot fire.** It reds when a phase *"admits fewer than it retires"* — but
§1 says the plan **deletes nothing**, so retirements are structurally zero. Replace it with the real
number above: **admissions/week against the 13/week target.**

**🔴 P1 has no clause in the contract, so the first admitted declaration has no identity.** C-1…C-12
require no id, owner, lifecycle state or version, and M1's gate is a *row count*. **This bites at
brick 1.** Add **C-0 (identity)** — id, owner, lifecycle state, contract version — as the first thing
M4 checks.

**Two identity SSOTs are specified.** R1's `mcp-tool-catalog.json` holds `lifecycle_state`, while M1's
`agent-runtime-manifest.json` is the runtime's *only* input and is generated solely from new
declarations — **so the runtime never sees a lifecycle state, and R9.3's policy layer has nothing to
read.** One file, or the policy layer is decorative.

**Dual identity across the membrane, at brick 2.** The old runtime stays live as the control group
(§7) while bricks 2–5 rebuild capabilities that already exist. **Same name** ⇒ `catalog.ts:78`'s
`if (map.has(t.name)) continue` silently keeps the first, with no warning, **outside M2's import
gate**. **Different name** ⇒ the control-group comparison has no join key. Neither is acceptable
implicitly: add an explicit **`counterpart_of`** edge, and make the collision loud.

**Re-measured today:** 202 advertised / 114 retired; **53 successor edges → 16 targets (3.3:1)**;
**61 of 114 declare no successor at all**; 2 edges terminate on an already-retired target; 3 cross an
owner-service boundary. Q14's "aggregate usage along the edge" is therefore **undefined for 54% of
retired declarations**.

---

### 0.10 🔴 The plan module — three corrections, one of which breaks §0.6

**1. `done_when` is not the ground truth §0.6 assumed.** It draws on a **closed 9-key vocabulary**
(`contracts/book-state-keys.contract.json`), all book-global counters with hardcoded probe routes. A
model-authored step cannot mint one — and the contract file **documents its own failure mode**:

> *"a renamed key or route disables the gate (**reads as satisfied, or falls back to the call log**)."*

*Falls back to the call log* is *"the tool ran"* is **`ok=true`**. §0.6 replaced `ok` with `done_when`;
`done_when` silently degrades back to `ok`. **Third layer of the same defect.**

Two fixes, both required:

> **Fail-safe:** a completion predicate that cannot be evaluated yields **`unknown`, never `satisfied`**
> — the same direction as C-7's unclassifiable-becomes-terminal rule.
>
> **Two levels of `done_when`.** **Step-level is derived from the step's own `emits`** — *did this step
> produce what it declared it would?* Always observable, no vocabulary to run out of, and it is C-6
> seen a third time. **Plan-level** keeps the 9-key book-state contract, because *the whole job*
> genuinely is a claim about world state.

**2. 🔴 §0.4's cache claim is false as built.** I wrote that a plan is *"cheap to re-present every turn
without touching the cache prefix."* Measured: `pinned_rail_text` sits in tail block #14 **inside** the
BP2-cached region (`system_message.py:73`) and its bytes change every turn (live counters, cursor) —
RT3 priced that at **+65% uncached**. And the message tail cannot hold it either: `LIMIT 50` and
`persist_auto_compact` delete it with **no reachable pin** (RT3-A7). **There is currently no position
that is both durable and cache-safe. Finding that position is a design task, not an assumption** — and
it is measurable today with the existing `context_breakdown` column.

**3. The plan has no home, so it evaporates.** Today's nearest thing is re-derived **every turn from a
regex over the current user message** (`stream_service.py:5427-5438`) — one off-topic turn and it is
gone. Worse, on suspend→resume only the mode-binding pin is recomputed
(`_compute_rail_drive_context:611-615`), so **an intent-pinned plan is lost at the confirm card** —
precisely where §0.8 needs it to still exist for the approval to bind. §0.4 names no owner, lifetime or
storage. **This is the module's first design decision and it is currently unmade.**

**Ranked below these, and recorded rather than solved here:** a judgement step cannot be expressed
(`canon-check` has three steps and **no `done_when`**, because the grammar admits only integer
comparisons); a **model-authored** plan is the one plan never checked for C-6 satisfiability — and the
check must **report, never block**, or it fails the Ceiling Test; and `repeat` is a **live bug** —
the seeds write a boolean into a `string` field whose unmarshal error is discarded, voiding the flag on
all 12 rows (this is P0-1, already known and still open).

**The cross-cutting note is the one to act on:** every capability §0.4 needs already exists somewhere
in this repo — PlanForge's DAG and derived freshness, campaign-service fan-out, `authoring_runs`
heartbeat-resume, agent-registry's authorable schema. **Nothing combines them, and a sixth partial
implementation is the default outcome** unless the plan's identity and lifetime are decided first.

---

### 0.11 ✅ DECIDED — where the plan lives: artifact outside, working memory inside *(PO, 2026-08-04)*

> **🔴 NARROWED 2026-08-05 (PO) — and the narrowing removes a checkpoint item's subject.**
>
> *"The agent's **executive** plan is used only inside its session. It is completely different from
> planforge and the writing-spec architecture. **Persisting it is noise, and it is also wrong.**"*
>
> **Two things were being called "the plan" and only one of them is a document.** The **authored
> artifact** — the writing plan, planforge, the writing-spec architecture — is user-facing, already
> exists, and is what "artifact outside" refers to below. The **executive plan** the agent runs is
> working memory: session-scoped, and it does not become a document by being written down.
>
> Persisting it is not merely redundant. It puts a second thing that looks like a plan next to the
> user's real one, and **a reader cannot tell which is authoritative** — the same confusion §0.8
> closes for permission and §0.1 closes for the tool surface.
>
> **🔴 AND THE FIRST READING OF THIS RULING WAS TOO STRONG — corrected within the hour, by the PO.**
> I wrote that CP-3.1's subject was *gone*. It is not. **The executive plan must have a representation
> in the source**, or there is nothing to execute, nothing to project into the context, and nothing
> for `emits`→`accepts` to bind against. The question *"then how does the agent read it?"* has no
> answer under my first reading.
>
> **The reconciliation is one word: "outside" above means outside the CONTEXT WINDOW, not "in the
> product's document library."** This section exists because *the context is a lossy carrier* — RT3
> measured `LIMIT 50`, pin-blind eviction, tool results dropped past the newest three. The complete
> version must live where the context cannot truncate it. **That is a runtime-state requirement, not
> a publishing one**, and the two were conflated by the word "artifact".
>
> | | keeps | loses |
> |---|---|---|
> | **executive plan** | a representation in src · full fidelity outside the context · a **hash** · a lifetime bounded by its session | any place in the user's document library, beside planforge and the writing specs |
>
> **What must survive the narrowing, because §0.8's closure rests on it:** permission-laundering is
> closed by *the artifact has a **hash***, and an approval binds to that hash — a replan changes it and
> invalidates an approval over changed gated steps. **The hash does not require the plan to be a
> product document.** The clause *"the thing the user approved is a thing they can read"* needs the
> gated step readable **at approval time**, which the confirm card already provides; it does not need
> a persisted document.
>
> **So CP-3.1 is rescoped, not deleted:** session-scoped runtime state, hashed, never surfaced as a
> user artifact. The **completed-effects ledger** (CP-3.5) is the one part with a reason to outlive
> the session on its own terms — a replan that cannot see what already ran is how `kg_project_create`
> fired **×57 in one turn** — and it is a record of *effects*, not of a plan.

> The plan is **authored outside the context** at full fidelity, **compressed into the context** as
> working memory, and the runtime helps the agent remember **the plan and what it has already made**.
> Lossy inside; a complete version always exists outside. **Spec-file + working-memory.**

**This closes the module's blocking decision, and it does so by conceding the thing the design kept
resisting: the context is a lossy carrier.** RT3 measured that carrier — `LIMIT 50`, pin-blind, tool
results evicted past the newest three, arguments dropped by the transcript renderer. §0.10 then found
there is **no position in the prompt that is both durable and cache-safe.** Putting the authority
*outside* dissolves the problem instead of solving it.

**Two representations, one authority.**

| | **artifact** (outside) | **working memory** (inside) |
|---|---|---|
| fidelity | complete | compressed |
| authored by | model · template · human | **derived — never authored** |
| changes | on plan events | when the artifact does |
| if they disagree | **wins** | is regenerated |

#### The compression rule is the whole design — and one class must never be compressed

> **Identifiers are never lossy.** A summarised UUID is a lost UUID, and that *is* the measured 61.8%
> carry-forward class. Everything else may be compressed.

| never compressed | may be compressed |
|---|---|
| the step list and the current position | rationale and prose |
| **every `emits` binding produced so far** (C-6) | completed-step detail |
| the current step's `done_when` | alternatives considered |
| the completed-effects ledger (§0.5) | history beyond the ledger |

The second row is the PO's *"and what it has already made"* — and it is the same object S3 required as
replan input. **The carry-forward fix and the recovery ledger are one structure, not two.**

#### It must declare its own lossiness

Per §0.3, a silent narrowing is the defect this whole spec exists to end. **The working-memory
projection must state that it is a projection and how to obtain the full artifact** — the MCP
`ResourceLink` shape (BUILD-VS-BUY §1), applied to the plan. A compressed plan that presents itself as
complete is arm E with a different subject.

#### What this resolves, and what it now demands

**Resolved:** §0.10's missing home and its false cache claim; RT3's A7 kill (the conversation was never
supposed to be the carrier); S7-M4's live slug re-resolution — **the artifact holds a frozen copy**;
and S3's four silent exits, which all become *"the artifact still says what is live."*

**And it closes §0.8's permission-laundering by construction:** the artifact is a document, so it has a
**hash** — which is exactly the `plan_version` binding that was missing. **An approval binds to the
artifact hash.** A replan writes a new version, the hash changes, and an approval over changed gated
steps is invalidated automatically. *The thing the user approved is a thing they can read.*

**Two new obligations this creates:**

1. **The projection is generated, with a gate.** Two representations can drift; the projection must be
   **derivable from the artifact**, checked, never hand-maintained. Otherwise this becomes the repo's
   eighth hand-synced copy.
2. **The projection changes at plan events, not per turn.** §0.10 measured `pinned_rail_text` breaking
   cache because its bytes moved every turn (live counters, cursor). **Stable between transitions** is
   a hard requirement, not a preference — and it is the cheap half of the +65% problem.

#### The artifact's shape — SPEC and STATE are separate, and that is forced

A contradiction has to be resolved before any field is named. **§0.8 binds an approval to the plan's
hash. §0.5 has the executor writing status, emitted values and committed effects as it goes.** If those
share one hash, **every completed step invalidates the user's approval** — the mechanism defeats itself
within one step.

> **The plan is two objects.**
> **SPEC** — *what we intend*: immutable, versioned, **hashed**. Steps, bindings, `done_when`.
> **STATE** — *what happened*: mutable, append-only. Status, emitted values, effects, outcomes.
> **The approval binds to the SPEC hash. Execution never changes it.**

A revision writes a **new SPEC version**; an approval over changed *gated* steps is invalidated, and
one over changed ungated steps is not (§0.8). That is the whole permission-laundering fix, and it only
works because the two are split.

| | SPEC (versioned, hashed) | STATE (mutable) |
|---|---|---|
| per step | `declaration` + `contract_version` · `accepts` bindings · declared `emits` · step `done_when` · **gates?** (from the §0.8 pre-flight) | `status` · **actual emitted values** · `outcome` (C-14) · effects ledger `{undo_hint, committed}` |
| per plan | goal · ordered steps · plan-level `done_when` · **template identity by value** · replan budget | current step · replan count · terminal state |

**Template identity travels by value, not by reference.** `workflows` lives in
`loreweave_agent_registry` and the plan will live beside `chat_messages` in `loreweave_chat` — **two
databases, so there is no foreign key to have.** Copying also fixes S7-M4: today a rail re-resolves its
slug live every pass, so **editing a template mutates a run in flight**.

**One writer during execution.** The model *proposes* — which produces a new SPEC version, never an
in-place edit. The **executor** is the only writer of STATE. That is what keeps the hash still while a
plan runs.

**Storage: one `plans` table in `loreweave_chat`, one live plan per session.** Session-scoped so
suspend/resume reaches it, durable so process death is recoverable (S3-M6: turns already checkpoint at
`finish_reason='streaming'` and **nothing ever reads those rows back**), and a row rather than a column
so versions are rows. S3-M4's concurrency rule attaches here: a second message during a live plan
**routes into it** — a hard reject would be a ceiling.

**What the projection takes from each:** the never-compressed set (§0.11) is *step list + position*
from SPEC and *every emitted value + the effects ledger* from STATE. **The identifiers all come from
STATE** — which is the concrete reason STATE must be re-presented losslessly while SPEC prose may be
summarised.

#### Two adjustments from the external survey *(BUILD-VS-BUY §4b)*

Every mature system surveyed — Kiro, LangGraph, Temporal — **separates specification from execution
state, and none puts execution state in the document.** The split above was derived from our own
constraints before the survey; it is now corroborated rather than invented. Two changes follow:

1. **STATE is event-sourced, not snapshotted.** §0.5's replan input is *"what has already committed"*,
   and an event history answers that natively while a snapshot does not. Temporal's model — replay to
   reconstruct, resume at the failed step without re-running completed work — is the fit. **We already
   write the events:** turns checkpoint per tool call at `finish_reason='streaming'` and **nothing ever
   reads a `'streaming'` row back.** The write half exists; only recovery is missing.
2. **The binding format is measured, not chosen.** Markdown is the industry default for the human
   surface and the most token-efficient of the compared formats — but the one benchmark that compared
   comprehension of **nested data** favoured YAML, and `accepts`/`emits` bindings *are* nested data.
   Different model, different task. **§0.12 forbids importing it: measure on our model, in brick 0.**

**Drift-checking is a separate mechanism, not an assumption.** Kiro does not trust the spec and the
work to stay aligned — it runs a hook that flags divergence. Our equivalent is already required: the
projection is **generated with a gate** (obligation 1 above), never hand-maintained.

**Still open, and it is one question, not many:** whether a plan is *also* a user-facing document in
the product sense (§0.8 argued an approval should be *a thing the user can read*). That decides whether
this gains a UI — but not its shape, so it does not block brick 4.

---

### 0.12 🔴 Evidence discipline — a test can reject, it cannot admit *(PO, 2026-08-04)*

> *"Is a measurement over test data that has never been in production trustworthy?"*

**No, and this project has five instances of being misled by exactly that** — all found while writing
this document:

| green in test | true in production |
|---|---|
| the **224-tool sweep, 211 passing** — MCP-direct, **zero LLM turns** | it certifies a tool measured **0/101** |
| `TestSchemaSQL_SameActionMeansTheSameThingInEveryRail` | the field it guards **never reached a consumer** |
| `find-tools.spec.ts` *"mirrors GROUP_DIRECTORY"* | it mirrors **a third copy typed into the test** |
| the tool-liveness generator's byte-equality test | it proves the manifest is **consistently copied**, never that it is **current** |
| *(this session)* duplicate books ⇒ "the agent duplicates real content" | the duplicates were **test debris** — `t` ×49, `ATOM-EDIT F2 FIXTURE` ×33 |

**The asymmetry, stated as the rule:**

> **A failure in test is information — it reproduces a real defect. A success in test bounds nothing.**
> Test evidence may **reject** a declaration. It may never **admit** one.

That is why every load-bearing finding in this corpus is a *negative* result on a real artifact
(arm E 0/3, the 0/101 tool, 61.8% carry-forward, `sweep_expired_runs` with zero callers, `NewToolMeta`
validating nothing) and every weak claim is a *positive* one (arms C/D at 3/3 — which bound failure
only at 63.2% against a 54.2% baseline).

**Honest limits of our own "production" corpus:** one dogfooding user, a shared dev database with test
debris mixed in, no seed on the chat path, temperature 0.2 in the POC against 0.0 in production, and
**three rows of user feedback**. It can be decontaminated. It cannot be enlarged.

#### Consequence — admission is a bound that tightens, not a gate that opens

§6.3's *"29 consecutive successes"* cannot be a precondition: at **414 tool calls/week across the whole
product** it is unaffordable, and if the runs are synthetic they measure the harness.

> **A declaration ships with `asserted_bound: unknown` and the bound tightens with real use.**
> The bound is **always stated**, never assumed, and it is **visible** — which makes it an enabler
> under §0.3 rather than a ceiling.

The two halves of admission therefore have different evidence rules, and only one of them is a gate:

| half | evidence | is it a gate? |
|---|---|---|
| **contract check (M4)** — the declaration is well-formed | **test, at boot** — it *rejects*, which is what tests can do | ✅ **yes** |
| **behavioural bound (§6.3)** — how often it actually works | **production traffic on the new runtime**, accumulated | ❌ **no** — it is published, not required |

This also supplies the *principled* reason for §0.9's arithmetic fix: the isolation must be the
**runtime**, not the surface, because a solo surface can only ever generate synthetic evidence — and
synthetic evidence cannot admit anything.

---

## 0.2 · What the architecture is — and what it is not

The architecture is a **substrate of six primitives**. Nothing in it knows what a "tool" is.

| # | primitive | answers |
|---|---|---|
| **P1 · Identity** | a declaration has a stable id, an owner, a lifecycle state, a revision history | *does this exist, whose is it, is it safe to retire* |
| **P2 · Contract** | what a declaration says about itself — inputs **with provenance**, outputs **with what they hand forward**, errors, post-conditions, bounds | *can a caller use this without guessing* |
| **P3 · Admission** | the gate: mechanical at boot, evidential at live run | *is it allowed to exist on this surface* |
| **P4 · Assembly** | what reaches the model this turn, from exactly one input | *what is on the wire, and why* |
| **P5 · Observation** | advertised · withheld · source · outcome · wrong-object | *what actually happened* |
| **P6 · Permission** | tier · scope · confirm-token · spend | *may this caller do it* — **kept unchanged; the spine is sound** |

**Tool, skill and workflow are three kinds of declaration over P1–P6**, differing only in arity and
ordering:

| kind | is | adds |
|---|---|---|
| **tool** | one executable declaration | an executor |
| **skill** | a named **set** of declarations + guidance | no execution of its own |
| **workflow** | an **ordered** set + a completion predicate | `done_when` |

**This is the correction that removes work rather than adding it.** Today these are three unrelated
systems — tool `_meta`, `SkillDef`, `workflows.steps[].tool` — hand-synchronised across three
languages, none compiler-checked, and the audit found three concepts already tripled. As derivatives
of one substrate they share identity, admission, assembly, telemetry and permission **by construction**.

Two consequences follow immediately, and both are things the old architecture could never do:

- **A reference to a non-admitted declaration is unresolvable.** A skill naming a dead tool, or a
  workflow step pointing at a retired one, **cannot load** — not "warns", not "lints". The repo
  currently ships 12 rails pointing at **30 dead tools**, behind a gate that **fails open**.
- **The owner's original invariant stops being a coverage ratchet.** *"Every tool belongs to a skill
  group and sits in ≥1 workflow"* was measured at 49% and 13% and needed a chased-forever gate. Over
  one substrate it is a **referential property of the manifest**, checked the way a foreign key is.

---

## 1 · Why this is the right shape, stated against the measurements

| the red team killed | because | this plan |
|---|---|---|
| **A9** big-bang deprecation | 170 public `TOOL_POLICY` entries, published OAuth scopes, **issued third-party keys** — cannot be dark | **deletes nothing.** The old runtime keeps serving the public edge, the FE bridge and today's chat |
| **the baseline** | arms C/D/E were built from a live catalog; after a retirement only the two arms that agree with the design survive | the old surface stays live and measurable **as the control group**, by construction |
| **A10** we cannot measure | no column records what a turn advertised; 3/3 bounds nothing | telemetry is a **component of the architecture**, not a retrofit — a tool that cannot be monitored cannot be admitted |
| **A1 / A2 / A4 / A5 / A7** the shape | every proposed shape failed on evidence | this plan **commits to no shape.** The shape is an output of admission data, not an input |

**The strangler pattern with an enforced membrane.** Two runtimes, one agent, and no path between them.

---

## 2 · The failure class no architectural shape addresses — and where it now lands

**Measured: 2,477 / 4,010 failures (61.8%) occur on a tool that already SUCCEEDED in the same
session.** Session `019faf5b`: `glossary_propose_entities` returns `entity_id:019fafa2-…` at step 12;
at step 16 the model sends `entity_id:"0"`.

**It is not a property of the tool surface.** An empty architecture does not fix it, and one-at-a-time
admission would score every declaration as failing for a reason none of them caused. Independent
corroboration: the 584-tool routing study measures a **Confusion Gap of 10pp that survives *perfect*
retrieval**.

**The model was not guessing — it was writing a plan with no syntax for one.** The clearest specimen is
a tool at **0/101** whose error message is already ideal (it names the field, quotes the bad value, and
states the remedy). What the model sent was `placeholder_id_1` ×60, `current_book_id_placeholder` ×18,
`placeholder_id` ×5, `"0"` ×2 — **template tokens, not hallucinated UUIDs.** It was trying to say *"the
entity I am about to create"*, and the only channel available demanded a concrete UUID immediately.

> **Better errors would not have fixed our worst tool. C-7 and C-12 were already satisfied there.**
> What was missing is a place to say *"this value comes from that step."*

**Three mechanisms close it, and they are one mechanism seen from three sides:**

- **C-6 `emits`** — a declaration states what its result hands forward (§4);
- **the plan binds** that emission to the step that consumes it, and the executor **satisfies the
  binding directly** rather than asking the model to retype a UUID it has already seen (§0.4);
- **the working-memory projection never compresses an identifier** (§0.11) — a summarised UUID is a
  lost UUID, which is this failure class restated.

This is no longer an open gap. It is the reason plan-as-data is load-bearing rather than convenient,
and **brick 4 is where it gets tested first** (§8).

---

## 3 · The membrane — how "only new tools load" is guaranteed by construction

The failure mode to avoid is precise and this repo has produced it thirteen times: **invisibility
implemented as a filter.** A filter is a code path from the old catalog to the new surface, and every
such path has eventually leaked or silently deleted the wrong thing.

> **Old declarations are not hidden. They are absent.** There is no branch in the new assembler that
> can read the old catalog — not one that is disabled, not one behind a flag. The old catalog is not
> an input.

The membrane is over **declarations** (P1), not over tools — so a legacy skill and a legacy workflow
step are excluded by the same construction, not by three separate suppressors.

Four mechanical properties, each with its own gate:

| # | property | mechanism | gate (red-able) |
|---|---|---|---|
| **M1** | a separate registry that starts empty | `contracts/agent-runtime-manifest.json`, generated **only** from new-style declarations — tools, skills and workflows in one manifest | ✅ **built:** `agentruntime-membrane-gate.py` compares the committed file to what the generator produces (at CP-1: `build([])`), re-runs the contract over every row, and reds CI on drift. *Was "row count == admitted count", describing nothing that existed* |
| **M2** | the new surface reads M1 and nothing else | the assembler (P4) takes the manifest as its **only** catalog argument; no import of the legacy catalog, skill-registry or workflow-seed modules | an import-graph gate: the new assembler's transitive imports must not include any legacy source. Break it, watch CI red |
| **M3** | discovery reads M1 only | same input, same argument | 🟡 **built, and armed for a subject it does not yet have:** the test reads all three real legacy registries and asserts every name is absent from discovery. With an empty manifest the intersection is empty *whatever* the left side holds, so it is a **positive control** (a planted leak is caught) rather than a live measurement until CP-4 admits a row |
| **M4** | a non-compliant declaration cannot register | the registration entry point **refuses to boot** on an incomplete contract — the existing `require_meta` chokepoint already panics on a missing tier; this extends it to all of P2 | remove one required clause, watch the service fail to start |
| **M5** | **a reference to a non-admitted declaration is unresolvable** | skill members and workflow steps are foreign keys into M1, resolved at generation | point a workflow step at an unadmitted name; generation fails. *(Today: 12 rails → 30 dead tools, gate fails open)* |

**M2 is the load-bearing one.** M1, M3 and M4 are enforceable by tests; M2 is what makes those tests
*meaningful*, because it removes the possibility of the path rather than checking that it is unused.

> **🔴 AMENDED 2026-08-04 — three of the four gate columns above described mechanisms that did not
> exist.** §6.1 was amended twice for the same fault while this table sat unread beside it; a
> verifier found that the corrections had been applied only where it was looking. **The table is
> what CP-1 was built against, so a wrong cell is not a documentation slip — it is a criterion
> nobody could have satisfied.** What is true after CP-1:
>
> | # | the cell said | what exists |
> |---|---|---|
> | **M1** | *"manifest row count == admitted count; drift reds CI"* | ✅ **now true, and it was not.** Proven red-able by typing a well-formed row into the JSON |
> | **M3** | *"a test that seeds a legacy-only declaration of **each of the three kinds**"* | 🟡 **built, and honestly a POSITIVE CONTROL rather than a measurement.** Round 3: with an empty manifest the intersection is empty *whatever* the legacy list holds — substituting 315 fictional names gives the identical result. It **would** fire on a real leak, so it is armed for CP-4; today it has no subject, and the earlier ✅ overstated that. The "non-vacuity floor" guarded the wrong side |
> | **M4** | *"the registration entry point **refuses to boot** on an incomplete contract"* | 🔴 **STILL FALSE, and it is not CP-1's to make true.** Nothing imports `app.agentruntime`, so there is no boot to refuse — the check runs where a declaration is *admitted*, not at service start. Wiring an import so the phrase becomes true would be pulling CP-2 forward. **Recorded as unmet rather than reworded** |
> | **M5** | *"point a workflow step at an unadmitted name; generation fails"* | ✅ true, and strengthened: the reference is re-resolved on **load** as well, because an edit can break what generation proved |
>
> **The pattern worth carrying, since it has now cost three rounds:** a correction applied to the
> clause a verifier quoted, and not to the other places making the same claim, leaves the document
> *more* misleading than before — the reader who checks one cell finds it accurate and stops.
>
> **🔴 AND THEN I DID IT AGAIN, IN THIS BLOCK.** Round 3 found that the table cells above were
> **never edited** — this amendment was *appended beneath them*, so `"seeds"` and
> `"row count == admitted count"` still read verbatim as criteria. **An erratum below a wrong line
> does not correct the wrong line**; it adds a second claim and lets the reader pick. The cells are
> now edited in place, and this block is kept only as the history of what they said. Writing the
> lesson down was not the same as applying it, which is the whole finding.

---

## 4 · P2 — the declaration contract, every clause traced to a measured failure

**This is a primitive of the architecture, not a property of tools.** A declaration of any kind is
admissible only if it satisfies every clause that applies to it. **Each clause exists because a
specific measurement showed its absence causing failure**; a clause with no such basis is not here.

Kinds: **T** tool · **S** skill · **W** workflow.

| # | clause | kinds | what it requires | the measurement that demands it |
|---|---|---|---|---|
| **C-1** | `group`, `lane` | T S W | data at registration, never inferred from a name | 5 prefix maps, 43 intent regexes and a 12-verb substring list all guess this today |
| **C-2** | `tier`, `scope` | T S W | unchanged — P6 is sound. A skill/workflow's tier is the **max** of its members | — (kept, not redesigned) |
| **C-3** | `limit` | T | a bound with a default, on every list/search/read | **18 of 36 read tools have no `limit` parameter at all** |
| **C-4** | **`accepts`** — argument **provenance** | T W | each argument is either caller-obvious (text the user said), **or** names the declaration that produces it, **or** accepts a human-usable alternative (name / ordinal / title) | **57% of real errors are identifier failures**; **189 of 315 declarations give no argument-source guidance**; `book_chapter_save_draft` already does this (*"pick the chapter by NUMBER or TITLE"*) and works |
| **C-5** | **no silent substitution** | T | never replace a malformed argument with an ambient value and report success | `stream_service.py:1619-1623` overwrites a non-UUID `chapter_id` with the turn's id — **a wrong-object success no `ok=false` autopsy can see** |
| **C-6** | **`emits`** — what a result hands forward | T W | the ids/handles a result carries are declared, so the runtime can assert the next call reused one. **A workflow step's `accepts` must be satisfiable from a prior step's `emits`** — checked at generation | **61.8% of failures are on a declaration that already succeeded** — the carry-forward class (§2) |
| **C-7** | **error contract** | T | 4 classes — `retryable_transient` / `retryable_modified` / `terminal_permanent` / `terminal_budget` — set **where the failure is raised**, with a remedy sentence. A wrapper that cannot classify returns `terminal_permanent` | **65.7% of all "errors" are our own breaker prose**; nothing tells a caller whether a retry is worth attempting |
| **C-8** | **post-condition** | T W | a call that changed nothing must not report success; a workflow's `done_when` is a predicate over real state | `noop_write_counts` fired 263× |
| **C-9** | **honest scope** | T S W | may not claim reach it does not have | K26, 2026-07-24: *"the universal find tool"* was retracted in writing for exactly this |
| **C-10** | **monitorability** | T S W | emits the §5 fields; what cannot be monitored cannot be admitted | A10 |
| **C-11** | **resolvable references** | S W | every member / step is a foreign key into M1 | 12 rails point at **30 dead tools** behind a gate that fails open |

**C-4, C-5 and C-6 are the three that are new**, and between them they own the **57%** and the
**61.8%** — the two largest measured failure classes. **C-6 is also what makes a workflow checkable
rather than declarative:** step *n+1* asking for something no earlier step emits is a generation
error, not a runtime surprise.

### 4.1 The rest of the contract — clauses added by the module interrogations

**This section is the clause list's only home.** Clauses were introduced across §0.5, §0.9 and §0.10 as
corrections; they are collected here because a contract defined in four places is the defect this spec
exists to remove.

| # | clause | kinds | what it requires | measurement |
|---|---|---|---|---|
| **C-0** | **identity** | T S W | id · owning service (**derived**, never authored) · lifecycle state · contract version | there is **no CODEOWNERS file and no `owner` key** in this repo; M4 gated on C-1…C-12, so the first admitted declaration would have had no identity |
| **C-12** | **fault locus** | T | name the **field path** rejected, the reason, and what would be accepted. **A field the server drops may never be reported as absent** | a misspelled key is dropped by the Go typed struct and reported as *"missing required"* — the model sent it, we dropped it, then blamed it |
| **C-13** | **`re_runnable`** ∈ `idempotent · duplicates · single_use` | T | only `idempotent` may be re-run automatically; `single_use` escalates to plan-invalid | §0.5's `binding-invalid` would otherwise duplicate: `kg_project_create` ×57 in one turn; `The Tidewright` ×6 in `books` |
| **C-14** | **typed outcome** *(replaces `ok: bool`)* | T | `done · partial · empty · ambiguous · refused · degraded · deferred · failed · unknown_effect`, with the reason field each value requires | **`ok=true` is untyped and means seven different things.** 358 refusals rode the success channel; 400 empty results have four indistinguishable causes; 430 results were silently truncated |
| **C-15** | **`requires`** — preconditions on world state | T W | `[{predicate, satisfied_by}]` | 102 failures on state the caller could not supply (*"no embedding model configured"*) |
| **C-16** | **`as_of` + `invalidates`** | T | a read carries a staleness token; a write declares what it invalidates | 25 optimistic-concurrency rejections, and a repeat-read breaker blocking **1,675** calls on an **undeclared** assumption |
| **C-17** | **`completion`** — for asynchronous work | T | `{poll, handle_field, terminal_states}` | 19 tools return before the effect exists; C-8's post-condition is unsatisfiable at return time. **This is `done_when` placed in time** |

**C-4 is extended, not duplicated:** `unknown kind: betrayal` is the same defect as an unresolvable
`entity_id` — a closed vocabulary the caller cannot enumerate. C-4 therefore names the **lister and
the creator of a vocabulary**, not only the producer of an id.

**Fifteen proposed clauses became six.** The module interrogation offered C-13…C-27; adopting all
fifteen would have reproduced the accumulation this spec exists to end. Seven of them
(`partial`, `refused`, `empty`, `ambiguous`, `degraded`, `truncated`, `unknown_effect`) were **one
clause wearing seven hats** — C-14 — and two more collapsed into C-13 and C-4.

### 4.2 Three taxonomies, reconciled — there are only two levels

The corrections introduced what looked like three parallel vocabularies. **They are not parallel, and
saying so is what stops them drifting into three hand-synced copies:**

```
 the tool RETURNS      ── outcome (C-14)            ← call level, in the envelope
                            └─ if `failed`: error class (C-7)   ← a REFINEMENT, not a peer
 the executor DERIVES  ── plan scope (§0.5)         ← plan level, needs the plan to exist
```

- **the error class is a sub-field of one outcome value**, not a second taxonomy. Only `failed` carries
  a retryability class; asking *"is `partial` retryable?"* is a category error;
- **the plan scope is never declared and never returned.** A tool *cannot* know it — the same
  `terminal_permanent` is `binding-invalid` when the argument came from a prior step's `emits` and
  `needs-human` when it came from the user. **Only the plan holds that fact**, which is why plan-as-data
  is load-bearing rather than convenient;
- therefore: **a tool that returns a plan scope is a defect, and a plan scope that was authored rather
  than derived is a defect.**

### 4.3 The widening rule — the half §0.1 left out

§0.1 governs only *narrowing* (**narrow, never invent, never silently**). The measured failure class
runs the other way: **a plan names a declaration that is not on the wire.** The repo has paid for that
omission three times, with three heuristics that exist for no other reason — the rail next-step budget
exemption, the **backtick prose scraper** that greps skill text for tool names, and `load_skill`
naming tools that were never advertised (the `co_write` incident: **6,948 characters, zero tool
calls**).

> **A plan step's declaration MUST be advertised while that step is current.**

One sentence, and it **deletes all three heuristics**. It is an obligation on assembly, not a licence
to invent: the declaration must already be **admitted** (M5/C-11), so this widens the *advertised* set
within the *admitted* set — exactly the direction §0.1 permits and forgot to require.

---

## 5 · Telemetry as a component, not a retrofit

The new runtime records, per turn, without exception — **four fields, not five**; the fifth was
mis-located and is corrected below.

| # | field | shape | why |
|---|---|---|---|
| 1 | **`advertised_tools`** | **`jsonb` — an array per pass**, each `{pass, tool_choice, names[]}` | today **no column anywhere answers this**, which is why arm-E deletion is invisible in production. **A scalar `text[]` would record only the last pass and lose the mid-turn deletion the field exists to catch** |
| 2 | **`withheld_tools`** | `[{tool, stage, reason}]` | **a withholding that does not register is a defect, not a policy.** Its denominator is `manifest_revision`, or no rate compares across deploys |
| 3 | **`source ∈ {tool, breaker, meta}`** | on every result | **58–66% of what the model sees as an error is our own prose.** Until this exists that fraction of the signal is uninterpretable |
| 4 | **outcome** | mandatory on every terminal path | `finish_reason` covers **9.4%** today. Mandatory means *no terminal path may omit it*, including cancel (§0.5's fifth scope) and crash |

**The wrong-object counter is not a P5 field.** §0.6: a counter without a detector ships reading zero.
Only substitution-shaped cases are detectable at the call; **the 61.8% carry-forward class is
detectable only from plan-binding state**, so the detector belongs with the plan (§0.11) and P5 merely
carries its output.

**Two things this must not be mistaken for.** It is not an OTel adoption — measured, **zero of these
four map cleanly** onto the GenAI conventions, because *OTel models what happened and never what was
suppressed* (§0.7: buy the vocabulary, build the store). And it is not a v2 concern: **the guardrail
shadow arm must be in v1** (§0.5 property 3 is unobservable if the guardrail blocks) and it cannot be
retrofitted.

**In the new runtime these are not optional and there is no path that skips them** — the same
construction argument as M2.

---

## 6 · Admission — one declaration at a time

*Rewritten 2026-08-04. The first draft made admission a single gate over a solo surface with a
29-success precondition; §0.9's arithmetic and §0.12's evidence discipline both overturned it. This is
the reconciled version — the corrections are folded in here rather than left to contradict it.*

**Admission has two halves with different evidence rules, and only one of them is a gate.**

### 6.1 The gate — the contract check (M4)

Mechanical, at boot, not a review. **A test may reject; this is the half that rejects.** A declaration
failing C-0…C-17 does not start the service.

**Prerequisite, verified missing:** M4 is Python-only today. `NewToolMeta`
(`sdks/go/loreweave_mcp/meta.go:184`) builds a map and validates nothing, and `MustValidateToolMeta`
has **14 call sites** against **58** `NewToolMeta` uses in glossary alone. **Construction must *be*
validation** — an `Admitted[D]` type whose only producer is the contract check.

> **🔴 AMENDED 2026-08-04, before CP-1's first line of code.** This clause read *"…with a private
> field, **so a bypass is a compile error**"*. **That guarantee does not exist in this repository and
> could not have been delivered.** Python has no compile-time access control, and — checked rather
> than assumed — **no type checker runs on chat-service at all**: there is no `mypy`/`pyright` config,
> no `pyproject.toml` or `setup.cfg` in the service, and no type-check job in any workflow that covers
> it. The only occurrence of the word `mypy` in `scripts/` is a cache directory in an ignore list. A
> criterion no mechanism can report is not a strict criterion; it is an **unfalsifiable** one, and
> CP-0 spent eleven rounds on the cost of those.
>
> **🔴 AMENDED AGAIN 2026-08-04, and this time the CODE is the evidence.** The first amendment
> replaced *"compile error"* with a five-row table of *"what is actually enforceable"*. **Three of
> those five rows were also false**, and V-CODE found them; the builder then reproduced every one by
> **execution**, not by reading:
>
> | row as first written | probe | result |
> |---|---|---|
> | 1 · `admit()` is the only producer | `from …admission import _TOKEN; Admitted(d, v, _TOKEN)` | 🔴 **succeeds** — a single-underscore name is a convention, and `import` does not honour it |
> | 2 · cannot be mutated | `object.__setattr__(a, "declaration", other)` | 🔴 **succeeds** — frozen blocks `a.x = …`, not the two-argument form the class's own `__init__` uses |
> | 3 · cannot be round-tripped | `copy` / `deepcopy` / `pickle.dumps` | ✅ all raise |
> | 4 · a forged instance is unusable | `object.__new__` then `object.__setattr__` ×2 | 🔴 **succeeds** — the slots can simply be filled |
> | 5 · the construction site stays single | gate over the package | ✅ holds |
>
> Subclassing is unrestricted as well. **So the honest statement is that Python cannot make this
> unforgeable, and no wording of this clause will change that.** Twice now this section has described
> a boundary stronger than the language provides; the fault is the same both times — asserting a
> property rather than probing for it.
>
> **M4 is therefore DEFENCE IN DEPTH, and the load-bearing layer is the third one, not the type:**
>
> | | layer | what it actually gives |
> |---|---|---|
> | 1 | **accident boundary** — the type | `Admitted(...)` raises; `copy`/`pickle` raise. Stops the *unintentional* producer, which is the 14-against-58 shape being replaced. It stops nothing deliberate. |
> | 2 | **detection boundary** — the gate | a bypass must either name a private symbol or call `object.__setattr__` on an `Admitted`. **The gate performs that scan repo-wide** — `_TOKEN`, `_AdmissionToken` and `object.__setattr__` in any module mentioning `agentruntime`, everywhere except `admission.py` itself — so a deliberate bypass is **loud in the diff that introduces it**. 🔴 *Round 2 caught this row describing a scan nothing performed: "both are greppable" was true, and no mechanism did the grepping. A capability written as though it existed — the third instance in this one clause, which is why the scan is now covered by the gate's own self-test rather than by this sentence.* |
> | 3 | **correctness boundary — REVALIDATION at both ends** | the manifest **writer** re-runs the contract check on every row it writes, and the **reader** re-runs it on every row it loads. This is the only layer that does not depend on the type being trustworthy. |
>
> **Layer 3 is the correction that matters, and it closes a defect the type was hiding.** Because
> `build()` trusted the type, any object carrying a `.declaration` attribute wrote a manifest row —
> reproduced: a four-line duck-typed class put `sneaky` into a generated manifest. And because
> `load()` trusted the file, a row **typed into the JSON by hand** was served to the assembler having
> passed no clause at all. Neither hole is about `Admitted`; both are about **a boundary asserting a
> guarantee its neighbour was supposed to provide.**
>
> The rule this leaves, and it generalises past this clause: **a type may express an invariant; it may
> not be the only thing enforcing one across a persistence boundary.** JSON on disk has no types.

### 6.2 Not a gate — the behavioural bound, which tightens

`3/3` bounds a failure rate only at **≤63.2%** against a **54.2%** baseline; **≤10% requires 29
consecutive successes**. At **414 tool calls/week across the whole product** that cannot be a
precondition, and synthetic runs would measure the harness (§0.12).

> **A declaration ships with `asserted_bound: unknown`, and the bound tightens with real use.**
> Always stated, never assumed, always visible — an enabler under §0.3, not a ceiling.

**The isolation is the RUNTIME, not the surface.** The noise the PO ruled out is *old-architecture
declarations*; other compliant ones are not noise. A declaration therefore accrues evidence **alongside
other admitted declarations**, from production traffic — which is also what makes §8's brick 4 (a
two-step pair) legal, where the first draft forbade it 130 lines away.

**Adversarial arm** — the same task with the declaration's hardest argument left unresolvable. It tests
C-4, C-7 and C-12: *is the model told what to do next.* It is a rejector, so it belongs with 6.1.

### 6.3 Throughput is the metric, and it has a number

**≈13 admissions/week** keeps pace with the model cadence (339 declarations ÷ 26 weeks). Report it per
phase. The first draft's metric — *"a phase that admits fewer than it retires"* — **cannot fire**,
because §1 says the plan deletes nothing and retirements are structurally zero.

### 6.4 When a declaration fails, and when the contract changes

**A declaration that fails admission is not patched into compliance and re-run.** The failure is data
about the contract.

**But amending the contract cannot silently invalidate what came before**, and as first written it did:
declarations #1–#30 were admitted against the older contract, so grandfathering them puts two contract
generations on one runtime while re-admitting them means the contract is never amended in practice.
**This is the design's intended mode of operation, so it needs a mechanism:**

| | |
|---|---|
| every declaration carries | `contract_version` + `admitted_against` |
| a **backward-compatible** amendment | prior admissions stand |
| a **breaking** amendment | prior declarations enter a re-admission queue **without leaving the runtime** |

---

## 7 · What stays on the old runtime, and why that is the point

Untouched and still serving: the public MCP edge (170 policy entries, third-party keys), the FE bridge
(**8 tools, all composition** — C3), today's chat surface, and every seeded rail.

**That is not tolerated legacy. It is the control group.** The claim to be proven is *"the new runtime
performs better than the old"*, and the red team's sharpest schedule finding was that a clean floor
destroys the only thing that sentence can be measured against.

**One prerequisite before the first brick, for the same reason:** snapshot `tools/list` into
`contracts/` and script the existing arms. They were built from a live catalog and are **not
reproducible today**.

---

## 8 · The first bricks

Chosen to test the *contract*, not to deliver features — the earliest bricks must be the ones whose
failure would be most informative:

| order | brick | what it proves |
|---|---|---|
| **0** | **the four telemetry fields + a frozen baseline** | **nothing below is observable without them** (§0.12). `advertised_tools` as `jsonb`-per-pass, `withheld_tools`, `source`, mandatory outcome — plus a `tools/list` snapshot in `contracts/`, because the existing arms were built from a live catalog and **are not reproducible today** |
| 1 | the runtime itself, **zero declarations** | **M1–M5** hold; the surface is empty and the agent **says so honestly**. Blocked on the Go fix (§6.1) and on C-0 (§10.2 Q6) |
| 2 | one **zero-argument read** | the floor case — arm A's territory, where the old surface already scores 1/1 |
| 3 | one **read whose argument is a name, not an id** (C-4) | the 57% class, at its cheapest |
| 4 | one **two-step pair** where step 2 consumes step 1's `emits` (C-6) | **the 61.8% class — the one no architectural shape addresses.** Legal under §6.2's runtime-level isolation; it was forbidden by the first draft's solo rule |
| 5 | one **write with a confirm token**, approved as a **plan** | the permission spine survives the membrane — and §0.8's missing middle, *assent to the whole job*, gets its first instance |

Brick 4 is the one that matters most and the one most likely to fail. **It should be built early, for
that reason.**

**Brick 0 was not in the first draft, and its absence was the most dangerous thing in it.** Every brick
above it is scored on evidence that today has no field to live in: no column records what a turn
advertised, `finish_reason` covers **9.4%**, and `message_feedback` holds **3 rows**. A brick laid
before its instrument is a brick nobody can see fall.

---

## 9 · Reading order

**§0.2 — *what the architecture is*, the six primitives — sits after §0.12** because nine corrections
were inserted ahead of it. **Read §0, §0.1, §0.2, then §0.3 onward.** The content is current in place;
only the sequence is out of order, and it is fixed by one reordering pass rather than by any change of
substance.

**§1–§8 were the first draft and §0.3–§0.12 are the correction layer. All of §1–§8 has now been folded
down** — §2 (the carry-forward class, closed by §0.11), §4 (the full clause list, §4.1–§4.3), §5 (four
fields, not five), §6 (rewritten: two halves, one gate), §7 (unchanged — the control-group argument
survived every attack), §8 (brick 0 added). **No section now contradicts a later correction.**
