# RUN-STATE — game tier: the actor hub's first consumer, then the command substrate

**Opened:** 2026-08-06 · **Base:** `6c075b5b8` · **Status:** CLARIFY, awaiting PO seal
**Predecessors:** [actor round](2026-08-02-actor-substrate-RUN-STATE.md) ·
[command round](2026-08-02-command-interaction-RUN-STATE.md)

> **Re-read this file after any compaction, before `git log`.** Context is lossy; a file is not.
> Nothing here is sealed by its author. Sealing is the PO's, and the seal list is §4.

---

## 1. The commitment

Two milestones, in this order, and the order is **derived rather than chosen** (§2):

1. **`M1` — the actor hub gets its first consumer.** `commit-service`'s domain is **rebuilt on the
   hub, and the legacy combat shape is DELETED** — not ported.
2. **`M2` — the command substrate's first declared verb**, replacing a hardcoded arm in `law.rs`.

> 🔴 **`M1` is a REPLACEMENT, not a migration — PO, 2026-08-06.**
> *"`hp` and friends are old src, rubbish too. Back then we only built to prove the kernel and the
> SDK could work, so dealing with them is right."*
>
> This is `D-11` (*the shipped engine is scaffolding and may be broken freely; zero production
> realities exist*) and `D-14` (*combat vocabulary is out of scope and will be rewritten*), stated
> again by the person who took them. **So `M1` does not port `hp` into a quantity one-for-one.** It
> declares the quantities the design needs and **deletes** `Actor`'s field list, `CombatStats`,
> and whatever else in the combat domain exists only to hold them.
>
> The distinction is load-bearing, not stylistic. A port preserves the old vocabulary in a new
> container — which is `D-2`'s exact failure (*a hardcoded noun is a manifest that cannot grow*),
> survived through a refactor that looked like progress. **Porting `hp` to `quantity[0] = "hp"`
> would satisfy every test and change nothing.**

**Done means:** a verb declared as a manifest row resolves end to end against a hub-backed actor,
with the refusal path and the presentation channel both real, and every check bite-tested.

## 2. The ordering is forced, and here is the measurement that forces it

Measured at `6c075b5b8`:

| | |
|---|---|
| `crates/actor-hub` | built, **91 tests green**, and **zero consumers** — no `Cargo.toml` in the workspace depends on it, `actor_hub::` appears nowhere outside the crate, and the only thing constructing a `DerivationRow` is `examples/two_plugins_fold.rs` |
| `commit-service::domain::Actor` | **live scaffolding, and it is `D-3`'s own subject**: `hp: i64` · `max_hp` · `defending` · `stance` · `fled` · `side` · `av` · `status` · `knocked_out`. **To be deleted, not carried** — see the PO note in §1 |
| the command substrate | **0 % implemented** — zero hits for `verb_declarations`, `VerbDeclaration`, `RequirementRow`, `EffectRow`, `offers_for`, `conflict_resolutions` |

**Why `M1` must precede `M2`.** A declared verb's `EffectRow` targets a **quantity ordinal**. While
an actor's numbers are struct fields, an effect cannot name one without a `match` arm per noun —
which is `CMD-6`'s defect, re-created by the very table meant to remove it. So the substrate cannot
be declarative until the actor's nouns are quantities.

**And `M1` does not need `M2`.** `law.rs` keeps driving changes, hardcoded, but operating on
quantities instead of fields. Each milestone is independently verifiable, which is the point.

> ⚠️ **A hub with no consumer is the shape this repo has already been burned by.**
> `scripts/orphan-model-gate.py` exists because seven `pc_*`/`npc_*` projection tables shipped with
> a projector, a rebuilder, a golden fixture, an independent oracle and a benchmark — and **no
> producer at all**. `M1` is what stops the actor hub becoming the same finding one layer up.

## 3. The door accounting — measured 2026-08-06, and it decides `M2`'s scope

`CMD-3` says an effect is a row from a closed primitive set, and the rule that makes the set
non-arbitrary is *"a primitive exists **iff the substrate already built the door** it goes
through."* `FATAL-2` found the rule unsatisfied by seven of eight. Re-measured at HEAD — nine of
its ten named surfaces still return **zero hits in the game tier**, and the tenth (`fiction_time`)
is in `tilemap-service`, an unrelated concept sharing a word:

| door | at HEAD |
|---|---|
| **`Delta`** | ✅ **BUILT** — hub quantities, `ModifierRow`/`DerivationRow`, the three-pass `fold`, `OpKind{Flat,Percent}` |
| `StatusPropose` | prose — `status_active`, 0 hits |
| `EdgeMove` | prose — 0 hits. The item round *designed* the holder graph; it is unbuilt, which is **buildable, not blocked** |
| `LifecycleRequest` | prose. `GoneState` is real but it is **entity existence** (severed/archived/dropped/user-erased) — a different ladder from a game lifecycle |
| `ClockAdvance` | prose — `fiction_time`, 0 hits in the game tier |
| `Materialise` | prose — `Residency`, 0 hits |
| `Oracle` | prose |

⇒ **One door of seven is open, and it is exactly the one the actor hub built.**

**Therefore `M2`'s first verb is `Delta`-only** — which is not a compromise, it is the sub-language
the round independently measured as working today: *"`/sleep · give · poison · execute · summon ·
fixed heal` — a verb fits when every number is a constant, it touches one other actor, takes no
parameter, and needs no state between two actors."* Two measurements, no contact, one answer.

## 4. The seal list — PO decides, author does not

### 4.1 The condition that blocked `CMD-1`..`CMD-6` is DISCHARGED

The PO declined to seal *"pending prior art"* and directed a research pass. It ran, three times:
08-02 §3's six systems (The Sims · GAS · Inform 7 · Caves of Qud · Evennia · lockstep) · round 2's
decision layer (IAUS · Pokémon/WC3 classifier matrices · GOAP · the shipped RNG door) · and the
2026-08-05 round, which turns out to have been that directed pass performed blind, now folded.

**A second blocker replaced it and is not discharged**: `F-8` (the classification test could not
fail) → `V1/V2/V3` → `R4` (the replacement passes anything given a flag set). `CMD-10` proposes the
repair. **So the seal ORDER is forced: `CMD-10` first, then `CMD-1`..`CMD-6`.**

### 4.2 What is asked of the PO

| # | ask | note |
|---|---|---|
| **`CMD-10`** | seal the fourth question — *operand, not predicate* | **owes a bite** (author a member that sets an authority-bearing field; assert the build refuses it). It was deferred by `8b`'s design-only rule; `M1`/`M2` lift that, so the bite is now doable and should land **with** the seal, not after |
| **`CMD-1`..`CMD-6`** | seal, re-scored under `CMD-10` | `R4-5` said `CMD-1` is mechanism by its own test; `CMD-10`'s score-versus-rank boundary dissolves that. Re-scoring is the author's job, the verdict is the PO's |
| **`CMD-11`** | the offer registry, in commit-service | needed by `M2` only if the first verb takes a target. A `Delta`-only verb on the actor itself does **not** need it — so this can seal after `M2`'s first slice |
| **`CMD-12`** | keyed-MAC `offer_id` | ⚠ **the load-bearing hole is elsewhere** — `actorForUser` returns `LW_CHANNEL_DEFAULT_ACTOR ?? '1'` for any authenticated user absent from the env map, so two users are legitimately bound to one subject. A MAC over a subject the caller can already be is a lock on the wrong door. **Fix the subject source first** |
| **`CMD-13`** | horizontal composition | needs **two bundles** to have a subject. `M1`/`M2` have one. Seal the *mechanism* now if the PO wants it fixed cheaply, or park it until the second bundle — both are defensible |
| **`O-71`/`C-0`** | the signed arrow | carried from the actor round, *"the whole gate"*. Now priced: quantity → **value** is shipped and signed; quantity → **ceiling** is what is missing |

### 4.3 Decisions with no derivable answer — these need the PO, not more analysis

| # | question |
|---|---|
| **`O-CI-24`** | **where is a `conflict_resolutions` row authored** — a third reconciling bundle, or the reality that assembled the pair? |
| **`O-CI-25`** | does `strict` earn a member of the merge-strategy set? Cheap to add later, expensive to remove |
| **`O-CI-7`** | **one table or two.** `/sleep` leaves four of six new columns inert, and a row whose normal state is mostly inert is the *"29 accreted fields are FOUR kinds"* signal |

## 5. Where the deep dive goes — four, and each is named for a reason

Not a wish list. Each of these **blocks writing code**, and inventing an answer under time pressure
is the failure mode this project has recorded most often.

1. **The effect primitive set, and the six unbuilt doors** (`C-1` · `O-CI-1` · `FATAL-2`). The
   round calls this *"the round's real unknown"* and §3 prices it: one door of seven. The question
   is a scope decision — **build doors, or narrow the primitive set to what is open** — and it
   decides how far `M2` reaches. Everything else in `M2` is downstream of it.
2. **`O-CI-16` — six types are named and never defined**: `ChanceSpec`, `InputKind`, arity's home,
   pair `subject`, the two-role `EffectRow`, `RefKindMask`. **Every `consideration` and every
   `success` row in a real manifest rests on an invented shape.** You cannot write code against a
   name. This is definition work rather than research, but it is genuinely undone.
3. **`O-CI-10` + `O-CI-11` — instance-level pair state, and its arity.** Twelve findings are one
   absence. No longer blocked on `O-71` (the magnitude it needs is shipped), but the real
   constraint is narrower and was found by measurement: **derivations read pass-1 values, so there
   is no derivation chain.** The open question is *where the bind-time projection lands in the
   fold* — and `O-CI-11` asks what happens at arity 3 (`believes(A, "B did X")`), where
   `O(arity^n)` stops being cheap.
4. **`O-CI-3` + `FATAL-3` — the roll.** `attack.rs` uses `SeedRole::Hit` **and** `SeedRole::Crit`
   inside one attack while the design's flat `gate` expresses one; and `role_rng` has **no verb
   term**, so `cast`'s roll would collide with `strike`'s. Fixing that touches **pinned replayed
   history**, which is why it is a dive and not an edit.

Honourable mention, because it will arrive on the first content request rather than the first
build: **`O-CI-21` — the dependency graph is acyclic BY ACCIDENT.** `statuses ⟷ thresholds` becomes
a real, unbreakable cycle the moment an author wants *"while `blood_low` is active, lose 3 blood
per tick"*. It is acyclic because a capability is missing, not because it was designed to be.

## 6. Slice board

`done` is an **evidence string**, never a tick.

| # | slice | evidence | state |
|---|---|---|---|
> 🔵 **Checked before opening `M1`, because getting it wrong would rebuild `D-3` one layer up:**
> `ruleset-core` and `actor-hub` are **not two parallel declaration systems — they are layered, and
> the layering is already correct.** `actor-hub` depends on `ruleset-core`;
> `ruleset-core::QuantityTable` holds the **names** (hashed, pinned) and `ResourceDecl` holds a
> pool's semantics against a `QTY-A5` ordinal; `actor-hub::QuantityDecl` is `{ ordinal, initial }`
> with **no name**, and `PluginDecl` carries *"no name, no kind, and no behaviour, because the hub
> knows nothing about what any of it means."* That is `D-2` running as designed: **the manifest
> closes on VOCABULARY, the engine closes on MECHANISM.**
> ⇒ **`M1` invents no plugin vocabulary.** The quantities are the ruleset's; the hub attaches and
> folds them. **But `QuantityTable::EMPTY` is the shipped default** (*"the engine declares
> nothing"*), so `M1` must also **populate a reality's quantity table** — that is content, and it is
> a real sub-task rather than a given.

| `M1.0` | **inventory what the legacy combat domain actually holds, and mark each: DELETE · re-declare · genuinely load-bearing.** The default is DELETE; anything claimed load-bearing needs a reason a reader can check | — | [ ] |
| `M1.1` | declare the quantities the DESIGN needs — **derived from the design, never read off the old field list.** A quantity named because a struct field was named is the port this milestone refuses | — | [ ] |
| `M1.2` | `commit-service` depends on `actor-hub`; the domain resolves an actor through the hub's fold | — | [ ] |
| `M1.3` | the legacy shape **deleted** — `Actor`'s field list, `CombatStats`, and whatever exists only to hold them. Deleted, not commented out | — | [ ] |
| `M1.4` | bite: delete a `QuantityDecl` and watch the consumer red | — | [ ] |
| `M1.5` | **a vocabulary check with teeth**: no game noun re-enters the engine tier as an identifier. `hub-vocabulary-gate` already asserts the hub names no ordinal — extend it, or state why it cannot reach the consumer | — | [ ] |
| `M2.1` | `CMD-10`'s owed bite, landed with its seal | — | [ ] |
| `M2.2` | the verb row, `Delta`-only, as a declared table | — | [ ] |
| `M2.3` | one `law.rs` arm replaced by a declared row | — | [ ] |
| `M2.4` | refusal as a committed fact (`CMD-5`) + the cue channel (`CMD-4`) | — | [ ] |

## 7. Registers — append as it happens

### Decisions

| # | sealed | |
|---|---|---|
| **`SCOPE-1`** | 2026-08-06 | **The scope contract is SEALED** — [`2026-08-06-command-hub.md`](../specs/2026-08-06-command-hub.md). The DUMB DRIVER test decides in-or-out; the architecture line is the actor hub's one level up, and **if the two sentences stop being the same sentence, one of the two designs has drifted** |
| **`SCOPE-2`** | 2026-08-06 | **The chooser is a FEATURE, not a column.** `considerations`, `InputKind`, the effectiveness matrix and `attack_class` leave the substrate. The substrate owes the decision layer a **declared seam** and nothing else. `PO-5` is honoured, not overridden: it asked for the layer, and this says which side of the boundary it lives on |
| **`SCOPE-3`** | 2026-08-06 | **The substrate RESOLVES actions; it does not BUILD rulesets.** `CMD-13` and `O-CI-23`..`O-CI-25` are the **ruleset builder's**, not this layer's |
| **`SEAL-ORDER`** | 2026-08-06 | `CMD-10` seals **first** — it is the test by which the rest are classified — and **its owed bite lands WITH the seal**, not after. Then `CMD-1`..`CMD-6`, re-scored under it |

### What the evictions changed — run immediately after sealing, because a goal aimed at a stale remainder is the wrong goal

| row | after `SCOPE-2` / `SCOPE-3` |
|---|---|
| `O-CI-12` per-archetype weighting | **RE-HOMED** to the decision-layer feature. It was never a substrate question |
| `R1-8` `Logistic` needs `exp` (`D-8` forbids it); the compensation factor self-refutes §2.2 | **RE-HOMED.** Both are properties of the chooser's *aggregation*. Note the feature inherits `D-8` — a float-free hashed substrate does not become float-friendly by moving one layer out |
| `R1-6` `effectiveness` is a MAP and `canon.rs` has no map primitive · `R1-7` sparse-with-a-default gives one behaviour two digests | **RE-HOMED** with the effectiveness matrix — **and they travel WITH it.** `R1-7` is `D-PROGRESSION-EMPTY-PIN` returning by the front door, and eviction does not fix it, it relocates it |
| `O-CI-16` six types named and never defined | **SHRINKS to five.** `InputKind` leaves with the chooser (it is `ConsiderationRow`'s input field). `ChanceSpec`, arity's home, a pair's `subject`, the two-role `EffectRow` and `RefKindMask` **all stay undefined** |
| `O-CI-7` one table or two | **NARROWED, not closed.** `A-7` counted four of six columns inert for `/sleep`; two of those four were `considerations` and `attack_class`, now gone. Two remain |
| `O-CI-10`/`O-CI-11` pair state | **STAYS.** A bribe's legality and an opposed check's magnitude are what-happened questions, not should-it questions. The dumb driver still needs them |
| `O-CI-19`/`O-CI-20` ordinal budget | **RELIEVED, not resolved.** Fewer columns; `RefKindMask` is still unpriced and still outside the six ordinal spaces (`AF-8`) |
| `CMD-9` spend ≠ weight | **CONFIRMED by the eviction.** It separated two meanings of one word; they now live in two different layers, which is the strongest possible form of that separation |

### Parked
| # | why | wakes on |
|---|---|---|
| `CMD-13` | needs two bundles to have a subject | the second bundle in a ruleset |
| `CMD-11`/`CMD-12` | a `Delta`-only verb on the actor itself takes no offered target | the first verb with a target role |

### Debt
| # | |
|---|---|
| `D-VOCAB-BINDING-TABLE-DRIVEN` | `CMD-8`, deferred to BUILD — **this run is that BUILD.** Its trigger is mechanical and already stated: the fifth tool in any `contracts/agent/vocabularies/*.json` makes `contains()` and `validate()` disagree |
| `D-REPLAY-PIN-REFUSAL-UNDEFINED` · `D-RNG-COORDS-SNAPSHOT-ONLY` · `D-NO-INPUT-LOG` | escalated 2026-08-06, each with a `PROSE_ONLY` trigger |
| **the `FATAL-1` fix and `D-14`** | Stated rather than discovered later: `0c7577600` fixed the `CombatEvent` ↔ `DomainEvent` drift, and `CombatEvent` is combat vocabulary that `D-14` slates for **rewrite**. What survives the rewrite is the **mechanism** — the contract `$defs`, and a mirror test on each side checking against it rather than against the other language — and that is the part worth having, since it is what stops the *next* enum drifting. What does not survive is the variant list. The fix was still right: it closed a live defect (`renderEvent` returning `undefined` for facts the server emits) and removed a comment that falsely claimed test coverage. **`M1.3` should delete the variants and keep the mirror.** |

### Drift
**A run that ends with an empty drift log is dishonest.**

| # | what nearly went wrong |
|---|---|
| `BDR-1` | I opened this file about to write *"the first consumer is the command substrate"*, which is what the previous turn's summary implied. Measuring first showed the ordering is the other way and **derivable**: an `EffectRow` targets a quantity ordinal, so while the actor's numbers are struct fields the substrate cannot be declarative. A plan whose first line is wrong about its own order is worse than no plan. |
| `BDR-3` | **I wrote `M1` as a MIGRATION of `commit-service::Actor`'s nouns into quantities, and the PO corrected it mid-draft**: that struct is scaffolding built to prove the kernel and SDK work, and it is to be deleted. `D-11` and `D-14` both say so and I had read both in this same session. The correction matters because a port is the *comfortable* answer — it keeps every test green, it looks like progress, and it carries the old vocabulary into a new container, which is `D-2`'s failure exactly. **`quantity[0] = "hp"` would have satisfied `M1` as I first wrote it.** The slice board now defaults every legacy field to DELETE and forbids deriving a quantity from a struct field name. |
| `BDR-2` | `FATAL-2`'s door count was written when the actor round declared *"No code this round"*, and `actor-hub` has shipped since. I nearly carried the old *"seven of eight are design only"* forward unchanged. Re-measured: it improved by **exactly one door**, and that one is `Delta`. Carrying it forward would have been the fourth stale-register claim this week. |
