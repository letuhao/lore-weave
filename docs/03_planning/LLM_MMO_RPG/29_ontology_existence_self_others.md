# 29 — Tồn tại · Ta · Chúng: the ontology the world is actually made of

> **Status:** SEALED 2026-07-28 (DESIGN). Axioms `ONT-A1..A4`, findings `ONT-F1..F4`, tests `ONT-T1..T3`,
> decisions `ONT-D1..D2`, open `ONT-Q1..Q2`. **Prefix `ONT` registered** in
> [`00_foundation/06_id_catalog.md`](00_foundation/06_id_catalog.md).
>
> Follows [28 — product definition](28_product_definition.md), which fixed the loop as *world
> simulation, the character genuinely living in its environment* (PRD-D1). The PO then framed what
> "living" means as three concepts — **tồn tại (existence) · ta (self) · chúng (the others)** — and
> said these are what we are actually building.
>
> **This document treats that as engineering, not decoration.** Each concept gets an operational
> definition, a deletion test, a status verified against the corpus, and a consequence for the build
> order. Every quoted mechanism was checked in the source doc named beside it.
>
> 🔒 **SEALED** means the *reasoning* is closed and must not be re-litigated from memory — re-read it. Open questions listed in this file remain open, and the amendment rows are **PROPOSED, not applied**: no feature spec was edited by this arc.


---

## 1. Why this frame earns its place

The three concepts are not a philosophical overlay on a technical design. They **partition the open
technical problems cleanly**, which is the test of whether an abstraction is real:

| Concept | The open problem it turns out to be |
|---|---|
| **Tồn tại** | [PRD-F1](28_product_definition.md) — the world does not act; and the AIT tier ladder, which is an *existence* ladder that was designed as a *cost* ladder |
| **Ta** | [XST-F9](27_extensibility_stress_test.md) — the closed 10 stat slots, plus `FlexibleState`, an explicitly un-validated property bag |
| **Chúng** | [PRD-F3](28_product_definition.md) — seven of eight extension seams extend the character; none extends what the world does *between* characters |

Each is also the thing the other two need. That is developed in §6, and it is where the actual core
loop turns out to be hiding.

> **ONT-A1 — the method: a concept counts only if deleting it changes something observable.** For each
> of the three, this document states *what would visibly change in a play session if the mechanism were
> removed*. A concept whose deletion changes nothing is scenery. This is the same non-vacuity discipline
> [doc 21](21_architecture_ceilings.md) applies to performance gates and [doc 28](28_product_definition.md)
> applies to product claims.

---

## 2. TỒN TẠI — existence is already a ladder, built for the wrong reason

**Operational definition:** *X exists to the degree that the world would be different without it —
**and stays different after X is gone**.* Existence is **persistence of consequence**, not presence.

The corpus already has this ladder. AIT_001's own opening sentence is *"billion-NPC simulation needs
**tier-based existence**"* — the word is already there. What it lacks is the recognition that a cost
tier is an **ontological** tier, and that players will feel it.

| Degree | Corpus name | What survives | The deletion test, in play |
|---|---|---|---|
| **0 · Generated** | Untracked NPC | **nothing.** Id is `blake3(reality_id ‖ cell_id ‖ fiction_day ‖ slot_index)`; discarded on cell-leave / session-end (5-variant `UntrackedDiscardReason`) | Talk to a villager, walk out, walk back: a villager is there again, unmarked. Kill one: tomorrow it is back. **It never existed.** |
| **1 · Declared** | Minor NPC | the **declaration**. Position is `ScheduledActionDecl` + deterministic per-NPC jitter (DL-D15), *evaluated*, never ticked | It is always exactly where it should be. Nothing that happened to it is remembered. It exists the way a train timetable exists. |
| **2 · Stateful** | Major NPC | `actor_progression`, opinion, memory | What you did survives. This is the first rung where the world is *changed* by you. |
| **3 · Irreversible** | PC | all of the above **+ mortality class** (WA_006; permadeath realities) | It can be **permanently lost**, which is the only thing that makes the rest matter. |

> **ONT-F1 — existence is currently decided by the author's declaration and by the cost model, and
> never by the player's attention.** A player who spends an hour befriending a villager has befriended
> a hash. The game knows this and will never say so.

That is not a bug in the tiering — the tiering is good engineering and the `fiction_day`-seeded crowd
is genuinely elegant. It is a **product** bug, and it is precisely the "vague product" failure this
whole line of work exists to kill: the thing the player cared about was the thing the system was
built to throw away.

> **ONT-D1 — attention promotes.** Meaningful interaction with an Untracked NPC promotes it up the
> ladder, deterministically and without an admin. The mechanism already exists — AIT_001 ships
> `Forge:PromoteUntrackedToTracked` — but **only as an `AdminAction`**. The proposal is to give it a
> second, in-world trigger.
>
> **The principle it encodes:** in a world simulation, *the author cannot predict who the player will
> care about*, so **existence must be earnable by attention rather than granted by declaration.**

Two constraints make this cheap rather than dangerous: promotion is bounded by `TierCapacityCaps`
(Major ≤ 20, and DL-D6 already establishes the *defer-never-drop* behaviour on overflow), and the
promotion trigger must be a **committed event** so replay reproduces exactly which villager became
real.

**And the sharper half of ONT-F1 is [PRD-F1](28_product_definition.md):** even at degree 2, an entity
persists but does not *act*. Full existence — the world being different because *it* chose something —
is not on the ladder at all. Degree 4 does not exist yet.

---

## 3. TA — the self is what accumulates irreversibly, and the corpus already decided it is not the decider

**Operational definition:** *"ta" is the locus of irreversible accumulation.*

The corpus already took the hard position here, in a doc about something else entirely:

> **DL-A8 — conversion is a driver swap, not a migration.** `HumanDriver → LlmDriver` **is** the
> conversion. The actor keeps its `EntityId`, aggregates, inventory, relationships and history.
> *"The entity does not change what it **is** — only who decides for it."*

> **ONT-A2 — the self is not the decider.** Control is a *field*, not an identity. What makes the
> character mine is not that I choose for it; it is that it carries what has happened to it. This is
> already locked by DL-A8, and it is the correct and unusual call — most games conflate the two.

Three consequences follow, and the first one is the load-bearing one:

**(a) The dimensions along which I can accumulate ARE my self.** Today those are: 10 fixed stat slots,
`actor_progression`, inventory, relationships — and `FlexibleState`, documented in ACT_001 §3.1.2 as
*typed standard fields + extension keys, **NOT engine-validated**, author guidance*.

> **ONT-F2 — the self is under-dimensioned, and its escape hatch is unvalidated.** [XST-F9](27_extensibility_stress_test.md)
> said the closed 10-slot set is *type-incorrect*, not merely lossy, and argued it on combat examples.
> The ontology makes the same point far more sharply: **a person is not expressible in ten numbers**,
> and everything that does not fit — mood, needs, standing, reputation, obligations — currently lands
> either in a separate aggregate or in an un-validated property bag. **The self is fragmenting by
> accident**, exactly as [XST-F9](27_extensibility_stress_test.md) predicted people would start
> overloading slots.
>
> This promotes [XST-R6](27_extensibility_stress_test.md) (ruleset-owned quantity set) from *"probably
> right"* to *"required by the product"*, and it is the same conclusion [28 §9](28_product_definition.md)
> reached from the loop. Two independent routes, one answer.

**(b) `WasPlayerCharacter` is the best idea in the corpus for this theme.** DL-D11 marks a converted PC
so it can be prompted with its own history — *"the world fills with characters who used to be someone's
protagonist."* That is **"ta" decaying into "chúng"**, as a mechanic, already designed. It should be
treated as a headline feature of the product, not as a side-effect of a cost optimisation.

**(c) A PC and an NPC are the same type.** ACT_001 unified them deliberately. Under ONT-A2 that is not
merely tidy — it is *required*: if the self is the accumulated thing rather than the decider, then a
player-driven and an LLM-driven actor must be the same kind of thing. **Keep this locked.**

> **ONT-A3 — irreversibility is what makes accumulation mean anything.** If nothing can be permanently
> lost, "ta" is a save file. WA_006's mortality class per reality is therefore not a difficulty
> setting; it is the switch that decides whether the self is real. A reality with no irreversibility
> can still be a good game — but it is not the game PRD-D1 describes.

---

## 4. CHÚNG — others are real to the degree they hold state about me

**Operational definition:** *"chúng" exists to the degree that others **hold state about me**.* Not
that they are present — that they **remember**.

**Deletion test:** delete every NPC's memory and opinion of me. What changes? If nothing changes, there
is no society — there is a diorama with people-shaped props in it.

What exists today:

| Mechanism | Shape | Reality in V1 |
|---|---|---|
| `actor_actor_opinion` (ACT_001 §3.3) | `(observer, target)` → `trust: i16`, `familiarity: u16`, `stance_tags` | **NPC→PC only.** PC→NPC (ACT-D2), NPC→NPC (ACT-D3), PC→PC (ACT-D4) are all **V1+** |
| its mutability | — | **session-end derivation** by world-service, plus `Forge:EditActorOpinion`. **Not written during play.** |
| `REP_001` | per-(actor, faction) standing | present |
| `actor_session_memory` | per-session | **per-session — it does not outlive the session** |

> **ONT-F3 — there is no society in V1. There is a set of NPCs each holding one number about you,
> recomputed once when you log off.** Nobody in the world has an opinion about anybody else
> (NPC→NPC is ACT-D3, V1+), and nothing anyone thinks about you changes *while you are there*.

That is the largest gap between the stated product and the built system, and it is larger than the
existence gap, because "chúng" is where PRD-D1's *"living in an environment"* actually happens. You do
not live in terrain. You live among others.

**The good news, and it is genuinely good.** ACT-A5 stores opinion as **two separate unilateral rows**
— *"symmetric pair NOT enforced; `du_si→ly_minh` and `ly_minh→du_si` stored as 2 SEPARATE rows; values
may differ."* It was decided that way so that feelings can be asymmetric. But under
**SL-A12** (*"an entity has exactly one owning island at any logical time"*), splitting the edge into
two halves keyed by **observer** means:

> **ONT-A4 — every relationship half has exactly one writer: the observer's island.** The
> cross-island edge-ownership problem that a bilateral relationship *would* have created is already
> solved — by a decision taken for a fictional reason. **Lock ACT-A5 for this second reason and record
> it**, because a future "optimisation" that merges the two rows into one symmetric row would silently
> reintroduce a multi-writer edge across islands, which is exactly the class of bug the whole
> single-writer design exists to prevent.

So the blocker on "chúng" is **not** architectural. The architecture is ready. The gaps are:

1. opinion is written **at session end**, not from events during play;
2. **NPC→NPC does not exist**, so there is no third party to have a society with;
3. `actor_session_memory` **dies with the session**, so nothing personal is remembered long-term.

---

## 5. ONT-F4 — the three compose into a loop, and the loop does not currently close

This is the payoff of the frame.

```
   I act  ──▶  the world KEEPS the consequence        (TỒN TẠI)
                        │
                        ▼
              I become someone specific               (TA)
                        │
                        ▼
              others HOLD that about me               (CHÚNG)
                        │
                        ▼
        what they hold changes what I can do  ──▶  I act
```

> **ONT-F4 — this is the actual core loop.** [PRD-D1](28_product_definition.md) named the *genre*
> ("world simulation"); this names the **content** of the loop. And it closes only if all three
> concepts are true at once — which is why partial versions of each add up to *nothing feeling alive*
> rather than to *two-thirds alive*.

Current state of each arrow:

| Arrow | Status |
|---|---|
| act → consequence kept | ⚠️ only for degree-2+ entities; the world itself never acts ([PRD-F1](28_product_definition.md)) |
| consequence → a specific self | ⚠️ accumulation exists but is under-dimensioned (ONT-F2) |
| self → others hold it | ❌ session-end only, NPC→PC only (ONT-F3) |
| what they hold → changes what I can do | ❌ nothing reads opinion back into what is *possible* |

**The last arrow is missing entirely, and it is the one that closes the loop.** Trust and reputation
are *recorded* and never *consulted*. Under the [Settings & Configuration](../../standards/settings-and-config.md)
discipline this repo already enforces, that is the **stored-but-never-read** bug class — applied here
not to a setting but to the entire social layer.

> **ONT-Q1 — what does opinion GATE?** Until something is refused or unlocked because of what someone
> thinks of you, "chúng" is telemetry. The smallest honest version: a `Precondition` variant that reads
> `trust`/`standing`, so a refusal is a **recorded normal outcome** exactly like every other failed
> precondition (which the kernel already treats as a first-class event, not an error).

---

## 6. The three tests — how a proposed mechanic earns its place

> **ONT-T1 (Tồn tại)** — does it make something **persist that previously did not**, or let the world
> **keep a consequence** it previously discarded?
>
> **ONT-T2 (Ta)** — does it give the character a **new dimension along which to become specific**, and
> is that dimension **irreversible enough to matter**?
>
> **ONT-T3 (Chúng)** — does it cause **someone else to hold something about me**, and does something
> **read it back**?

A mechanic that passes none of the three is content, not a mechanic — which is fine, but it is E1 in
[28 §8](28_product_definition.md)'s tiering and should not consume engine work.

Applying the tests to the extension tiers already defined:

| | ONT-T1 | ONT-T2 | ONT-T3 |
|---|---|---|---|
| **E2 · new quantities** ([XST-R6](27_extensibility_stress_test.md)/[R8](27_extensibility_stress_test.md)) | — | ✅ **directly** — new dimensions of self | enables (standing, obligation as quantities) |
| **E3 · new mechanics** ([XST-R9](27_extensibility_stress_test.md)/[R10](27_extensibility_stress_test.md)) | ✅ the world can act | — | ✅ triggers can write opinion during play |
| Combat depth (COMB_002/003, ABL_001) | — | — | — |

**Combat depth passes none of the three.** That is an independent confirmation of
[PRD-D3](28_product_definition.md)'s demotion, arrived at from a completely different direction — and
it is the kind of agreement that should increase confidence in the call.

---

## 7. What this changes about the build order

> **ONT-D2 — the ordering within the world tier is `chúng` → `tồn tại` → `ta`'s new dimensions**,
> which is *not* the order the concepts were stated in.

The reasoning:

1. **"Chúng" is cheapest and closes the loop.** The architecture is ready (ONT-A4), the storage exists,
   and three named gaps (write-during-play, NPC→NPC, read-back) are ordinary work rather than new
   substrate. It is also the arrow whose absence is most responsible for the world feeling dead.
2. **"Tồn tại" (ONT-D1 attention-promotes) is next** because it is what makes "chúng" *matter* — an
   opinion held by something that gets discarded on cell-leave is not held at all. Note the dependency
   runs this way and not the other way, which is why the stated order is inverted.
3. **"Ta"'s new dimensions (E2) come third** — they are the largest piece of engine work
   ([XST-R6](27_extensibility_stress_test.md) is a data-migration deadline, see
   [27 §11.6](27_extensibility_stress_test.md)), and both of the above sharpen what the dimensions
   need to be. Building the quantity system *before* knowing which quantities the social loop reads
   would be the same inversion [26](26_implementation_architecture.md) already warned about: building
   consumers before the supply chain, and its mirror, building the supply before knowing the demand.

**Unchanged:** F1/F2 (`ruleset-core` + `ruleset-loader`) still come first. Every item above is a
consumer of a real ruleset with a real digest, and [XST-D5](27_extensibility_stress_test.md) — the
digest being decorative — is still the cheapest-now / archaeology-later row on the whole board.

---

## 8. Open

| # | Question |
|---|---|
| **ONT-Q1** | **What does opinion gate?** (§5) Until something is refused or unlocked by what someone thinks of you, "chúng" is telemetry. Proposed smallest form: a `Precondition` reading `trust`/standing, so refusal is a recorded outcome. |
| **ONT-Q2** | **What counts as "meaningful interaction" for ONT-D1's promotion trigger?** It must be a committed event (so replay reproduces which villager became real), bounded by `TierCapacityCaps`, and resistant to a player farming promotions. Candidate: the same `InteractionKind` vocabulary `TrainingRuleDecl` already triggers on — reusing the one WHEN seam that exists rather than inventing a second. |
| **PRD-Q1** (carried) | May the world act **deterministically**? Existence degree 4 — an entity that *chooses* — is unreachable until this is answered. |

---

## 9. Cross-references

* Product decision + the 4-tuple mechanic model — [`28_product_definition.md`](28_product_definition.md)
* Extensibility findings + the recommendation set — [`27_extensibility_stress_test.md`](27_extensibility_stress_test.md)
* Actor identity, mood, opinion, memory — [`features/00_actor/ACT_001_actor_foundation.md`](features/00_actor/ACT_001_actor_foundation.md)
* Existence tiers + Untracked generation — [`features/16_ai_tier/AIT_001_ai_tier_foundation.md`](features/16_ai_tier/AIT_001_ai_tier_foundation.md)
* Driver swap, offline body, conversion — [`features/12_daily_life/DL_001_daily_life_foundation.md`](features/12_daily_life/DL_001_daily_life_foundation.md)
* Island ownership (SL-A12) — [`13_simulation_loop.md`](13_simulation_loop.md)
* Reputation — [`features/00_reputation/`](features/00_reputation/)
* Mortality — [`features/02_world_authoring/WA_006_mortality.md`](features/02_world_authoring/WA_006_mortality.md)
