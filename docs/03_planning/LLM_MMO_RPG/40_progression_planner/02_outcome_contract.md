# 40.2 — The outcome contract: what a progression planner must produce, and why there is more than one

> **Status:** DESIGN · **Date:** 2026-07-31 · **Prefix:** `PPO-`
> **Blocks** [`40.1 — the planner architecture`](01_planner_architecture.md) — the planner
> cannot be built until this document is locked, because a planner is defined by its output.
> **Method:** take one complex cultivation system, enumerate every gameplay loop that revolves around
> it, and read the outcome shape off the enumeration.

---

> ### ⚠ Corrected by [`40.3 — the generator boundary`](03_generator_boundary.md), 2026-07-31
> This document was written broad enough to reach into other element modules' scope, which
> [`38`](../38_content_pipeline_architecture.md) `CPL-A3` forbids. **`PPO-A1`'s *"demands the mechanism"* is retracted, and §5's nineteen CQs must be split into planner-CQs and assembly-CQs before the spike.** See
> [`40.3` §9](03_generator_boundary.md) for the full correction list. Kept in place rather than
> laundered — the drift is the finding.

---

## 0 — The question, and why it blocks everything

> *"For the experiment to succeed, answer this for me: what is our **outcome**? Because if we cannot
> settle this, we cannot build the planner. Take one complex cultivation system and look: how many
> kinds of gameplay revolve around it? Answering that lets us model the outcome. Note that we are
> allowed to be **biased** — different gameplay may need the planner extended, or different kinds of
> planner. Do not think about building an all-in-one; that is meaningless. In coding, every
> development process, every kind of software, every language has a different approach."*

Doc 40 designed the *machine*: a loop, six provenances, an abductive register, a logic engine. Every
one of those is parameterised by a thing doc 40 assumed and never defined — **what counts as done.**
`PPL-A2` says a plan is closed when every Variable has an inflow and a gate. That is necessary and it
is not sufficient, and until we can say what *is* sufficient, the abduction has no goal to abduce
toward. **A solver with no goal returns everything or nothing.**

So: one complex system, walked, and the outcome read off it.

---

## 1 — The survey: one complex cultivation system, loop by loop

Composite of the genre's deep end — *A Record of a Mortal's Journey to Immortality* as the spine,
with *Renegade Immortal*'s body-seizing and *Battle Through the Heavens*' profession trees. Not the simplified ladder every summary shows; the whole surface.

| # | gameplay loop | what it actually is, mechanically |
|---|---|---|
| 1 | **seated meditation** | a meter fills over time; rate = f(spirit-root quality, technique grade, ambient spirit-energy density of the place, elixirs consumed) |
| 2 | **breakthrough** | discrete gated transition at meter cap; needs item + place + mental state; **may fail** → injury, regression, death |
| 3 | **spirit-stone economy** | dual-purpose currency: buys things **and** is burned as fuel. Faucets, sinks, market towns |
| 4 | **alchemy** (pill refining) | recipes, furnace grade, success probability, **its own grade ladder** (alchemist grades 1–9) |
| 5 | **artifact refining** | same shape, different inputs; produces *treasures* with ranks and charges |
| 6 | **talisman-making / formation arrays / beast taming / puppetry** | four more professions, each the same shape as #4 with different vocabulary |
| 7 | **combat** | technique costs, treasure activation, and a **hard realm-gap curve** — a Foundation Establishment cultivator cannot meaningfully touch a Core Formation one |
| 8 | **body / qi / soul tracks** | three parallel tracks with different inflows, different gates, and cross-caps between them |
| 9 | **sect life** | membership, contribution points as a *second currency*, missions, rank promotion, resource allowance |
| 10 | **secret realms** | instanced content gated on realm; time-windowed; the main non-grind resource faucet |
| 11 | **heavenly tribulation** | escalating scripted survival challenge at major thresholds; artifacts/formations mitigate |
| 12 | **lifespan** | **a depleting meter.** Each realm grants more. Fail to advance in time → death. *The genre's master clock.* |
| 13 | **heart demon / dao heart** (resolve) | a mental-state variable that gates breakthrough and can **regress** you |
| 14 | **fated opportunity / inheritance** | random encounters, inheritances — the discontinuity that makes a protagonist |
| 15 | **dual cultivation / spirit pets** | partner and pet systems that modify #1's rate |
| 16 | **body-seizing / reincarnation** | identity transfer: the soul track persists, the body track resets |
| 17 | **sect building / territory** | late-game management layer over #3 and #9 |
| 18 | **spatial gating** | whole regions (the Scattered Star Sea, the Spirit Realm) gated on realm; travel is progression-gated content |

Eighteen loops. Now the useful question, which is not *"how many"* but *"how many are progression?"*

---

## 2 — `PPO-A1` — most of a cultivation system is NOT progression, and the demand register is the larger artifact

Classified against the module boundaries this repo already owns:

| class | count | loops | who owns it |
|---|---|---|---|
| **Pure progression** | **4** | 1, 2, 8, 12 | `PROG_001` — the planner's own output |
| **Straddling** — a progression kind whose inflow *or* gate lives elsewhere | **5** | 4, 5, 6, 9, 13 | planner declares the kind; **demands** the mechanism |
| **Pure demand** — not progression at all | **9** | 3, 7, 10, 11, 14, 15, 16, 17, 18 | `RES_001` · `COMB_*` · place/geo · event · identity · org |

> **`PPO-A1`.** ~22% of a cultivation system is a progression declaration. ~50% is a **demand on
> another module**. The `PPL-A7` demand register is therefore not a footnote to the plan — **it is
> the larger half of the outcome**, and a planner that emits only progression declarations has
> produced roughly a fifth of the thing the PO asked for.

The **straddling** class is the interesting one and it was invisible before this survey. Take alchemy:

```
alchemist_grade   is a Skill kind        → the planner declares it
  ↑ inflow   "successfully refine a pill of grade >= N"  → owned by the CRAFTING module
  ↓ gate     "may attempt grade-N recipes"               → owned by the CRAFTING module
```

**A variable the planner owns whose inflow and gate both live in another module.** `PPL-A2` closure
cannot be evaluated inside the progression plan at all — it is only decidable across the module
boundary. The same shape repeats five times (alchemy, refining, talismans/formations/taming/puppetry,
sect rank, heart-demon). **This is the single strongest structural finding of the survey**, and it
means the outcome must be a *pair*:

```
OUTCOME = ⟨ progression fact set , demand manifest ⟩      — neither alone is checkable
```

### 2.1 Two substrate gaps this survey exposes

**`PPO-A2` — the genre's master clock has no home.** Lifespan (#12) is a **depleting** variable: it falls
with time, each realm grants a refill, and exhaustion is death. It converts the entire game from
*"grow at your leisure"* into *"race the clock"* — it is the source of nearly every plot in the genre.
`PROG_001` §8.1 is explicit: **"V1 NO atrophy"**, and `ResourceBound` is deferred to V1+30d. **There is
no V1 shape for a variable that goes down.** A cultivation planner built on today's substrate produces a
cultivation system with its central tension removed, and neither doc 39 nor doc 40 would notice —
closure is satisfied (lifespan would simply not be declared).

**`PPO-A3` — regression is not modelled either.** Loops 2, 11 and 13 all include *going backwards*:
failed breakthrough, tribulation damage, heart-demon regression. `PROG_001` reserves `TierRegress`
(PROG-D2) but V1 has no producer. A ladder that can only go up is not this genre.

Both are **buildable, not blocked** — schema-additive per `I14`. They are named here because the
outcome contract must state whether they are in scope, and if they are out, the planner must **refuse**
a source that asserts them rather than silently dropping to a one-directional ladder.

---

## 3 — `PPO-A4` — three games from the same lore need three different outcomes

The PO's *"we are allowed to be biased"*, made concrete. Same novel, same 18 loops, same realm ladder — three
products. What each one actually needs from a progression plan:

| | **X · idle/incremental** | **Y · combat MMO** | **Z · LLM narrative sim** |
|---|---|---|---|
| the loop | accumulate → spend → prestige | fight → gear → rank | act → the world responds |
| **rate curves** | **CRITICAL — the game *is* the curve** | important (pacing to endgame) | low precision needed |
| **combat formula** | **not needed** | **REQUIRED** — realm-gap curve, PvP balance | needed, but the LLM proposes inside engine bounds |
| **capability vocabulary**<br>*(what a tier lets you DO, in words)* | not needed | optional flavour | **REQUIRED — without it the model cannot narrate or refuse** |
| **economy coupling** | **REQUIRED** — sinks are the whole design | required | light |
| **refusal narratability** | not a concept | an error toast | **REQUIRED** — *"why can't I?"* must be answerable in prose |
| **NPC materialisation** | no NPCs | server-authoritative, all tracked | **REQUIRED** — lazy/Schrödinger at scale (`PROG_001` §7) |
| **offline accrual** | **REQUIRED** | n/a | partial |

> **`PPO-A4`.** **Closure is profile-relative.** The *same* fact set is closed under X and open under
> Z. A plan with perfect rate curves and no capability vocabulary ships a complete idle game and an
> unplayable narrative game — and `PPL-A2` as written cannot tell them apart.

This is the formal statement of *"we are allowed to be biased"*: the bias is not a compromise, it is **a parameter
that must be declared** so the closure check knows which rules to run. And it is the formal statement
of the anti-AIO rule too — an AIO planner is one that runs the union of all three rule sets, which
means every plan fails on requirements its product does not have.

### 3.1 The mechanism is already free

`PPL-A8` made the rules **data**; `PPL-A9` made the authority table **data**. So a *planner type* costs
nothing new:

```
CORE pack       universal truths       a variable needs an inflow · cycles are illegal ·
(small, locked)                        provenance authority · demands must resolve

PROFILE pack    what THIS product      Z: capability_vocabulary(Tier) is required for every tier
(the bias)      additionally requires  Y: strike_formula is required; realm_gap curve is required
                                       X: rate(K) required at every tier; combat_formula forbidden
```

**One engine, N rule packs.** Exactly the coding analogy the PO drew: one compiler, different project
templates and lint configs — a web app, an embedded firmware and a data pipeline share the language
and share almost none of their "is this ready to ship" criteria. Adding a profile is authoring a
`.lp` file, not writing a planner.

> **`PPO-A5` — the profile is DECLARED, and it is declared BEFORE the skeleton.** `PPL-A4` said the
> roster is the denominator. The profile is the denominator of the *denominator*: it decides which
> slots exist to be counted at all. A profile that changes mid-plan invalidates the closure verdict
> the same way a skeleton amendment invalidates coverage (`PPL-A4.1`).

---

## 4 — `PPO-A6` — the outcome, defined

Everything above converges on one definition, and it is testable rather than aspirational:

> **`PPO-A6` — THE OUTCOME.** The planner's output is a **typed fact set + demand manifest** that can
> answer its profile's **competency questions with no human in the room**. Not "every field is
> filled". Not "every question was answered". **Answerable, by machine, from the artifact alone.**

*Competency questions* is the ontology-engineering term for exactly this, and the LLM-KG literature
converges on it: you define what the artifact must be able to answer, then build until it answers.
It is the right instrument here for three reasons:

1. **It is the acceptance test.** *"detailed enough and playable"* becomes: run the CQ set, count
   how many are answerable. That is a number, and it can be low.
2. **The closure rules are DERIVABLE from it.** Each CQ needs certain facts to be answerable; a CQ
   that cannot be answered **is** a missing fact — which is an abduction (`PPL-A8`). The CQ set and
   the rule pack are two views of one thing, so they cannot drift.
3. **It *is* the profile.** A planner type is fully specified by its CQ set. This is the cleanest
   available definition of *"different planners for different gameplay"* and it is mechanically
   checkable rather than a matter of judgement.

**So the CQ set is the artifact this document must deliver, and if we cannot write it, we cannot build
the planner.** Below.

---

## 5 — LoreWeave's profile, and its competency questions

LoreWeave is not X and not purely Z: it is an **LLM-arbitrated MMO simulation** — Z's narration with
Y's authoritative resolution underneath (`PROG_001` §9's hybrid: *the LLM proposes within engine
bounds; the engine clamps*). Call it **profile `Z+`**. Its CQ set, grouped by who must answer:

### 5.1 Engine-resolution CQs — the engine alone, deterministically, no model

| id | question | facts it requires |
|---|---|---|
| `CQ-R1` | A at tier T₍a₎ strikes B at tier T₍b₎ — what damage? | `strike_formula` + the realm-gap curve + L3 contributions |
| `CQ-R2` | A meditates N ticks in place P — how far does the meter move? | `TrainingRule` + rate + `LocationMatch` + the ambient spirit-energy property of P |
| `CQ-R3` | A is at `tier_max` — may they break through, and what happens on failure? | `BreakthroughCondition` with every leaf resolvable + a failure branch (`PPO-A3`) |
| `CQ-R4` | May A enter place P / attempt recipe R / join rank S? | a gate predicate per gated resource |
| `CQ-R5` | A consumes item I — what advances, and by how much? | item→progression coupling + a magnitude |
| `CQ-R6` | Time passes for A with no action — what changes? | inflow *and* **outflow** (`PPO-A2` — lifespan) |

### 5.2 LLM-context CQs — the model must narrate without inventing rules

| id | question | facts it requires |
|---|---|---|
| `CQ-N1` | **What can a T-tier actor do that a (T−1) cannot?** | **`capability_vocabulary(T)` — DOES NOT EXIST TODAY** |
| `CQ-N2` | What is this tier called here, and what would an NPC call it? | label + i18n bundle (`PGN-A18`, outside the digest) |
| `CQ-N3` | The engine refused an action — say why, in prose an NPC could speak | a narratable reason string on every gate |
| `CQ-N4` | What would this actor *want*, given their tier? | tier → motivation hints, for the NPC agent tier |

### 5.3 Simulation-at-scale CQs — LoreWeave-specific, meaningless for X

| id | question | facts it requires |
|---|---|---|
| `CQ-S1` | An untracked NPC is observed at time t — what is their state? | a **deterministic materialisation function** of (t, archetype, seed) — `PROG_001` §7.5 |
| `CQ-S2` | Do NPCs break through off-screen, and at what compute cost? | a lazy-advance rule with a bounded cost |

### 5.4 Authoring CQs — the human's own feedback loop

| id | question | facts it requires |
|---|---|---|
| `CQ-A1` | How long from tier 1 to tier 5 for an ordinary actor? | rates + costs, integrated — **the pacing question** |
| `CQ-A2` | What is the cheapest path to tier T? | the resource-sink graph |
| `CQ-A3` | If I add kind K, what breaks? | the coupling graph, queried |

**Nineteen questions. Compare to doc 39's eleven — and note that of doc 39's eleven, *zero* appear
here.** All eleven were about how the ladder is *described*; every question above is about what the
system can *do*. That is the same finding as doc 40's M3, arrived at from the opposite direction, and
the agreement is worth stating: an outcome defined by *schema coverage* and an outcome defined by
*competency* do not overlap at all.

### 5.5 The finding that falls out: `PPO-A7` — capability vocabulary

> **`PPO-A7`.** For any LLM-arbitrated profile, **`capability_vocabulary(tier)` is a first-class
> required output** — an enumerated, tier-indexed list of what an actor at that tier may plausibly
> attempt. It exists in `PROG_001` nowhere, doc 39 never asks for it, and `CQ-N1` and `CQ-N3` are both
> unanswerable without it.

Why it is load-bearing rather than flavour: LoreWeave's engine clamps an LLM proposal to engine bounds.
Bounds on a *number* it has (`PROG_001` §9). Bounds on an *action* it does not — so when a player says
*"I leap the ravine"*, nothing in the manifest says whether a Qi Condensation cultivator can, and the model
decides. **That is the rules being authored at runtime by a model, in the resolution path, which
`CPL-A11` forbids.** The vocabulary is what turns that from a model decision into a lookup.

It is also the cheapest thing in this document to produce: it is *cardinality and names*, never
magnitude — squarely inside `PGN-A5`'s permitted zone, well-supported by the corpus (novels describe
what cultivators can do at length), and expandable by pattern (`PPL-A5` ⑤).

---

## 6 — The outcome contract

**Done** = all five, for the declared profile:

| # | condition | checked by |
|---|---|---|
| 1 | `closed(F)` under **CORE + profile pack** — every variable has an inflow and a gate | deduction (Rust + clingo, `PPL-T8` parity) |
| 2 | `violation(F) = ∅` — every decision made by a permitted provenance (`PPL-A9`) | deduction |
| 3 | `open_demand(F) = ∅` — every cross-module requirement satisfied **or explicitly refused with an owner** | deduction, across the boundary (`PPO-A1`) |
| 4 | `compile(F)` → a manifest the Rust `S-1` validator **admits** | doc 39 S5 |
| 5 | **every CQ in the profile's set is answerable from `F` alone** | the CQ harness — `PPO-A6` |

Condition 5 is the one that is new, and it is the one that would have caught POC-1 in the first hour.

**And the negative form, which is what makes it a real gate:** a plan that fails any condition is
**REFUSED, not clamped**. Doc 39's failure mode was a policy file quietly authoring what nobody
answered; conditions 2 and 5 make that impossible — a magnitude may default, an *answer* may not.

---

## 7 — What the experiment must now do

The spike from the previous turn, with a goal it did not have before:

**Build:** `CORE.lp` + `profile_Z+.lp` in clingo · the `Decision` fact loader (`PPL-A10`) · the CQ
harness for §5's nineteen questions.

**Load:** the actual fact set POC-1 produced on its last live run — the five answers it got, plus the
policy defaults it would have applied.

**Expect** (this is the falsifiable part — written before running):

- `closed = false`
- the repair set names **missing inflows for every declared kind** (no `TrainingRule` exists at all)
- the repair set names **missing gates** (no `strike_formula`, no capability vocabulary)
- **≥ 15 of 19 CQs unanswerable**, and each one names the fact that would answer it
- at least one **`open_demand`** — the *cold pool* breakthrough condition demands a place that no
  module has supplied

**Falsified if:** the repair set is empty, or it names things that are present, or the CQ failures do
not point at facts a human could actually supply. Any of those means `PPO-A6` is the wrong outcome
model and this document is wrong before anyone builds on it.

**Cost:** small — one `.lp` file, one loader, one harness. The value is that it converts every claim in
docs 40 and 41 from an argument into a printed repair set.

---

## 8 — Profiles: which ones we admit, and which we refuse to pretend to serve

| profile | status | why |
|---|---|---|
| **`Z+` LLM-arbitrated MMO sim** | **BUILD** | LoreWeave's actual product (doc 28). §5 is its CQ set. |
| `Y` combat MMO | **defer** | a strict subset of `Z+`'s resolution CQs minus the narration ones; cheap to add later, no value now |
| `X` idle/incremental | **refuse for now** | needs offline accrual, prestige and sink design that `Z+` does not have. Adding it would grow CORE to serve a product we are not building — the AIO mistake, in miniature |
| `W` tabletop/TTRPG export | **refuse** | outcome is a *document for humans*, not a machine-resolvable fact set. Different outcome ⇒ different tool, not a profile |

**Refusing `X` and `W` here is the point of the document.** The temptation is to keep CORE general
enough for all four; the survey says that produces a CORE whose closure rules are the *intersection* of
four products, and the intersection of four products is `PPL-A2` alone — the check we already know is
insufficient (§3, `PPO-A4`).

---

## 9 — What this changes in doc 40

| doc 40 | change |
|---|---|
| `PPL-A2` closure | **profile-relative** — CORE pack + profile pack, not one universal rule (`PPO-A4`) |
| `PPL-A4` skeleton-first | **profile is declared before the skeleton** (`PPO-A5`) |
| `PPL-A7` demands | promoted: it is **~50% of the outcome**, not an edge case (`PPO-A1`) |
| `PPL-A10` fact set | gains a second artifact — the **demand manifest** — and `OUTCOME` is the pair |
| `PPL-T2` "a shipped system is playable" | restated as `PPO-A6`: **the CQ set is answerable**. Strictly stronger and actually checkable |
| §13 open #3 (pacing) | now `CQ-A1`, i.e. **in scope for the outcome**, not a deferred nicety |

And two findings that leave the planner track entirely, for the substrate owners:

- **`PROG_001` needs a depleting variable** (`PPO-A2` — lifespan). Schema-additive.
- **`PROG_001` needs regression** (`PPO-A3` — failed breakthrough, tribulation, heart demon).
  `TierRegress` is reserved as PROG-D2 with no producer.

---

## 10 — Open

1. **Is `capability_vocabulary` a progression artifact or its own element?** (`PPO-A7`) It is consumed
   by the agent tier, produced from the corpus, indexed by tier. Argument either way; leaning
   *progression-owned, agent-tier-consumed*, because its index is the tier.
2. **How are straddling kinds (§2) planned?** The progression planner declares `alchemist_grade` and
   demands both its inflow and its gate from crafting. Does crafting then run its own planner and
   satisfy the demand — i.e. **planners compose over the demand graph**? That is elegant and it is a
   much bigger commitment than one planner.
3. **`CQ-A1` pacing needs simulation, not a query.** Answering *"how long from tier 1 to 5"* means
   integrating rates against costs — a numeric constraint problem (the Z3/MiniZinc pointer from
   doc 40 §8A.5). In scope for the outcome, out of scope for the first spike; say so plainly.
4. **How many CQs must be answerable to ship?** 19/19 is probably wrong (some are V1+). The threshold
   is a PO decision and it should be set **before** the spike prints its number, not after.

---

## Sources

- [Cultivation 101: How Xianxia Power Systems Actually Work](https://donghuawiki.com/guides/cultivation-explained) — qi → dantian → realms
- [Xianxia Cultivation Realms: Complete 10-Stage Guide](https://wuxiatales.com/cultivation/cultivation-realms-explained/)
- [Extended Cultivation Encyclopedia — Half-Steps, Loose Immortals, Body Cultivation, Spirit Stones](https://xianxialitrpgwiki.com/cultivation-encyclopedia/) — body-vs-qi tracks, spirit-stone dual role
- [Xianxia & Xuanhuan Cultivation & Power Systems](https://shapes.inc/fandom/xianxia-xuanhuan/cultivation-systems) — tribulation as escalating waves; sect resource competition
- [Chinese Cultivation Systems: Qi, Realms, and Immortality](https://read.teanovel.com/blog/chinese-cultivation-systems) — lifespan grants per realm
- [Xianxia Video Games: The Best Cultivation Gaming Experiences](https://xiuxian0.com/modern-influence/xianxia-games-guide/)
- [Incremental game (Wikipedia)](https://en.wikipedia.org/wiki/Incremental_game) · [Top 7 Idle Game Mechanics](https://mobilefreetoplay.com/top-7-idle-game-mechanics/) — profile X: multiple currencies, parallel tracks, time-based unlocks, automation
- [How to Make an Idle Game](https://apptrove.com/how-to-make-an-idle-game/) — the curve *is* the game
- [From human experts to machines: LLM-supported ontology and KG construction](https://arxiv.org/abs/2403.08345) — competency questions as the completeness criterion (`PPO-A6`)
