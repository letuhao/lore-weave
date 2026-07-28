# 33 — Trigger GROUP order + failure tolerance: the resolution law

> **Status:** SEALED 2026-07-28 (DESIGN). Axioms `TRG-A1..A18`, laws `TRG-L1..L6`, findings `TRG-F1..F5`,
> tests `TRG-T1..T6`, amendment rows `TRG-R25..R31`, open `TRG-Q1`, `TRG-Q4`
> (**`TRG-Q2` resolved in §9** — the wave model; **`TRG-Q3` resolved in §10** — attribution follows
> ownership).
> **Prefix `TRG` registered** in [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Answers the PO's correction to [32 §6(a)](32_locus_as_actor.md):
>
> > *"Chính xác phải là **trigger group order**. Trong 1 nhóm thì không có order, trước sau không ảnh
> > hưởng; nhưng giữa 2 nhóm phải có order để không bị hỏng, và phải có **failure tolerance**. Ví dụ
> > actor đã chết (body, soul still exist) thì các trigger liên quan tới body sau đó sẽ không được
> > trigger, hoặc trigger nhưng sau đó không làm gì nữa (vì ref đã bị xóa) — nhưng soul còn thì mấy
> > trigger liên quan tới soul vẫn đi theo. Ví dụ chết rồi nhưng vẫn bị ghi thù bởi actor khác."*
>
> **The correction is right, and it is the same law the stat system already needed.** §1. It also
> turns [XST-F5](27_extensibility_stress_test.md) — *"the LOCKED layer order is unfalsifiable"* — from
> an embarrassment into a testable property, because unlike summed stat layers, **these groups
> genuinely do not commute** (§4).
>
> 🔒 **SEALED** means the *reasoning* is closed and must not be re-litigated from memory — re-read it. Open questions listed in this file remain open, and the amendment rows are **PROPOSED, not applied**: no feature spec was edited by this arc.


---

## 1. TRG-A1 — group order, and why this is one law with two applications

> **TRG-A1 — resolution proceeds in ORDERED GROUPS. Within a group, order is semantically irrelevant.
> Across groups, order is load-bearing and LOCKED.**

This is **structurally identical** to the law [XST-F12](27_extensibility_stress_test.md) derived for
stat resolution from the Balatro `640 vs 480` case:

```
within a stage: contributions combine by ONE commutative operator
across stages:  the ordered layer sequence applies
```

> **TRG-F1 — the stat system and the trigger system obey the SAME law, and it was discovered
> independently twice.** That is the strongest available evidence that the law is real and not a
> convenience. It should be stated once, at the architecture level, and referenced by both — not
> re-derived a third time when the next subsystem needs it.

**Why "group order" beats "trigger order" concretely.** A total order over individual triggers has to
be *authored*, so it is (i) impossible for an author to get right against triggers they have never
seen, (ii) a load-order dependency in disguise — exactly [XST-D8](27_extensibility_stress_test.md)'s
clamp bug, where `.find()` silently made the winner depend on `Vec` position — and (iii) unstable
under content addition. A **group** order is authored once, by the engine, and content slots into it.

> **TRG-A2 — group assignment is ENGINE-owned, never author-declared.** An author declares
> `WHEN · IF · THEN · ON` ([PRD-A2](28_product_definition.md)); the engine derives the group from the
> trigger point. Authors cannot reorder groups, which is precisely what keeps content from breaking
> the world.

---

## 2. TRG-A3 — the ordered groups

| # | Group | Contains | Commutative inside? |
|---|---|---|---|
| **G1** | **ADMIT** | pure-message checks, outside the loop ([IAS-A2](22_ingress_and_admission.md)) | yes |
| **G2** | **AUTHORISE** | preconditions incl. the capability read ([EXC-A4](30_exchange_model_and_dataflow.md)) | yes |
| **G3** | **REPLACE** | prevention / substitution / doubling ([XST-R11](27_extensibility_stress_test.md)) | **NO — see TRG-A4** |
| **G4** | **APPLY** | the transaction's deltas across the three currencies | yes |
| **G5** | **LIFECYCLE** | aspect death, destruction, thresholds crossed | yes |
| **G6** | **REACT** | interleaved turns ([WSA-A11](32_locus_as_actor.md)) | yes |
| **G7** | **IMPRINT** | who records what about whom | yes |
| **G8** | **DERIVE** | invalidate + re-resolve snapshots, capability | yes |

> **TRG-A4 — G3 REPLACE is the ONE internally-ordered group, and it must declare its order.**
> Prevention effects genuinely do not commute — the Gisela case in
> [27a](27a_stress_test_agent_reports.md) resolves to **7 or 8** depending on which of two
> replacements applies first. So G3 carries a declared `replacement_priority: i16`, ties broken by a
> deterministic key (entity ordinal, never creation time or map order).
>
> **Naming the exception is better than a law with a quiet hole in it.** Every other group is
> genuinely commutative, and TRG-T1 below proves it rather than assuming it.

---

## 3. TRG-L1 — the order is LOCKED, and every boundary has the bug that names it

> **TRG-L1 — the G1..G8 sequence is locked. Each adjacent boundary exists because swapping it produces
> a specific, observable defect.**

| Swap | The bug it produces |
|---|---|
| G2 ↔ G3 | a replacement fires for an action that was never authorised — **prevention charges burn on refused actions** |
| G3 ↔ G4 | *"prevent all damage"* runs **after** the damage is applied — the thing it exists to prevent already happened |
| G4 ↔ G5 | death is evaluated before the damage that causes it — **nobody ever dies from a hit** |
| **G5 ↔ G6** | **the PO's example.** A *"when I die"* reaction cannot fire (not dead yet), and a body-scoped reaction fires **from a corpse whose body is already gone** |
| G6 ↔ G7 | the grudge records the **proposal** instead of the outcome — *you resent me for a blow that was prevented* |
| G7 ↔ G8 | capability is derived from **stale standing** — the very next action ignores what just happened |

**This is the acceptance suite, not an illustration.** Six adjacent swaps, six named failures, each
independently assertable. It is exactly what [XST-F5](27_extensibility_stress_test.md) found missing
for the stat layers — and the difference is real: flat stat layers are *summed*, and addition
commutes, so their order was unobservable. **These groups interact, so their order is observable, so
it can be tested.**

---

## 4. TRG-A5 — commutative in SEMANTICS, deterministic in ITERATION

The trap hiding inside *"trong 1 nhóm thì không có order"*:

> **TRG-A5 — "order does not matter" is a claim about MEANING, never a licence for nondeterministic
> iteration.** Replay requires byte-identical output, so the engine still iterates a group in a fixed
> order, keyed by a stable ordinal — the `BTreeMap`-only discipline `sim-core` already enforces for
> replay state. Semantic commutativity and deterministic iteration are two separate requirements and
> **both** are mandatory.

> **TRG-T1 — the shuffle test.** Submit the same triggers to a group in a **shuffled registration
> order**; assert the committed event stream is **byte-identical**.
>
> **This test can genuinely fail**, which is what makes it worth having: it reds on any group-internal
> operation that is secretly order-sensitive — a `.find()` that takes the first match, a "first writer
> wins" resolution, an accumulator that saturates. It would have caught
> [XST-D8](27_extensibility_stress_test.md) (clamps not composing, load-order deciding the winner) on
> the day that code was written.
>
> Note the shuffle must be applied to **registration/submission** order, not to the engine's internal
> iteration — shuffling the input to a `BTreeMap` and observing the same output proves nothing, and
> that vacuous variant is the one a tired implementer will write.

---

## 5. Failure tolerance — aspects, and the three persistence classes

The PO's example is not hypothetical. **The corpus already carries the discriminator it needs**, and
already carries one instance of the rule:

* `PROG_001` §4.3 — `BodyOrSoul { Body | Soul | Both }`, with explicit semantics: *"body progressions
  stay with body — a new soul inherits martial skills; soul progressions travel with soul — academic
  knowledge follows the soul to a new body."*
* `EF_001` — `entity_binding.cell_owner`: *"when soul transmigrates into another body, this field
  follows **the body**, not the soul."*
* `EF_001` — `LifecycleState { Existing | Suspended | Destroyed | Removed }`, today **per entity**.

> **TRG-A6 — lifecycle is a property of an ASPECT, not of an entity.** `BodyOrSoul` is already an
> aspect tag; it is currently used only to decide what transfers on transmigration. Generalise it:
> each aspect carries its own `LifecycleState`, and **a trigger is scoped to the aspect it acts
> through**. A body-scoped trigger on an entity whose body is `Destroyed` has no valid subject; a
> soul-scoped trigger on the same entity still does.

**Three persistence classes fall out, and the third is the interesting one:**

| Class | Survives body death? | Survives everything? | Example |
|---|---|---|---|
| **Body-bound** | ❌ | ❌ | position, equipment slots, `cell_owner`, martial cultivation |
| **Soul-bound** | ✅ | ❌ (soul can also be destroyed) | knowledge, language, cognitive progression |
| **Held-by-others** | ✅ | ✅ | **the grudge** — a rival's hatred of a dead man |

> **TRG-A7 — what others hold about you cannot be killed by your death, and this is FREE.** Under
> [WSA-A1](31_world_simulation_architecture.md) an imprint is state held **by the subject** about an
> object. The grudge lives in the rival's rows, not in the dead actor's. **A dangling reference is
> only a hazard when the data lives on the referent** — and by construction, here it never does.
>
> *"Chết rồi nhưng vẫn bị ghi thù"* therefore requires **no special case at all**. It is a
> correctness result the architecture already earned, and it is worth recording explicitly so nobody
> later "cleans up" imprints on death and destroys it.

### 5.1 The failure-tolerance laws

> **TRG-L2 — a trigger whose subject aspect is gone is DISCARDED, never an error.** It resolves to
> `Outcome::Discarded { reason }` — the kernel's existing discipline, in which *a failed precondition
> is a normal recorded outcome, never an error*. The PO's *"trigger nhưng sau đó không làm gì nữa"* is
> exactly this, with one addition: **it must not be silent.** A discarded trigger is a recorded event,
> per CS-D5/EVT-L5. Silence here would be [XST-D2](27_extensibility_stress_test.md)'s bug class — a
> degrade path that absorbs the failure and reports success.

> **TRG-L3 — a group is TOTAL: no trigger may abort its group.** One item's failure discards that
> item and nothing else. This is what makes the system tolerant rather than brittle, and it is the
> same totality requirement `Domain::apply` already carries.

**And the isolation that makes it safe:** under [WSA-A11](32_locus_as_actor.md) a reaction is a
*turn*, therefore a **separate transaction**. A failing reaction in G6 cannot roll back or corrupt the
G4 transaction that provoked it — the original already committed. **Failure isolation is not new
machinery; it is a consequence of modelling reactions as turns.**

> **TRG-F2 — the two halves of the PO's requirement are already satisfied by two decisions taken for
> other reasons.** Aspect-scoped invalidation comes from `BodyOrSoul` (built for xuyên không), and
> failure isolation comes from reactions-as-turns (built to bound recursion depth). Neither was
> designed for this. **That is the third time in this document that an existing decision turns out to
> be load-bearing for a problem it was not built for** — a pattern worth trusting.

---

## 6. The remaining tests

> **TRG-T2 — the six swap tests** of §3, one per adjacent boundary. Each asserts the named defect
> appears when the order is inverted. A boundary with no failing swap test is a boundary that does not
> need to exist — and should be merged into its neighbour rather than documented as locked.

> **TRG-T3 — the aspect-death matrix.** For each aspect ∈ {Body, Soul} × each state ∈ {Existing,
> Destroyed}: a trigger scoped to that aspect either fires or is discarded-with-reason, and **the
> discard is present in the event stream**. Paired per [IAS-D10](22_ingress_and_admission.md) with the
> positive case: a soul-scoped trigger on a body-dead actor **still fires**, and a rival's grudge
> against that actor **still exists and is still readable**.

---

## 7. Amendments

| # | Target | Change | Confidence |
|---|---|---|---|
| **R25** | `EF_001` `LifecycleState` | currently **per entity**; must become **per aspect** (TRG-A6) | **verified** |
| **R26** | `PROG_001` §4.3 `BodyOrSoul` | promote from *"what transfers on transmigration"* to a general **aspect tag** governing lifecycle and trigger scope | **verified** |
| **R27** | `DF07` / stat resolution | reference the single statement of TRG-A1 rather than restating the stage law a second time (TRG-F1) | **verified** |
| **R28** | [`27`](27_extensibility_stress_test.md) XST-R11 | `replacement_priority` is now **required**, scoped to G3, with the deterministic tie-break named | **verified** |
| **R29** | wherever death cleanup is specified | **must not** delete imprints held by others about the deceased (TRG-A7). Add an explicit *do-not-clean-up* note, since it looks like garbage to a future optimiser | **verify** |

**Build-order impact:** the [31 §6](31_world_simulation_architecture.md) sequence is unchanged, but
**E3 gains its real content**: not "design a trigger system" but *"declare the eight groups, implement
G3's priority, and write TRG-T1..T3"*. That is a substantially smaller and much better-specified
piece of work than it was two documents ago.

---

## 8. Open

| # | Question |
|---|---|
| **TRG-Q1** | **What is the full aspect set?** `Body` and `Soul` are established. Candidates: `Estate` (holdings that outlive both — an inheritance mechanic), `Name` (what is known of you, though TRG-A7 suggests this is not an aspect at all but purely held-by-others). Deciding wrongly means either a special case per aspect or an over-general tag nobody uses. |
| ~~**TRG-Q2**~~ | ✅ **RESOLVED in §9** — waves, `G2..G8` (never G1), `G3` rewrites / `G6` spawns. A reaction **may** be prevented, and it does not reproduce MTG's hardness. Two narrower questions opened: TRG-Q3, TRG-Q4. |
| **WSA-Q4/Q5** (carried) | what schedules a locus-actor's turn · may a locus act unwitnessed |

---

## 9. TRG-Q2 RESOLVED — the wave model

> **The question:** does a G6 reaction nest into its own `G1..G8` pass, and if so, may a reaction be
> **prevented** by a re-entered G3 — which is where MTG's rules become genuinely hard?

### 9.1 Three candidate shapes; two of them fail

| Shape | Fails because |
|---|---|
| **A · No nesting** — a reaction is just a normal turn in the initiative queue | *"Reflect when struck"* that resolves on your next turn **is not a reflect, it is a counterattack.** Timing **is** the mechanic; deferring it changes what the mechanic means. Rejected on fiction, not cost. |
| **B · Full recursion** — each reaction immediately re-enters `G1..G8` before the next reaction runs | Reactions become **order-dependent** (reaction 2 sees reaction 1's effects), which breaks [TRG-A1](33_trigger_group_order.md)'s within-group commutativity and would make TRG-T1's shuffle test red **by design**. It also makes "current HP" undefined mid-pass. Rejected on correctness. |
| **C · WAVES** ✅ | reactions are **collected**, then the whole batch resolves as one level; its reactions form the next level; repeat until empty or the budget is spent |

> **TRG-A8 — reactions resolve in WAVES.** Wave *n*'s outcomes are collected into a batch; the batch
> resolves as one pass; the outcomes of *that* pass form wave *n+1*. Waves are strictly sequential;
> members of a wave are simultaneous.

This is the same answer the genre's most-tested rules engines converged on (MTG's simultaneous-trigger
batching, Hearthstone's queue), reached here from the commutativity requirement rather than by
imitation — which is the better reason to trust it.

### 9.2 TRG-A9 — a nested pass runs G2..G8, and NEVER G1

> **TRG-A9 — G1 ADMIT applies once per EXTERNAL message and never to an engine-generated
> transaction.**

G1 is the trust boundary — producer identity, dedup, rate limiting, spam refusal
([22](22_ingress_and_admission.md)). A reaction originates *inside* the loop, from the engine, in
response to a committed event. Running it through G1 would mean **the engine rate-limiting its own
emissions**, and under [IAS-A6](22_ingress_and_admission.md) (a transport refusal must produce no
event) a dropped reaction would vanish silently — the exact failure [TRG-L2](33_trigger_group_order.md)
forbids.

Everything else applies. In particular **G2 AUTHORISE does**: a reflect still requires its owner to be
alive, to hold the shield, to afford the stamina. A reaction is a transaction, not an exemption.

### 9.3 TRG-A10 — G3 REWRITES, G6 SPAWNS: two powers that must never be conflated

This is the rule that makes the whole thing terminate, and it is the answer to *"does re-entering G3
reproduce MTG's hardness?"*

> **TRG-A10 — G3 REPLACE is `Transaction → Transaction` (a pure rewrite of the pending transaction).
> G6 REACT is `Outcome → Vec<Transaction>` (it spawns proposals into the NEXT wave). A replacement may
> never spawn; a reaction may never rewrite.**

Each half then carries its own, separately trivial, termination argument:

| | Why it terminates |
|---|---|
| **G3 rewrite** | a replacement applies **at most once per event** (MTG CR 616.1's actual rule, and it is the simple one), so the set of applicable replacements **strictly shrinks** with each application. No budget needed — it terminates structurally. |
| **G6 spawn** | each wave decrements a declared budget. |

**If G3 could spawn — or G6 could rewrite — the two would recurse into each other and neither argument
would hold.** That mutual recursion is precisely the source of MTG's hard cases; forbidding the
crossing removes it rather than managing it.

### 9.4 TRG-L4 — within a wave: read-old, write-together, conflicts by STABLE KEY

> **TRG-L4 — every member of a wave reads the **pre-wave** state and contributes deltas that are
> applied together. Where two deltas conflict, the conflict resolves by a **declared stable key**
> (entity ordinal), **never by arrival order**.**

The read-old half is what makes wave members commutative — if reaction 2 could see reaction 1's
effects, shape B's problem returns through the back door.

The conflict half is subtler and is the part that would have been got wrong. Two reactions each spend
my last coin: under read-old both see it, and applying both would breach the floor. One must be
discarded — so G4 is **not** unconditionally commutative. It stays **shuffle-invariant** anyway,
because the loser is chosen by a stable key rather than by who arrived first. That is what keeps
[TRG-T1](33_trigger_group_order.md) green *and* meaningful:

> **Determinism and shuffle-invariance are different properties, and the stable-key rule is what buys
> both at once.** Note this is the *same* rule G3 already needed for its priority tie-break — one
> rule, two groups.

### 9.5 The budget cuts at WAVE granularity, never mid-wave

> **TRG-A11 — when the wave budget is exhausted, the entire next wave is refused; a wave is never
> partially run.**

A mid-wave cut-off would drop *some* reactions and keep others, and the choice of which would depend
on iteration order — reintroducing order-dependence exactly where TRG-A1 forbids it. **A truncated
group is order-sensitive by construction.**

Refusal is recorded per [TRG-L2](33_trigger_group_order.md): each unrun reaction resolves to
`Outcome::Discarded { reason: WaveBudgetExhausted }`. The budget is a declared ruleset constant
([IMP-D1](26_implementation_architecture.md): a law's structure is code, its constants are config) and
is scoped to the originating turn — turn slots ([IAS-D6](22_ingress_and_admission.md)) already bound
how many turns an actor gets, so no second budget is needed.

### 9.6 So: may a reaction be prevented? **Yes** — and it costs nothing

A reaction is a transaction in wave *n+1*, and wave *n+1* runs G3. So *"my ward prevents your reflect"*
works, with no special case.

The three things that make MTG hard **are all absent here**:

| MTG's difficulty | Here |
|---|---|
| the affected player **chooses** the order of applicable replacements | no player prompts (COMB-A1 — the engine is deterministic and LLM-free); order is a **declared** `replacement_priority` |
| replacements replacing replacements, unboundedly | **at most once per event** (TRG-A10) |
| replacement and triggering interleaved in one priority system | **G3 rewrites, G6 spawns** — structurally separated (TRG-A10) |

> **TRG-F3 — the property that makes this tractable is the same one that made the whole design
> deterministic: no player prompt in the resolution path.** The constraint that looked like a
> limitation (COMB-A1) is what removes the genre's hardest rules problem.

### 9.7 What a wave re-derives, and what it does not

**G8 DERIVE runs per wave — as an invalidation, not a re-resolution.** Wave *n+1*'s G2 must not
authorise against capability computed before wave *n* (if wave *n* bankrupted me, my reaction should
fail). But a full capability fold per wave would multiply the cost.

The pattern already exists: `StatSnapshot`/`StatEpoch` — **bump the epoch, re-resolve lazily at
read, never patch in place** ([DF7-A2](27_extensibility_stress_test.md)). So a wave's G8 is an epoch
bump; the fold runs only if wave *n+1* actually reads it.

**And the reaction surface is the wave's committed event stream — including discards.** Since a
discard is an event (TRG-L2), *"when my reflect is prevented, gain rage"* is expressible with no new
mechanism. That uniformity is worth having deliberately rather than discovering later.

### 9.8 Still open, narrowed

| # | Question |
|---|---|
| ~~**TRG-Q3**~~ | ✅ **RESOLVED in §10** — attribution follows the **ownership** chain to the nearest accountable entity, stamped at commit. The proximate-vs-provoker framing was the wrong question: there is no global fault field, only per-observer records. |
| **TRG-Q4** | **May a reaction fire from a G3 or G5 event, or only from G4/G5 outcomes?** §9.7 says the surface is the wave's event stream, which is uniform — but a reaction to a *replacement* is one step closer to the recursion TRG-A10 exists to prevent. Leaning yes-because-uniform; wants one adversarial pass before E3. |

---

## 10. TRG-Q3 RESOLVED — attribution follows OWNERSHIP, not causation

> **The PO's rule:** *"ghi lỗi cho owner — ví dụ thực tế: chó cắn người thì người ta kiện chủ con chó."*

> **TRG-A12 — every effect is attributed to the OWNER of the thing that produced it, never to the
> thing itself.** The dog is not sued; its owner is.

**This is better than either option TRG-Q3 offered**, and the reason is structural rather than
legalistic: I framed the question as *proximate cause vs provoker*, which is a **causal** question —
and causal chains **fork** (the blow, the shield, the smith who made it, the sect that trained him).
Ownership chains do not. Attribution by ownership is therefore **total and single-valued**, which is
exactly what an engine needs and what a causal rule can never give.

It also introduces **no new concept**: ownership is already the relation
[EXC-A3](30_exchange_model_and_dataflow.md) defines, and it is already *"a relation the world
recognises"* — which is precisely what accountability is.

### 10.1 Where the chain stops

A dog is owned by a servant, who serves a lord. Climbing forever makes a king liable for every bite.

> **TRG-A13 — attribution climbs the ownership chain to the nearest ACCOUNTABLE entity and stops
> there.** *Accountable* is not a new flag: it is **"may be the object of an imprint"**, a predicate
> the corpus already expresses (`ACT_001`'s `actor.synthetic_actor_forbidden` is the same predicate,
> written as a prohibition).

| Producer | Climbs to | Because |
|---|---|---|
| a shield's reflect | its wearer | a shield does not decide, and cannot be resented |
| a dog | its owner | a beast can be killed but not held to account |
| a trap in a village | **the village-locus** ([WSA-A7](32_locus_as_actor.md)) | a locus is an entity *and* an actor, so it can be resented — *"that village is dangerous"* is a real, useful imprint |
| a servant acting on orders | **the servant** | a servant *is* accountable; the chain stops at the first entity that could have chosen otherwise |

The lord is reachable only through a *second*, separate mechanism (command, faction standing) — not by
attribution climbing past an accountable link. **One climb rule, one stop condition, no special
cases.**

### 10.2 Attribution is stamped at commit, never re-derived

Sell the dog the day after it bites: the new owner is not liable. So:

> **TRG-L5 — `attributed_to` is resolved at G7 and STAMPED INTO THE EVENT.** It is never looked up
> from current ownership afterwards.

This is not a detail — re-deriving attribution from present-day ownership would let a **property
transfer silently rewrite history**, and in an event-sourced system whose recovery model is replay,
that is a correctness failure, not a fiction problem. Stamping is also what makes attribution replay
identically, which the digest work ([XST-D5](27_extensibility_stress_test.md)) requires.

### 10.3 The original question dissolves

*A strikes B; B's reflect kills A. Who does A's family blame?*

* The reflect is owned by B, and B is accountable ⇒ **A's family records a grudge against B.**
* **And, separately**, B and every witness record that **A struck first.**

**Both happen. Nothing arbitrates between them** — because imprints are non-conserved and
per-observer ([WSA-A1](31_world_simulation_architecture.md), ACT-A5's two asymmetric rows).

> **TRG-F4 — there is no global "fault" field, and there must never be one.** There are only
> per-observer records, and different observers legitimately record different things: A's family
> blames B, B's sect records that A was the aggressor, the village records that both are trouble.
> The question *"who was really at fault?"* has no engine-level answer **by design** — which is what a
> social simulation should do, and it is why this resolves at zero cost.

### 10.4 Three consequences worth having deliberately

1. **Blood feud is free.** A grudge names an entity, and under
   [TRG-A7](33_trigger_group_order.md) it survives that entity's death. So a grudge against a dead man
   persists and can pass to his heirs — an inheritance mechanic that needs no new machinery.
2. **Territorial reputation is free.** Attribution to a locus makes *"this village is dangerous"* an
   ordinary imprint, which is exactly the strategy-layer substrate
   [WSA-F6](32_locus_as_actor.md) argued for.
3. **"Nobody to blame" must be EXPLICIT.** An ownerless trap in an Untracked cell attributes to
   nothing — and that must be a **recorded `Unattributed` value, never a null that gets skipped.** A
   silently dropped attribution is [XST-D2](27_extensibility_stress_test.md)'s bug class (a degrade
   path that absorbs the failure and reports success) reappearing in the social layer.

### 10.5 Tests

> **TRG-T4 — the attribution matrix.** For each producer kind {reflect, beast, trap, servant,
> ownerless}: assert the grudge names the expected accountable entity, and that a **transfer of
> ownership after the event does not move the blame**. Paired per
> [IAS-D10](22_ingress_and_admission.md): the ownerless case must produce a recorded `Unattributed`,
> not an absent imprint.

> **TRG-R30 (amendment)** — the event envelope gains `attributed_to: Attribution` where
> `Attribution = Entity(EntityId) | Unattributed`. Closed set, no `Option`, so the "nobody" case cannot
> be silently skipped by a `if let Some(...)`.

---

## 11. Chain termination — three layers, and they are NOT interchangeable

> **The PO's rules:** *"mọi trigger phải có chance và hard cap x% (ví dụ 95%); trigger chain limit x
> chain (ví dụ 10); trong một số game cả hai nhân vật đều có phản đòn, thì người ta chỉ tính phản đòn
> trên sát thương gốc thôi, bỏ qua phản đòn của phản đòn — compute lag."*

All three are right and all three should ship. But they provide **different kinds of guarantee**, and
the most important thing to state up front is that **the probability cap is not a bound.**

| Layer | Guarantee | Role |
|---|---|---|
| **L1 · once-per-kind** (the third rule) | **structural — guaranteed termination**, depth ≤ number of declared reaction kinds | **correctness** |
| **L2 · chain limit** (the second rule) | absolute, arbitrary | **safety net for a bug in L1** |
| **L3 · chance ≤ 95 %** (the first rule) | **none — it is a taper, not a bound** | **feel + degenerate-case shaping** |

**Why L3 alone cannot be the bound.** At `p = 0.95` the expected chain is `1/(1−p) = 20`, but
`P(depth ≥ 100) = 0.95¹⁰⁰ ≈ 0.6 %`. Across millions of actions that is not rare — it is routine. A
probabilistic taper shapes the *distribution*; it never closes the *tail*. Shipping it as the
termination argument would mean the worst case is a live incident waiting for enough traffic.

### 11.1 L1 — TRG-A14: the real rule, and it is one we already have

> **TRG-A14 — a reaction of kind K may not be triggered by an event that a reaction of kind K
> produced. Each reaction kind fires AT MOST ONCE per originating chain.**

The PO's *"chỉ tính phản đòn trên sát thương gốc"* is exactly this, and it is **structurally stronger
than both other rules**: termination needs no budget and no dice, because the set of still-eligible
kinds strictly shrinks with each wave. Max depth is `|reaction_kinds|`, deterministically.

> **TRG-F5 — this is the SAME rule as G3's.** [TRG-A10](33_trigger_group_order.md) already gives
> replacements *"at most once per event"* (MTG CR 616.1). Applying the identical rule to G6 makes
> **one termination argument cover both groups** — and the fourth time in this document that a rule
> adopted for one reason turns out to be the right one elsewhere.

### 11.2 L2 — TRG-A15: the cap must sit ABOVE the structural bound, and firing it is a DEFECT

> **TRG-A15 — `chain_limit` is a declared ruleset constant, and `chain_limit > |reaction_kinds|` is
> validated at ruleset load.**

If the cap is set *below* the structural bound it stops being a safety net and silently becomes a
**gameplay rule** — legal chains get truncated, and content authored against the declared kinds
mysteriously stops working at depth 10. The load-time validation is the same shape as PL_007's ITM-C7
bootstrap warning (*a rule referencing an instrument tag no item carries*), and it is cheap.

> **TRG-L6 — if the chain limit ever actually fires, that is a DEFECT SIGNAL, not normal operation.**
> It means L1 failed. It must be recorded as `Outcome::Discarded { reason: ChainLimitExceeded }` **and
> surfaced as an alertable metric** — never absorbed quietly.
>
> A cap that silently truncates gameplay is [XST-D2](27_extensibility_stress_test.md)'s bug class
> exactly: *a degrade path absorbs the bug and reports success.* This project has now shipped that
> pattern twice (`saturating_mul`, the `Substitute` fallback); the third time should be caught by the
> rule rather than by an audit.

### 11.3 L3 — TRG-A16: chance is scoped to G6, and it costs an RNG coordinate

> **TRG-A16 — the `≤ 95 %` cap applies to CHAIN-EXTENDING reactions (G6), never to all triggers.**

A blanket cap is wrong in a way that would read as a bug: *"when I die, explode"* must fire **100 %**
of the time — at 95 % one death in twenty silently fails to explode, and no player would ever call
that a design choice. Likewise **G7 IMPRINT must never be probabilistic**: a villager either witnessed
what you did or did not. Probability belongs where it shapes a *fight*, not where it decides whether
the world *remembers*.

**And it has a hard prerequisite.** Every chance is an RNG draw, so every draw needs its own
coordinate — otherwise every reaction in a wave draws the *same* value (all fire or none), which is
[convergence point #6 / XST-R4](27_extensibility_stress_test.md)'s multi-hit bug in a new place. So:

> **TRG-A17 — the RNG coordinate for a reaction is `(…, wave_depth, sub_index, role)`.**
> [XST-R4](27_extensibility_stress_test.md) must land **before** L3 ships, and its cost is the reason
> that recommendation was already marked *"cheap now, expensive later"* — retrofit cost rises with
> every replay log written.

### 11.4 The real cost is not compute — it is WRITE amplification

The PO's stated motivation is compute lag. Against the measured numbers the picture is a little
different, and sharper:

* an island step is **176–229 ns** ([21](21_architecture_ceilings.md)) — a 10-wave chain of a few
  reactions each is *microseconds* of CPU. **Compute is not the constraint.**
* but every wave's outcomes are **durable events** (rejections included, per CS-A4), and the measured
  single-writer ceiling is **~170 commits/s**. **That** is the constraint — the same
  write-amplification argument [IAS-A6](22_ingress_and_admission.md) already made about spam.

> **TRG-A18 — a chain commits ONCE, not once per wave.** Waves are *internal resolution*; the durable
> unit is the originating action **plus everything it caused**.
>
> This does not conflict with [TRG-A10](33_trigger_group_order.md)'s failure isolation, because the
> two are different axes: a reaction is a separate **transaction** (its own preconditions, its own
> discard) but shares the originating action's **commit batch**. It also buys atomicity for free — no
> observer ever sees a half-resolved chain.

### 11.5 Tests

> **TRG-T5 — the mutual-reflect test.** Two actors both carrying reflect; A strikes B. Assert the
> chain is `strike → B's reflect → STOP`, that A's reflect is **discarded with a recorded reason**
> (kind already fired), and that the whole thing lands as **one commit batch**.
>
> **TRG-T6 — the cap must be reachable in a test and unreachable in play.** A synthetic ruleset with
> `chain_limit` deliberately set low must produce `ChainLimitExceeded` and increment the metric —
> proving the alarm works. The real ruleset must then be shown to satisfy
> `chain_limit > |reaction_kinds|` at load. **A safety net nobody has ever seen fire is a safety net
> nobody knows is connected.**

**Amendment R31** — `chain_limit` and per-kind `chance` (capped) join the declared ruleset constants;
`ChainLimitExceeded` and `ReactionKindAlreadyFired` join `DiscardReason`.

---

## 12. Cross-references

* [`32_locus_as_actor.md`](32_locus_as_actor.md) — reactions as turns, locus-actors
* [`31_world_simulation_architecture.md`](31_world_simulation_architecture.md) — layers, imprint definition
* [`30_exchange_model_and_dataflow.md`](30_exchange_model_and_dataflow.md) — the transaction, three currencies
* [`27_extensibility_stress_test.md`](27_extensibility_stress_test.md) — XST-F5 (unfalsifiable order), XST-D8 (clamps), XST-R11 (REPLACE)
* [`22_ingress_and_admission.md`](22_ingress_and_admission.md) — IAS-A2 in/out of loop, IAS-D10 paired tests
* [`14_sim_core_spec.md`](14_sim_core_spec.md) — `Outcome::Discarded`, totality of `apply`
* [`features/00_progression/PROG_001_progression_foundation.md`](features/00_progression/PROG_001_progression_foundation.md) — `BodyOrSoul`
* [`features/00_entity/EF_001_entity_foundation.md`](features/00_entity/EF_001_entity_foundation.md) — `LifecycleState`, `cell_owner` follows the body
