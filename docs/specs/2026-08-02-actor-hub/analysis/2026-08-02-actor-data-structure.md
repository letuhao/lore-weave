# Actor data structure — early decision record (pools, stats, status, lifecycle)

> ## ⚠ SUPERSEDED AS SSOT — 2026-08-02. THIS IS A DERIVATION RECORD.
>
> **Two things about this file were wrong once the round finished, and both are corrected here rather than
> left for a reader to discover:**
>
> **① Its former title claimed *the substrate*.** The substrate is now owned by
> [`2026-08-02-engine-substrate.md`](../2026-08-02-engine-substrate.md). **Two documents naming themselves the substrate is
> the exact two-SSOT defect this round spent its last hours removing**, so the claim is withdrawn.
>
> **② Its precedence rule pointed at a document that is no longer a contract.** It said *"where the two
> disagree, the dataflow spec wins"* — but [`2026-08-02-actor-dataflow.md`](2026-08-02-actor-dataflow.md)
> was itself demoted to a derivation record. **The chain resolved to a non-contract.**
>
> **The precedence chain, corrected:**
>
> | rank | document | role |
> |---|---|---|
> | 1 | [`2026-08-02-actor-hub.md`](../2026-08-02-actor-hub.md) · [`2026-08-02-engine-substrate.md`](../2026-08-02-engine-substrate.md) · [`2026-08-02-seams-and-triggers.md`](../2026-08-02-seams-and-triggers.md) | **the contracts** — what is decided |
> | 2 | [`the RUN-STATE`](../../../plans/2026-08-02-actor-substrate-RUN-STATE.md) | the sealed decisions, `D-1`..`D-194` |
> | 3 | [`2026-08-02-actor-dataflow.md`](2026-08-02-actor-dataflow.md) | derivation record — **how** it was decided |
> | 4 | **this file** | derivation record, earliest layer — predates the plugin frame entirely |
>
> **What this file still has that nothing else does:** the `D-1`..`D-14` era reasoning and the first
> red-team round. **What it no longer states correctly:** anything about actor scope. It was written before
> the boundary existed, so it treats as actor-core several things the hub spec hands to plugins.

**Status:** DERIVATION RECORD (was: DESIGN) · **Date:** 2026-08-02 · **Base:** `50bff49a4`
**Run state:** [`docs/plans/2026-08-02-actor-substrate-RUN-STATE.md`](../../../plans/2026-08-02-actor-substrate-RUN-STATE.md) — decisions `D-1..D-14` are sealed there; this document does not re-open them.

> **⚠ READ THIS FIRST — 2026-08-02, after nine rounds of PO review.** This document is the **decision
> record**; [`2026-08-02-actor-dataflow.md`](2026-08-02-actor-dataflow.md) (~4 200 lines, 21 diagrams) is
> the **reasoning**, the measured evidence and the open register. ~~Where the two disagree, **the dataflow
> spec wins**~~ **[CORRECTED — see the precedence table above: BOTH are derivation records now, and the
> CONTRACTS win over either]** — it is where every decision after `D-14` was made and where each was checked against code.
>
> **Sections superseded since this file was written:** §3.1 (survives, with the S1-only blast radius now
> established) · **§4** (per-actor projection — see `D-25`/`D-27`: a feature attaches through **rows**, not
> fields) · **§5.3** (three axes → **four**, corrected in place below) · **§7.1** (predates `D-10`). §10
> folds in `D-15`..`D-53`.
>
> **Do not cite `services/commit-service/src/domain/` as evidence** — it is a 649-line **stub** for an
> undesigned feature (`D-35`), and it misled the dataflow spec four times. §1's `law.rs` example is
> retained because it illustrates the *shape* of the seam problem, not because the stub decides anything.

**Scope:** the actor and its data structure. Combat vocabulary is **out** (`D-14`) — it belongs to the
combat element's own design, and the current combat logic will be rewritten. The trigger/generator
mechanism is **out** (`D-9`) — this round only guarantees the seam exists.

---

## 1. What this settles, and why it could not wait

Three independent designs describe one concept, and none of them is built.

| | `RES_001` §4.1 (locked 2026-04-26) | `ruleset-core::resource` (shipped 2026-07-29) | `commit-service::Actor` (running) |
|---|---|---|---|
| identity | `VitalKind` — closed engine enum | declared quantity ordinal, 32 wide | `hp`, a field |
| ceiling | `max_value: u32` on the instance | `CeilingBinding::{Slot, Fixed}` | `max_hp: i64` |
| regen | `RegenRule::{TimeBased, RestBased, Manual}` | `RegenType::{None, Flat, PerMille}` | none |
| at floor | `OnZeroEffect::{EmitMortalityTrigger, …}` | `ZeroBehaviour::{Clamp, BlockCosts}` | `hp > 0` |
| home | aggregate `vital_pool` keyed by `actor_ref` | hashed ruleset + an actor array that does not exist | inline on `Actor` |

`grep` for `LifecycleState`, `entity_binding`, `vital_pool`, `VitalKind`, `ActorCore`,
`resource_inventory` across `crates/` + `services/` + `migrations/` returns **zero hits for all six**.
About 3,100 lines of design, no code. What runs is the third column — smaller than either design, and
already violating the boundary both of them draw.

**The concrete failure this produces.** `law.rs:218` sets `knocked_out = Some(5)` with the comment
*"KO, not death: revivable"*, and `law.rs:225` — the next statement — evaluates the encounter as over,
because `outcome_of` passes `a.hp` and `evaluate_outcome` tests `hp > 0`. The revival window is opened
and closed in one breath. There is no seam between *a number reached zero* and *the consequence
resolved*, so an ability that fires at zero has nothing to attach to.

## 2. The principle, and where it cuts — **Q1**

> **`D-2`.** The engine closes on **mechanism**. The manifest closes on **vocabulary**.

An OS does not fix your file names; it fixes `read`/`write`/`seek`. A DB does not fix your table
names; it fixes `SELECT`/`JOIN` and the index kinds. The engine is an environment in that sense. A
hardcoded noun is a manifest that cannot grow.

| concern | **Mechanism** — engine, closed | **Vocabulary** — manifest, declared |
|---|---|---|
| quantity identity | ordinal assignment, never-reuse, the table living inside the hashed bytes | which quantities exist, and their machine keys |
| quantity kind | the three kinds and their differing storage + update rules (§3) | which kind each declared quantity is |
| regeneration | the closed set of arithmetic shapes, each with a closed form (§6.4) | which shape, and where the rate comes from |
| ceiling | that a ceiling is a target contributions aggregate into, never a stored constant | which quantity or derived value supplies it |
| modifier layers | ⚠️ **CORRECTED 2026-08-02 (`O-96`)** — the engine owns the **layer set AND its order** (`DF7-A3`), because the aggregation policy depends on what each layer *means*: per-mille factors sum **within** a layer and do not chain **across** one, so an author inserting a layer changes arithmetic they cannot see. It also avoids a fifth ordinal space for never-reuse to guard | **not the layers.** An author who wants *"sect blessing"* declares a **modifier SOURCE inside an existing layer** — the same shape as a feature contributing to an ordinal the reality declared without owning one |
| threshold | that a threshold is stateful, has distinct enter/exit conditions, and coalesces its events | which thresholds, at what values, with what effects |
| status | that a status carries source, magnitude, duration and a stack policy | which statuses exist |
| lifecycle | holding a state · validating a transition against the declared set · running a cascade policy · appending to the log atomically with the transition | which states exist, which transitions are legal and what triggers them, which cascade policy each state uses, and the reason vocabulary |
| cascade policy | the closed set `Drop \| Cascade \| Suspend \| Keep` | which policy each declared state uses |

The shape is consistent throughout: **the policy enum is closed, the assignment of a policy is
declared.** chaos reaches the same shape from the other direction — `cap_layers.resources.yaml`
declares the layers `REALM/WORLD/EVENT/TOTAL` while `across_layer_policy: INTERSECT` stays a fixed
choice from a closed set.

### 2.1 `ActorKind` and archetype are different axes, and both are needed

`ActorKind::{Pc, Npc, Synthetic, Locus}` answers engine questions — is this actor **in the world**,
does it **take turns**, may it hold an opinion. That is mechanism and stays closed.

*Which quantities and which lifecycle an actor has* is vocabulary. It is carried by a declared
**archetype** (§4). A village and a swordsman are both `ActorKind::Locus` / `Npc` respectively, but
what separates their data is their archetype, not their kind.

## 3. The quantity substrate — **Q2**

`D-7` unifies stats and pools. They are the same thing seen at different update frequencies, and the
distinction that actually matters is **stored vs recomputed**:

| kind | stored? | what moves it | example |
|---|---|---|---|
| **Pool** | yes — a `current` | spending, and a regen contribution per tick | hp, mana, qi |
| **Accumulated** | yes — a `current` that only grows or decays slowly | cultivation breakthrough, achievement, permanent equipment infusion | base constitution after ascending a realm |
| **Derived** | **no** — recomputed from the other two | the layered modifier resolution | strike power, armour, move range |

### 3.1 Three tables, one ordinal space — **PO-DECIDED 2026-08-02**

`QTY-Q10` records the right worry: that a shared declaration table accretes a discriminant, then
per-kind optional fields, then per-kind validators, and becomes the god class by a slower road — *"the
shape `RulesetPatch`'s 20 optional fields already have."*

**The PO chose three separate declared tables**, over the tagged-union alternative this document first
proposed, for a reason not weighed in the original draft: **the manifest is generated by an LLM.**
Three flat tables with distinct, non-overlapping schemas are markedly easier to generate correctly and
to validate per-table than one table whose row shape depends on a discriminant — a generator that picks
the wrong variant produces a *plausible* row, which is the worst failure mode for generated content.
Extension is also cheaper: a new field on `Pool` cannot widen `Derived`.

```
pool_quantities        [ key, floor, base, ceiling: CeilingBinding, regen: RegenSpec, at_floor ]
accumulated_quantities [ key, floor, base, ceiling: CeilingBinding, decay: RegenSpec ]
derived_quantities     [ key, terms ]                    // resolved, never stored
```

**One ordinal space across all three, and that is not negotiable.** `Vital → qi` must be able to name
any declared quantity, a per-actor value array must be indexable by one number, and `QTY-A5`'s
never-reuse guarantee is meaningless if three tables number independently. So ordinals are assigned
across the union of the three tables in declaration order; the tables partition the *vocabulary*, not
the *numbering*.

> ⚠ **The cost this buys, stated so the red team does not have to find it:** three tables means the
> *"which table is this ordinal in"* lookup is now a real question that a tagged union answered for
> free. Resolution must not become three scans. Field names above are indicative; the load-bearing
> claims are **three tables** and **one ordinal space**.
>
> **Blast radius, established since** (dataflow §1's S1/S2 split + §11.9): this affects **S1 authoring
> only** — the resolved ordinal space at S2 is identical either way — so being wrong costs a re-authoring
> pass, **not** a schema change and **not** a digest move. And the experiment that would settle it (`O-4`)
> **cannot run yet**: its metric is validator-refusal rate, the validator (`O-13`) does not exist, and
> both arms would score zero. Take three tables on judgement.

### 3.2 The accumulated kind has no home today, and that is the larger hole

`ModifierSource::Progression` names a layer ([modifier.rs:12](../../../../crates/game-rules/src/stats/modifier.rs#L12)) and **nothing produces its modifiers**. `grep` for
`actor_progression`, `ProgressionState`, `accumulated`, `realm_level`, `tier_reached` over `crates/` +
`services/` finds nothing relevant. `StatEpoch.progression_turn` is a staleness counter, not storage.

So *"how far has this actor cultivated"* has nowhere to live. That is the same absence as `pools[]`
having no home, and it is why the two must be designed together: solve them separately and the result
is two substrates that drift.

### 3.3 A rate may come from another quantity

`ResourceDecl.regen_rate: i32` is a constant in the hashed ruleset — identical for every actor. chaos
computes it per actor: `derived_stats.go:221` sets `ResourceRegen = Vitality × multiplier`.

Our current design **cannot express "you recover qi faster because your constitution is higher"**,
which is a central mechanism of any cultivation system. `RegenSpec` must therefore admit a **rate
sourced from a derived quantity**, not only a literal — which is also what makes the three kinds one
substrate rather than three parallel ones.

## 4. The per-actor projection — **Q3**, and `D-13`

A reality declares its quantities and its lifecycles. Which of them does *this* actor have?

The question has no answer in the shipped substrate: `ResourceDecl`/`ResourceTable` carry no actor,
kind, class or archetype dimension — `grep` finds nothing. Every actor in a reality therefore receives
every declared pool, starting at the same `base`. *"This race has no hp"* is inexpressible, and it is
not hypothetical: `ActorKind::Locus` was applied on 2026-07-30, a village is an actor, and a village
has no hp. Today it would receive one — or receive zero, which under `hp > 0` reads as already dead.

`D-13` observes that *"which pools does this actor have"* and *"which lifecycle does this actor
follow"* are **the same question**. Answering it twice guarantees two mechanisms that drift.

**PO-DECIDED 2026-08-02 — the archetype is a PRESET; the ACTOR is the data.** The draft of this
section proposed the archetype as the unit of projection and the actor as a thin delta. The PO rejected
that, citing Bethesda's base-form/reference split:

> An archetype is only used to **fetch a preset at spawn**. The actor is the **snapshot and the data
> actually used** — an aggregate of many sources, because it can change at runtime. Close the actor
> completely and you close gameplay completely; extending features later becomes very hard.

So:

| | archetype | actor |
|---|---|---|
| what it is | a **declared template**, in the hashed bytes | the **live snapshot**, per-actor state |
| when it is read | **at spawn**, once | every tick |
| after spawn | the actor does **not** consult it | authoritative on its own |
| may diverge | — | **arbitrarily**, at runtime |

An archetype names which quantities to grant, with what starting parameters, which lifecycle machine to
adopt, and which thresholds to install. The actor **copies** that at spawn and then owns it. A
swordsman who learns a technique granting a new pool simply **gains that pool on the actor** — no
overlay type, no new archetype, no author work. This is what makes a runtime-granted ability
expressible at all.

**Why this is the right call and not merely the PO's call.** A template consulted at read time makes
every runtime divergence a special case, and the set of special cases is exactly the set of features
nobody has thought of yet. Copy-at-spawn makes divergence the *default* and costs only storage —
`O(quantities the actor actually has)`, which is small precisely because §4's absence is structural.

**Absence stays structural.** An actor has no slot for a quantity it was never granted — not a zero, not
a sentinel. This is what makes *"this race has no hp"* and *"a village has no hp"* representable, and it
is the property that must survive the red team's attention.

> ⚠ **The cost, stated rather than hidden:** the archetype is in the digest, the actor's copy is not.
> Editing an archetype therefore does **not** retroactively change actors already spawned from it, and
> that is deliberate — but it means *"what rules is this actor running under"* is answered by the actor,
> not by the current manifest. `RLS-A13`'s digest pin covers the rules; the actor's divergence from them
> is per-actor state and needs its own provenance story. **This is the sharpest open edge in this
> document.**

## 5. The three layers — **Q4**

> **`D-5`.** Depletion, status and lifecycle are three things. Fusing them is what makes an ability
> that fires at zero unimplementable.

### 5.1 The layers, and what each is forbidden to know

| layer | owns | must NOT know |
|---|---|---|
| **1 · Quantity** | the number, its bounds, its regen, and the fact that it crossed a declared threshold | what any threshold *means* |
| **2 · Status** | which statuses an actor carries, with source, magnitude, duration and stack policy | arithmetic |
| **3 · Lifecycle** | the durable state, its transitions, and the cascade | combat, or any single quantity |

Each boundary is crossed by an **ordered event**, and that ordering is the whole hook `D-9` needs later:

```
quantity crosses a declared threshold
        │   emits  ThresholdCrossed { actor, quantity, threshold_id, direction }
        ▼
adjudication  ── declared reactions may intervene here ── (mechanism DEFERRED, D-9)
        │   emits  StatusApplied / StatusCleared
        ▼
a status reaching a declared terminal condition
        │   emits  LifecycleTransitionRequested { actor, to_state, reason }
        ▼
the state machine validates against the DECLARED transition set, runs the cascade
policy, and appends to the lifecycle log — atomically with the transition
```

This round builds none of it. It fixes that **the seam exists and is ordered**, so the deferred
mechanism has somewhere to attach. A design in which layer 1 writes layer 3 directly — which is what
`law.rs:218-228` does today — has no such place.

### 5.2 `Vital` restated

> **`D-6`.** `Vital` names *"the pool whose exhaustion raises the mortality question"* — **not**
> *"the pool whose zero means dead"*.

`RES_001` already had the right instinct in its naming: `OnZeroEffect::EmitMortalityTrigger` emits a
*trigger* ([RES_001:326](../../../03_planning/LLM_MMO_RPG/features/00_resource/RES_001_resource_foundation.md#L326)), and `RES_001:604` emits `MortalityTransitionTrigger`. The three-layer
model is present in that spec. **The shipped code jumps from layer 1 to layer 3 and skips layer 2
entirely.**

`ZeroBehaviour` having **no `Defeat` variant** is correct and stays — though for a deeper reason than
doc 35 gives. Doc 35 argues law-versus-config; the real reason is that **death is not a property of a
pool at any layer.**

### 5.3 Lifecycle is THREE orthogonal axes, not one enum

**The repo already carries two lifecycle axes, designed in two documents that do not reference each
other's mechanism:**

| | axis | values |
|---|---|---|
| [`EF_001 §6`](../../../03_planning/LLM_MMO_RPG/features/00_entity/EF_001_entity_foundation.md) | lifecycle state | `Existing · Suspended · Destroyed · Removed` |
| [`AIT_001` / doc 29](../../../03_planning/LLM_MMO_RPG/29_ontology_existence_self_others.md) | **existence tier** | `0 Generated (Untracked) · 1 Declared · 2 Stateful · 3 Irreversible` |

And `ONT-D1`'s **attention-promotes** moves an entity between **tiers**, not between lifecycle states.
Two mechanisms for one concept, neither aware of the other — the shape this whole round exists to clear.

**Cross-domain evidence that the single enum is the defect, not merely incomplete.** Every architecture
consulted separates *existing* from *resident*:

| | does it exist | **is it resident / live** | eviction policy |
|---|---|---|---|
| **OS 7-state model** | `New` / `Terminated` | `Ready`⟷`Suspended Ready`, `Blocked`⟷`Suspended Blocked` | swapping |
| **Vue `<KeepAlive>`** | mounted / unmounted | **`activated` / `deactivated`** — separate hooks; a deactivated component is **not destroyed** | LRU with `max` |
| **Akka Cluster Sharding** | entity identity persists | **`Passivate`** — the instance stops, the identity survives, messages are buffered and delivered to a **new incarnation** | `passivate-idle-entity-after` |
| **Cloudflare Durable Objects** | id persists globally | **hibernation / eviction** — in-memory state lost, durable storage intact, constructor re-runs | idle |

The seven-state process model exists **precisely because** the five-state model could not distinguish
*in main memory* from *swapped to disk*. `LifecycleState` places `Suspended` (residency) on the same
axis as `Destroyed` (existence), so one field answers two unrelated questions. **That is why the
observer pattern is not controllable today.**

#### The model

> **⚠ CORRECTED 2026-08-02 — this table had THREE axes and conflated two of them. The surviving model has
> FOUR, and "Fidelity" is not one of them.** The original row 1 fused *how much is persisted* (mechanism)
> with *what state the fiction says it is in* (vocabulary); row 3's AoI/LOD is not a separate axis at all
> — **simulation LOD IS rows 1+2** (`P-E`); and control was missing entirely. See dataflow §5.8.1, §5.10,
> §9.5.

| # | axis | closed by | values | moved by | fiction-visible? |
|---|---|---|---|---|---|
| **1 · Tier** | **mechanism — engine** | `Untracked · Declared · Stateful · Irreversible` — *how much of the actor is materialised*, and which declared transitions are enabled | attention (`ONT-D1`), capacity caps | **no** |
| **2 · Existence** | **vocabulary — declared** | an ordinal into the reality's declared state set (`alive`, `destroyed`, a settlement's `razed`, …) | death, admin action, a declared trigger | **yes — this is the point** |
| **3 · Residency** | **mechanism — engine** | `Active · Passivated · Evicted` | the scheduler, a memory budget, **an observer arriving or leaving** | **no — and that is the law** |
| **4 · Control** | **a RELATION, not a field** | `control_binding` per-`(controller, actor)`, **many-to-many** — one controller may hold several actors (分身 *fēnshēn*, a cultivator's split body) | bind / release / handover (`ACT-D1`) | **yes** |

**Why "Fidelity" disappeared as an axis** (`P-E`): *how often and how coarsely we compute* is platform
config and player-**invisible** — that is rows 1+3 doing their job. What a game with time dilation calls
LOD is a different thing entirely: `TDIL_001`'s *how much in-world time passes* is **hashed rules and
player-visible**. Opposite classification ⇒ **they may never share a field**, and neither is a third axis
of lifecycle.

> **The load-bearing law: a movement on axis 2 must be INVISIBLE IN THE FICTION.**
>
> If passivating a village changes what the world remembers about it, passivation is wrong. This is the
> one assertion that makes axis 3 safe to be engine-owned and invisible to the author.
>
> **Its testable subject, which the first draft did not supply:** the law's observable form is that **the
> event vocabulary contains no residency variant** — enforced by the type system, not by convention. Plus
> a metamorphic test: passivate, restore, require the fiction-visible state byte-identical.
>
> **It has since decided three questions that were otherwise coin tosses** — the residency budget is
> config while the `Language` roster cap is hashed rules · simulation LOD is config while fiction dilation
> is hashed rules (`P-E`) · prompt fidelity belongs on the **controller**, not the tier (`O-23`). A law
> that keeps deciding otherwise-arbitrary questions has earned its place.

**Axis 2 stays fully closed in the engine** (`D-2` still holds): residency is memory and scheduling, and
an author has nothing to declare there. Axis 1 is fully vocabulary. Axis 3 is engine mechanism whose
*caps* an author may tune.

#### Three things this exposes that we have nowhere to put

1. **A message buffer across the passivation gap.** Akka buffers messages between `Passivate` and
   termination and delivers them to the next incarnation. Without it, freezing an actor loses input —
   and an observer walking away mid-interaction is exactly when that happens.
2. **A budget-driven eviction policy on axis 2.** Vue uses LRU with a `max`; Akka an idle timeout.
   `TierCapacityCaps` (`WSA-R06`) caps **axis 1** and nothing caps axis 2.
3. **Cascade is per-axis, and this answers `PO-4` properly.** Four policies were not "too few" — the
   question was mis-framed. `Destroyed` on axis 1 drops held items into the world; `Passivated` on
   axis 2 must cascade to the held subtree **without changing any of their fiction state** — Vue
   deactivating a whole cached subtree. That is not `Drop`, `Cascade`, `Suspend` or `Keep` in the sense
   originally meant. **Each axis needs its own policy set, and axis 2's may well be a single policy.**

#### What survives from `D-12` unchanged

`Existing | Suspended | Destroyed | Removed` is one reality's **axis-1 vocabulary** minus `Suspended`,
which was never an existence state and moves to axis 2. The engine still closes: holding a state ·
validating a transition against the declared set · the append-only log · atomicity of a transition with
its cascade. `HolderCascade` remains the one reason the engine owns.

## 6. Behaviour, from the chaos golden vectors — **Q5**

`chaos-backend-service/docs/resource-manager/golden_vectors/` contains six cases. They are behavioural
specifications we do not have. Our chosen behaviour for each:

| case | our behaviour |
|---|---|
| **damage + heal same tick** | deltas apply in declared order within the tick, then **one** clamp at emit — the same discipline `DF7-A4` applies to stat resolution |
| **out-of-combat regen** | there is no engine "combat mode". *Out of combat* is a **declared status**, and it gates a regen contribution like any other declared condition |
| **shield decay** | a `Pool` with a negative rate. Decay is regen with the sign flipped, not a second mechanism |
| **offline catch-up** | regen is a function of a **tick delta**, never wall-clock. Catch-up applies N ticks in **closed form** — which constrains §2's regen shapes: every admitted shape must have an O(1) closed form, or an absence produces an unbounded loop |
| **exhaustion hysteresis + coalescing** | enter and exit conditions are **distinct declared values**; events inside a declared window coalesce. This is what stops a value oscillating at a boundary from emitting forever |
| **simultaneous exhaustion precedence** | thresholds carry a declared `order`; **ties break on quantity ordinal**, which gives determinism for free and needs no extra declaration |

The offline-catch-up row is the one that reaches back and constrains the mechanism set — a good sign
the vectors were worth reading.

## 7. Rot ledger — **Q6**

Statements now contradicted. `U` = update, `D` = delete.

### 7.1 `DF7-A1` — the closed slot set

[`DF07_001:110`](../../../03_planning/LLM_MMO_RPG/features/DF/DF07_pc_stats/DF07_001_actor_stat_block.md#L110) upholds a closed `StatSlot` enum, and its 2026-07-28 amendment explicitly retires
`WSA-R02`'s proposal to make the slot set ruleset-declared. **`D-10` reverses that.** The amendment
gave three reasons; all three have since lapsed, and this is the part worth recording rather than
overwriting:

| its reason | status now |
|---|---|
| *"the laws read 9 of 10 slots **by name**, so opening the set buys one dead slot"* | **dissolved by `D-14`** — those laws are being rewritten. A property of code that is being discarded cannot justify the shape of what replaces it. |
| *"moving `SLOT_COUNT` makes every stored `.canon` undecodable … reds the golden digest with no legal repin"* | **cost is currently zero** — no production reality exists (`D-11`), which doc 35 §12 states itself: *"zero production realities exist, so the clock is under our control."* |
| *"`upcaster.rs` versions **event** schemas, not **rules** — there is no migration story"* | **shipped 2026-07-29 as `Q0a`** — the version-dispatched codec, `upcast v1→v2`, and the epoch switch. The named blocker was cleared and the question was never re-opened. |

| id | site | action |
|---|---|---|
| R-1 | `DF07_001:110-145` — `DF7-A1` and its amendment | **U** — restate as: the engine closes the *resolution mechanism*; the slot vocabulary is declared. Keep the amendment's history and record why each reason lapsed. |
| R-2 | `DF07_001:4` — *"a closed set of 10 engine stat slots"* | **U** |
| R-3 | `DF07_001:398` — *"closed engine enum — NOT a free-form stat string"* | **U** — a declared key is not a free-form string either; it is a machine key with an assigned ordinal. |
| R-4 | `DF07_001:690` — validator `stat.slot_unknown`, *"manifest declares a slot outside the closed enum"* | **U** — inverted. The check becomes *"a term names a quantity this reality did not declare."* |
| R-5 | doc 35 §1 lines 60-79 — the `SLOT_COUNT` cost table and `QTY-F1` | **U** — the sites are real; annotate that the cost is currently zero and that `Q0a` supplied the migration story the passage says is missing. |
| R-6 | doc 35 §3.1 review note — roles for `StrikePower`/`Armor`/`Speed` were *"indirection with no consumer"* | **U** — the premise was *"an author cannot rebind a closed derived slot"*. Under `D-10` there is no closed derived slot. |
| R-7 | doc 35 `QTY-D1` — *"one role, not six"* | **U** — the argument rests on *"every other law input is an L1 derived slot the law names directly."* Re-derive it, or record that it now depends on the combat redesign (`D-14`). |

### 7.2 `VitalKind` — a closed vital vocabulary

| id | site | action |
|---|---|---|
| R-8 | `RES_001:120, 181, 305` — `VitalKind::{Hp, Stamina, Mana}` | **D** — replaced by a declared quantity of kind `Pool`. |
| R-9 | `features/00_resource/00_CONCEPT_NOTES.md:274-276, 359, 377, 399, 505` | **U** — same substitution; `Q3d`'s *"V1 active: Hp, Stamina"* becomes a preset's content, not the engine's set. |
| R-10 | `PROG_001:867` and `00_progression/00_CONCEPT_NOTES.md:1061` — `VitalKind::Hp` in emitted deltas | **U** — the delta names a declared quantity ordinal. |
| R-11 | `features/00_resource/01_REFERENCE_GAMES_SURVEY.md:436, 642` | **U** — survey text; correct the claimed V1 shape. |

### 7.3 Lifecycle as a closed enum

| id | site | action |
|---|---|---|
| R-12 | `EF_001:73` — *"Closed enum 4-state"* | **U** per `D-12` — the machine is mechanism, the states are vocabulary. |
| R-13 | `EF_001:115, 198-199, 257, 265` — `LifecycleState` as a type on `entity_binding` and the trait | **U** — becomes a declared-state ordinal. |
| R-14 | `EF_001:205` — `LifecycleReasonKind` closed enum | **U** — declared, except `HolderCascade`, which the engine owns. |
| R-15 | `EF_001:403-448` — the transition table and forbidden list | **U** — becomes the *shape* of a declared machine, with the table as a preset's example rather than the engine's law. |

### 7.4 The float ban (`D-8`)

| id | site | action |
|---|---|---|
| R-16 | `DF07_001:380` — *"the engine never sees a float"* | **U** → §7 of the RUN-STATE's revised text. |
| R-17 | `DF07_001:728` — *"no float in the path (DF7-A4)"* | **U** |
| R-18 | `ABL_001:354, 731` — inherits `DF7-A4` | **U** — reword to byte-stability; the substantive claim survives. |
| R-19 | `27_extensibility_stress_test.md:313` — *"no float"* in the preservation list | **U** |
| R-20 | `16_ruleset_loader_and_registry.md:482` — *"no floats (RLS-A8)"* in the canonical encoding | **U with care** — this one is about a *canonical byte encoding*, where the real requirement is one byte pattern per value. A canonicalised float satisfies it. `RLS-A8` should say that rather than banning a type. |
| — | `MAP_001:310` — withdraws `f32` `cos`/`sin` because *"results differ across platforms"* | **KEEP UNCHANGED.** This is hazard 1 of the revised rule, stated correctly. The revision does not loosen it. |
| — | `COMB_003:53, 433` — integer accrual, no floats | **defer to combat redesign** (`D-14`) |

### 7.5 Rot found outside this scope, recorded so it is not lost

| id | site | note |
|---|---|---|
| R-21 | `26_implementation_architecture.md` §6, `S1b` row — *"Asserted, not remembered: `s1b_has_no_subject_yet_and_says_so` reds the day it arrives"* | **The test does not exist.** `grep -rni "s1b" --include=*.rs` returns nothing in the engine crates. Its trigger (`Q1`) fired on 2026-07-29 and nothing noticed. Prose wearing the costume of a mechanism — parked as `P-3`, but the false sentence should be corrected whenever that row is next touched. |
| R-22 | doc 35 §12, `Q0b` row — *"`RulesetEpochActivated` has ZERO occurrences"* and *"`BindingStore` has no mutating method at all"* | Both false now. The type is generated at `contracts/events/generated/rust/ruleset_epoch_activated_v1.rs:9`; `BindingStore::activate_epoch` is called at `epoch.rs:187`. |
| R-23 | `31_world_simulation_architecture.md` §6 — *"The consolidated build order"* | 12 rows, **0** completion marks, while doc 26 carries 5 and doc 35 carries 4 for overlapping rows. The only unifying plan describes a world about a week stale. Parked as `P-5`. |

## 8. Deferred, with reasons

| item | why |
|---|---|
| Trigger / generator mechanism — pub-sub, register-pool, or loop | `D-9`. Chosen later on performance evidence. §5.1 guarantees the seam. |
| Combat vocabulary and the damage chain | `D-14`. Belongs to the combat element. |
| A lint for `DF7-A4`'s three hazards | It would have no subject — the replayed path contains no float today. Building it now repeats the `NV-2` vacuity that `S1b` already demonstrated. **Trigger:** the first float to enter a replayed path. |
| Manifest remainder — `S1b` arms, preset content, `IMP-D5` | `S1b` enforces floor and mutability on `ResourceTable`, which §3 reshapes. Doing it now is doing it twice. |

## 9. PO decisions — all four resolved 2026-08-02

| # | Resolution |
|---|---|
| **PO-1** | **Three tables** (§3.1). Decided on manifest-generation grounds: an LLM generates these, and three flat non-overlapping schemas fail loudly where one discriminated row fails plausibly. One ordinal space across all three. |
| **PO-2** | **Per-actor, Bethesda-style** (§4). Archetype = preset consulted at spawn; actor = live snapshot that may diverge arbitrarily at runtime. *"Close the actor completely and you close gameplay completely."* |
| **PO-3** | `DF7-A1` reversal **applied** per `D-10`; this was a wording review, not an open decision. |
| **PO-4** | **Three orthogonal axes** (§5.3), not a wider cascade-policy set. The original question was mis-framed: four policies were not too few, the single axis was wrong. |

> **The PO did not claim the expertise to ratify §5.3 and asked instead for adversarial review.** That
> is the correct move and is recorded as such: the three-axis model is **adopted, not validated**. It
> enters the spec so a red team has something concrete to attack, and §9.1 is what they should aim at.

### 9.1 Where this design is most likely to be wrong

Written for the red team, by the author, before they arrive.

| # | The attack surface |
|---|---|
| **A-1** | **§4's provenance hole.** The archetype is in the digest; the actor's copy is not. `RLS-A13` pins events to the rules that produced them, and a runtime-diverged actor is not covered by that pin. *"What rules is this actor running under"* has no answer. This is the sharpest edge and the author knows it. |
| **A-2** | **§5.3's invisibility law is asserted, not enforced.** *"A movement on axis 2 must be invisible in the fiction"* has no mechanism. Per `non-vacuity`, an unenforced law is prose. What test could red on a violation, and does anything today make that test possible? |
| **A-3** | **Three tables, one ordinal space** (§3.1) — the union numbering is stated as non-negotiable, but nothing here says how a resolver finds which table an ordinal is in without three scans, nor what happens when a table is extended between epochs. |
| **A-4** | **Axis 2 closed in the engine.** Asserted on the grounds that residency is memory and scheduling. Is there a genuine authoring need on axis 2 — a reality that wants *"this NPC never passivates"*? If yes, `D-2` says that is vocabulary and the axis is mis-classified. |
| **A-5** | **The two existing axes were never reconciled, only re-labelled.** `EF_001`'s states and `AIT_001`'s tiers are declared to be one axis here. Nobody has checked that every transition each document defines still has a home. |
| **A-6** | **`D-13` was declared solved, then the answer changed.** With `PO-2`'s copy-at-spawn, "which pools" and "which lifecycle" are both copied from the archetype — but a runtime-granted pool has no matching story for a runtime-changed lifecycle machine. Is the unification still real, or did it survive only in the draft where the archetype was authoritative? |

---

## 10. The surviving model — `D-15`..`D-53` folded in (2026-08-02)

Everything decided after this file was first written. Reasoning and evidence live in
[`2026-08-02-actor-dataflow.md`](2026-08-02-actor-dataflow.md); this is the conclusion.

### 10.1 The actor is not one record, and that is CORRECT

The corpus stores an actor as **31 separately-owned aggregates** across 21 features, all keyed by
`actor_id`. That is not fragmentation to be fixed — it is the domain-driven decomposition: **an identity
may span bounded contexts; an entity instance may not.** `QTY-A7`'s one-home rule is this stated for
quantities; the corpus applied it to the whole actor first. **They are not to be unified** (`D-15`).

So the struct this document is about is **one context's view** — the deterministic-law context — and is
named accordingly:

```
ActorQuantities {                                            // NOT `Actor`
  id: ActorId                                                //   the only thing that crosses a boundary
  rules:            RulesPin { ruleset, epoch, overlay }     40 B
  values:           [i32; 32]                               128 B
  granted:          u32     // bit i => ordinal i exists       4 B   — never encodes lifecycle (D-18)
  threshold_active: [u32; 4]                                 16 B
  status_active:    u64     // a PROJECTION of actor_status    8 B   — records stay in PL_006
  control:          Option<ControllerId>                      8 B   — a CACHE of control_binding
  tier · existence · residency                                3 B
}                                                     TOTAL 216 B
```

**`size_of::<ActorQuantities>()` is the architecture's anti-accretion gate** (`D-26`), not merely a
`Vec`-trap guard: it makes *"a feature may not add a field"* a **build failure** rather than a review
opinion. An unsized field disables it silently — which is exactly what `statuses: StatusSet` did in the
first draft of this struct.

### 10.2 How a feature reaches the actor — and there is no third way

> **A contribution is DATA, never CODE** (`D-27`, generalising `CPL-A17`). A feature does **not run**
> during the tick. It leaves **rows**; the engine folds rows.

| | what the feature does | does actor core change? |
|---|---|---|
| **own a table** keyed by `actor_id` | holds its own state; actor core never reads it | no — it never learns the table exists |
| **write `ModifierRow`s** | `(actor, target ordinal, op, magnitude, layer, condition, source, expiry)` | no — no new field, no reserved ordinal |

**The engine never calls a feature, never enumerates features, never learns that "equipment" is a word.**
It validates the row *shape* and folds. The test a plugin registry fails and this passes: **a feature that
contributes nothing needs no opt-out, no null implementation, no registration** — absence is free.

- **Where an edge lives is cardinality, never convenience** (`D-25`): the **many** side, or a pair table
  when both are many. An actor *owns* an item ⇒ the edge is on the **item** (`EF_001`
  `LocationKind::HeldBy`). An `inventory: Vec<ItemId>` on the actor is the same error as `opinions` and
  `titles` — three features, three unbounded fields, and the actor is a god object by the third.
- **One commit primitive** (`D-50`): `commit_with_modifiers(feature_row, modifiers)`. One call, one
  transaction, one `seq`. Atomicity becomes a **signature** rather than a rule, and the engine is the sole
  writer of `modifier_rows`.
- **A condition is a declared THRESHOLD, never a predicate grammar** (`D-29`) — a grammar with nesting is
  a scripting language, which is `CPL-A17` violated by the mechanism meant to honour it. A threshold is
  already declared, already evaluated, already in `threshold_active`: one bit test.
- **Acceptance test:** adding a feature must touch **zero files** in actor core (`D-30`).

### 10.3 The tick, and the storage layers

**Phase 0 · Resolve** (`D-49`) — fold modifier rows, refresh every derived field (`status_active`,
`control`), evaluate modifier `expiry`. **No law runs, no input is admitted, nothing durable is written.**
After phase 0 the quantity block is complete and self-contained, which is what makes *"a law reads the
quantity block and nothing else"* a property rather than an aspiration. Input becomes phase 1.

**Three storage layers, and the L1 to L3 boundary is a LINK boundary** (`D-16`): L1 crates do not depend
on the persistence client, so a law writing durable storage is a **compile error**, not a review finding.
§4.7's phase discipline governs **L1 only**.

**Two SSOTs and only two** (`D-36`): the pinned **ruleset digest** + content manifest, and the **event
log**. Everything else is derived — aggregates, snapshots, both kernel caches, projections, room state, FE
context, **and `Domain::State` inside a running island**. The kernel already implements this:
`0004_aggregate_snapshots_table.up.sql` says *"snapshots are a write-path cache, not the SSOT"*.

**Single writer** per aggregate (`D-37`) — and the reason is **replay**, not concurrency: two writers
interleave events from different states and the fold cannot be reconstructed. **Declared readers**
(`D-38`) — a sole writer still leaves hidden contracts; declaring readers makes a schema change's blast
radius computable. **One rule for every derived copy** (`D-39`, `D-53`): rebuildable, carries
`(reality_id, seq)`, **discarded on divergence, never reconciled**.

### 10.4 Storage, disposal, and identity over time

**The container is a slot table** (`D-51`), and `D-23` decides it before we start — a tier-2 row is a
**fold over the ledger**, so:

> **Disposal is CACHE EVICTION, not deletion.** Freeing an actor frees a **slot**; the ledger is
> untouched; re-materialisation is a re-fold. There is nothing to delete, because the row was never the
> truth.

Dense `Vec<Option<ActorQuantities>>` + per-slot `gens` + a free list + an `ActorId` to `SlotIx` index.
Iteration order = **slot order**, deterministic for replay by construction. **`EntityId` is never reused;
the slot is**, guarded by the `Gen` the kernel already built. `Gen(u64)` saturating, plus a tick invariant
that no slot sits at `MAX` — so *unreachable* is **checked**, not argued.

**Canon is what is written to the LEDGER** (`D-23`). State never written is fabricated, may be lost, and
did not matter because nothing observed it. Mechanically: demotion is lossless exactly when materialised
state is a pure function of *(ledger, `RulesPin`, elapsed fiction time)* — and `O-20`'s invertibility
restriction is what makes the elapsed-time term closed-form, so it buys demotion-safety as a side effect.

**Identity across schema evolution is already built** (`D-45`): `activate_reality_epoch` refuses an ordinal
rebinding via `check_never_reused` against the reality's prior tables, **validating before appending**.
Two questions, not one (`D-46`): *what does ordinal 7 mean* is answered by the reality's **append-only
ordinal registry** at **zero bytes per event**; *what rules were in force* is `RulesPin` plus
`RulesPinChanged`. **A quantity is retired by retiring its ordinal, never by reassigning it.**

### 10.5 What left this scope

| | went where | why |
|---|---|---|
| **opinion · reputation · the social layer · NPC decision-making** | a separate **AI + emotion** feature (`D-24`, parked `P-6`) | **the game is playable without it** — and a thing you can remove and still ship is not substrate |
| **remote trade · auction houses · banking** | the **trade + economy** feature, per-reality (`D-22`) | built from escrow and order books, not from the atomic two-delta transfer primitive. A transfer is face to face; co-located actors are in one island by construction |
| **combat vocabulary** | the combat element's own design (`D-14`) | unchanged, and the shipped code is a stub |

### 10.6 The scale numbers this design commits to

| | |
|---|---|
| hot per-actor | **216 B**, fixed width, `Copy`, `size_of`-asserted |
| quantities per reality | **32** (`QTY-A6`), one ordinal space across three declaration tables |
| status kinds per reality | **64** (`status_active: u64`) |
| thresholds | at most 4 per quantity (`threshold_active: [u32; 4]`) |
| wave depth | **8** rounds, refusal **recorded** (`O-10`) — a manifest must never be able to hang the engine |
| modifier scale | fixed point **`1e-4`**, converted once at S1 to S2, inside the hashed bytes (`D-52`) |

**These are the only quantified numbers in the design** — there is no tick budget, no per-island actor
ceiling and no projection-lag target (`O-54`). The actor ceiling is derivable from a memory target; the
other two need a measurement on real hardware, not a decision.
