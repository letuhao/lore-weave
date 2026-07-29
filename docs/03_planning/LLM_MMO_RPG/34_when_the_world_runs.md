# 34 — When the world runs, and what gets written down

> **Status:** SEALED 2026-07-28 (DESIGN). Continues the `WSA` prefix (axioms `WSA-A12..A28`, laws
> `WSA-L1..L3`, findings `WSA-F7..F14`, tests `WSA-T1..T9`, amendment rows `WSA-R32..R43`, open
> `WSA-Q6`). Resolves **`WSA-Q4`** and **`WSA-Q5`** from [32](32_locus_as_actor.md).
>
> **§9 supersedes §3's framing** at the PO's correction: computation is triggered by an **observer**
> (`Player` · `Agent` · `EventGenerator`), and the wake queue is demoted from a mechanism to one
> observer's policy. Everything else in §2–§7 stands. **§10 adds fabrication-on-observation** —
> deterministic, anchored by committed facts, and pinned once surfaced. **§11 then NARROWS
> WSA-A23** — the corpus's EVT-A8 (*non-canonical regenerable content is NOT events*) already drew
> most of that line, and the tier axis completes it.
>
> These were logged as two questions. **They are one question**, and answering it settles the cost
> model for the entire world tier.
>
> 🔒 **SEALED** means the *reasoning* is closed and must not be re-litigated from memory — re-read it. Open questions listed in this file remain open, and the amendment rows are **PROPOSED, not applied**: no feature spec was edited by this arc.


---

## 1. The two questions are one

* **WSA-Q4** — what schedules a locus-actor's turn?
* **WSA-Q5** — may a locus act while nobody is watching?

Q5 looks like a product question and Q4 like an engineering one, but a locus acts *exactly when it is
scheduled to*, so **whatever answers Q4 answers Q5**. The apparent conflict:

| | Claim |
|---|---|
| **DL-D1** | routines are *"evaluated, never ticked"*; **a cold cell costs literally zero** |
| **[PRD-D1](28_product_definition.md)** | the character must genuinely live in the world — and **a village must be able to starve unwitnessed**, or the world only changes where someone is looking |

Stated that way it reads as a straight trade: pay per-tick for a living world, or keep the zero-cost
property and accept a world that freezes behind your back. **It is a false trade**, and the corpus
already contains the technique that dissolves it — twice.

---

## 2. WSA-A12 — accumulation can be LAZY, if it is closed-form between events

The reason "evaluated, never ticked" felt incompatible with "the world accumulates" is an unexamined
assumption: **that path-dependence requires stepping.** It does not.

Take [EXC-F3](30_exchange_model_and_dataflow.md)'s balancing cell. Between events, production and
consumption are constant rates, so the stockpile is

```
S(t) = clamp(S₀ + (P − C)·Δt, 0, cap)
```

— a **closed form**. And the escalation ladder (draw down → buy → take → starve → disperse) is a
function of `S`, so *"what state is this village in at time T"* is answerable **without having ticked
it**. Even *"when will it run out"* is closed-form: `t₀ = S₀ / (C − P)`.

> **WSA-A12 — a locus's trajectory must be closed-form solvable between events.** Its state at any
> time is *computed*, never *stepped*. This is DL-A4's rule (a routine is a pure function of
> `(actor_class, fiction_time, cell)`) generalised from *position* to *quantity* — the same rule, one
> domain wider.

> **WSA-F7 — the corpus already does this twice, and neither instance was recognised as a general
> technique.**
> * **AC-DL-15**: *"one `offline_vitals` sweep with `elapsed = 1h` yields **exactly** the vital values
>   sixty per-turn evaluations would"* — closed-form accumulation, proven lossless by an acceptance
>   test.
> * **TDIL-A11**: *"an unattended channel's clock advances **lazily, at observation**"*, via
>   `last_baseline_sync`.
>
> Two subsystems independently invented lazy closed-form advance. **Naming it once and applying it to
> loci is the whole of this document's first half.**

**And the no-float rule pays off again.** Closed-form wake times must be computed **identically on
replay**; in floating point they would not be. Because [DF7-A4](27_extensibility_stress_test.md) bans
float from the whole path, `t₀` is an integer expression and replays byte-identically. A constraint
adopted for determinism turns out to be the precondition for lazy scheduling.

---

## 3. WSA-A13 — the scheduler is a next-crossing event queue, not a tick

If a trajectory is closed-form, a locus does not need to be *visited* — it needs to be *woken at the
moment its trajectory crosses a threshold*.

> **WSA-A13 — each locus publishes a `next_wake` = the fiction-time at which its own trajectory
> crosses its next declared threshold. The island wakes loci in `next_wake` order. There is no tick.**

This is standard **discrete-event simulation** (the ns-3 / SimPy shape), and it is `O(log n)` per
*event* rather than `O(n)` per *tick* — the difference between a cost that scales with **change** and
one that scales with **world size**.

> **WSA-A14 — the queue is PER ISLAND, never global.** A global wake queue would be shared mutable
> state across islands, breaking [WSA-A3](31_world_simulation_architecture.md)'s local-write rule and
> the shared-nothing model wholesale. Each island owns the queue for its own loci; cross-island
> coupling travels the existing handoff path, exactly as entity movement already does (SL-A12).

**So WSA-Q5 is answered YES, and it costs almost nothing:** a village whose stores are draining
publishes a wake at the moment they hit zero. It starves at that moment whether or not anyone is
there. Nobody ticked it; nothing polled it; one event fired.

---

## 4. WSA-L1 — the cost law, and it is measurable

> **WSA-L1 — the cost of a living world is proportional to the number of loci currently OUT OF
> BALANCE, not to the size of the world.**

A locus at equilibrium (`P = C`, no active status, no draining store) has **no next crossing**, so it
publishes no wake and costs zero — DL-D1's property, preserved rather than traded away.

This lands exactly on top of [EXC-F3](30_exchange_model_and_dataflow.md): *an entity acts when its
ledger cannot balance*. **The wake set and the acting set are the same set.** The scheduling rule and
the behaviour rule are one rule seen from two sides, which is why neither needs to know about the
other.

> **WSA-F8 — this makes the world tier's cost a measurable quantity with a falsifier**, which
> [doc 21](21_architecture_ceilings.md)'s discipline demands and which a tick-based design could never
> offer. The gate: *a world of N loci at equilibrium consumes zero wakes; perturbing k of them
> produces exactly k wake chains.* If cost tracks N rather than k, the closed-form property has been
> broken somewhere — and that is a bug with a specific address.

---

## 5. What this constrains — four honest costs

**(a) Trajectories must be piecewise-constant between events.** If a production rate itself varies
continuously, closed form breaks.

> **WSA-A15 — a declared rate is constant between events. A rule whose rate varies continuously must
> be discretised BY THE AUTHOR into declared steps**, and the ruleset loader must refuse a
> continuously-varying rate rather than silently sampling it. Silent sampling would be the
> stored-but-wrong class: it computes *something*, and nobody can say what.

**(b) Coupling invalidates predictions.** A raids B ⇒ B's `next_wake` is now wrong. This is ordinary
DES invalidation: any state change recomputes that locus's next crossing and reschedules. Cheap, but
it must be **unconditional** — a missed invalidation is a locus frozen in the past, and it would be
invisible until a player walked in.

> **WSA-L2 — every committed delta to a locus's quantities MUST recompute its `next_wake`.** No
> exceptions, no "this delta is too small to matter". A conditional invalidation is a correctness bug
> that presents as a content bug months later.

**(c) ~~Two read paths must agree.~~ — ⚠️ SUPERSEDED BY §9.** This was listed as an unavoidable cost:
a lazy read on observation, plus a separate wake-on-crossing path, with WSA-T1 needed to prove them
equivalent. **The observer model collapses them into one path** — the wake queue becomes the
`EventGenerator`'s policy for *when to look*, not a second way of computing.

**(d) Thresholds must be declared, not inferred.** A locus can only publish a wake for a crossing it
knows about. So the set of thresholds — `stockpile = 0`, `population < n`, `contamination > c` — is
part of the ruleset declaration, which fits the [E2 tier](28_product_definition.md) already planned.

---

## 6. Tests

> **WSA-T1 — the equivalence test (the important one).** For a locus with a known trajectory:
> evaluate lazily at time `T`, and separately wake it through every crossing up to `T`. **Assert
> byte-identical state.**
>
> This is exactly the AC-DL-15 pattern promoted to a general law, and it is genuinely falsifiable: it
> reds on any threshold whose effect is not closed-form, on an off-by-one in a crossing time, and on
> any accumulated rounding difference between the two paths.

> **WSA-T2 — the equilibrium test.** N loci in balance ⇒ **zero** wakes over a fiction-year. Perturb
> k ⇒ exactly the k expected wake chains. The bite: a build that ticks loci passes every behavioural
> test and fails this one.

> **WSA-T3 — the unwitnessed-starvation test.** A village left alone with `C > P` and no observer
> starves and disperses at the computed time; a player arriving afterwards finds ruins and a recorded
> event chain. Paired per [IAS-D10](22_ingress_and_admission.md): a village in balance, left equally
> long, is **unchanged** — proving the mechanism is driven by the ledger and not by elapsed time.

---

## 7. Amendments

| # | Target | Change | Confidence |
|---|---|---|---|
| **WSA-R32** | `DL_001` DL-D1 | narrow from *"evaluated, never ticked"* to **"evaluated or woken at a computed crossing — never ticked"**. This is the amendment [R01](31_world_simulation_architecture.md) asked for, now in its precise form: **the thing DL-D1 was protecting (no polling, no cold-cell cost) is fully preserved** | **verified** |
| **WSA-R33** | `TDIL_001` TDIL-A11 | recognise lazy-advance-at-observation as an instance of WSA-A12, not a clock-specific trick | **verified** |
| **WSA-R34** | `RES_001` generators | publish a `next_wake` when a stockpile is draining toward 0 or filling toward `cap`; a capped/equilibrium stockpile publishes none | **verify** |
| **WSA-R35** | ruleset loader (F2) | refuse a continuously-varying rate (WSA-A15); validate that every declared threshold is closed-form solvable | **verify** |

**Build-order impact.** [31 §6](31_world_simulation_architecture.md)'s **W6 (the balancing cell)** is
now fully specified: a locus with a declared trajectory, declared thresholds, a published `next_wake`,
and the four-rung escalation — provable by WSA-T1/T2/T3. It stops being *"the world-tier equivalent of
one REAL encounter"* by analogy and becomes a slice with acceptance criteria.

---

## 8. Open

| # | Question |
|---|---|
| **WSA-Q6** | **What wakes a locus whose crossing depends on ANOTHER island's locus?** WSA-A14 keeps queues island-local and routes coupling through handoff — but a caravan that will arrive in six fiction-days is a crossing whose time is known *now*, in a different island. Either the destination schedules a speculative wake that the origin may invalidate (a distributed-cancellation problem), or arrival is modelled as a message that simply arrives (simpler, but the destination cannot *anticipate*). Leaning toward the message, since anticipation is what the standing fold is for. |
| **WSA-Q1..Q3** (carried) | relation-as-fourth-kind · where the ledger assertion runs · standing-fold freshness |
| **TRG-Q1, TRG-Q4** (carried) | the full aspect set · reactions firing from G3/G5 events |

---

## 9. The observer mechanism — supersedes §3's framing

> **The PO's correction:** *"Nó là cơ chế người quan sát. Chỉ có player, agent, và event generator
> (human, agent, system) là người quan sát — và chỉ khi chúng quan sát thì mới kích hoạt cơ chế lazy
> compute."*

**This is better than §3, and it is better for a specific reason:** §5(c) listed *"two read paths must
agree"* as an unavoidable cost — a lazy read on observation, and a separate wake-on-crossing path,
with WSA-T1 needed to prove them equivalent. **The observer model collapses them into one path.** The
wake queue does not disappear; it stops being a second mechanism and becomes **one observer's
policy**.

> **WSA-A18 — the observer set is CLOSED: `Player` (human) · `Agent` (a driver deciding) ·
> `EventGenerator` (system policy). Nothing else observes.**

> **WSA-A19 — computation happens ONLY on observation.** A locus's state is a function; evaluating
> that function is *an act of observation*. Nothing "happens" in the world — things are **found to
> have happened** when someone looks.

That is not word-play; it is the same statement as [ONT-A1](29_ontology_existence_self_others.md)
(*a thing exists to the degree the world keeps its consequence*) reaching the runtime. A consequence
nobody can read is not a consequence.

**WSA-A13 is therefore demoted from a mechanism to a policy:** `next_wake` is how the
`EventGenerator` decides *when to look*. Everything else in §2–§7 stands unchanged — closed-form
trajectories (WSA-A12), per-island scope (WSA-A14), piecewise-constant rates (WSA-A15), unconditional
invalidation (WSA-L2), and all three tests.

### 9.1 The tree-falls-in-a-forest objection, and why it does not bite

*If nobody observes, does the village never starve?*

For a **self-contained** trajectory the question is empty: whenever anyone eventually looks, they find
the correct post-starvation state, computed in closed form. **The observable behaviour is identical**,
so whether it "happened" in the interim is not a question the system needs to answer.

**But there is a real exception, and it is where the `EventGenerator` earns its place:**

> **WSA-F9 — lazy observation is sound only while a trajectory is SELF-CONTAINED. The moment a
> crossing has cross-entity effects, laziness becomes a dependency closure.**
>
> Village A collapses ⇒ refugees reach B, a trade route dies, land falls vacant. Observing B correctly
> would then require observing A; observing A requires observing whatever A was coupled to; and the
> closure can span the map.
>
> **Cutting that closure is the `EventGenerator`'s actual job.** It is therefore not a convenience or
> a background nicety — for coupled loci it is a **correctness requirement**, and it should be
> specified as one rather than as a scheduler.

### 9.2 WSA-A20 — the fix this makes possible: `occurred_at` ≠ `recorded_at`

Observation-triggered compute raises an obvious worry: if computation fires when someone looks, does
the world depend on *when* people looked?

**The state does not** — a pure function of `(state₀, elapsed)` gives the same answer regardless of
when it is evaluated. That property is exactly WSA-T1, which is now promoted from *a test that two
paths agree* to **the central correctness invariant of the whole model**.

**The event stream is the subtle part**, and the corpus already hit it: DL-D13 accepts that *"a PC
whose hunger would reach zero at `T+3.2h` is recorded dead at the `T+4h` sweep — a delayed trigger,
deliberately."*

> **WSA-A20 — an event caused by a crossing carries the CROSSING's fiction-time, not the observation's.
> Every such event is bitemporal: `occurred_at` (computed, canonical) and `recorded_at` (when observed).**

This turns DL-D13's accepted wart into a principled rule. The event's *content* becomes
observation-independent; only its *position in the log* varies with who looked when. Two players
observing in different orders then produce differently-ordered logs that agree on every fact —
which is exactly what an event-sourced system can tolerate, and what it cannot tolerate is the
opposite.

> **WSA-L3 — observation is READ-ONLY with respect to what is true. It may only commit what was
> already determined by the trajectory.** An observation that *changes* an outcome — a threshold that
> fires differently because a player happened to walk in — makes the world depend on attention, and
> is the one failure mode this whole model must forbid. It is also exactly the bug a careless
> "recompute on visit" implementation would introduce.

### 9.3 The cost law improves, and becomes a knob

[WSA-L1](34_when_the_world_runs.md) said cost is proportional to loci **out of balance**. Under the
observer model it is sharper:

```
cost  ∝  player observations  +  agent observations  +  EventGenerator policy
```

The first two are demand-driven and self-limiting. **The third is a dial.** World liveness is
therefore not a fixed architectural cost — it is a **tunable**, and the trade it exposes is exactly
the one worth exposing: *how far can the world drift out of date before someone notices?*

Which is WSA-Q3 (standing-fold freshness) arriving from a second direction — **the same question, one
answer needed**, and that convergence is a reason to answer it once rather than per-subsystem.

### 9.4 One more test

> **WSA-T4 — the observation-independence test.** Run a scenario twice with **different observation
> schedules** (early+often vs once at the end). Assert: identical final state, and identical
> `occurred_at` on every event — **only `recorded_at` and log order may differ.**
>
> This reds on any "recompute on visit" that lets attention change outcomes (WSA-L3), on any crossing
> whose effect is not closed-form, and on any event that stamps the observation time as its canonical
> time. It is the sharpest single test in the world tier.

**Amendments R36** — the event envelope carries `occurred_at` and `recorded_at`; DL-D13's delayed
trigger is restated in terms of WSA-A20. **R37** — the `EventGenerator` is specified as a correctness
component for coupled loci (WSA-F9), not as a background scheduler.

---

## 10. Fabrication-on-observation — the cost model's last piece

> **The PO's point:** *"Chỗ trôi lạc hậu thực tế không nhiều tới như vậy — sẽ không ai thực sự quan
> tâm NPC làm gì trong 1 tháng vừa qua cả, cho tới khi họ chú ý tới NPC đó, hay tòa thành sinh hoạt
> như thế nào. Nên chúng ta có thể dùng event generator định kỳ vào **bịa đặt dữ liệu khi có người
> quan sát**."*

**The framing correction is right and I had it wrong in §9.3.** I posed the trade as *"how far can the
world drift out of date before someone notices?"* — but drift is only a defect if it is **measurable**,
and nobody measures what they do not look at. The right question is not *how stale is the world* but
**how much history must exist at the moment attention arrives**. That is a much smaller quantity.

> **WSA-A21 — history is FABRICATED on observation, and fabrication is a deterministic FUNCTION, never
> a draw.**
>
> ```
> history(entity, window) = f(entity_id, window, ruleset_digest, committed_events_in_window)
> ```
>
> Same inputs ⇒ same history, for every observer, at every time.

**This is the one rule that makes the technique safe**, and without it the technique breaks §9
outright: fabricating *randomly* at observation would make history depend on **who looked and when**,
violating [WSA-L3](34_when_the_world_runs.md) (observation is read-only with respect to what is true)
and reddening [WSA-T4](34_when_the_world_runs.md) by construction. Two players would get two pasts.

**And the corpus already ships fabrication done correctly**, which is the fourth instance of this
pattern in the design: AIT_001's Untracked crowd is
`blake3(reality_id ‖ cell_id ‖ fiction_day ‖ slot_index)` — *"different villagers on Tuesday than
Monday, deterministically, with no simulation whatsoever; nothing to build."* That is exactly
fabrication-on-observation, already proven, already free. §10 is that mechanism generalised from
*who is in the crowd* to *what happened while you were away*.

### 10.1 WSA-A22 — facts anchor; fabrication fills the gaps

Fabricated history must never contradict what actually happened. If the player killed the blacksmith's
son last month — a committed event — the fabricated month must not describe a contented family.

> **WSA-A22 — the committed event stream is authoritative. The fabricator READS the real events in the
> window and generates AROUND them; it may never generate OVER them.**

This yields a property worth stating because it is the design working as intended rather than a
constraint being tolerated:

> **WSA-F10 — the fabrication ratio is inversely proportional to attention.** An NPC you have never met
> is 100 % fabricated. One you fought last week has real events anchoring the filler. One you have
> lived beside is almost entirely real.
>
> **This is [ONT-D1](29_ontology_existence_self_others.md) — *attention promotes existence* — appearing
> at the level of history rather than of entities.** Same principle, second application, and it is the
> reason this cost optimisation does not feel like one: the parts of the world the player cares about
> are precisely the parts that are real.

### 10.2 WSA-A23 — surfacing COLLAPSES it

A pure function is stable only while its inputs are. `ruleset_digest` is an input, so a ruleset patch
would silently rewrite the blacksmith's past — *"his history changed after the update"*, which is a
worse bug than the staleness it was avoiding.

> **WSA-A23 — fabricated content that is SURFACED to a player or agent is COMMITTED at that moment,
> and is thereafter a fact like any other.** `occurred_at` = the fabricated past time; `recorded_at` =
> the observation ([WSA-A20](34_when_the_world_runs.md)). Once committed it is immune to digest drift.

The distinction that keeps this cheap: **computed-and-discarded is free; only SURFACED content is
committed.** A fabrication used to answer *"is the granary full?"* and then thrown away costs nothing
durable. One that becomes dialogue, a quest hook, or an LLM prompt is now part of the world and must
be pinned.

And it is [ONT-D1](29_ontology_existence_self_others.md) once more, mechanically: **observation
promotes fabricated history from existence degree 0 to degree 2.** One mechanism, three applications
(crowds, entities, histories) — which is the signal that the ladder was the right abstraction.

### 10.3 WSA-A24 — the generative layer must never be load-bearing

*"Bịa đặt"* invites an LLM, and DL_001 already has the correct split — deterministic V1, generative
V2/V3 under `daily_budget_usd`. AIT_001 even ships the right shape: *"hybrid 2-stage — Stage 1
template + RNG, Stage 2 LLM-flavour lazy."*

> **WSA-A24 — the deterministic skeleton carries every MECHANICAL fact (who was where, what was
> produced, what was consumed, who met whom). The generative layer adds PRESENTATION only.** No rule,
> precondition, trigger or ledger entry may ever read a value that an LLM invented.

If a mechanic could depend on generated detail, the world's rules would depend on token spend and on
model nondeterminism, and replay would stop being reproducible. This is the same boundary the
[provider-gateway](../../standards/README.md) discipline draws elsewhere in the repo: the LLM is
allowed to *say*, never to *decide*.

### 10.4 WSA-F11 — this also weakens the coupling worry I raised in §9.1

[WSA-F9](34_when_the_world_runs.md) warned that lazy observation becomes a dependency closure once
crossings have cross-entity effects — observing B requires observing A, and so on.

**Under closed-form trajectories that closure is far cheaper than it sounded.** Pulling A forward is
**one formula evaluation**, not a month of simulation. So observing B can simply pull its coupled
neighbours forward on demand, and the cost is the *number of coupled loci*, not the *elapsed time*.

Two guards keep it bounded, and both already exist in shape:

* a declared **closure depth budget**, the same construction as
  [TRG-A15](33_trigger_group_order.md)'s chain limit — and, as there, **exceeding it is a defect
  signal, not normal operation**;
* coupling is overwhelmingly **spatially local**, so the practical closure is neighbours, not the map.

`EventGenerator`'s periodic pass therefore keeps the job WSA-F9 gave it, but as an **optimisation that
bounds closure depth**, not as the sole guarantee of correctness. That is a strictly better position:
if the periodic pass is disabled, the world is still correct — only more expensive at the moment
attention arrives.

### 10.5 Tests

> **WSA-T5 — two-observer agreement.** Two different observers, at two different times, request the
> same NPC's last month. Assert **identical fabricated history**. Reds on any fabrication that draws
> instead of computing — the single most likely implementation mistake here.

> **WSA-T6 — the patch-stability test.** Surface a fabricated history, commit it (WSA-A23), then bump
> the `ruleset_digest`. Assert the surfaced history is **unchanged**, while an *unobserved* NPC's
> history is permitted to differ. The pairing is the point: it proves the collapse actually pins
> something, rather than the whole thing being accidentally stable.

> **WSA-T7 — the anchor test.** Commit a real event in the window (the player killed the son), then
> fabricate the surrounding month. Assert the fabrication is **consistent with** and does not
> **overwrite** the committed event (WSA-A22).

**Amendments R38** — `EventGenerator` gains the fabrication role, specified as deterministic-function
+ committed-on-surface. **R39** — AIT_001's `fiction_day`-seeded generation is recorded as the
reference implementation of WSA-A21 and generalised beyond crowds. **R40** — DL_001's V2
`major_drift_summary` is restated as *presentation over a deterministic skeleton* (WSA-A24), not as
the source of mechanical facts.

---

## 11. Fabrication is a WRITE — and the tiered event model already says what to write

> **The PO's correction:** *"Bịa đặt là cần thiết nhưng nó là phép ghi dữ liệu. Nên nhớ lúc đầu chúng
> ta thiết kế **tiered event** để ghi vào ledger — tức là bản thân các loại event vô hại thì bịa đặt
> rồi chả ghi lại là đúng rồi. Các minor NPC spawn ra rồi bị lướt qua thì ghi lại làm gì? Chỉ khi
> người chơi thực sự quan tâm và biến mấy NPC này thành major NPC (cơ chế leo thang) thì lúc này mới
> cần biến bịa đặt thành sự thật. Tức là chúng ta có thể tạo ra các loại dữ liệu vô hại, người dùng
> không thể xem chi tiết nội dung được, họ tự biết nó là bịa đặt."*

> **WSA-F12 — [WSA-A23](34_when_the_world_runs.md) was too aggressive, and it partly reinvented an
> invariant that already exists.** I wrote *"surfaced ⇒ committed"*. The corpus already has the
> sharper rule:
>
> **EVT-A8 — non-canonical regenerable content is NOT events.** *"Content marked non-canonical by the
> producing service — LLM narrative texture, **routine-fill flavor**, or any payload explicitly tagged
> `flavor=true` — is NOT committed as an event. Only the **structural deltas** caused by the parent
> event (money decremented, location changed, fiction-clock advanced) are committed."* It is enforced,
> not aspirational: *"the SDK rejects commits attempting to log flavor as canonical EVT-T1/T3/T5."*
>
> **WSA-A23 is hereby narrowed to: surfacing promotes only what the tier makes INSPECTABLE (§11.2).**

### 11.1 WSA-F13 — two orthogonal axes, and only one of them existed

EVT-A8 draws the line by **kind of content**: narrative texture is flavor, structural delta is canon.
The PO's rule draws a second, independent line by **existence tier**: an Untracked villager's entire
existence is flavor; a Major NPC's is canon.

| | **structural delta** | **texture** |
|---|---|---|
| **Untracked / Minor** | **flavor** ← *the new cell* | flavor (EVT-A8) |
| **Major / PC** | **canonical** | flavor (EVT-A8) |

> **WSA-A25 — canonicity is a function of (content kind × existence tier), not of content kind alone.**
> A structural delta on an Untracked entity — the villager bought bread, walked home, slept — is
> **flavor**, because the entity itself is regenerable from
> `blake3(reality_id ‖ cell_id ‖ fiction_day ‖ slot_index)`. Recording it stores a fact that is already
> a pure function of the seed.

**And promotion is exactly the transition between the two rows.** [ONT-D1](29_ontology_existence_self_others.md)'s
*attention promotes* is therefore not merely an existence mechanism — **it is the write barrier of the
whole ledger.** That is the fourth job that one mechanism turns out to do, and the strongest argument
yet for building it early.

### 11.2 WSA-A26 — the sharpest rule: commit exactly what the player could FALSIFY

The PO's last sentence is the load-bearing one: *"người dùng không thể xem chi tiết nội dung được, họ
tự biết nó là bịa đặt."*

> **WSA-A26 — presentation fidelity is CAPPED BY TIER, and a fabrication needs pinning only at the
> fidelity the player can actually inspect.**
>
> If an Untracked villager can never be examined in detail, the player can never catch their history
> changing — so there is nothing to pin. What is surfaced at that tier is deliberately coarse
> (*"a farmer, busy with the harvest"*), the player reads it as ambience, and **no commitment is
> created.**

This is the repo's own **[non-vacuity discipline](../../standards/non-vacuity.md)** (NV-1..6) turned onto storage: *a check that cannot fail is
not a check* becomes **a fact that cannot be contradicted is not a fact worth storing.** It gives a
crisp, testable criterion for the flavor/canon boundary that EVT-A8 previously left to per-category
judgement — and it derives a *UI rule* from a *storage rule*, which is the right direction of travel.

> **WSA-A27 — the fidelity cap is enforced at the READ API, never by UI discipline.** If any endpoint
> ever returns detail above a tier's cap, an unbacked commitment has been created **silently** — the
> player now holds a fact the ledger cannot reproduce.
>
> This is precisely the [Frontend-Tool Contract](../../standards/mcp-tool-io.md) failure mode this
> repo already shipped once: a boundary spanning two services, joined only by convention, that passes
> unit tests and breaks live. The cap must be a **contract**, machine-checked on both sides.

### 11.3 WSA-A28 — promotion backfills only what was shown

A worry the tier rule dissolves: *at promotion, must we backfill a month of fabricated detail?*

**No.** Only the coarse summary that was actually surfaced was ever inspectable, so only that needs
pinning.

> **WSA-A28 — promotion commits (a) the entity, (b) the coarse facts already surfaced at the old
> tier's fidelity, and (c) real events from that moment on.** Promotion cost is bounded by *what was
> shown*, not by *elapsed time*.

The fabricated detail generated *below* the cap was computed-and-discarded and cost nothing durable —
which is [§10.2](34_when_the_world_runs.md)'s distinction, now with a principled boundary instead of a
hand-wave.

### 11.4 WSA-F14 — a redundancy this exposes

AIT_001 emits two EVT-T5 sub-types: `Generated:UntrackedNpcSpawn` and
`Generated:UntrackedNpcDiscarded`.

> **WSA-F14 (`verify`) — the spawn event may be storing a derivable fact.** The Untracked id *is*
> `blake3(reality_id ‖ cell_id ‖ fiction_day ‖ slot_index)`, so who spawned where and when is a pure
> function of the seed — reproducible without the event. Under WSA-A25 that makes it **flavor**, and
> under [EVT-A8](07_event_model/02_invariants.md) it should not be committed at all.
>
> The **discard** event may be different: `UntrackedDiscardReason` has five variants and at least some
> may not be derivable. **This needs checking against AIT_001 before either is changed** — but if the
> spawn is redundant, it is pure write amplification against the measured ~170 commits/s ceiling, at a
> volume that scales with crowd size × cells visited.

### 11.5 Tests

> **WSA-T8 — the fidelity-cap test.** Request detail above an Untracked entity's cap via the read API.
> Assert the API **refuses** (or returns the coarse form) rather than synthesising detail. Paired: the
> same request against a Major entity **succeeds**, proving the cap is tier-driven and not a blanket
> refusal.

> **WSA-T9 — the promotion-freeze test.** Surface a coarse fabricated summary, promote the entity, then
> bump the `ruleset_digest`. Assert the surfaced summary is unchanged, and that **no detail below the
> old cap was backfilled** — proving WSA-A28's bound holds rather than being asserted.

**Amendments R41** — EVT-A8 gains the tier axis (WSA-A25); the `flavor` tag becomes derivable from
`(kind, tier)` rather than set by producer judgement alone. **R42** — the read API declares a
per-tier fidelity cap as a machine-checked contract (WSA-A27). **R43** — verify WSA-F14 against
AIT_001 and, if confirmed, drop `Generated:UntrackedNpcSpawn`.

---

## 12. Cross-references

* [`32_locus_as_actor.md`](32_locus_as_actor.md) — loci as entities + actors, WSA-Q4/Q5 origin
* [`31_world_simulation_architecture.md`](31_world_simulation_architecture.md) — layers, local writes, R01
* [`30_exchange_model_and_dataflow.md`](30_exchange_model_and_dataflow.md) — EXC-F3 ledger imbalance
* [`33_trigger_group_order.md`](33_trigger_group_order.md) — what happens once a locus is woken
* [`21_architecture_ceilings.md`](21_architecture_ceilings.md) — the measurement discipline WSA-F8 answers to
* [`features/12_daily_life/DL_001_daily_life_foundation.md`](features/12_daily_life/DL_001_daily_life_foundation.md) — DL-D1, AC-DL-15
* [`features/17_time_dilation/TDIL_001_time_dilation_foundation.md`](features/17_time_dilation/TDIL_001_time_dilation_foundation.md) — TDIL-A11 lazy advance
* [`features/00_resource/RES_001_resource_foundation.md`](features/00_resource/RES_001_resource_foundation.md) — generators, stockpile caps
