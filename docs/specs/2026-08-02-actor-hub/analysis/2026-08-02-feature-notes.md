# Feature notes — measured findings for combat, progression and ownership

> ## THIS IS ANALYSIS, NOT A DECISION
>
> Kept because it cost real effort and a later feature can reuse it instead of re-deriving it.
> **It binds nobody.** The owning feature may take any of it, amend it, or discard it outright.
>
> **What is DECIDED lives in the contracts** — [`2026-08-02-actor-hub.md`](../2026-08-02-actor-hub.md) and
> [`2026-08-02-engine-substrate.md`](../2026-08-02-engine-substrate.md) — and the measured seams live in
> [`2026-08-02-seams-and-triggers.md`](../2026-08-02-seams-and-triggers.md).

> **Scope violation, recorded.** This file was originally written as *"what the round DECIDED on behalf of
> features that were not in the room"* — worked proposals with mechanics and numbers. **That was feature #1
> specifying feature N.** The measurements below are sound and were expensive to make; the proposals around
> them were not ours to write. **Read the evidence; ignore the imperatives.**

**Status:** handoff · **Date:** 2026-08-02
**Companions:** [`2026-08-02-actor-hub.md`](../2026-08-02-actor-hub.md) ·
[`2026-08-02-engine-substrate.md`](../2026-08-02-engine-substrate.md) ·
[`2026-08-02-actor-dataflow.md`](2026-08-02-actor-dataflow.md) *(derivation record)*

---

## 0. Why this document exists, and how to read it

An audit of the round found **four decisions made inside another feature's territory**. Deleting them would
lose real work; leaving them in the actor spec would create the exact failure the PO named — **a later
feature that cannot be designed, or two SSOTs in conflict.**

> **Everything below is a PROPOSAL to the owning feature, not a decision it inherits.**
> The owning feature may accept, amend or overturn any row. **If it overturns one, the substrate and hub
> documents must not change** — and if they must, that is a defect in the boundary, not in the feature.

Each row states the **evidence** behind it, so an owner can judge it rather than trust it.

---

## 1. To **combat** (`features/18_combat`)

### 1.1 🔴 A shipped defect — the damage law guarantees ≥ 1 damage on every LANDED hit

```rust
// crates/game-rules/src/combat/attack.rs:135
let base = (atk.strike_power - def.armor).max(1);
// :185
let damage = if capped { rules.max_hit } else { raw as i64 }.max(1);
```

Both floors are defended in place and **both defences are correct in their own scope** — the first prevents
an `armor ≥ strike_power` stalemate *"the win/lose rule has no answer for"*; the second prevents a glancing
hit rounding to zero and reading as *"a miss that was reported as a hit."*

**Together they mean accumulation defeats scale: a far weaker attacker can kill a far stronger defender by
attrition** — in `hit_points / hit_rate` blows, not the astronomically many the power gap implies.

> **Corrected from *"unconditionally"* (`V-SEAL/F-22`).** The floor is unconditional **within a landed
> hit**; `attack.rs:109-111` returns `damage: 0` on a miss. **So the attrition count depends on hit rate
> against `def.dodge_pm`** — exactly the term a large band gap would move, and which combat may decide is
> already part of the answer. **The finding is real; the arithmetic is combat's to run.**

**Diagnosis:** a rule authored for **within-band** combat is enforced at **every** band, where it stops being
an anti-stalemate rule and becomes an anti-scale one.

**Proposal:** one floor cannot serve two opposite failure modes.

| situation | danger | proposal |
|---|---|---|
| **within a band** | a stalemate that never resolves | **keep `max(1)`** — a blow must do something |
| **across bands** | accumulation defeating scale | **no floor — the interaction is REFUSED.** Not 1 damage: no damage and no blow |

```
Δ = band_delta(attacker, defender)
Δ < −threshold  →  REFUSED (§11's verb)
otherwise       →  the existing chain, max(1) and all
```

**Combat owns `threshold`.** The substrate provides only `band_delta` (substrate §10).

### 1.2 Consequences worth knowing before you decide

| | |
|---|---|
| **the zerg needs no special rule** | a thousand weak attackers become a thousand refusals, not a thousand × 1 damage. The comparable MMO problem is patched explicitly elsewhere with level-scaling and anti-twink rules |
| **the narrator gets an instrument** | this is an LLM-narrated simulator. *"Your blade does not reach him"* becomes a mechanical outcome with a readable reason instead of flavour laid over a 1-damage hit. **A model that cannot refuse cannot express futility** |
| **inadmissibility must be an EVENT** | the chain already commits a `capped` flag into `Struck` so *"a bound ceiling is a fact in the log rather than a number nobody can explain."* Same discipline at the floor, or **a refused blow is indistinguishable from a dropped one** |

### 1.3 Do not encode the genre claim as mechanism

*"A weaker being can never harm a stronger one"* is a **genre claim**. The threshold must be
**author-declared**, and there must be a **named escape that works through the mechanism, not around it** —
because *fighting above one's realm* is a celebrated feat **precisely because it is exceptional**, and in the
fiction the weaker party never wins by hitting harder. They win by **changing the terms**.

**Mechanically that is a one-shot Log-domain modifier that raises effective magnitude for a single action at
a cost — so it moves the actor ACROSS the line rather than exempting them from it.** No pragma, no special
case: the exception uses the same arrow as the rule.

### 1.4 The stat slots are combat's, and they should leave the hub

> **⚠ CORRECTED TWICE (`V-SEAL/F-5`).** The claim *"the fold and the stat block never need a slot's name;
> all by-name sites are combat"* is **false, and inverted on both axes.** Re-measured: **non-test
> by-name sites OUTSIDE combat exist and are load-bearing** — a recount put the figure anywhere from 19 to
> 30 depending on whether the defining `ALL` array and doc comments are counted, so **the number is
> deliberately not restated; the SITES are** — including **inside the fold itself** (`resolve.rs:131-133`,
> `let mr = StatSlot::MoveRange`) and **inside the stat block** (`block.rs:76` `get(Speed)`, `:89`
> `set(MoveRange, …)`), plus `ruleset-core/src/slots.rs:71` and `stats.rs:56-76`. Meanwhile the **resource
> tier — the named exception — has ZERO non-test by-name sites**; it uses `StatSlot::ALL` only, and the one
> by-name binding is in a test.

**What this means for the proposal below:** making the slot table private to combat **would not compile** —
`resolve.rs:131` and `block.rs:76,89` break first. The `MoveRange` derivation and the `Speed` read must move
out of the shared fold **before** the table can move, and that ordering is now part of the proposal rather
than an assumption behind it.

`StrikePower`, `Armor`, `CritChance` are **not what a being IS**. They are **what combat computes about a
being**, from the intrinsic plus the external (a sword, a formation).

**Proposal:** the slot table becomes **combat's own projection**, private to combat's part. Combat may then
key it however it likes, because nobody else can see it. **The resource tier stops binding ceilings to combat
slots and binds them to quantity ordinals instead** (substrate §8) — after which the resource tier does not
know combat exists.

### 1.5 The archetype is yours, and today it is the only source of a playable actor

**Measured:** `StatRules::melee_archetype` and `slot_defaults` are `[i32; SLOT_COUNT]` over **ten combat
slots** — combat vocabulary by construction. `CombatStats::archetype_melee` is the only non-test producer of
playable numbers, and `StatBlock::zeroed`'s own doc says *"NOT a playable actor — a zeroed block has 0 max
HP"*, while `StatBlock::from_defaults` exists because *"'Playable with zero declaration' is a hard
requirement"*.

**A completeness audit read the hub's removal of the layer-source enum as *"the archetype has nowhere to
go"*, and an earlier draft of the hub accepted that as a gap to fill.** It is not the hub's: the hub reads
initial values from each plugin's own declaration (hub §3.4b) and has no opinion about what a melee fighter
starts with.

**So the question is yours, and it is real:** *"playable with zero declaration"* is a shipped requirement
with a shipped implementation, and **nothing in the new frame restates it.** Whether it stays combat's, or
moves to an archetype feature that does not exist yet, is a decision this round deliberately does not take.

### 1.6 If damage becomes a permille — combat's call, not the hub's

If a pool's `current` is a permille of its capacity (substrate §5.3), then within a band only the **ratio**
matters and across bands §1.1 refuses. **A damage figure expressed as a permille of the defender's capacity
follows**, and the existing absolute maximum-hit cap would become a permille cap — *"no single blow removes
more than N ‰ of a reserve"* — which does not need re-tuning at every band.

**This is stated as a consequence, not a decision.** It was originally written into the actor spec, which was
the leak this document exists to correct.

---

## 2. To **progression / cultivation** (`features/00_progression`)

### 2.1 Magnitude and tier are not duplicates — the bottleneck is the missing piece

Giving an entity a log-domain magnitude alongside an existing tier index looks like two representations of
*how strong*. **It is not, and the resolution already ships** as a tier-based cap rule:

```
magnitude              = the VALUE that accumulates
tiers[i].tier_max      = the CEILING it may reach          ← the bottleneck
tier_index             = WHICH ceiling currently applies
BreakthroughCondition  = what unlocks the NEXT ceiling
```

**Accumulation stops at `tier_max`** — that is *"peak of the Nth stage"*, holdable indefinitely.
**Breakthrough does not raise the value; it raises the ceiling**, and the value then has somewhere to go.

### 2.2 The ladder is ratcheted going up and free going down

| direction | mechanism |
|---|---|
| **rising** | **gated** — the value stalls at `tier_max`; only a breakthrough condition raises the ceiling |
| **falling** | **automatic** — the magnitude drops, and below the band's floor the tier simply *is* lower |

Neither half is a rule anyone wrote: rising is gated because a **ceiling** gates it; falling is free because
**nothing** gates a value going down once contributions may be negative.

### 2.3 Do not encode monotonicity as mechanism

The current validator **refuses a ladder whose rungs do not rise** — and its own message states the genre
claim out loud. **That sentence is true for a cultivation ladder and false as a law.** Being monotone is a
legitimate design; **making it unrefusable is the defect**, and the test says so: signed and unsigned
integers add identically, so the engine's arithmetic does not differ between *can fall* and *cannot fall*.

> **⚠ CORRECTED — `TierFall` does NOT replace the shipped check; the two govern different subjects.**
> `validate.rs:212-219` constrains **the declared ladder's rungs** (`tiers[i+1].tier_max > tiers[i].tier_max`)
> and never sees an entity. `TierFall` is a **runtime policy on an entity's tier index**. **A
> descending-rung ladder stays refused under every `TierFall` value.** ⇒ this is an **ADDITION**, and the
> *never delete a check* rule is satisfied because **nothing is deleted**.

**Proposal — an ADDITIONAL declared property:**

```
TierFall { Automatic, Gated, Never }        // default: Automatic
```

`Never` = a stage once attained is never lost. **`Gated` is the interesting one** — a fall costs its own
condition, making it as narratively expensive as a breakthrough.

> **General rule this is an instance of: never DELETE a check that encodes a content claim — give it an
> author-declared subject, and keep the safe value as the default.**

### 2.4 A fall is an appended event

Canon is the ledger, so **a fall is a new entry on a rising ledger, not a rewrite of it.** Two monotonicities
must not be confused: **the ledger's is correct and stays**; **an entity's value is not history.**

`TierChanged { from, to, cause }` — **`cause` is load-bearing.** A narrator cannot tell *crippled by an
enemy* from *burned your own foundation to escape* out of a delta alone.

### 2.5 Transfer overflow is yours to interpret

If magnitude transfer between entities exists, the receiving side can overflow its ceiling by a large factor
when the gap is large. **The substrate clamps and emits an event** (substrate §11). **What that event means —
a deviation, a boon, a scar — is progression's**, and it is the natural home for the genre's
cultivation-deviation concept, arriving as a consequence of arithmetic rather than a special case.

### 2.6 Declared numbers must fit — and the refusal is your guard

The substrate refuses a declared number wider than `i32`. **Write `tier_max` as a WITHIN-tier span that
resets, not as an absolute magnitude that grows multiplicatively.** A wide type is an invitation to the
exploding design; the refusal is what makes the invitation fail loudly, pointing at the tier mechanism
instead.

---

## 3. To the **ITEM / ownership round**

> **`C-9` was wrong and is retracted.** This section previously read *"to ownership — which has no feature
> folder"*, measured from the planning tree's 35 feature folders. **The home exists**: an item round is in
> flight — [`2026-08-02-item-data-structure.md`](../../2026-08-02-item-data-structure.md),
> [`2026-08-02-item-dataflow.md`](../../2026-08-02-item-dataflow.md) and its
> [run state](../../../plans/2026-08-02-item-substrate-RUN-STATE.md) — created by a parallel agent that was asked
> to reference the actor data structure. **The error was mine: I asserted a directory's contents without
> listing it.**
>
> **Reconciliation is deliberately NOT attempted here.** The item round inherits `D-1`..`D-109`; this round
> continued to `D-194`, and the difference includes the plugin frame, the shrunk hub scope, the permille pool and the contract split. **That is a note for whoever reconciles, not a task for this
> session** — this session is still building the FIRST feature, and the others are plugins.

### 3.1 Money is external — it is not the actor's

A possession does not travel with a being stripped naked into another world. **Money, items, equipment and
treasuries are ownership's, and none of them belongs in the actor hub.**

### 3.2 What the substrate legitimately learned from the currency question

**One sentence, and money was the evidence rather than the subject:**

> **The domain set was incomplete.** A currency is **additive** (you add coins), **exact** (you hold 37, not
> *"about 10^1.57"*) **and unbounded across bands** — which **neither a linear count nor a log magnitude can
> express**. That is a real gap, and it is **yours**, because money is 身外之物.
>
> **⚠ CORRECTED.** An earlier draft concluded *"a `Scaled { value, scale }` type subsumes both"*. **It does
> not** — its `add` truncates the smaller operand across a scale gap, so it fails the *exact* conjunct of
> the very three-part requirement stated above, and adversarial verification found five of its six
> operations broken. **The type has been deleted from the engine substrate.**
>
> **What survives for you is the SHAPE, and it is a solved problem** — decade-quantised exponent with a
> nine-digit normalised mantissa (substrate §5.1.1), which is what every arbitrary-precision decimal library
> has used since the 1960s. **The earlier version's exponent was a milli-log, and that was the defect**: it
> was not quantised to decades, so comparison was simply false.

### 3.3 What is NOT the substrate's, and is proposed to you only as a starting point

| | |
|---|---|
| **denominations** | the genre's own answer to unbounded wealth is a **change of unit** — a hundred of one grade make one of the next, so nobody holds 10¹² of the smallest. That maps onto an exponent, but **the radix, the grades and their names are yours** — and note a decade-quantised exponent implies a radix of 10, so a radix of 100 needs its grades expressed as every second decade |
| **what an absorption means** | the substrate guarantees that a payment too small to register **emits an event** rather than vanishing silently. **Whether that is a rounding note, a slight, or nothing at all is ownership's** |
| **transfer semantics** | who may give what to whom, and what a clamped overflow means economically |
| **a group-held quantity** | a faction treasury is held by the group as such. **The engine substrate does not care** — it holds values by entity id, and a faction is an entity. **Whether that is the right model is yours and social's** |

### 3.4 One thing the substrate does ask of you

**If a quantity is wealth-shaped, declare its domain and its scale explicitly.** The substrate refuses
cross-domain contributions rather than converting them, so an economy that mixes a linear count with a scaled
magnitude will be refused at declaration — **which is the intended behaviour, not an obstacle to work
around.**

---

## 4. Rows deliberately NOT handed off

| | why |
|---|---|
| the playable combat band — where combat stays interesting when one band is a large multiple of the last | **purely combat's**, and no substrate finding constrains it. Recorded here only so it is not mistaken for an oversight |
| what a status means, stacks like, or lasts | status plugin's, untouched by this round |
| which entity kinds exist | actor and social features' vocabulary |
