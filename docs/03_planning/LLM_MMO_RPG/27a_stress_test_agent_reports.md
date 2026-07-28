# 27a — Stress-test agent reports (RAW APPENDIX)

> **Status:** RAW EVIDENCE — 2026-07-28. Companion to
> [`27_extensibility_stress_test.md`](27_extensibility_stress_test.md).
>
> **What this is.** The five stress-test agents' final reports, verbatim and unedited. Doc 27 is the
> distillate; this is the source it was distilled from. Recovered from the session's subagent
> transcripts after a context compaction, at the PO's instruction (*"điều tra phần bị mất"*) — the
> summaries in doc 27 §5 had survived, the full reports had not.
>
> ⚠️ **This file is NOT authoritative and its claims are NOT verified.** It is model output about
> both this codebase and about shipped games. Doc 27 records which claims were re-checked against
> the source; everything here that doc 27 does not carry forward should be treated as **a lead, not
> a finding**. Quote doc 27, not this file. It exists so that a future reader can audit the
> distillation — and so that a lead dropped in §5's compression can be picked up later without
> re-running the agents.
>
> `design-lint: ok prefix EP` — the `EP-*` / `E*` / `F*` ids below are the agents' OWN
> local numbering inside their own reports, not repo ids. They are deliberately NOT registered:
> registering them would imply this file is normative, which is exactly what it is not.
>
> No `XST-*` ids are minted here. An idea from this file earns an id only by being promoted into
> doc 27.

---


## Contents

* [Deckbuilders / roguelikes — the compositional-effects test](#deckbuilder) — distilled into doc 27 §5.1
* [ARPG / MMO itemization — the stat-count and damage-formula test](#arpg) — distilled into doc 27 §5.2
* [Immersive sims / colony sims — the open-ended-modding test](#immersive) — distilled into doc 27 §5.3
* [Cultivation / idle / prestige — the unbounded-growth test](#cultivation) — distilled into doc 27 §5.4
* [Adversarial architecture critic — where this rots in two years](#adversarial) — distilled into doc 27 §9

---


<a id="deckbuilder"></a>

## Deckbuilders / roguelikes — the compositional-effects test

*Distilled into doc 27 §5.1. Verbatim below.*

### Extensibility Stress Test: Deckbuilders / Roguelikes / Compositional Card Games

Researched: Balatro (joker activation sequence, xMult ordering, Blueprint/Brainstorm/Baseball Card, Oops! All 6s, Chicot, Showman), MTG (CR 613 layers, CR 616 replacement-effect interaction, Furnace of Rath × Gisela), Hearthstone (Advanced Rulebook: trigger queues, order of play, queue immutability), Slay the Spire (Double Tap, Necronomicon, Duplication Potion, Snecko Eye, Velvet Choker, Corruption), Monster Train (Multistrike/Trample/Spikes/Strike trigger stacking, Silence), Inscryption (Bifurcated/Trifurcated Strike, Touch of Death, sigil stacking), Dicey Dungeons (countdown equipment), Griftlands (grafts).

---

#### 1. Verdict Table

| # | Mechanic (genre source) | Verdict | Mechanism that absorbs it / Axiom it breaks |
|---|---|---|---|
| 1 | **Reactive triggers** — "whenever you take damage, deal 3 back" (StS Thorns, MT Spikes, MTG Boros Reckoner) | **BREAKS** | Axiom 6 (closed action vocab + inert `Decision`) **and** Axiom 7 (one action per turn). Event-sourcing *records*; it does not *dispatch*. There is no path from a committed event back into effect resolution. |
| 2 | **Retrigger / multi-hit** — Multistrike, Double Tap, Necronomicon, Hanging Chad, Bifurcated Strike | **BREAKS** | Axiom 1/2 (closed 10 slots + projection-only). No cardinality slot, and `max(1, sp−armor)` is non-linear so hit-count does **not** distribute into StrikePower. Also breaks Axiom 10 (one RNG draw per action ⇒ all hits crit or none). |
| 3 | **Order-dependent multiplicative chain** — Balatro jokers, +Mult before xMult | **BREAKS** | Axiom 4 (percent SUM, never chain). Balatro's *entire decision space* is the player dragging jokers to choose the order; sum-not-chain deletes the game. |
| 4 | **Damage replacement effects** — "damage is dealt twice" + "damage is halved" (Furnace of Rath × Gisela) | **BREAKS** | Axiom 5 (locked 4-step chain, no insertion point) **and** Axiom 4 (two doublers must be 4×; summing gives 3×). |
| 5 | **Effects that modify other effects** — Blueprint/Brainstorm copying a neighbor joker; "your Strikes also apply Burn" | **BREAKS** (behavior) / **BENDS** (stat-shaped) | Axiom 6. `EffectOp` is a closed sum matched by the engine; content cannot say "run whatever op that other entity has." Stat-shaped versions fit `StatSlotDecl.terms`. |
| 6 | **Non-linear scaling** — Baseball Card (×1.5 *per* Uncommon Joker ⇒ 1.5ⁿ) | **BREAKS** | Axiom 4. `terms:[{kind_id, weight}]` is a weighted **sum**; 5 uncommons gives 3.5× where truth is 7.59×. |
| 7 | **Numeric range** — Balatro scores past 1e30 → naneinf | **BREAKS** | i64 milli-units cap at ~9.2e15. Not fixable inside the domain; needs a firewalled second number type. |
| 8 | **Effect suppression** — Chicot (disables all Boss Blind effects), MT Silence (disables triggers), MTG layer 6 ability removal | **SPLIT: SURVIVES / BREAKS** | Stat suppression **survives** — the Lex clamp applied LAST is exactly this, and it's in the right position. Behavior suppression **breaks** Axiom 6: a sum-only algebra has no negation, and there are no author-visible behaviors to suppress. |
| 9 | **Rules-changing relics** — "play 2 cards per turn", Velvet Choker (max 6), Corruption (Skills cost 0), Snecko Eye | **BENDS → SURVIVES** | Axiom 8 is the right mechanism and is a genuine strength: a rules change is a **Ruleset delta**, and the digest is already pinned per event, so mid-run rule mutation is replay-safe. Breaks only because "one action per turn" is stated as *structural* rather than as a ruleset scalar. |
| 10 | **The Stack** — priority windows, instant-speed response, counterspells | **BENDS** | `Decision` = validated-then-committed proposal gives a **1-deep response window nearly free**. Unbounded LIFO with re-entrant priority breaks Axiom 7 (responding = acting without spending AV). |
| 11 | **Delayed / countdown effects** — Dicey Dungeons countdown equipment, MTG suspend, MT Endless | **BENDS** | Expiry-as-removal **survives** (round boundary already expires round-scoped statuses). Expiry-as-*detonation* needs #1. Cheapest trigger to add — the round-boundary code already visits the site. |
| 12 | **Zones** — draw pile / hand / discard / exhaust, shuffle, "top card of deck" | **BENDS (orthogonal, simply absent)** | Breaks nothing, but the stat/status/action triad has no 4th primitive for *ordered mutable collections*. Notably the **closed action vocabulary survives beautifully** — `play_card(id)` is one tool; the pressure lands entirely on `EffectOp`. Needs `shuffle`/`draw` RNG roles. |
| 13 | **Computed magnitudes** — "deal damage equal to your Block", X-cost cards, Chemical X | **BENDS** | `StatSlotDecl.terms` is a linear form over kinds — covers linear cases. Lost: volatile per-combat counters force re-projection *per resolution*, eroding the cold/hot split that justifies the dense array. |
| 14 | **Copies carrying accumulated state** — Showman, Invisible Joker, Ankh, MT Fecundity ("a copy of the summoned unit, upgrades and all"), Dolly's Mirror | **SURVIVES — and better** | The LOCKED layer order makes "copy at layer N" a *well-defined cut* over explicit inputs. MTG needed CR 613 (7 layers) + CR 706 to define what a copy copies. |
| 15 | **Simultaneous deaths / trigger ordering** — Hearthstone order-of-play + queue immutability | **SURVIVES — and better** | Event sourcing gives a total order and an entity creation index for free; the durable commit boundary *is* queue immutability. Hearthstone had to legislate both and still ships sequencing bugs. |
| 16 | **Positional / adjacency targeting** — Bifurcated + Trifurcated Strike (which now *stack* to 2-left/1-mid/2-right), MT floors, joker slot adjacency | **BENDS → SURVIVES** | MoveRange + a `position` RNG role means spatial exists. Target shapes as **offset lists** stay data; set-union of offsets is commutative, so stacking fits the order-independence spirit exactly. |
| 17 | **Probability modifiers** — Oops! All 6s ("doubles all listed probabilities", stacks: 2 copies = **quadruple**) | **BENDS** | Per-mille CritChance + slot clamp handles one copy cleanly. Lost: two copies give 3× under sum-not-chain where the genre requires 4×. |

**The pervasive theme:** rows 3, 4, 6, 17 are the same collision. *Every doubling effect in this genre is multiplicative on stack.* Axiom 4 turns 2× ∘ 2× into 3×. This is not an edge case — it is the genre's default composition operator.

---

#### 2. The Three Most Dangerous BREAKS

##### BREAK 1 — Multiplicity is provably unprojectable

The cleanest disproof in the report, because it's arithmetic, not taste.

> Monster Train unit with **Multistrike 2** (attacks 2 additional times). StrikePower 10, enemy Armor 8.
> Truth: 3 hits × `max(1, 10−8)` = **6 damage**.
> Try to project Multistrike into StrikePower: you need `sp` with `max(1, sp−8) = 6` ⇒ `sp = 14`. The required weight is **4**.
> Same unit vs Armor 0: truth = 3 × 10 = 30 ⇒ you need `sp = 30`, weight **20**.

The projection weight depends on the *target's* Armor, which is not knowable at cold projection time. **No `StatSlotDecl` can express Multistrike**, because step 1 of the damage chain (`max(1, sp − armor)`) is non-linear and hit-count therefore does not distribute across it. The closed 10 slots have magnitude dimensions but no **cardinality** dimension, and cardinality is not reachable from magnitude.

Second-order damage: Axiom 10 keys RNG on `(actor, action_index, role)`. Three hits inside one action share one `damage` draw and one `crit` draw — **all three hits crit or none do**. Monster Train explicitly notes Multistrike "doubles the effect of any boosts"; Inscryption pairs Touch of Death with Trifurcated Strike specifically to kill three creatures. Both need per-hit independence.

Broken: Axiom 1, Axiom 2, Axiom 10.

##### BREAK 2 — Damage replacement ordering (the sum-vs-product collision at its sharpest)

> Player holds relic **Furnace** (all damage doubled). Boss has **Gisela** (damage dealt to you is halved, rounded up). Incoming damage: **7**.
> Double-then-halve = `ceil(14/2)` = **7**. Halve-then-double = `ceil(7/2)×2` = **8**.

Under MTG CR 616 both orders are legal and the **affected player chooses**. The locked 4-step chain has exactly one multiplicative element slot (`elem_mult`) and one resist slot (`1−resist`), so it can encode at most one of these orders and has no author-visible insertion point for either.

Worse, the pure case: **two** damage doublers. MTG gives 4×. Axiom 4 models each as +100%, sums to +200%, yields **3×**. There is no encoding of "two independent doublers" in a sum-only algebra. And this isn't obscure — StS's Vulnerable/Weak, Balatro's xMult, Monster Train's Rage all compose this way.

Broken: Axiom 5 (locked chain, no insertion point) **and** Axiom 4 (sum kills product).

##### BREAK 3 — The reactive cascade

> Enemy has Multistrike 2. Player has **Thorns 3** and a relic *"whenever an enemy dies, draw a card"*; the drawn card has *"when drawn, gain 1 Block"*.
> Enemy attacks → 3 hits → Thorns fires **3 times** → the third kills the enemy → OnKill fires → a card is drawn → OnDraw fires → Block is gained.

A depth-4 causal chain, on the **enemy's** turn, in which the player performs six state mutations and consumes **zero** turn slots.

The architecture has no dispatch mechanism at all. Event sourcing records what happened; nothing reads the log back into effect resolution. `Decision` is explicitly "a PROPOSAL that executes nothing" — it is a *pre*-commit construct, and triggers are inherently *post*-commit. And Axiom 7's one-action-per-turn resource is the wrong shape: the reacting actor has no slot to spend, and shouldn't need one.

The "effects modifying effects" half is the harder break. Balatro's Blueprint *copies the compatible Joker to its right*; Brainstorm copies the leftmost. That is content saying **"execute whatever `EffectOp` that other entity holds."** A closed 9-variant sum type dispatched by `match` has no variant for indirection. This is not a missing leaf — it's a missing *combinator*.

Broken: Axiom 6 (twice over) and Axiom 7.

---

#### 3. Where This Architecture Is BETTER Than the Genre

Five of these are things the genre has genuinely never solved.

1. **Replay across a patch.** Balatro and Slay the Spire seeds *break between versions* — a seed is not a contract. Digest-pinning the ruleset into every event makes a run reproducible across arbitrary content churn. No shipped deckbuilder can do this.

2. **Deterministic replacement ordering.** MTG CR 616 resolves order by *"the affected player chooses"*, with APNAP only as a multi-player tiebreak. That is a hidden decision that **cannot be replayed from a log** unless the choice is recorded. Replacing the prompt with a declared per-entity priority key + entity-creation-index tiebreak gives the same expressiveness, zero prompts, and total replayability — strictly better than the rules text it's modeling.

3. **Trigger ordering falls out for free.** Hearthstone had to *invent* "order of play" (oldest-to-newest entity index) and "the queue becomes immutable once resolution starts" — and still ships sequencing bugs. In an event-sourced engine, order-of-play is the entity creation index and queue immutability is the commit boundary. Both are structural, not legislated.

4. **Copy semantics are well-defined by construction.** MTG needs CR 613's seven layers plus CR 706 to answer "what does a copy copy?" (printed values + copy effects; *not* counters or auras). A LOCKED layer order over explicit inputs makes "copy at layer N" a declarative cut. This is the single cleanest win.

5. **Integer-only math.** Balatro's float scoring produces platform-divergent naneinf behavior at the extremes. i64 milli-units eliminate an entire desync class in a server-authoritative game.

6. **The Lex clamp is in the right position.** Genre games bolt global caps on ad hoc, scattered per-power. A world-rule clamp applied *last*, after all content, is the correct home for exactly the thing Chicot and Silence are reaching for.

7. **The closed action vocabulary is an asset, not a liability, for card games.** A card *is* a fixed tool. "An LLM or script driver picks an action from a fixed tool set" maps 1:1 onto "play card #37" — this is literally how Slay the Spire's AI interface works. All the extension pressure lands on `EffectOp`, and none on the action set. That's a good place for the pressure to be.

---

#### 4. Extension Points That Fix the BREAKS Without Abandoning the Design

Every proposal below preserves: closed sum types, dense arrays, cold resolution / hot indexing, integer-only, deterministic replay.

##### E1 — Restate Axiom 4 correctly (the highest-leverage single change, zero cost)

**Axiom 4 conflates "order-independent" with "additive." Multiplication is also commutative.**

The thing that actually destroys order-independence is *mixing* `+` and `×` in one unordered pool — which is precisely Balatro's `40 × ((4+4)×2) = 640` vs `40 × ((4×2)+4) = 480`. The fix is not to ban products; it is to **stage** them:

```
within a stage: contributions combine by ONE commutative operator (Sum or Product)
across stages:  the LOCKED layer order applies
```

Add one field: `StatSlotDecl { base, terms, clamp, combine: Sum | Product }`. Product-mode declarations still resolve **cold**, still emit a dense `i32`, and are still order-independent *within the stage*.

This alone fixes rows 3, 4, 6, and 17: two doublers become 4×, Oops! All 6s stacks to 4×, and Baseball Card's 1.5ⁿ is expressible. Balatro's player-dragged joker order is, viewed correctly, a UI for **choosing stage assignment** — and staging is the better model, because it's replayable.

##### E2 — Keywords as a dense bitset (the KYWD escape hatch, done better than Skyrim)

Skyrim's `KYWD` records are interned FormIDs and `HasKeyword` is a **linear list scan** — that's Bethesda's perf bug, not a design to copy. Take the idea, drop the container:

```rust
struct Resolved {
    stats: StatBlock,      // [i32; 10] — UNTOUCHED
    keywords: u128,        // 128 interned behavior tags, resolved COLD alongside stats
    overflow: KeywordPage, // sorted &[KeywordId], cold path only, for >128
}
```

Hot-path test is `kw & MASK != 0` — **~1 cycle, faster than the 4 ns precondition check**, and it never hashes. The keyword→bit assignment table lives in the **Ruleset** and is digest-pinned, so it's replay-safe.

This absorbs: "your attacks also apply Burn" (weapon carries `KW_APPLIES_BURN`; one damage-chain step reads the bitset), Silence (`kw &= !TRIGGER_MASK` — negation now exists, at the keyword layer rather than the arithmetic layer), card typing ("all your **Attacks** cost 1 less"), and targeting-shape selection.

##### E3 — A bounded trigger bus built on the log you already have

Do **not** add scripting. Add three closed types:

```rust
enum TriggerPoint {            // RULESET concept, closed, ~12 engine-defined moments
    OnDamageDealt, OnDamageTaken, OnKill, OnDeath,
    OnStatusApplied, OnStatusExpired,
    OnTurnStart, OnTurnEnd, OnRoundStart, OnRoundEnd,
    OnCardPlayed, OnZoneMove,
}
struct Reaction {              // CONTENT-authored, but assembled only from closed vocabularies
    when: TriggerPoint,
    guard: Precondition,       // the existing closed 5-variant set
    then: EffectOpId,
}
```

- **Axiom 7 is preserved verbatim**: a Reaction is not an action. It consumes no turn slot and does not touch AV. "One action per turn" was never the obstacle — treating reactions *as* actions was.
- **Resolution discipline, straight from Hearthstone**: on a trigger point, snapshot subscribers in **order of play** (entity creation index), make the queue **immutable**, resolve. Both are free here.
- **Loop-proofing is a ruleset scalar**: `MAX_TRIGGER_DEPTH` (say 8) and `MAX_REACTIONS_PER_COMMIT`. Digest-pinned ⇒ replay-safe *and* halting-guaranteed.
- **Perf**: index subscribers as `[SmallVec<[ReactionId; 4]>; N_TRIGGER_POINTS]` — the same dense-array discipline as `StatBlock`. Zero-subscriber case is one length check, ~1 ns, which is the case in the overwhelming majority of steps.

##### E4 — Promote structural constants into the Ruleset

`actions_per_turn: u8` fixes Velvet Choker, "play two cards per turn", and Corruption in one line. This is Axiom 8 *working as designed*, and it's the architecture's best idea — but only if the ruleset is a **stack of pinned deltas** whose digest is the hash of the stack. Then acquiring a rules-changing relic mid-run is simply an event that pushes a delta, and every subsequent event pins the new digest. Mid-run rule mutation becomes replay-safe, which no game in this genre achieves.

Audit rule: any structural constant currently living in code (`1` action, `4` damage steps, `8` layers, `10` slots) is a candidate. The ones that must stay in code are exactly the ones the dense array depends on.

##### E5 — A `REPLACE` stage before step 1 of the damage chain

Keep the 4 steps locked. Add exactly one stage in front, holding a closed set:

```rust
enum DamageReplacement { Double, Halve, SetTo(i64), MinimumOf(i64), PreventAll }
```

Order them by a declared per-entity `replacement_priority: i16`, ties broken by entity creation index. This is **MTG CR 616 made deterministic** — same expressive power, no player prompt, fully replayable. Note the ordering is genuinely load-bearing (7 → 7 vs 8 in the Gisela case), so it must be *declared*, not inferred.

##### E6 — Fix the RNG key **now**, before any replay logs exist

Two changes that are cheap today and catastrophic to retrofit:

1. **Add a sub-index**: `(actor, action_index, sub_index, role)`. Without it, every multi-hit, retrigger, and multi-target effect shares one draw.
2. **Reserve roles now**: add `shuffle`, `draw`, `cost`, `trigger_order` to the closed role set. Adding a role is *additive* under `hash(seed, actor, action_index, sub_index, role_tag)` — it perturbs no existing stream — but adding one later still bumps the ruleset digest. Reserving them costs nothing and buys the entire zone subsystem plus Snecko Eye.

This is the one recommendation I'd act on **immediately and independently of everything else here**, because its cost rises monotonically with every replay log written.

##### E7 — Give `EffectOp` combinators, not more leaves

If the 9 variants are all leaves, ~300 cards will never fit and you'll be at 40 variants within a year. Three combinators turn a flat enum into a closed **grammar**:

```rust
Seq(SmallVec<[EffectOpId; 4]>),          // composition
Repeat(u8, EffectOpId),                  // retriggers: Double Tap, Multistrike, Hanging Chad
IfElse(Precondition, EffectOpId, EffectOpId),  // conditional cards
```

Store ops in a **flat arena** in the content artifact and reference by `u32` index — no `Box`, no pointer chasing, arena-local and cache-friendly. Still a closed `match`. Still no dynamic scripting. `Repeat` alone resolves most of BREAK 1's behavioral half (the arithmetic half still needs E1 + hit-count living in the action-resolution descriptor rather than in `StatBlock` — multiplicity is a *count of resolutions*, not a magnitude, and does not belong in the dense array).

`Blueprint`-style indirection needs one more: an `EffectOpId` resolved through an entity reference at *cold* time (`CopyFrom(EntityRef, Slot)`), which keeps hot dispatch unchanged.

##### E8 — Firewall the big-number domain

Do not touch `i64` milli — it carries the perf and determinism story. If Balatro-scale scoring is ever in scope, add a separate cold-path-only `Score` type (i128 mantissa + i16 exponent) that **never feeds back into `StatBlock`**. The firewall is the design; the number type is an implementation detail.

---

##### Bottom line

The architecture's **quantity model** (closed slots + linear projection + sum-only) is the part that breaks, and it breaks on the genre's defining operation: multiplicative, order-sensitive composition. The architecture's **structural model** (event sourcing, digest-pinned rulesets, locked layer order, inert proposals, seeded role-keyed RNG) is not just adequate but *ahead of the genre* — it solves replay-across-patch, deterministic replacement ordering, and copy semantics, three problems MTG and Hearthstone address with rules lawyering rather than architecture.

The single highest-value change is **E1**: restating Axiom 4 as "commutative within a stage, ordered across stages." That preserves the real goal (order-independence) while unblocking four of the five arithmetic breaks, and it costs one enum field.

**Sources:** [Balatro Wiki — Guide: Activation Sequence](https://balatrowiki.org/w/Guide:_Activation_Sequence) · [Balatro Joker Order Guide](https://balatrocalculator.blog/blog/balatro-joker-order-guide/) · [Balatro Wiki — Oops! All 6s](https://balatrowiki.org/w/Oops!_All_6s) · [Balatro Wiki — Chicot](https://balatrowiki.org/w/Chicot) · [Balatro Wiki — Hanging Chad](https://balatrowiki.org/w/Hanging_Chad) · [Balatro Wiki — Mime](https://balatrowiki.org/w/Mime) · [MTG CR 616 — Interaction of Replacement and/or Prevention Effects](https://ancestral.vision/spells-abilities-and-effects/interaction-of-replacement-andor-prevention-effects.html) · [MTG Wiki — Layer](https://mtg.fandom.com/wiki/Layer) · [How Layers Work — Pocket Judge](https://www.pocket-judge.com/guides/how-layers-work) · [MTG Salvation — Gisela and Furnace of Rath](https://www.mtgsalvation.com/forums/magic-fundamentals/magic-rulings/magic-rulings-archives/580264-gisela-and-furnace-of-rath) · [Hearthstone Wiki — Advanced rulebook](https://hearthstone.wiki.gg/wiki/Advanced_rulebook) · [Hearthstone Wiki — Triggered effect](https://hearthstone.wiki.gg/wiki/Triggered_effect) · [Slay the Spire Wiki — Double Tap](https://slaythespire.wiki.gg/wiki/Double_Tap) · [Slay the Spire Wiki — Necronomicon](https://slaythespire.wiki.gg/wiki/Necronomicon) · [Slay the Spire Wiki — Snecko Eye](https://slaythespire.wiki.gg/wiki/Snecko_Eye) · [Slay the Spire Wiki — Velvet Choker](https://slaythespire.wiki.gg/wiki/Velvet_Choker) · [Monster Train 2 Wiki — Multistrike](https://monstertrain2.miraheze.org/wiki/Multistrike) · [Monster Train 2 Wiki — Spikes](https://monstertrain2.miraheze.org/wiki/Spikes) · [Monster Train 2 Wiki — Trample](https://monstertrain2.miraheze.org/wiki/Trample) · [Monster Train Wiki — Status Effects](https://monster-train.fandom.com/wiki/Status_Effects) · [Inscryption Wiki — Bifurcated Strike](https://inscryption.fandom.com/wiki/Bifurcated_Strike) · [Inscryption Wiki — Touch of Death](https://inscryption.fandom.com/wiki/Touch_of_Death) · [Dicey Dungeons Wiki — Equipment](https://wiki.diceydungeons.com/doku.php?id=equipment) · [Griftlands Wiki — How to play](https://griftlands.fandom.com/wiki/How_to_play_guide_of_Griftlands)

---


<a id="arpg"></a>

## ARPG / MMO itemization — the stat-count and damage-formula test

*Distilled into doc 27 §5.2. Verbatim below.*

I researched the actual systems, then read the real code (`services/commit-service/src/stats.rs`, `src/combat.rs`, `docs/.../ABL_001_ability_foundation.md`, `DF07_001_actor_stat_block.md`) so the verdicts are against the implementation, not the summary.

---

### ARPG/MMO Itemization Stress Test

#### 1 · Verdict table

| # | Mechanic (source game) | Verdict | Mechanism that absorbs it / axiom it breaks |
|---|---|---|---|
| 1 | **Affix tiers, rarity, crafting re-rolls** (PoE, D4, LE) | **SURVIVES** | Pure CONTENT. An affix = `Vec<StatModifier{slot, op, source:Equipment}>`; tier = a roll band; rarity = affix count. `StatEpoch.equipment_version` already invalidates the snapshot. Only engine ask: a `SeedRole::Craft` and craft-rolls committed as events (they're already role-derived, so this is additive by design). |
| 2 | **Auras / party buffs / "N% increased X"** (WoW, PoE) | **SURVIVES** | `ModifierOp::Percent` summed across sources is exactly the aura model. Order-independence is a real win here. |
| 3 | **Rating→percent secondary stats with DR** (WoW haste/vers; FFXIV crit) | **SURVIVES** | `StatSlotDecl{base, terms, clamp}` *is* a rating curve; FFXIV literally ships `⌊200(CRIT−420)/2780 + 50⌋/1000` — per-mille floor math is the genre-professional choice, not a compromise. DR = the `clamp`, or a piecewise `StatSlotDecl`. |
| 4 | **"Increased" (additive) vs "more" (multiplicative)** (PoE core) | **BENDS → fixable** | Not a break of *DF7-A5* if you read it precisely: A5 governs **stat-slot** percent. A closed, LOCKED-order `MultBucket` set living on the **hit** (not the block) reproduces "more" with zero float and full order-independence. **Note the stated rationale is half-wrong**: multiplication is commutative, so chaining is *also* order-independent. What summing actually buys is (a) no exponential stacking and (b) no *integer-truncation* path-dependence. That's the real axiom, and buckets preserve both. See E3. |
| 5 | **Per-element resistance + penetration** (PoE, GD, D2) | **BENDS** | `StatSlot` closed at 10 with ONE hardcoded `RESIST_PM = 0`. `DF7-D2` already reserves `Resist(ElementId)`/`ElemPower(ElementId)` — that survives **only if `ElementId` is engine-closed and small**. Author-declared elements (a tu tiên ngũ hành reality) would make `[i32;10]` non-dense. Fix: 8 engine element ordinals + author labels, exactly the StatSlot precedent. |
| 6 | **Three distinct resist-reduction stacking laws** (Grim Dawn: additive `-X%`, best-only `X% reduced`, flat) | **BENDS** | DF7-A5 has exactly ONE stacking law (sum). GD ships three for one concept. Expressible only by making stacking-rule part of the modifier: `ModifierOp::Percent{ bucket, rule }`. Loses "one law for all percent" — a real conceptual cost. |
| 7 | **Damage conversion chains** (PoE: Phys→Light→Cold→Fire→Chaos, pre-scaling, source tags retained) | **BREAKS**, then recoverable | Breaks the scalar chain **and** the locked step order (`base = max(1, sp − armor)` runs first, but PoE armour applies to physical only — after 100% conversion armour must not apply). Recoverable *without* touching the 4-step order, because conversion is a property of (actor, ability), not of the hit → resolve it **cold** into a lower-triangular 8×8 per-mille matrix pinned in `StatSnapshot`. See E2. |
| 8 | **A hit that is 60% phys / 40% fire** | **BREAKS** | `AttackOutcome.damage: i64` is a scalar; `resolve_attack` has one `ELEM_MULT_PM` const. Everything downstream (leech, reflect, thorns, ailment magnitude) reads one number. Needs a `DamagePacket = [i64; 8]` with **one** `max(1)` on the sum and **one** floor at emit. |
| 9 | **Ailments/DoT scaled off the causing hit** (PoE ignite = 90% of fire hit ×4s; bleed 70%, ×3 while moving; poison 30%, stacks ∞) | **BREAKS** | `EffectOp::StatusApply{ magnitude: u8 }` is an author **constant**. "Ignite for 90% of the fire damage dealt" is unrepresentable, and emitting a number is explicitly forbidden (ABL-Q9/ABL-V9 killed `VitalDelta{amount}` for exactly this). Also: `StatusFlag` is a per-(actor,flag) singleton — no stack count, no per-stack duration, no per-stack source. LE applies *multiple stacks per hit* above 100% ailment chance; unrepresentable. |
| 10 | **Leech / reflect / thorns / on-hit / on-kill triggers** | **BREAKS** | There is **no event-trigger substrate at all**. `EffectOp` is actor-fired, 1..=4 effects in declared order; reactions/retaliation are explicitly deferred (ABL-D3, COMB_002 §11). Reflect+thorns is also a *cycle* — in a 176–229 ns island step an unbounded cascade is a step-time DoS. Leech additionally needs "% of damage dealt" (same `PowerTerm` gap as #9) plus PoE's instance-list + rate cap (2%/s per instance, 20%/s total). |
| 11 | **Conditional affixes** ("+50% while at full life", "+X vs bleeding") | **BENDS** | `StatSlotDecl` is a *linear* projection; a predicated modifier isn't. `Precondition` (5 variants) is an **admission** gate, not a stat-resolution gate — conflating them would repeat the ABL-Q9 defect. Needs a separate closed `ModifierGuard`, split cold (equipment-stable) vs hit-time (target-state). |
| 12 | **Attack/cast speed vs turn-based `Speed`** | **BENDS (hard ceiling)** | `av = 10000/speed` integer-divides → **breakpoints**, authentically D2-like (D2's exist because 25 fps quantizes animation frames). But here the granularity **collapses**: speed 1000→AV 10, speed 5000→AV 2, speed ≥10000→AV 1 forever. Tempo is capped at 10000× nothing. Also DPS = damage × attacks/sec has no time base; multi-hit and channelled skills are ABL-D2/D9 deferred. Cheap fix: numerator 10000 → 1_000_000 as a digest-pinned constant. |
| 13 | **Subtractive armour vs stat explosion** | **BENDS** | `max(1, sp − armor)` is a cliff, not a curve: armour is either irrelevant (5k vs 5M strike) or absolute (5k vs 100 strike → the `max(1)` floor). Every game in the genre uses a ratio: PoE2 `armour/(armour + 12×hit)`, D2/D3 `armor/(armor+K)` — precisely so armour degrades gracefully against large hits. IMP-D1 calls the chain's *structure* code, so this is a law change, not a constant. |
| 14 | **Energy shield / ward / secondary pools** (PoE ES, LE Ward) | **BENDS** | `MaxHp` is one slot and the chain emits one number applied to HP. `VitalKind` exists (RES_001), so the *pool* is representable; the **routing** (ES-then-HP, with its own recharge/decay) is not. |
| 15 | **Accuracy vs evasion at scale** | **BENDS** | `clamp(500 + acc − dodge, 50, 950)` is additive and saturates at +450 pm. Above that, accuracy is a dead stat — the opposite of an ARPG where accuracy is a lifelong scaling concern (PoE uses a *ratio* with a fractional exponent). The clamps are load-bearing for encounter termination, so this is a deliberate, defensible bend. |

---

#### 2 · The three most dangerous BREAKS

##### B1 — The damage packet is a scalar, and the chain's *first* step is armour

**Axiom broken:** COMB_001 §4's locked 4-step chain, specifically that step 1 is `max(1, strike_power − armor)` on a single scalar.

**Scenario.** An author ships a "Flameblood Saber": *60% of physical damage converted to fire.* Target is a Fire Wraith: 0 armour, 75% fire resist. Correct ARPG resolution: 40% of the base takes armour and no resist; 60% takes no armour and 75% resist. In `resolve_attack` today there is one `base`, one `ELEM_MULT_PM`, one `RESIST_PM`. Every ordering you can express is wrong:

- Armour-then-elem (current order) subtracts armour from the fire portion too — a fire-converted build gets worse against armour, backwards from every game in the genre.
- Even with `Resist(ElementId)` slots added (DF7-D2), a *scalar* base cannot carry "which fraction is which element."

It cascades: leech ("gain 5% of fire damage as life"), reflect ("reflects physical"), and ailment magnitude ("ignite for 90% of *fire* damage") all need the typed breakdown, so the scalar break silently invalidates four later features. And the `max(1)` floor must apply once to the *total* — apply it per-component and an 8-element hit gets 8 free damage, turning a fully-resisted attack into guaranteed chip.

##### B2 — The chain silently saturates at ~1.6M base damage, **today**

**Axiom broken:** "i64 milli-units, exactly one floor at emit" — the arithmetic doesn't actually have the headroom the design assumes.

`combat.rs:220-230` builds `numer = base × 1000 × 1000 × roll_band × crit_mult` with `saturating_mul`, `denom = 1000^4`.

```
crit_mult_pm = 5000 (5×, a modest ARPG value), roll = 1150
numer = base × 10^6 × 1150 × 5000 = base × 5.75×10^12
i64::MAX = 9.223×10^18  →  base saturates above ~1.60×10^6
```

`StrikePower` is `i32` (2.1×10⁹), and percent modifiers *sum*, so `strike_power 100_000` with `Σpct = 20000` (+2000%, ordinary for the genre) resolves to 2.1M — already past the ceiling. Above it, **every hit produces the identical saturated number.** `saturating_mul` makes it silent, and worse, *deterministically* silent: replay agrees, conformance stays green, the bug is invisible to every existing test. The comment at line 226 congratulates the code for catching a 1000× error loudly; this failure mode is the exact opposite.

**And the fix for B1 makes it far worse.** Every new per-mille factor divides the ceiling by 1000. Adding an element factor + one `more` bucket takes the safe base from 1.6M to ~1600. **i128 intermediates are a hard prerequisite for any of the extensions below, not an optimization.**

##### B3 — No trigger substrate, and adding one naively is unbounded recursion inside a 176 ns step

**Axiom broken:** none yet — that's the danger. There is simply no seam, and the obvious implementations violate the closed-set discipline (an effect *script*) or the step budget (a cascade).

**Scenario.** Player has *Thorns 20%*. Boss has *Reflect 30% physical*. Player strikes → boss thorns the player → player's reflect returns it → boss's thorns fire again. In PoE this class of interaction produced the infamous reflect-death; here it produces an island step that never terminates. Every mitigation must be built in from the start:

1. Trigger resolution order must be `(trigger ordinal, source EntityId, decl index)` — never arrival order, or replay diverges across nodes.
2. Each cascade level needs its own RNG coordinate; `role_rng` currently keys on `(seed, actor, action_idx, role)` with no depth term, so two triggers at different depths in the same action **collide on one stream** and correlate rolls that must be independent — the precise failure `combat.rs:9-21` was written to prevent.
3. Termination must be a *declared, observable* budget (emit `TriggerBudgetExhausted`), not a silent drop — a silent drop is B2's failure mode again.

Also inside B3: "+50% damage while at full life" is the single most common ARPG affix shape and there is nowhere to evaluate it per-hit.

---

#### 3 · Where this architecture is **better** than the genre

1. **Percent-sums is where D4 ended up after shipping the mistake.** D4 launched with fully multiplicative Crit/Vulnerable buckets, watched damage inflate, and in Season 2 moved additional Crit/Vulnerable/Overpower sources into the *additive* pool. D3 needed a full number-squish for the same reason. This design starts at the answer.
2. **Integer determinism is the professional choice, not a handicap.** FFXIV ships `⌊200(CRIT−420)/2780+50⌋/1000`; WoW ratings are integers; D2's breakpoints are integer frame quantization. The difference is that D2's quantization is an *accident* of a 25 fps renderer, while here it's uniform and intentional.
3. **Replay is possible at all.** None of PoE, D2, D4, GD, or LE can replay a fight. Per-`(actor, action_idx, role)` RNG derivation — rather than a sequential stream — means adding loot, ailments, or crafting rolls doesn't renumber history. That is strictly stronger than anything in the genre.
4. **Players could actually see their own numbers.** Path of Building exists as a third-party project because PoE cannot tell you your real DPS. A resolved dense `StatBlock` plus a `StatEpoch` staleness tuple makes the true resolved value a first-class, inspectable artifact.
5. **Encounter termination is guaranteed by construction.** D2's Hell-difficulty immunities meant certain monsters were literally unkillable without specific `-resist` gear. `max(1, …)` plus the 50/950 hit clamps make that state unreachable. Keep this — it is worth more than fidelity to PoE's resist model.
6. **The order of operations is one function.** PoE's is community-reverse-engineered and still disputed on its own forums.
7. **Ruleset/content split with a digest in every event** is stronger than any of these games, where league mechanics are engine releases.

---

#### 4 · Extension points that fix the breaks *without* abandoning closed sets or the dense array

**E0 (prerequisite) — widen intermediates to `i128`, replace `saturating_mul` with a declared cap.**
128-bit integers are float-free and bit-exact, so no axiom moves. Define `MAX_HIT` as a ruleset constant and clamp explicitly at emit; a *declared* cap is inspectable and replayable, a saturating multiply is an accident. Measure the hot path — a 128-bit multiply is a few ns on x86-64, well inside the 176–229 ns step. **Do this before E1–E3; each adds a ×1000 factor.**

**E1 — Closed `Element` set (8 ordinals) + `DamagePacket = [i64; 8]`.**
`StatBlock` grows `[i32;10] → [i32;26]` (10 base + 8 `Resist` + 8 `Pen`) — 104 bytes, still ordinal-indexed, still ~1.42 ns per access. The 88× HashMap argument is untouched. Authors project their cosmology onto the 8 ordinals with i18n labels, exactly as `StatSlotDecl` projects kinds onto slots. Ruleset declares which ordinals are `physical_like` (armour applies) — that resolves B1's armour-ordering problem *inside* the locked step order. One `max(1)` on the sum, one floor at emit.

**E2 — Conversion as a COLD 8×8 lower-triangular matrix pinned in `StatSnapshot`.**
The key insight: PoE conversion applies to the *skill's base* before scaling, so it is a property of `(actor, ability)`, not of the hit. Resolve it at snapshot time; the hot path does one matrix apply producing the packet. Lower-triangular in element ordinal order *is* the Phys→Light→Cold→Fire→Chaos law, structurally. Over-100% normalization (PoE's "conversions over 100% are scaled back") happens cold. **Provenance is solved for free**: "converted physical still receives physical modifiers" becomes a cold computation over the source column's modifier set — so damage packets need no tag sets at hit time. **The locked 4-step chain does not change; its input becomes a packet instead of a scalar.**

**E3 — `MultBucket`: closed, LOCKED-order multiplicative buckets on the *hit*.**
```rust
enum MultBucket { Support, Keystone, Situational, Ailment, Less }  // engine-closed, order LOCKED
```
Sum within a bucket, multiply across buckets, one final division by `1000^k` in i128. DF7-A5 is preserved *verbatim* — it governs stat-slot percent, and buckets live in the damage chain, a separately-axiomatised layer. This is D4's bucket model with PoE's naming: proven to give build depth without the exponential spiral, because the bucket count is small and closed. **Bonus:** the `Less` bucket is the only construct that lets a Lex world-rule nerf survive arbitrary stacking. Right now a Lex *clamp* is inescapable but a Lex *percent* is just another addend that +2000% of equipment drowns — a real hole this closes.

**E4 — `PowerTerm` on `StatusApply` + an explicit `StackRule`.**
```rust
StatusApply { flag, magnitude: PowerTerm, duration_rounds: u8, stack: StackRule }
enum StackRule { Refresh, HighestWins, Independent { cap: u8 } }
```
`PowerTerm` is the mechanism ABL-Q3 already invented for exactly this problem ("an ability changes damage without emitting a number"). Reusing it means ailments never bypass the law-chain, satisfying ABL-V9. `Refresh`/`HighestWins` covers PoE ignite, `Independent{cap}` covers poison and LE stacks. A DoT tick routes through a reduced chain (no hit roll, no armour, resist+pen apply) under a new `SeedRole::Ailment` — `combat.rs:20` already licenses adding a role without disturbing existing ones. **Record the bend honestly: PoE's unbounded poison stacking becomes a declared cap.** The cap is what keeps the island step bounded, and that trade is correct.

**E5 — `CombatTrigger`: closed event vocabulary + a bounded, observable cascade.**
```rust
enum CombatTrigger { OnHitDealt, OnHitTaken, OnKill, OnCrit, OnBlock, OnStatusApplied }
```
A trigger fires an existing `EffectOp` list — adds **no new effect substrate**, which is precisely ABL-A2's discipline. Determinism: resolve in `(trigger ordinal, source EntityId, decl index)`; extend `role_rng` to `(seed, actor, action_idx, cascade_depth, decl_idx, role)` — without the depth term, two triggers in one action collide on a stream. Termination: a per-action `cascade_budget: u8` (≈8) decremented across the whole cascade, emitting `TriggerBudgetExhausted` on exhaustion. Leech becomes `OnHitDealt → VitalRestore{ PowerTerm::PctOfDamageDealt }` plus a per-round rate-cap slot (PoE's model, turn-quantized).

**E6 — `ModifierGuard`: conditional affixes, split by when the condition can change.**
A distinct closed predicate set (do **not** overload `Precondition` — that's an admission gate; conflating them is the ABL-Q9 defect pattern). Equipment-stable guards ("while wielding a sword") resolve cold into the snapshot at zero hot cost; only target/self-state guards ("while at full life", "vs bleeding") evaluate per hit, and those are a small minority.

**E7 — Two constants worth changing now.**
`action_value`'s numerator `10_000 → 1_000_000` (digest-pinned) un-caps tempo scaling at trivial cost. And `roll_band_pm = 850 + roll_pm*300/1000` yields 850..1149, never 1150 — mean ≈ 0.9996× rather than 1.000×, a permanent ~0.05% DPS shortfall. Use `roll_pm*301/1000` or an explicit inclusive range.

**E8 — The general principle: the ruleset digest already gives you law *versioning*.**
"Order LOCKED for all future versions" is stricter than the architecture requires. Because a `RulesetDigest` is pinned into every event, two law variants can coexist and old events replay under the law they were committed with:
```rust
enum MitigationLaw { Subtractive, Ratio { k: i32 } }   // selected by ruleset, pinned by digest
```
That is how B3's subtractive-armour cliff gets fixed to a PoE/D3-style ratio curve **without breaking a single historical replay**. Treat "locked" as "locked *per digest*", not "locked forever" — it is the escape hatch the design already paid for and hasn't spent.

---

**Bottom line:** the closed-set/dense-array core is genuinely sound and in two places (percent-sums, integer determinism) ahead of shipped AAA practice. What actually breaks is narrower than it looks: **the damage value is a scalar** (B1), **the arithmetic has ~1.6M of headroom and fails silently** (B2, live today), and **there is no trigger substrate** (B3). E0–E2 fix B1/B2 while leaving the 4-step order literally unchanged, because conversion is a cold property of the actor+ability, not a hot property of the hit — that single reframing is what saves the locked chain.

**Sources:** [PoE Damage Conversion (Fandom)](https://pathofexile.fandom.com/wiki/Damage_conversion) · [PoE 2 Damage Conversion (Mobalytics)](https://mobalytics.gg/poe-2/guides/damage-conversion) · [PoE Damage for Beginners (Maxroll)](https://maxroll.gg/poe/getting-started/damage-for-beginners) · [PoE 2 Damage Scaling (Maxroll)](https://maxroll.gg/poe2/getting-started/damage-scaling) · [PoE Resistance Penetration (Fandom)](https://pathofexile.fandom.com/wiki/Resistance_penetration) · [PoE 2 Penetration (Mobalytics)](https://mobalytics.gg/poe-2/guides/penetration) · [PoE Ailment (Fandom)](https://pathofexile.fandom.com/wiki/Ailment) · [PoE 2 Ailments (Mobalytics)](https://mobalytics.gg/poe-2/guides/ailments) · [PoE Leech (Fandom)](https://pathofexile.fandom.com/wiki/Leech) · [PoE Armour (Fandom)](https://pathofexile.fandom.com/wiki/Armour) · [PoE 2 Armour (Mobalytics)](https://mobalytics.gg/poe-2/guides/armour) · [D4 Damage Buckets (Mobalytics)](https://mobalytics.gg/diablo-4/guides/damage-buckets-deep-dive) · [D4 In-Depth Damage Guide (Maxroll)](https://maxroll.gg/d4/resources/in-depth-damage-guide) · [Grim Dawn Game Mechanics wiki](https://grimdawn.fandom.com/wiki/Game_Mechanics) · [Grim Dawn Resist Reduction Guide](https://gamefaqs.gamespot.com/pc/671567-grim-dawn/faqs/78675) · [Last Epoch Ailment Mechanics (official)](https://support.lastepoch.com/hc/en-us/articles/46361901350043-Ailment-Mechanics) · [Last Epoch Damage Explained (Maxroll)](https://maxroll.gg/last-epoch/resources/damage-explained) · [FFXIV Crit stat tables (AkhMorning)](https://www.akhmorning.com/allagan-studies/stats/crit/) · [D2R Breakpoints & Animations (Maxroll)](https://maxroll.gg/d2/resources/breakpoints-animations) · [WoW Combat Rating System (Warcraft Wiki)](https://warcraft.wiki.gg/wiki/Combat_rating_system) · [WoW Secondary Stat DR (Wowhead)](https://www.wowhead.com/guide/diminishing-returns-on-secondary-stats-in-world-of-warcraft)

---


<a id="immersive"></a>

## Immersive sims / colony sims — the open-ended-modding test

*Distilled into doc 27 §5.3. Verbatim below.*

### Extensibility Stress Test — Immersive Sims / Colony Sims / Heavily-Modded Emergent Systems

#### What I verified

I researched the genre's real data architectures (sources at the bottom) and then grounded every verdict against the **actual code**, not the prose spec:

- `d:\Works\source\lore-weave-game-foundation\services\commit-service\src\stats.rs` — `StatSlot` is `#[repr(usize)]` with hard-coded ordinals `MaxHp=0 … MoveRange=9`, `SLOT_COUNT: usize = 10`, `pub struct StatBlock([i32; SLOT_COUNT])`. `ModifierSource { Base, Archetype, Progression, Equipment, Status, Lex }` — Lex last, "inescapable". `ModifierOp { Flat(i32), Percent(i32) }` per-mille, summed. The doc comment states the honest cost: *"Extending the set is an engine release plus a boundary-matrix registration."*
- `d:\Works\source\lore-weave-game-foundation\crates\sim-core\src\types.rs` — `Precondition<D: Domain>` has exactly 5 variants: `EntityAlive, EncounterActive, ActorEligible, ResourceAtLeast, IslandOwns`. Note the kernel is generic over a `Domain` trait with associated `ResKind`/`Payload`/`Event` — a **compile-time** extension seam, not a data-time one.
- `d:\Works\source\lore-weave-game-foundation\services\tilemap-service\src\registry.rs` — a precedent that matters: the tilemap registry already validates ids against `^[a-z][a-z0-9_:.-]*$` (namespacing with `:` already allowed) and deliberately uses `BTreeMap` not `HashMap` for iteration determinism.

The single most load-bearing observation: **`StatSlot` is a Rust enum, so the slot set is a property of the binary, not of the ruleset.** Everything below flows from that.

---

#### 1 · Verdict table

| # | Proposed quantity / mechanic | Verdict | Absorbing mechanism, or the axiom it breaks |
|---|---|---|---|
| 1 | **Material with DF's ~28–30 numeric properties** (6 force types × yield/fracture/strain, melting/boiling/ignite/heatdam/colddam/spec_heat, density) | **SURVIVES** | Materials are Content. A `MaterialDef` side-table is projected into `StrikePower`/`Armor` + an element id by `StatSlotDecl` at cold path. Nothing touches the hot array. |
| 2 | **Pairwise material-vs-material dispatch** (DF: steel maul vs iron plate → blunt path *dents*; steel sword vs same → shear path *fails*) | **BREAKS** — A5 (damage chain) | `max(1, sp − armor) × elem_mult × (1−resist) × roll × crit_mult` has exactly one channel for material identity (`elem_mult`) and it's a property of the *attacker* alone. There is no seat for a function of (attacker_mat, defender_mat). DF's combat is a materials solver; this is a formula. |
| 3 | **Per-element resistance vector** (add acid / psychic / warp / bleed) | **BENDS → BREAKS** — A1 in spirit | `resist` is in the damage chain but *not among the 10 slots* (only `Armor` is). So resists already live in an unbounded side map. The chain smuggles a HashMap-shaped thing in through the back door while the stats layer forbids one. Inconsistent. |
| 4 | **Per-limb HP / wounds** (DF tissue trees; RimWorld `BodyPartRecord`; Kenshi's 6-part "combat anatomy") | **BREAKS** — A1 + A2 | One `MaxHp` slot. Worse than the storage problem: RimWorld recomputes `PawnCapacity` (tag-weighted aggregation over parts) **on every hediff change**, i.e. every strike. `StatSlotDecl` resolves at *cold* path. See BREAK 1. |
| 5 | **Capacities as an intermediate layer** (Consciousness/Moving/Manipulation → derived stats) | **SURVIVES structurally, BREAKS on cardinality** | RimWorld's `CalculateTagEfficiency` is *literally* `base + Σ(weight_i × term_i)` with a lerp and a cap — the same shape as `StatSlotDecl { base, terms, clamp }`. The math is already right. There is simply nowhere to *put* 11 capacities. |
| 6 | **Infection / disease with continuous severity + stages** (RimWorld hediff; DF syndrome) | **BENDS** | Survives only if `StatusFlag` carries per-instance `severity` + `expiry` + `stacks`. If it is a pure bitflag (name says flag), it breaks: no stage selection, no progression, no "severity 0.31 → stage 2". |
| 7 | **Prosthetics / bionics** (RimWorld `partEfficiency` 1.25; Kenshi robot limbs) | **BENDS** — A4 | Equipment-flat layer absorbs *storage*. But `partEfficiency` is **multiplicative on a part**, and A4 says percents sum. Two 200%-efficiency bionics should not yield +200%; they should yield a per-part product then a capacity aggregation. Summing gives the wrong number, not just a different one. |
| 8 | **Needs / mood / thoughts** (RimWorld mood = Σ thought offsets with `stackLimit`+`durationDays`; DF facets, values, needs, 3-tier memory) | **BREAKS by omission** — A1 | The *mechanism* is perfect — Σ weighted terms + clamp is exactly `StatSlotDecl`. The *slot set is combat-only*. There is no Mood, no Focus, no Stress, no Sanity, no Stealth. This is the cleanest proof that the problem is the **closed-in-code** part, not the **closed** part. |
| 9 | **Personality drift** (DF: a memory's emotion changes over time and permanently alters facets/values) | **BREAKS** — A2 | The *term weights themselves* mutate during play. `StatSlotDecl` treats the projection as an authored constant. |
| 10 | **Social relationships / opinions** (N² pairwise, DF + RimWorld) | **BREAKS** — A1 + A7 | An opinion is a property of an *edge*, not a node — it cannot live in a per-entity dense array. And with one entity per island, A and B are routinely in different islands; the edge has no single writer. |
| 11 | **Crafting / recipes with arbitrary reagents** (Factorio `data.raw`, Minecraft datapacks, DF `[REACTION_CLASS:whatever]`) | **SURVIVES** — best case | Pure Content. Reagent matching is a cold-path set query, touches zero slots. Factorio's data-stage/control-stage split is the *same architecture*, independently arrived at, and it's what makes Factorio's lockstep determinism possible. |
| 11b | **Reactions that derive their product's material from the input's** ("ask the material for details") | **BENDS** — A8 | Produces *generated* content at runtime with no authored id. Ruleset/Content assumes content is authored and digest-stable. Generated content needs a deterministic derived-id scheme or the digest becomes meaningless. |
| 12 | **Skill system at DF scale (~100 skills)** | **SURVIVES** | Skills are a progression side-table; only their *projection* enters slots. This is the extension mechanism working exactly as designed — the best advertisement for it. |
| 13 | **Encumbrance / carry weight → Speed** | **BENDS** — A2 | Correct in shape, but inventory changes on every pickup, so "cold" resolution runs at play tempo. Same root cause as #4. |
| 14 | **Temperature / gas / fluid / light as continuous fields** (ONI's per-cell element sim, DTU/(m·s)/°C, transfer rate gated by the *lower* conductivity of the pair) | **BREAKS** — A7 | Sub-island spatial resolution, ~5–20 Hz, deterministic, durable, and *cross-island coupled*. Class A is 20 Hz but not event-sourced; Class C is minutes-scale; Class B is turn-based. The field sim falls in the gap between all three. See BREAK 2. |
| 15 | **Emergent chain the engine never enumerated** (DF: contact material → syndrome → `CE_CAN_DO_INTERACTION` → `[CDI:…]` emits a *new* material → …) | **BREAKS** — A6 | "Grant an ability" is not one of the 9 `EffectOp`s, and the action set is closed at 4. In DF this is ~30 lines of raws and zero engine change. Here it is an engine PR. See BREAK 3. |
| 16 | **Multi-entity chemistry within an encounter** (grease + spark; fire spreads) | **SURVIVES (in-island)** | Single-writer island is genuinely the right substrate for local pairwise interactions — better than DF's global single thread. Breaks only at island boundaries. |
| 17 | **Total conversion** (Enderal-scale: new world, lore, leveling, perks) | **BENDS** | Ruleset+Content can retune *everything within* the 10 slots and the locked chain. It cannot change the *shape* of reality. That is a total **reskin**, not a total conversion. Roughly Factorio-level moddability; short of Skyrim's (Enderal replaced the whole leveling system), far short of DF's or Qud's. |

---

#### 2 · The three most dangerous BREAKS

##### BREAK 1 — The cold/hot boundary is drawn by *authoring time*, but the genre needs it drawn by *change frequency*

`StatSlotDecl` is "resolved at COLD path into the dense array the hot path indexes." That is correct only if the terms are stable during play. **In every game I researched, they are not.**

**Concrete scenario.** A raider takes a bolt to the left leg.
- *RimWorld*: `leg.HitPoints` drops → `CalculatePartEfficiency` returns `hp/maxHp` → `CalculateLimbEfficiency` multiplies the leg core by its segments and lerps in the digit efficiency by `appendageWeight` → `CalculateTagEfficiency` does a weighted average over parts tagged `MovingLimbCore`, biased by `bestPartEfficiencySpecialWeight` → `Moving` capacity falls → `MoveSpeed` stat falls. Below 15% Moving the pawn is downed. **This whole cascade runs on the damage event.**
- *Here*: there is no leg. If you add one (EP-4 below), its efficiency becomes a `StatSlotDecl` term — and the "cold" resolution must now run **mid-encounter, on a hot event**.

This is not a perf problem. Re-projecting 10 slots × K terms is tens of nanoseconds; you have a 176–229 ns island-step budget. It is an **architectural-claim** problem: the dense array is justified by "the hot path only ever indexes; resolution is cold," and the moment wounds, encumbrance, hediff severity ticks, or drug metabolism become terms, that justification is false and nobody has budgeted for the re-resolution.

The same root cause produces rows #4, #9, #13 in the table. It is one bug, not three.

**Danger rating: highest**, because it is invisible until you build the first system that needs it, and by then the "cold path" invariant has silently rotted into "the path that runs whenever, unbudgeted."

##### BREAK 2 — Continuous fields have no home in the island taxonomy, and the handoff primitive actively fights them

Islands are shared-nothing, single-writer, one-entity-per-island, with an explicit *extract portable state → install* handoff for crossing.

**Concrete scenario.** The player breaches an aquifer in a mine (ONI/DF's signature moment). Water flows down three z-levels across, say, 30 cells = 30 islands. Per tick, every boundary between wet and dry cells must move mass and enthalpy. Under the current model, each transfer is a cross-island message or an entity handoff. At 10–20 Hz across 30 boundaries, **the cross-island messaging channel stops being an occasional coordination primitive and becomes the simulation itself** — which is precisely the "no global mutable state" property islands were built to buy.

It gets worse in two directions:
- Water isn't an entity, so "one entity in exactly one island" has nothing to say about it, and mass conservation across the handoff is not something the handoff primitive guarantees.
- Event-sourcing a 10⁵-cell lattice at 10 Hz is not viable. Klei's answer was to lift the element sim out into a separate native `SIM` library on its own thread with its own fixed tick — an explicit admission that field sim is a *different kind of thing* from entity sim.

Attempting to fake this — "temperature is an island-scoped scalar that sets a `Freezing` StatusFlag" — gives you a temperature nobody believes: no gradients, no per-tile, no *transfer* (my forge doesn't heat the room), and no cross-island coupling (the burning tavern doesn't warm the street).

**Danger rating: high**, because the failure mode is to ship the fake version, discover it's not believable, and then find the island model can't be retrofitted.

##### BREAK 3 — A closed op vocabulary caps emergence at *recombination*, and this genre's entire value proposition is *combination the designer never wrote*

DF's canonical modding chain: a material carries a syndrome; contact confers it; the syndrome's `[CE_CAN_DO_INTERACTION]` grants the victim an interaction; `[CDI:…]` with `[I_EFFECT:MATERIAL_EMISSION]` makes that interaction *emit another material*, which can carry another syndrome. Tarn Adams never wrote "hemolymph-spraying zombie." A modder assembled it from orthogonal primitives.

**Concrete scenario.** A modder adds `hemolymph`: on contact, the victim gains the ability to spray hemolymph. Cost in DF: ~30 lines of raws, zero engine change. Cost here: `EffectOp` has 9 variants and none of them is "grant an action"; the action set is `{strike, defend, move, flee}` and is closed; `Precondition` has 5 variants and **not one of them can ask a content-authored question**. The modder's only recourse is an engine pull request.

That is the thing that kills modded ecosystems — the platform becomes the bottleneck and the long tail never gets built. Skyrim survived it only because it shipped `KYWD`.

Note the closed vocabulary is currently doing *two* jobs — replay determinism *and* LLM tool-safety — and conflating them is what makes it look non-negotiable. They separate cleanly (EP-7).

**Danger rating: high but slow.** Nothing breaks on day one. It shows up as "why does every content request need an engine release," eighteen months in.

---

#### 3 · Where this architecture is *better* than the genre

These are not consolation prizes. Several are things the genre has repeatedly failed to solve.

1. **Determinism is actually achieved, not aspired to.** i64 milli-units, no float, digest-pinned ruleset in every event. DF saves are not replayable and its behavior shifts between builds. RimWorld's multiplayer mod has fought float/`Rand`-state desync for years. Only **Factorio** is in the same class, and it got there the same way: fixed-point integers, prototype data frozen before the control stage, lockstep on inputs only. Being independently in Factorio's category is a strong result.
2. **The ruleset digest in every event solves the genre's #1 pathology.** Skyrim's classic failure: two mods create `KYWD` records with the same EditorID and different FormIDs; only one registers; the other's items **silently malfunction**. Same bug class in Minecraft datapack conflicts, in RimWorld def conflicts, in load-order-dependent Factorio `data-final-fixes`. None of them solved it. Digest-pinning makes "which reality produced this event" a first-class, verifiable fact.
3. **Σ-percent makes mod composition commutative.** This is underrated. RimWorld `StatWorker` ordering and Skyrim perk-entry-point ordering both produce "mod A before mod B gives a different number," which is unfixable-by-construction and generates endless patch mods. Order-independence is precisely the algebraic property a multi-author ecosystem needs, and the design has it by axiom.
4. **Single-writer islands beat DF's global single thread.** DF's FPS death is structural — one thread, one world. ONI had to extract its sim to a native lib. Islands give per-encounter parallelism with no lock and no shared state, from day one.
5. **Proposal → validate → commit beats direct mutation.** Papyrus scripts mutate game state directly, which is the source of Skyrim's save-game bloat, orphaned scripts, and "dirty save" folklore. A validated proposal boundary is strictly better engineering *and* is the only thing that makes an LLM driver safe.
6. **A measured, published perf budget.** 176–229 ns/island-step, ~4 ns precondition, 5.4 ms durable commit, 125.78 ns HashMap vs 1.42 ns array field. Nobody in this genre publishes one. DF's entire reputation is "it gets slow and nobody knows exactly why." The budget is the thing that will let you say *no* to a bad extension with evidence rather than taste.
7. **The `Lex` layer applied last and inescapable** is a genuinely good idea with no genre equivalent — it gives world rules a guaranteed final word, which Skyrim (where any mod can outrank any other) and RimWorld (where Harmony patches can rewrite anything) both lack.

---

#### 4 · Extension points that fix the BREAKs without abandoning closed sets or dense arrays

Everything below preserves: dense ordinal-indexed arrays, no HashMap on the hot path, no floats, closed vocabularies, digest-pinned determinism.

##### EP-1 · Slot-set **versioning**, not slot-set **openness** — the single highest-value change

Keep the array dense; move `SLOT_COUNT` from a *language* constant to a *ruleset* constant.

- The ruleset declares an ordered **slot manifest**; the digest covers it; slot ordinals are assigned by the manifest, never by load order.
- Representation: `[i32; MAX_SLOTS]` with `MAX_SLOTS = 32` (or 64) and a live count, or a const-generic `StatBlock<const N: usize>`. Hot access becomes a bounds-checked index into a fixed array: **~1.5–2 ns vs the measured 1.42 ns direct field, vs 125.78 ns HashMap.** The 88× argument is entirely preserved.
- This buys rows #5 (capacities), #8 (mood/focus/stress/stealth/sanity), and most of #17 (total conversion) in one move.
- It converts "closed enum" (a fact about the binary) into "closed set per ruleset" (a fact about data) — which is what **Skyrim** does at the record-type level and **Factorio** does at the prototype level. The closed-ness that buys determinism is *cardinality bounded + ordinals pinned*, not *declared in Rust*.

The current doc comment — *"Extending the set is an engine release plus a boundary-matrix registration"* — is an accurate description of a cost that does not need to be paid.

##### EP-2 · A keyword/tag mechanism — **yes, and it is cheaper here than in Skyrim**

**Does the design have a KYWD equivalent today? No.** The nearest thing is `kind_id` inside `StatSlotDecl.terms`, but that is a *projection weight source*, not a *queryable predicate*. Skyrim's keywords work because **hardcoded systems interrogate them** — the engine asks "does this have `VendorItemWeapon`?" Our engine has 5 preconditions and not one of them can ask a content-authored question. That is the gap.

**Should it? Yes** — but implemented as interned bitsets, not Skyrim's FormID arrays.

Design:
- Authors declare `TagDef { id }` in the ruleset, namespaced (`mod_id:tag`) — the `^[a-z][a-z0-9_:.-]*$` pattern already in `tilemap-service/src/registry.rs` accepts this. Minecraft's namespaced resource locations prove this defuses the collision problem.
- Cold path interns all ruleset tags into ordinals `0..T-1`, **T bounded (256) and pinned by the ruleset digest**. Unknown tag in content = hard load error, never a silent no-op.
- Each entity / item / material / body-part carries `TagSet = [u64; 4]` (256 bits, 32 bytes).
- `Precondition` gains **one** variant: `HasTags(TagMask)`. Still a closed set (6 variants). Still LLM-safe — the driver picks a tag from a *runtime-enumerable registry*, which is exactly the closed-set-arg discipline this repo already enforces for frontend tools.
- Predicates ("weapon is any of {Blunt, Edged}") are compiled to a mask at cold path. The LLM and the script never see a string at runtime.

**Hot-path cost, concretely:**

| Operation | Cost | Reference point |
|---|---|---|
| `has_tag(t)` — one `u64` load at `t>>6`, shift, AND, test | **~1–2 ns** | direct array field = 1.42 ns |
| `matches_any(mask)` — 4 ANDs + OR-reduce + test | **~2–3 ns** | precondition budget = ~4 ns |
| String→ordinal lookup at runtime | **never happens** | HashMap = 125.78 ns |
| Extra cache footprint | 32 B, adjacent to the 40 B `StatBlock` → both fit in 2 lines | island step = 176–229 ns |

This is the *same trick* as the dense stat array, applied one level up: dense ordinals instead of strings. It strengthens the perf argument rather than eroding it. Skyrim's version is a linear scan over a `KWDA` FormID array evaluated in per-frame `CTDA` conditions — we get the same expressive power at roughly an order of magnitude less cost, because we have a cold path Bethesda doesn't.

**The two non-negotiable disciplines:**
1. **Tags are membership, never values.** `Flammable` yes; `melting_point=1811` never. Values live in typed side-tables keyed by ordinal (EP-3). Violating this is how a tag system degenerates into the property-bag HashMap the architecture correctly rejected.
2. **Ordinals come from the digest, not from load order.** If they don't, you reproduce Skyrim's EditorID/FormID collision — but instead of a broken sword you get *silent replay divergence*, which is far worse. This is the real cost of tags, and it is a correctness cost, not a nanosecond cost.

DF independently invented this too: `[REACTION_CLASS:whatever]` is an arbitrary author-defined tag on a material that reactions query to accept "any reagent of this class." Two of the three most-modded games in the genre converged on the same escape hatch. That is strong evidence it is the right one.

##### EP-3 · Typed side-tables + an explicit, budgeted **reprojection** step *(fixes BREAK 1)*

- `MaterialDef`, `BodyPlan`, `SkillSet`, `NeedSet` live in dense typed arrays **outside** `StatBlock`, each with its own ordinal space. `StatSlotDecl.terms` may reference them.
- Add a dirty mask + an event-sourced `Reproject { dirty_slots }` step so replay is exact.
- Redefine "cold path" as **"resolved from a declaration"**, not **"never runs during play"** — which is what it needed to mean all along. Then *measure* it: a 10-slot × 16-term reprojection is tens of ns and fits inside the 176–229 ns step with room to spare. The point is that it becomes a **budgeted, visible** cost instead of an invariant quietly rotting.

##### EP-4 · Body plan as a **bounded** closed set *per ruleset* — Kenshi's storage, RimWorld's math *(fixes #4, #5, #7)*

- Ruleset declares `BodyPlanDef { parts: [PartDef { id, parent, max_hp, tags, coverage }] }`, bounded at ≤64 parts → per-entity part HP is `[i16; 64]`, dense, no allocation.
- Capacities are computed with RimWorld's exact algorithm: per-part efficiency = `hp/max_hp` (+ prosthetic `partEfficiency` override), limb efficiency = product down the chain with appendage lerp, capacity = **tag-weighted aggregate over parts matching a tag** with a best-part bias, lerp, and cap.
- Capacities become slots via EP-1. Part tags come from EP-2. Wound → dirty → reproject via EP-3.
- Prosthetic multiplicativity (#7) resolves correctly here because the multiply happens *at the part layer*, before the Σ-percent layer — A4 stays intact and the number comes out right.

Kenshi is the proof this is enough: a fixed per-race "combat anatomy" (max limb health + hit chance per limb) delivers a beloved dismemberment/prosthetics system with a closed body plan.

##### EP-5 · Status **instances**, not flags *(fixes #6)*

`StatusInstance { flag_ordinal: u8, severity_milli: i32, stacks: u8, expires_at_tick }` in a bounded per-entity array (≤32), with a derived `StatusFlag` bitmask maintained alongside for the ~1 ns hot check. The bitmask stays the fast path; the instance array is the authority. This buys RimWorld hediff stages, DF syndrome severity, and RimWorld thought `stackLimit`/`durationDays` — all three at once.

##### EP-6 · **Class D** — a deterministic field lattice *(fixes BREAK 2)*

Field simulation is not an entity system and should stop pretending to be one.

- Fixed tick (5–10 Hz), integer lattice, its own class alongside A/B/C.
- **Domain-decomposed to align with island/cell boundaries, with ghost-cell halo exchange at tick boundaries only.** This is textbook domain decomposition and it *preserves single-writer-per-tile* — no entity handoff, no cross-island message storm. It is the correct answer to the aquifer scenario.
- Durability by periodic checkpoint + tick seed, **not** per-cell event sourcing.
- Entities *read* the field (ambient temp, gas concentration at my tile) as reprojection inputs at a coarse cadence; entities *write* via a small bounded set of source/sink ops.

This is a real new subsystem, not a patch — but it is the honest answer, and ONI's separate `SIM` library is direct precedent that the split is correct rather than an admission of defeat.

##### EP-7 · Reserve the seam for a sandboxed rule hook — argue against it now, but don't foreclose it

The closed `EffectOp` set is doing two jobs, and they separate:
- **LLM safety** needs the *proposal* vocabulary closed. Keep it closed forever.
- **Replay determinism** needs *resolution* to be deterministic — which does **not** require it to be hardcoded in Rust.

A digest-pinned, fuel-metered, integer-only mini-VM evaluated at **cold path only** would let authors express `StatSlotDecl` terms and reaction outcomes the engine never enumerated, while the hot path stays a pure array read and the LLM's tool vocabulary stays closed. That would fully close BREAK 3.

My recommendation: **not in v1** — a deterministic VM with fuel accounting folded into the digest is a serious build. But **reserve the seam now**: make `StatSlotDecl.terms` an enum whose future variant is `Computed(program_ref)`. Retrofitting that later is a wire-format break; adding the variant now is free.

##### What I would deliberately *not* fix

- **Row #2 (pairwise material dispatch).** Making the damage chain a function of both materials would unlock DF-grade combat, but the locked 4-step chain is the thing that makes damage auditable, LLM-explainable, and replay-stable. Take the loss knowingly. Recover ~70% of the flavor cheaply via EP-2: tag-gated `elem_mult` lookup (`attacker has Blunt` ∧ `defender has Rigid` → a table entry), which is a bounded 2-D table, not a solver.
- **Row #10 (relationships).** These belong in a Class C batch store outside `StatBlock` with a designated owning shard per edge. Do not try to make islands hold them.
- **Row #17.** Accept "Factorio-level total conversion," and say so explicitly in the docs. Promising DF-level moddability and delivering reskins is worse than promising reskins.

---

##### Sources researched

- [Dwarf Fortress Wiki — Material definition token](https://dwarffortresswiki.org/index.php/DF2014:Material_definition_token) · [Modding](https://dwarffortresswiki.org/Modding) · [Inorganic material definition token](https://dwarffortresswiki.org/index.php/DF2014:Inorganic_material_definition_token) · [Syndrome](https://dwarffortresswiki.org/index.php/DF2014:Syndrome) · [Reaction](https://dwarffortresswiki.org/index.php/DF2014:Reaction) · [Interaction examples](https://dwarffortresswiki.org/index.php/DF2014:Interaction_examples) · [Thoughts and preferences](https://dwarffortresswiki.org/index.php/DF2014:Thoughts_and_preferences) · [Memory (thought)](https://dwarffortresswiki.org/index.php/DF2014:Memory_(thought))
- [RimWorld — `PawnCapacityUtility.cs` (decompiled)](https://github.com/josh-m/RW-Decompile/blob/master/Verse/PawnCapacityUtility.cs) · [Hediffs](https://rimworldwiki.com/wiki/Hediffs) · [Capacity](https://rimworldwiki.com/wiki/Capacity) · [Consciousness](https://rimworldwiki.com/wiki/Consciousness) · [Manipulation](https://rimworldwiki.com/wiki/Manipulation) · [Body Parts](https://rimworldwiki.com/wiki/Body_Parts) · [Def Types](https://rimworldmodding.wiki.gg/wiki/Def_Types)
- [Skyrim Mod File Format — KYWD (UESP)](https://en.uesp.net/wiki/Skyrim_Mod:Mod_File_Format/KYWD) · [Injected Record Registry (CK Wiki)](https://ck.uesp.net/wiki/Injected_Record_Registry) · [Injected Record Dev Reference ESPs](https://www.nexusmods.com/skyrimspecialedition/mods/47423) · [Creation Kit Keywords guide](https://d3timer.com/skyrim-creation-kit-keywords-the-complete-guide-to-mastering-custom-content-in-2026/) · [Enderal](https://en.wikipedia.org/wiki/Enderal)
- [Factorio — Data lifecycle](https://lua-api.factorio.com/latest/auxiliary/data-lifecycle.html) · [Desynchronization](https://wiki.factorio.com/Desynchronization) · [Modding tutorial](https://wiki.factorio.com/Tutorial:Modding_tutorial/Gangsir)
- [Minecraft Forge — Tags](https://docs.minecraftforge.net/en/1.18.x/resources/server/tags/) · [Datapack Registry Object Providers](https://docs.minecraftforge.net/en/latest/datagen/server/datapackregistries/) · [Data pack (Minecraft Wiki)](https://minecraft.wiki/w/Data_pack) · [Data Attributes mod](https://www.curseforge.com/minecraft/mc-mods/data-attributes)
- [Oxygen Not Included — Thermal Conductivity](https://oxygennotincluded.wiki.gg/wiki/Thermal_Conductivity) · [Elements DB](https://oni-db.com/explore/elements)
- [Caves of Qud — Modding: Objects](https://wiki.cavesofqud.com/wiki/Modding:Objects) · [Modding: Active Parts](https://wiki.cavesofqud.com/wiki/Modding:Active_Parts) · [Modding: Compatibility](https://wiki.cavesofqud.com/wiki/Modding:Compatibility)
- [Kenshi — How to make custom robotic limbs](https://kenshi.fandom.com/wiki/How_to_make_custom_robotic_limbs) · [Robot Limbs](https://kenshi.fandom.com/wiki/Robot_Limbs)

---


<a id="cultivation"></a>

## Cultivation / idle / prestige — the unbounded-growth test

*Distilled into doc 27 §5.4. Verbatim below.*

### Extensibility Stress Test — Cultivation / Idle / Prestige Domain

I grounded every verdict against the real code, not just the prose spec:
- `d:\Works\source\lore-weave-game-foundation\services\commit-service\src\stats.rs` (the 10-slot enum, `resolve_block`, `saturating_mul`, the i32 emit narrowing)
- `d:\Works\source\lore-weave-game-foundation\services\commit-service\src\combat.rs` (`resolve_attack`, `role_rng`, the 4-step chain, `SeedRole`)
- `d:\Works\source\lore-weave-game-foundation\crates\sim-core\src\types.rs` (`Precondition` — 5 variants)
- `d:\Works\source\lore-weave-game-foundation\docs\03_planning\LLM_MMO_RPG\features\00_progression\PROG_001_progression_foundation.md` (`ProgressionKindDecl`, `CapRule`, `CurveDecl`, `Scheduled:CultivationTick`, the deferred register)
- `...\features\DF\DF07_pc_stats\DF07_001_actor_stat_block.md` (`StatSlotDecl`, `StatTerm`, layer order)
- `...\features\00_resource\RES_001_resource_foundation.md` (`ResourceKind`, `VitalKind`)
- `...\features\19_ability\ABL_001_ability_foundation.md` (`EffectOp` — now 10 variants, `SeverBinding` was added 2026-07-26)

Note up front: a prior **CULT_001 stress-test pre-audit (2026-04-27)** already registered PROG-D33/D34/D36/D37 for dual cultivation, drain, karma-gated breakthrough and rebirth bonuses. Where I overlap I say so; the findings below that are *new* are M2, M5, M8, M14, M15 and the sign-inversion hazard.

---

#### 1 · Verdict table

| # | Mechanic (source game) | Verdict | Mechanism / violated axiom |
|---|---|---|---|
| M1 | **Realm ladder** — Qi Refining → Foundation → Golden Core → Nascent Soul, each realm a step-change (*Tale of Immortal*, generic xianxia) | **BENDS** | `ProgressionType::Stage` + `CurveDecl::Stage` + `CapRule::TierBased` + `StatSlotDecl.terms` carries it. Lossy because the projection `base + Σ(raw × weight)` is **linear in raw_value**, so a ×10-per-realm ladder must be pushed into `raw_value` (u64, ~1.8e19) and then dies at the **i32 slot emit (2.147e9)** — ~7–8 realms of ×10. The canonical 9–12-realm ladder does not fit. |
| M2 | **Realm suppression (境界压制)** — a Nascent Soul cultivator is *categorically* untouchable by a mortal; cross-realm attacks auto-hit, cross-realm defense is absolute | **BREAKS** | Two axioms at once: (a) the **`max(1, sp − armor)` floor** in `resolve_attack` guarantees a mortal always does ≥1 damage, so a mortal army *always* kills an immortal given rounds; (b) `hit_chance_pm = accuracy − dodge` is an **additive per-mille difference clamped 0..1000**, so the minimum expressible hit chance is 1/1000 — you cannot say "0.0001%". There is also **no (attacker, defender) relational term** anywhere in the locked 4-step chain. |
| M3 | **Wuxing generation/destruction cycle** + **Melvor combat triangle** (Wood⊣Earth, Fire⊣Metal…; melee>ranged>magic>melee at ±10%) | **SURVIVES** | Exactly the reserved `elem_mult` step (currently identity 1.0, deliberately kept in the chain so promotion is "filling in a constant"). Implement as a **ruleset n×n per-mille table** indexed by (attack_element, defend_element). The ACS *environment* half (a Fire-law disciple must live in a Wood room) survives separately as `TrainingRuleDecl` + `TrainingCondition::LocationMatch`. |
| M4 | **Spirit roots / talent / destiny** — a birth-rolled multiplier on all cultivation speed (*ACS* spirit roots, *ToI* destinies) | **SURVIVES** | Content + `ProgressionKindDecl { progression_type: Attribute }` + `derives_from: DerivationDecl` (skill ← attribute *training-rate* scaling, already V1). Birth roll is a seeded chargen draw. It never needs a stat slot because it modifies **accrual**, not the resolved block. |
| M5 | **Qi as a spendable pool with a cultivated max** (*ACS*, *NGU Idle* energy/magic caps, any mana system) | **BREAKS** *(reported as BENDS-with-no-good-workaround)* | The *resource* survives (`ResourceKind::Consumable(ConsumableKindId)` is author-declared). The **cap does not**: only `MaxHp` and `MaxStamina` are pool slots, both hardcoded in the closed 10. "+20% max qi from this robe" has **no slot to land in**, so it exits the entire equipment/status/Σ-percent/Lex pipeline. `ProgressionType::ResourceBound` is explicitly deferred (PROG-D31), confirming the hole is known. |
| M6 | **Prestige / rebirth** — *Cookie Clicker* ascension (`floor((cookies/1e12)^(1/3))` heavenly chips), *Realm Grinder* abdication→gems + reincarnation, *NGU* rebirth→EXP, *AD* Infinity/Eternity/Reality | **SURVIVES (reset) / BREAKS (composition)** | The **reset+remap is a strength**: it is one event that zeroes `actor_progression.values` and grants a new kind; replay reconstructs it exactly. `RebirthBonusDecl` is already registered (PROG-D37). What **BREAKS** is **axiom 4 (percent modifiers SUM)**: the genre's core loop is *multiplicative composition across layers*. Two prestige layers each meant to be ×100 give **×199, not ×10,000**. |
| M7 | **Offline / idle accrual of a non-combat skill over days logged out** (*Melvor*, *Realm Grinder* offline production, *AD* catch-up) | **SURVIVES — and beats the genre** | `Scheduled:CultivationTick` (day-boundary Generator) + the **hybrid observation-driven model** (`last_observed_at_fiction_ts`, `tracking_tier`, lazy materialization). This is the idle-game delta-time pattern already built in, but **exact** rather than approximate. See §3. |
| M8 | **Idle *combat* offline** — *Melvor Idle* kills monsters and rolls loot for 12–24h while closed | **BREAKS on the durability budget** | Not a type violation — a throughput one. ~2.4 s/kill × 86,400 s ≈ **36,000 encounters/player/day**. At **5.4 ms per durable commit** that is ~194 s of pure commit time per player per login, per day offline. The island step (176–229 ns) is irrelevant; the commit is the wall. The axiom in tension is *one durable event per outcome* meeting *unbounded outcomes per wall-second*. |
| M9 | **Karma / merit / sin** as a signed unbounded quantity gating breakthroughs (heart-demon tribulation) | **BENDS → small BREAK** | Already registered as `BreakthroughCondition::KarmaThreshold` (PROG-D36). But: `EffectOp::ResourceGrant { amount: u64 }` **cannot grant negative karma**, and `Precondition` (5 variants) has **only `ResourceAtLeast`** — there is no `ResourceAtMost`. "May only break through if sin < 100" is **inexpressible without adding a `Precondition` variant**. Workaround = two non-negative resources (merit, sin) + a derived net, which loses the single signed quantity and still can't express the ≤ gate. |
| M10 | **Heavenly tribulation** at breakthrough; failure → death or realm regression (走火入魔 / qi deviation) | **SURVIVES** | `BreakthroughAdvance` cascade trigger spawns an encounter; failure branch is `ProgressionDeltaKind::RawValueDecrement` (PROG-D34) or tier regress (PROG-D2). Needs **no new `SeedRole`** — and the code explicitly notes a new role can be added without renumbering existing rolls. Server-side seeded outcome makes it **un-save-scummable**, which the genre cannot do. |
| M11 | **Lifespan / 寿元** — a hard clock, +N years per realm, run out → death; tradeable as a commodity | **BENDS** | Expressible as a Consumable + a day-boundary sink (the `Scheduled:HungerTick` precedent) + a Lex rule for zero→death. Lost: **body-boundness** (it lands in the portable `resource_inventory`, so it's stealable — happily *correct* for xianxia, accidentally) and you **re-implement the mortality trigger outside the `vital_pool` state machine**, which owns HP=0→death. `VitalKind` is closed (Hp, Stamina). |
| M12 | **Dual cultivation / demonic absorption** — one action moves progression on **two** actors | **SURVIVES (as declared future work)** | `TrainingSource::CrossActor` (PROG-D33) + `RawValueDecrement` (PROG-D34), both schema-additive. **Determinism trap worth flagging:** `role_rng(session_seed, actor, action_idx, role)` is keyed on the *acting* actor. A drain resolved from the victim's coordinate would collide with the victim's own action stream. It must be resolved once, inside the actor's action, keyed on the actor. |
| M13 | **Soft caps / diminishing returns** — *NGU* cap reduction, *Melvor* mastery-pool checkpoints | **SURVIVES** | `CurveDecl::Log` + `CapRule::SoftCap` exist; the i32 slot clamp is itself a hard cap. Minor loss: the curve applies to **raw_value accrual**, not to the **projection** (which is linear), so you cannot apply a *joint* soft cap across two kinds feeding one slot — only that slot's hard clamp. |
| M14 | **Challenge / modifier runs** — *Realm Grinder* challenges, *AD* Infinity Challenges ("production halved", "cannot buy X"), for permanent rewards | **BENDS, possibly BREAKS** | `ModifierSource::Lex` applied **last and inescapable** is the perfect mechanism for "your damage is capped at 1 this run". **But Lex is a *world* rule and the Ruleset is digest-pinned per reality.** If Lex clamps cannot be scoped to one actor/run, per-player challenges require **one reality per challenge variant** — an unacceptable multiplication of digest-pinned artifacts. This is an open architectural question, not a settled break. |
| M15 | **Numbers past 1e9 / 1e308** — *NGU* NGU levels to 1e9, *AD* antimatter past 1.79e308; the genre literally built `break_infinity.js` (to 1e9e15) and `break_eternity.js` (to 10^^1e308) for this | **BREAKS for true incrementals / does not apply to cultivation sims** | `StatBlock = [i32; 10]` saturates at 2.147e9; `raw_value: u64` at 1.8e19. Honest boundary finding: this is a **cultivation-RPG architecture, not an incremental-game architecture**. *ToI* and *ACS* use flat numbers and fit fine; *NGU*/*AD*/*Realm Grinder* do not and never will. |

##### Bonus hazard found in the code (not a proposed mechanic — a live bug class)

`resolve_block` computes `flat.saturating_mul(1000 + pct) / 1000` where **`pct` is the sum over all sources including Lex**. Two `-60%` suppression debuffs sum to `-120%`, giving factor `(1000 − 1200)/1000 = −0.2` → a **negative StrikePower / negative MaxHp**. The only guard is the author's `StatSlotDecl.clamp.min` (or the `StatTuningDecl` default). Cultivation realities are debuff-dense (realm suppression, formation arrays, poison, qi deviation), so **sign inversion is reachable in normal play**, and the saturation/clamp is **silent**. See suggestion **S10**.

---

#### 2 · The three most dangerous BREAKS

##### BREAK #1 — Realm suppression is inexpressible (M2)

**Why it's the worst:** this is not a nice-to-have. Realm suppression *is* the cultivation genre. It is the reason a xianxia protagonist flees rather than fights, the reason a sect elder's presence ends a scene, the reason "kill above your realm" is the single highest-praise trope. An architecture for this genre that cannot say it is missing the load-bearing beam.

**Concrete scenario.** A reality declares 9 realms. A Nascent Soul (realm 4) elder is ambushed by 200 mortal bandits in a `COMB_002` grid encounter.

- Elder: `MaxHp` clamped to 2,147,483,647 (i32 ceiling — see M1); `Armor` = 5,000,000; `Dodge` = 1000‰ (clamped).
- Bandit: `StrikePower` = 20; `Accuracy` = 450‰.

Run the locked chain:
- `hit_chance_pm(450, 1000)` → additive difference is ≤ 0, so `roll_pm() >= 0` is **always true** → every bandit misses. **Good** — accuracy accidentally works, but only because `Dodge` saturated at its per-mille ceiling. That ceiling is the *only* thing making it work, and it means **every** realm ≥ the one that hits 1000‰ Dodge is identically untouchable. Realm 4 and realm 9 are indistinguishable. Suppression has no *gradient*.
- Now give the bandits a `+600‰` accuracy elixir (perfectly ordinary content). `hit_chance_pm(1050, 1000)` → 50‰. Now each bandit hits 5% of the time for `max(1, 20 − 5_000_000)` = **1 damage** — the deliberate anti-stalemate floor.
- 200 bandits × 5% × 1 damage = 10 damage/round. The elder has 2.1e9 HP, so it takes 2.1e8 rounds. Practically safe — **but only by arithmetic accident, and it inverts the moment the author uses a smaller HP number.** At a sane `MaxHp` of 50,000 the mortals kill the Nascent Soul elder in 5,000 rounds — and an idle/offline auto-resolve (M7/M8) will happily run 5,000 rounds.

**What must change:** the `max(1, …)` floor is a *literal in a locked chain*, and there is no term keyed on `(attacker, defender)`. Neither is reachable from `StatSlotDecl`, from content, or from a ruleset number. → **S3 + S4.**

---

##### BREAK #2 — Multiplicative prestige composition vs axiom 4 (M6)

**Why it's dangerous:** axiom 4 is *correct* for buffs and *wrong* for prestige, and the architecture cannot tell the two apart because both arrive as `ModifierOp::Percent`.

**Concrete scenario.** A reality wants *Realm Grinder*'s two-layer reset: **Abdication** (soft reset → "Dao Gems", each +0.1% to all cultivation) and **Reincarnation** (hard reset → "Reincarnation Power", a flat ×N to everything). Player has 5,000 gems (+500%) and 3 reincarnations (intended ×8).

- Intended (genre-native, multiplicative): `base × 6.0 × 8.0 = ×48`.
- Actual under Σ-percent: gems contribute `+5000‰`, reincarnation contributes `+7000‰`, Σ = `+12000‰` → `× (1000+12000)/1000 = ×13`.

**×13 instead of ×48.** And the error *grows*: at 50,000 gems and 6 reincarnations the intended value is ×51 × ×64 = ×3,264 while the actual is ×(1 + 50 + 63) = ×114 — a **28× under-delivery** that widens without bound. There is no author-side workaround, because the author cannot pre-multiply: the two layers advance independently.

The perverse consequence is that **the designer's only lever is to inflate the per-unit percent**, which then interacts additively with *combat* buffs on the same slot and destroys combat balance. The genre solved this by keeping prestige on a separate multiplicative track; the architecture has no separate track.

Note the asymmetry that makes this survivable-looking at first glance: a **single** additive prestige track is fine. Cookie Clicker's `+1% CpS per heavenly chip` is genuinely additive within itself, and 10,000 chips → Σpct = 100,000‰ → ×101 is representable in i64 and only fails at the i32 emit. It is **layering** that breaks. → **S2.**

---

##### BREAK #3 — Adding a resource type does not survive the "project into 10 slots" promise (M5), compounded by the i32 ceiling (M1/M15)

**Why it's dangerous:** the architecture's headline extensibility claim is "authors declare how their kinds *project into* the closed slots." That claim is true for **derived combat quantities** and **false for pools**. A pool is not a projection target — it is a *container* with a max, a current, a regen rate, and a zero-behavior. There are exactly two of those (`MaxHp`, `MaxStamina`), both named after their semantics, and `VitalKind` is a closed engine enum.

**Concrete scenario.** An *ACS*-style reality declares three body resources: **Health**, **Stamina**, and **Qi**, plus (M11) **Lifespan**. Author writes:

```
ProgressionKindDecl { kind_id: "qi_refinement", progression_type: Attribute, ... }
StatSlotDecl { slot: ???, terms: [{ kind_id: "qi_refinement", weight: 12.0 }] }
```

There is no slot. The three options are all bad:

1. **Re-map `MaxStamina` → qi.** The reality now has no stamina; every piece of shared content that grants stamina (RES_001 hunger, COMB flee costs) silently means "qi". Cross-reality content becomes non-portable.
2. **Put qi in `resource_inventory` as `Consumable("qi")`.** Works for the *current* value, but the **max is now an ordinary number with no slot**, so it is invisible to `resolve_block` — no equipment `+20% max qi`, no status `−50% max qi` (qi deviation!), no Lex ceiling, and it is **not in `StatEpoch`**, so nothing invalidates a snapshot when it changes. It also becomes portable/tradeable, which is wrong for a body-bound resource.
3. **Add a slot.** Requires an engine release + boundary-matrix registration (per DF7-A1) — i.e. the extensibility mechanism has failed by definition.

Compounding: even option 1 hits M1. A 9-realm ×10 qi-pool ladder starting at 100 needs 1e10 at realm 9; the i32 emit **saturates silently at 2.147e9** and `resolve_block`'s `value.clamp(i32::MIN as i64, i32::MAX as i64) as i32` emits no signal. Realms 8 and 9 are numerically identical and nothing tells the author. → **S1 + S6 + S7 + S10.**

---

#### 3 · Where this architecture is genuinely BETTER than the genre

1. **Offline accrual is *exact*; the genre's is admittedly approximate.** *Antimatter Dimensions* documents that its catch-up "is only somewhat accurate, as the game is too mathematically complicated to be run at full accuracy in a reasonable amount of time" — it stretches ticks to 3.6 s each. *Melvor* caps offline at a fixed window. Here, `last_observed_at_fiction_ts` + lazy materialization + a pure accrual function means 30 days offline resolves to the *same* value as 30 days online, and it's replayable. That is strictly better, and it is already built (PROG_001 Q4 REVISED).

2. **Idle games are trivially cheatable; this one is not.** Cookie Clicker, NGU and Melvor all compute offline gain client-side from the wall clock — the entire genre has a system-clock-rollback exploit. Server-authoritative fiction-time + `role_rng(session_seed, actor, action_idx, role)` makes both accrual and tribulation outcomes uncheatable and **un-save-scummable**. For a *multiplayer* cultivation game this isn't a nicety, it's a precondition.

3. **Σ-percent is the right answer to a real genre disease.** Realm Grinder and Antimatter Dimensions are multiplicative, and the consequence is that both had to invent *layered resets* largely to manage numbers that had escaped — and then invent `break_infinity.js` (to 1e9e15) and `break_eternity.js` (to 10^^1e308) to hold them. Additive stacking means a content author **cannot accidentally mint a ×10⁶ combo** by shipping two items. My BREAK #2 is an argument for a *bounded, ruleset-declared* multiplicative layer, **not** for abandoning the axiom.

4. **The Lex-clamp-last correction is a balance guarantee the genre has no analogue for.** The recorded correction (Lex after slot clamp, because "whichever clamp runs last wins") gives an operator an inescapable ceiling on any stat regardless of what content does. Realm Grinder has shipped unbounded-multiplier bugs; there is no ceiling to catch them.

5. **Per-roll derived RNG survives content patches.** Because a roll's stream is derived from its coordinates rather than drawn sequentially, *adding a new random call anywhere never renumbers existing rolls*. Idle games break replays and leaderboards on nearly every content patch for exactly this reason.

6. **`StatEpoch` is a real staleness contract.** A 5-tuple of input versions with "re-resolve, never patch" beats every idle game's ad-hoc derived-stat cache (Melvor has a long history of equipment-change desync bugs).

7. **The dense array is measurably the right call and shouldn't be given up.** 1.42 ns vs 125.78 ns is 88×; at 176–229 ns per island step, a HashMap stat block would dominate the step. Every suggestion below **preserves the dense closed array.**

---

#### 4 · Extension points that fix the BREAKs without abandoning the design

Ordered by (value ÷ cost). None of these introduces a map, a float, or an author-declared slot.

| ID | Change | Fixes | Cost |
|---|---|---|---|
| **S1** | **Widen `StatBlock` to `[i64; 10]`.** The resolution math in `resolve_block` is *already* i64; only the emit narrows. Access cost is identical (still a direct indexed array field); the block grows 40 B → 80 B, still ≤ one 64 B line + a bit. Buys 9.2e18 instead of 2.1e9. | M1, M5, M15 | Trivial. Highest value/cost ratio on this list. |
| **S2** | **Add `ModifierOp::Multiply(i32 /*per-mille*/)`, admissible ONLY from a ruleset-declared, digest-pinned, bounded-cardinality `prestige_layers: [LayerDecl; ≤4]`.** Applied as its own layer after Σ-percent, in list order (so order-independence is preserved *by construction*, not by luck). Content can never emit one — only the ruleset. This keeps "no exponential from content" (the actual point of axiom 4) while making prestige compose the way the genre requires. | M6 | One `ModifierOp` variant + one layer in the locked order. Axiom 4's *rationale* survives verbatim. |
| **S3** | **Add one step to the damage chain: a `relational_mult`, a ruleset-declared per-mille table indexed by `clamp(atk_rank − def_rank, −N..=N)`,** where `rank` is a ruleset-nominated `StatSlot` or progression tier. Insert between `elem_mult` and `resist` (the chain already reserves identity slots, so this is *filling in a constant*, exactly as the code comment describes for elem/resist). | **M2**, and M3 and Melvor's combat triangle fall out of the same mechanism for free | One chain step + one ruleset table. No closed set changes. |
| **S4** | **Make the `max(1, …)` floor a ruleset constant `min_damage: i64` (default 1).** Setting it to 0 makes "a mortal cannot scratch an immortal" expressible; the anti-stalemate concern is then handled where it belongs (encounter round cap / forced flee), not by a magic literal in the damage law. | **M2** | One number. |
| **S5** | **Add `Precondition::ResourceInRange { id, kind, min: Option<i64>, max: Option<i64> }`** (or a 6th `ResourceAtMost`), **and widen `EffectOp::ResourceGrant.amount` to `i64`.** | M9 (karma/sin/corruption), and every "may only X if Y is *below* Z" gate in the genre | One variant + one type widening. Note `EffectOp` already went 9→10 for `SeverBinding`, so the set is evolvable in practice. |
| **S6** | **Apply the `ResourceKind::Consumable(ConsumableKindId)` pattern to vitals:** `VitalKind::Declared(VitalKindId)` with a **closed set of behaviors** — `{ body_bound: bool, zero_is_death: bool, regen: RegenDecl }`. The behaviors stay closed; only the *identity* opens. | M5 (qi pool), M11 (lifespan gets the real mortality trigger and body-boundness) | Mirrors an existing, proven pattern in the same codebase. |
| **S7** | **Replace `MaxHp`/`MaxStamina` with four generic `MaxPool0..MaxPool3` slots**, bound by the ruleset to declared vitals (S6). Slot count 10 → 12; still a dense `[i64; 12]`, still closed, still one indexed access. Authors get **up to 4 pools with the full equipment/status/percent/clamp/Lex pipeline**. | **M5** — this is the single change that unlocks the whole "genre adds a resource" class | The engine-release cost DF7-A1 anticipates, spent **once** to buy the general case instead of per-resource. |
| **S8** | **Add a batched-accrual event shape:** one durable commit carrying `(from_ts, to_ts, seed_range, aggregate_deltas, rng_draw_count)`, replayable to a bit-identical result. This is the *Tideward* "O(actions), not O(time)" pattern — collapse a run of identical actions into one statistical draw. | **M8** — 36,000 idle kills becomes **1 commit** instead of 36,000 × 5.4 ms | Determinism is preserved because the batch is still a pure function of (state, from, to, seed). Requires proving batch ≡ per-tick replay, which is a testable property. |
| **S9** | **Let `ModifierSource::Lex(rule_id)` carry an optional actor/run scope.** | M14 — per-player challenge runs without minting one digest-pinned reality per challenge | Small, but resolve the design question first: is a scoped Lex still "a world rule"? |
| **S10** | **Emit a signal on silent saturation.** `resolve_block` currently `saturating_mul`s and then `clamp`s to i32 with **no observable effect**. Emit a counter/event when a slot saturates, when Σpct pushes a factor negative, or when Σpct exceeds a ruleset threshold. | The **sign-inversion hazard** above, plus M1's silent realm-8-equals-realm-9 failure | Cheapest item here, and directly in the spirit of the project's *non-vacuity / bite-test* discipline: **the current clamp is a check that can never be observed to fire.** |

**Minimum set to make this architecture genuinely cultivation-capable:** S1 + S3 + S4 + S10 (all small) closes BREAK #1 and the silent-saturation class. S7 (+S6) closes BREAK #3. S2 closes BREAK #2. S8 is required only if you want idle *combat*.

**What I would not change:** the dense closed array (the 88× number justifies it), no-float, per-roll derived RNG, Lex-clamp-last, and the ruleset/content split. None of the ten suggestions touches any of those.

---

#### Sources

Cultivation / xianxia:
- [Amazing Cultivation Simulator — Five Attributes (Fandom)](https://amazing-cultivation-simulator.fandom.com/wiki/Five_Attributes) · [Spirit Roots](https://amazing-cultivation-simulator.fandom.com/wiki/Spirit_Roots) · [Cultivation Systems overview](https://shapes.inc/fandom/amazing-cultivation-simulator/cultivation-systems)
- [Tale of Immortal — Stats (Fandom)](https://tale-of-immortal.fandom.com/wiki/Stats) · [Beginner Guide](https://tale-of-immortal.fandom.com/wiki/Beginner_Guide)
- [Xianxia Cultivation Realms: Complete 10-Stage Guide](https://wuxiatales.com/cultivation/cultivation-realms-explained/) · [Cultivation Stages: The Complete Realm Breakdown](https://immortalcultivationhub.com/cultivation-stages-complete-breakdown/) · [Meridians in Cultivation](https://immortalcultivationhub.com/meridians-in-cultivation-explained/)
- [Chinese Cultivation Systems: Qi, Realms, and Immortality (TeaNovel)](https://read.teanovel.com/blog/chinese-cultivation-systems) · [Wu Xing five-element generation/destruction cycles](https://www.thechinajourney.com/wuxing/) · [Wu Xing, Gaming the Five Elements](https://gocorral.com/2024/11/18/wu-xing-gaming-the-five-elements/)
- [Cultivation games and cosmotechnics (Morgan Yu Hao, 2026)](https://journals.sagepub.com/doi/10.1177/20594364251364733)

Idle / incremental / prestige:
- [NGU Idle — NGU system (Fandom)](https://ngu-idle.fandom.com/wiki/NGU) · [NGU Idle Guide — NGU mechanics](https://sayolove.github.io/ngu-guide/en/mechanics/ngu/) · [Features overview](https://shapes.inc/fandom/ngu-idle/features)
- [Melvor Idle — Combat (wiki)](https://wiki.melvoridle.com/w/Combat) · [Prayer](https://wiki.melvoridle.com/w/Prayer) · [Combat Guide](https://wiki.melvoridle.com/w/Combat_Guide)
- [Cookie Clicker — Ascension (wiki.gg)](https://cookieclicker.wiki.gg/wiki/Ascension) · [Heavenly Chips](https://cookieclicker.fandom.com/wiki/Heavenly_Chips)
- [Realm Grinder — Abdication](https://realm-grinder.fandom.com/wiki/Abdication) · [Offline Production](https://realm-grinder.fandom.com/wiki/Offline_Production) · [Spells](https://realm-grinder.fandom.com/wiki/Spells)
- [Antimatter Dimensions — Break Infinity](https://antimatterdimensions.wiki.gg/wiki/Break_Infinity) · [Prestige](https://antimatterdimensions.wiki.gg/wiki/Prestige) · [Offline Progress](https://antimatter-dimensions.fandom.com/wiki/Offline_Progress)
- [break_infinity.js](https://github.com/Patashu/break_infinity.js) · [break_eternity.js](https://github.com/Patashu/break_eternity.js/) — the genre's numeric-range escape hatch
- [24-Hour Offline Progression, Like Melvor Idle (Tideward)](https://tideward.app/offline-progression/) — the O(actions)-not-O(time) batched-accrual pattern behind S8 · [The Idle Game Illusion: How Delta-Time Powers Progress](https://www.geekextreme.com/idle-games-offline-progression-math/)

---


<a id="adversarial"></a>

## Adversarial architecture critic — where this rots in two years

*Distilled into doc 27 §9. Verbatim below.*

Research agents haven't returned; I'll report on what I verified directly in the code, which turned out to be far more damning than any external citation.

#### Method note

I did not critique the summary — I read the implementation and **ran probes against it**. Four suspected defects were confirmed empirically (probe file written, run, then deleted; working tree is clean). I also re-ran the benchmark that the entire closed-enum design rests on.

---

### 1. Ranked failure modes

##### F1 · The ruleset digest is decorative. The real rules are Rust literals. — **FATAL**

**Mechanism.** `EventEnvelope` (`crates/dp-kernel/src/envelope.rs:46-59`) has **no `ruleset_digest` field**. `RulesetDigest` exists on `Island` and in the checkpoint, is **never stamped into an event and never compared to anything** — a repo-wide grep for `digest ==`/`digest !=`/`DigestMismatch` returns zero hits. `Island::restore` (`island.rs:333`) takes `rules` from the caller and blindly stamps `cp.digest` on them with **no verification that those rules hash to that digest**.

Worse: `CombatRules` (`services/commit-service/src/domain.rs:220-228`) has two fields. One (`strike_damage`) is documented as dead. The other, `ko_duration_rounds`, has **exactly one read site** (`domain.rs:444`). Every number that actually decides a fight is a literal in Rust: `500/50/950` in `hit_chance_pm`, the `850..1150` variance band, `ELEM_MULT_PM`, `RESIST_PM`, `1200/800/2000/750` in `action_value`, and all ten stat defaults plus `StatTuning` in `stats.rs`.

**Concrete trigger.** A designer edits the crit variance band from `300` to `250` in `combat.rs`. The binary ships. Every historical event now replays to a different outcome, and **the digest does not move**, because the digest covers a config struct that governs one value. The mechanism built to detect exactly this is blind to it.

This inverts the purpose of the design. And it means **replay-correctness is currently vacuous** — there is no test that can bite on rules drift, because the rules aren't in the artifact being hashed. Given your bite-test discipline, this is the finding I'd escalate first.

**Fixable now cheaply: YES — and the cost curve is brutal.** `CombatRules` has 2 fields and ~11 tests today. After 10⁶ events exist, reconstructing which binary produced which event is archaeology.

---

##### F2 · The "inviolable, applied-last" Lex clamp is escapable — **SERIOUS** (proven)

```
PROBE-A  MoveRange under Lex ceiling of max=2  =  5
```
`resolve_block` applies slot clamps then Lex clamps inside the per-slot loop, then calls `derive_move_range` **after the loop** (`stats.rs:251`), which overwrites `MoveRange` with `clamp(base + speed/per_tile, 1, tuning.max_move)` — discarding the world rule.

The doc treats Lex-clamp-last as a **recorded correction** (DF07_002 EC-1) with a dedicated test. That test covers `StrikePower`. Nothing covers the one slot where the invariant is actually broken. A world rule "in this reality nothing moves more than 2 tiles" silently does nothing.

**Fixable now: trivially** (derive before the clamp pass, or re-apply lex clamps after derivation). Add the bite test.

---

##### F3 · Additive percent underflows past −100% and **inverts** stats — **SERIOUS** (proven)

```
PROBE-C  Speed 100 with 3× Percent(-400)  = -20
PROBE-C  MaxHp 100 with 2× Percent(-600)  = -20
```
`flat.saturating_mul(1000 + pct) / 1000` with no floor on `(1000 + pct)`. Three −40% slows stack to −120% and the stat goes negative. Negative `max_hp` flows into `CombatStats`, and `evaluate_outcome` tests `hp > 0` — so a stack of debuffs is an instant-death mechanic nobody designed.

This is the canonical failure of sum-only stacking, and it is precisely why Path of Exile splits *"increased"* (additive) from *"more"* (multiplicative): additive reduction can reach and cross 100%, multiplicative asymptotically cannot. **Sum-not-chain does not remove the stacking problem — it moves it from unbounded growth to sign inversion**, and sign inversion is the worse failure because it's silent and type-valid.

Directly answering your Q3: sum-only forbids (a) diminishing-returns resistances, (b) any "×N damage" multiplier that should compose independently of gear percentages, (c) the *"more/less"* design vocabulary that lets a designer add a strong effect without re-rating every existing modifier. The order-independence you bought is real but **you already have it for free** — see F9, addition is commutative, so nothing was purchased.

**Fixable now cheaply: YES.** Clamp `(1000+pct)` at 0, and add a second, explicitly multiplicative "less" bucket applied after the sum. Doing this after content authors have tuned against additive-only is a rebalance of the entire item set.

---

##### F4 · Silent no-op: Flat modifiers on Base/Archetype/Lex are dropped — **SERIOUS** (proven)

```
PROBE-B  Base      Flat(+50) on StrikePower(10) -> 10
PROBE-B  Archetype Flat(+50) on StrikePower(10) -> 10
PROBE-B  Lex       Flat(+50) on StrikePower(10) -> 10
PROBE-B  Equipment Flat(+50) on StrikePower(10) -> 60
```
The flat loop iterates only `[Progression, Equipment, Status]` (`stats.rs:216-217`). Three of six `ModifierSource` variants are constructible, accepted, and silently discarded. The **percent** filter is *not* source-filtered — so `Lex Percent` applies while `Lex Flat` vanishes. A world rule expressed as a flat bonus does nothing; the same rule expressed as a percent works. No error, no validator, no test.

This is exactly the no-silent-no-op class your own CLAUDE.md names as a shipped bug (`panel_id` with no enum → silent no-op → hallucinated success).

**Fixable now: trivially.** Either apply them or reject at construction. The enum should not be able to express something the resolver ignores.

---

##### F5 · The 88× benchmark does not support the conclusion drawn from it — **SERIOUS (architectural)**

`26_implementation_architecture.md §1` uses a prior project's numbers (HashMap 125.78 ns vs direct field 1.42 ns) to justify a closed 10-slot enum with an engine-release cost. I re-ran the comparison that actually matters:

| | ns/read |
|---|---:|
| A · closed `[i32; 10]` by enum ordinal (the shipped design) | **1.384** |
| B · **open** `Box<[i32]>` indexed by interned `StatId(u16)`, per-reality sized | **1.496** |
| C · `HashMap<String, i32>`, SipHash | 11.952 |

A reproduces the cited 1.42 ns, so the rig is comparable. Two things follow:

1. **The cited 125.78 ns is ~10× slower than even a plain string-keyed `HashMap`.** It did not measure "dynamic stats." It measured a pathological structure — nested maps, cloned keys, or lock/Arc indirection. The number is real; the inference from it is not.
2. **The open, unbounded design costs 1.08× — 0.11 ns per read.** Against a 176–229 ns island step that is **0.05%**. Even at 8 stat reads per damage resolution the total is ~0.9 ns, ~0.4% of one step. The doc's claim that a dynamic path means "~1 µs, or 5× the whole step budget" assumes the hot path does the lookup.

And it doesn't — **by your own design**. `CombatStats::from_block` (`combat.rs:119`) projects the block into a flat struct once; `resolve_attack` reads that struct, never the block. IMP-A3 (resolve extensibility cold, ahead of the hot path) *already* eliminates the hot-path lookup. **The closed enum is a second payment for a problem projection already solved.** The ceiling, the ownership matrix, and the engine-release cost buy 0.11 ns.

**Fixable now cheaply: YES, and only now.** Once ordinals are baked into serialized snapshots and event payloads, opening the tail is a data migration.

---

##### F6 · The 10-slot ceiling: projection is **type-incorrect**, not merely lossy — **SERIOUS**

You asked for a case where projecting two author concepts onto one slot is *wrong*, not lossy. There are three in the current code:

**(a) `Accuracy` — wrong operator.** `hit_chance_pm = clamp(500 + acc − dodge, 50, 950)`. Accuracy is a *term in a difference*. Now project two concepts: *"keen-eyed"* (+accuracy) and *"true strike: ignores dodge"*. "Ignores dodge" is **suppression of the dodge term** — a different operator, not a bigger accuracy. The only available projection is a large `acc`, which (i) saturates at 950 and (ii) makes the actor near-unmissable against *every* target, not just the evasive one. Against a 0-dodge target the two concepts are indistinguishable; against a 400-dodge target both give 950. The mechanic is not approximated — it is **replaced by a different mechanic**, and which build is strong changes as a result.

**(b) `Armor` — ratio projected into a difference.** `base = (strike_power − armor).max(1)`. Plate armor is a flat reduction; a magic ward is a *percentage*. Projecting 30% reduction into `Armor` requires choosing a flat number that is correct at exactly one attacker power level and wrong everywhere else — and it degrades to the `.max(1)` floor against weak attackers. The slot where a ratio belongs is `RESIST_PM`, which is `const RESIST_PM: i64 = 0` at compile time. **There is nowhere else to put it.**

**(c) `MoveRange` collapses two independent axes.** It is derived from `Speed`. "Lumbering but long-striding" and "quick but short-stepping" are the same point in this model. Not lossy — unrepresentable.

**Realistic pressure for slot #11+.** Resistances (per element = 3–6 slots), mana/resource pools, casting speed, healing power, threat modifier, stealth, carry weight, block/parry. Every one of these is table stakes for the genre. Once "engine release + ownership-matrix registration" is the price of a slot, the observed organisational response is universal: **people stop asking and start overloading**. They will encode "fire resistance" as a negative `Armor` contribution or a `CritMult` fudge, and two years later nobody can say what `Armor` means. This is precisely why Bethesda's Creation Engine — which has a fixed, enumerated Actor Value list — grew the open-ended **keyword (KYWD)** record type as the extension escape hatch, and why the modding community's persistent complaint is running out of usable actor values. A closed attribute list plus an open tag namespace is the shipped answer to this exact problem.

**Fixable now: YES (see change #3). Later: rewrite.**

---

##### F7 · Cross-island handoff fabricates a corpse and can lose entities — **SERIOUS**

`extract` is `state.actors.remove(&id).unwrap_or_else(|| Actor::new(0))` (`domain.rs:532`). `Actor::new(0)` → `hp: 0, max_hp: 0, side: Side::B`. The `Domain` trait says *"TOTAL — an entity with no domain rows yet still departs (the portable encodes the empty case)"* — but `type Portable = Actor` **has no empty case**, so the contract was satisfied by inventing a dead body.

Now combine with `CombatDomain::outcome_of` (`domain.rs:255`), which iterates **all** of `state.actors` with **no encounter scoping**. An entity crossing in without a domain row installs a dead Side::B actor → `any_present(B) && !b_standing` → **`Victory` declared for side A**.

Separately: `depart` and `arrive` are two non-atomic calls on two islands with no durable carrier anywhere in the production path (only `TestDomain` and `CombatDomain` implement the seam; nothing in `realm.rs` or `manager.rs` transports a `Portable`). "Exactly one island" is structurally enforced against **duplication** but not against **loss** — a crash between the two leaves the entity in zero islands, holding a `Portable` in dead memory.

**Fixable now cheaply: YES.** `Portable = Option<Actor>`; scope `outcome_of` by encounter; make the handoff a durable outbox row.

---

##### F8 · `CombatState` is single-encounter; `Island` is multi-encounter — **SERIOUS**

`CombatState` has one `session_seed`, one `round_number`, one `outcome`. `Island` maintains `encounters: BTreeMap<EntityId, Gen>`. The kernel is built for N encounters per island; the domain state is built for exactly 1. The first time two encounters share an island, encounter A's victory condition is evaluated over encounter B's corpses. This is latent today and looks like a mystery bug later.

---

##### F9 · "LOCKED layer order" is currently unobservable — **ANNOYING now, SERIOUS later**

```
PROBE-D  swap flat values across layers: 10 vs 10  (equal => order unobservable)
```
The flat layers are summed. Addition is commutative. The comment claims iterating an ordered source list "keeps the result independent of the order modifiers arrive in" — but plain summation already is. **The only orderings that are actually observable are flat-before-percent and slot-clamp-before-lex-clamp.** The "inviolable layer order" invariant has, today, **no test that is capable of failing** — the mechanism doesn't merely pass the check, it makes the check unfalsifiable.

That's fine until someone adds a genuinely order-sensitive op (a multiplicative modifier, or a `SetTo`), at which point the invariant becomes load-bearing with zero regression coverage behind it.

---

##### F10 · Clamps don't compose; load order silently decides — **SERIOUS**

`slot_clamps.iter().find(|c| c.slot == slot)` takes the **first** clamp for a slot; a second is discarded, not intersected. Two content packs each clamping `MaxHp` → the winner depends on `Vec` order, i.e. load order. Order-dependence reintroduced through the back door of the mechanism advertised as order-independent. There is no upstream builder that intersects them (clamps are only ever constructed in tests, one per slot).

---

##### F11 · Closed `EffectOp` already grew before a line of Rust exists — **SERIOUS (trajectory)**

- `26_implementation_architecture.md:61` and `SESSION_HANDOFF`: *"closed **9**-variant `EffectOp`"*
- `catalog/cat_19_ABL_ability.md:44`: *"closed **11**-variant dispatch vocabulary"*

**+22% during the design phase.** And `PL_007c_integration.md §12.13` records that two copies of the enum **diverged within 24 hours** (`StatusApply` gained `duration_rounds` in one and not the other; `VitalDelta` named its field `kind` vs `vital`), and that the signed `VitalDelta { amount: i32 }` was a **damage-law-chain bypass** — an unmissable, armour-ignoring PvP weapon usable in a sanctuary.

That last one is the real lesson and it argues *against* your framing: the closed vocabulary did not prevent the bypass. A closed enum constrains *which* variants exist; it says nothing about whether a variant routes through the law chain. The defect was caught by a human reading two files side by side, not by the closedness.

For scale: World of Warcraft's spell-effect enum sits in the ~180-range and its aura enum in the many hundreds after twenty years of content. A ten-variant closed effect vocabulary for a game that wants ongoing content is not a ceiling you approach — it's one you pass in year one. *(Numbers here are from my own knowledge; the web-research agents had not returned by report time — treat the WoW/Skyrim figures as directionally reliable but verify before quoting externally. Everything sourced to file paths above is verified in-repo.)*

---

##### F12 · Determinism forbids less than you think — but the **clock** is the real constraint — **ANNOYING**

The no-float rule genuinely holds: zero `f32`/`f64` in `crates/sim-core/src/*` and `services/commit-service/src/*` outside benchmark binaries. Credit where due. No-float forbids essentially nothing a turn-based RPG needs; fixed point covers it. It *does* forbid cheap `sqrt`/trig, so future line-of-sight, ballistics, or continuous movement needs integer implementations.

The actual constraint is different: **`Domain::apply(state, rules, input, rng)` receives no `Tick`.** The domain cannot ask "how long has it been." Every duration must be a counter decremented by an explicitly injected engine payload — as `knocked_out: Option<u8>` already is. That's correct and workable, but it means **the number of scheduled admissions scales with the number of live timed effects**. At 100 players with DoTs, HoTs, and buffs, timer inputs become the dominant admission load — and `21_architecture_ceilings.md §7` honestly lists validator-pipeline cost as unmeasured. This is the load nobody has budgeted.

---

##### F13 · Where it actually rots in 2 years — **the prediction**

`26_implementation_architecture.md §4` guesses `domain.rs` (539 lines). **I think that's the wrong guess.** `domain.rs` is a dispatch file; dispatch files grow linearly and split cleanly.

The god-object will be **`combat.rs` — specifically `resolve_attack`** — because every mechanic F6 makes unrepresentable gets solved the same way: a special case threaded into the law.

The pattern is **already in the file, twice**:
- `defending: bool` is a parameter of `resolve_attack` with `if defending { 2 }` in the denominator, explicitly documented as *"not a stat modifier (DF7-A8)."*
- `AvStatus { slowed, hasted, stunned }` is a **second, parallel, ad-hoc modifier system** that exists precisely because those effects couldn't be stat modifiers.

That is two escape hatches before any content ships. The trajectory: `resolve_attack` grows a `&ResolutionFlags` argument; `ResolutionFlags` accumulates ~20 bools; the denominator becomes a chain of `if` multipliers whose **order is load-bearing, undocumented, and untested** (because F9 established no harness exists for order). `combat.rs` becomes the place where every mechanic the slot system couldn't express is hardcoded — and it will be the file nobody can safely change, because it's also the file the digest doesn't cover (F1).

---

### 2. Fixable now vs rewrite later

| # | Finding | Verdict |
|---|---|---|
| F1 | Digest decorative | **Cheap now (~200 LOC).** After 10⁶ events: archaeology. |
| F2 | Lex clamp escaped | **Trivial now.** Reorder + one test. |
| F3 | Percent underflow | **Cheap now.** After content tuning: full rebalance. |
| F4 | Dropped flat modifiers | **Trivial now.** |
| F5/F6 | Closed slots | **Cheap now** (two accessors, 11 tests). After ordinals are serialized: **data migration + rewrite**. |
| F7 | Handoff corpse / loss | **Cheap now.** Durable handoff later = protocol rewrite. |
| F8 | Encounter scoping | **Cheap now.** Later: mystery-bug archaeology. |
| F9 | Unobservable layer order | **Cheap now** (make it observable or drop the claim). |
| F10 | Clamp composition | **Trivial now.** |
| F11 | EffectOp growth | **Not fixable by tightening** — needs an open tag namespace (change #3). |
| F13 | `combat.rs` rot | **Preventable now** by policy; **not fixable later** at any price. |

---

### 3. The three changes I'd make TODAY

**① Make the digest bite.** Move every game constant out of `combat.rs`/`stats.rs` into `CombatRules`. Hash the real struct. Add `ruleset_digest` **and `engine_build`** to `EventEnvelope`. Make `Island::restore` **verify** that the supplied rules hash to `cp.digest` instead of stamping it. Then add the bite test your own discipline demands: *edit one constant → assert the digest moves → assert replay under a mismatched digest is refused*. Right now that test cannot be written, which is the tell.

This also gives you the answer to your Q5 that you currently don't have: **there is no migration story for a locked order under digest-pinned replay**, because nothing versions the rules *engine*. `dp-kernel/src/upcaster.rs` versions event schemas, not rules. The standard shape (Greg Young's weak-schema + upcasting; the fork-block pattern from consensus systems) requires the rules version to be an explicit, resident input to `apply` — meaning `Rules` must be resolvable by historical version, not just by digest. Decide that now; it's a trait-shape change today and an impossible retrofit later.

**② Fix the four silent-correctness defects and add the four tests that can fail.** Floor `(1000 + pct)` at zero (and add a separate multiplicative "less" bucket). Apply-or-reject `Base`/`Archetype`/`Lex` flat modifiers. Derive `MoveRange` before the clamp pass. Intersect clamps instead of first-wins. Every one is a few lines; **every one currently has no test capable of failing**, which is why they survived review.

**③ Open the tail of the stat array — keep the closed head.** Keep the enum for the ~8 slots the laws `match` on; they must be named to be matched. Make `StatBlock` a per-reality-sized dense allocation with an interned `StatId(u16)` tail for author-declared stats that only feed projections, UI, and content conditions. Cost, measured on this machine: **1.08× (0.11 ns/read, 0.05% of an island step)** — not 88×. This is the closed-core-plus-open-tag shape that Creation Engine arrived at empirically (fixed actor values + open keywords), and it removes the organisational failure mode in F6 without touching the hot path. Do it while `StatBlock` has two accessors.

---

### 4. What this gets right that most game backends get wrong

Not flattery — these are specific and rare:

1. **Per-coordinate RNG derivation instead of a shared draw-order stream.** `role_rng(session_seed, actor, action_idx, role)` with **pinned discriminants** (`combat.rs:47-55`) and an explicit comment that reordering the enum must not change historical rolls. The overwhelmingly common design is to draw sequentially from one PRNG, which couples every historical roll to the number of prior draws — so adding one ability silently renumbers all of history and breaks every replay. This project identified that failure mode and engineered it out. **This is the best decision in the codebase.**

2. **Non-vacuity with actual bites, asserted as ratios.** `21_architecture_ceilings.md §8` ships a falsifier per ceiling that must *move the number* (`sync_commit` off → 2.05×; pool=1 → 13× worse; fat payload → 8.1× worse), and asserts on **ratios rather than absolutes** so the gate stays honest on slower hardware instead of going red on a fast box and green through a real regression. §7 then enumerates what is **not** measured and forbids inference. Performance docs in game backends are almost always an unfalsifiable table of numbers.

3. **The no-float rule is actually held, not merely stated.** Verified zero `f32`/`f64` in the entire simulation path. Most projects declare this and leak a float within a month.

4. **Rules held behind `Arc` *outside* `State`** (`island.rs:42-44`), so they cannot enter checkpoints, migration payloads, or crash rebuilds. Tiny, correct, and agonising to retrofit once state has been serialized with rules embedded.

5. **A failed precondition is a recorded normal outcome, not an error.** `Fallback`/`Outcome`/`DiscardReason` mean *every* item's fate is recorded — including duplicates and expiries. Most backends drop invalid input silently and then cannot explain player-reported "my action didn't do anything."

6. **Departure removes the registry entry before any message can exist**, making entity duplication structurally impossible rather than a protocol promise. The right instinct; it just needs the loss side closed too (F7).

---

**Bottom line.** The architecture's stated invariants are good ones. The problem is that **four of them are currently false in code and a fifth is unfalsifiable** — the Lex clamp is escapable, percent stacking inverts stats, three modifier sources are silently dropped, the digest covers rules that govern nothing, and the locked layer order has no test that can fail. The closed-enum ceiling that gets the most design attention is, by measurement, buying 0.05% of an island step. I'd spend the next cycle making the existing invariants *true and biteable* before defending them further.

---
