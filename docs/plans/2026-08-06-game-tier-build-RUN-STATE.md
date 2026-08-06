# RUN-STATE — game tier: the actor hub's first consumer, then the command substrate

**Opened:** 2026-08-06 · **Base:** `6c075b5b8` · **Status:** CLARIFY, awaiting PO seal
**Predecessors:** [actor round](2026-08-02-actor-substrate-RUN-STATE.md) ·
[command round](2026-08-02-command-interaction-RUN-STATE.md)

> **Re-read this file after any compaction, before `git log`.** Context is lossy; a file is not.
> Nothing here is sealed by its author. Sealing is the PO's, and the seal list is §4.

---

## 0. DEFINITION OF DONE — three axes and an independent verdict

> **The goal is to CLEAR the command substrate**, not to reach `M1`. `M1` is a step inside it.
>
> **Why it is written as pasted evidence:** the `/goal` evaluator **reads the transcript only — it
> cannot run a command or open a file.** It is therefore satisfied by the agent *claiming* a check
> passed. `/goal` enforces persistence, not honesty. Every clause below forces the proof INTO the
> transcript, because a clause that does not is a clause the author grades themselves.

### Axis 1 — CODE (static: does it hold without running?)

| | |
|---|---|
| `A1.1` | `cargo test -p actor-hub -p commit-service -p world-service` green, run fresh, **counts pasted** |
| `A1.2` | the game-server TypeScript suite green, **pasted** |
| `A1.3` | a full pre-commit gate run green, **tail pasted** |
| `A1.4` | greps pasted: `commit-service::domain::Actor` carries **no** `hp` / `max_hp` / `av` / `stats`; `actor_hub::` **is** used by commit-service; **no `match` on a verb name** survives in command core |
| `A1.5` | **the acceptance test exists and runs**: declaring a verb is rows only, and a test asserts **zero files in command core** changed — the actor hub's own test, one level up |
| `A1.6` | **NON-VACUITY, per check**: break it, paste the **RED**, restore, paste the **GREEN**. A check with no pasted red **is not a check** |

### Axis 2 — RUN (does it actually execute?)

| | |
|---|---|
| `A2.1` | a **live smoke on a real stack**: a command submitted → a committed fact on the log → projected to the wire. **Paste the actual ids and payload**, not a description of them |
| `A2.2` | the **refusal path fires on a real refusal** and commits a fact carrying its reason ordinal — pasted. A substrate that only proves its happy path has proved half of `CMD-5` |
| `A2.3` | the **cue channel carries the outcome** and the consumer renders it — pasted |
| `A2.4` | if the stack genuinely cannot boot, say `live infra unavailable: <reason>` explicitly — **and then this goal is NOT met.** The token is for honesty, not for credit |

### Axis 3 — DATA MEASURE (numbers off a real run, not off the design)

| | |
|---|---|
| `A3.1` | **determinism**: the same input replayed twice, **both digests pasted and byte-identical** |
| `A3.2` | the digest **MOVES** when the ruleset changes and **does NOT** move when only provenance changes — **both pasted.** One without the other proves nothing |
| `A3.3` | the fold produces a value **through a populated quantity table** — table size and resolved value pasted |
| `A3.4` | counts pasted: quantities declared · verbs declared · **which doors the verb actually used** (expected: `Delta` only — if more, the closure rule was broken and that must be argued, not assumed) |

### The independent verifier

| | |
|---|---|
| `V.1` | a **cold-start reviewer that did not write the code**, given the diff and told to **REFUTE** it, with its verdict pasted **in full — including what it could NOT break.** An absent finding is evidence and is part of the result |
| `V.2` | a **mechanical oracle**: at least one result computed by a **DIFFERENT method** and shown to agree, pasted. Two implementations of one method is not an oracle |

### What does NOT satisfy this goal

- **Renaming a legacy field into a quantity of the same name.** `quantity[0] = "hp"` passes every
  structural check and changes nothing — it is `D-2`'s failure surviving a refactor that looks like
  progress.
- **Claiming a check passed without pasting its output.**
- **A mock standing in for the live path** on Axis 2.
- **The author reviewing themselves in a different hat** on `V.1`.
- **A check that cannot fail**, however green.

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
   round calls this *"the round's real unknown"* and §3 prices it: one door of seven.
   
   > 🔴 **The question is NOT "should the substrate build doors" — PO, 2026-08-06.**
   > **A door belongs to the FEATURE that owns it.** `Delta`'s door was built by the actor hub,
   > which is feature #1; `StatusPropose`'s belongs to a **status feature**, which does not exist.
   > The substrate does not open a door — it *gains a primitive* when a feature opens one.
   >
   > The phrasing this replaces was *"build doors, or narrow the primitive set"*, which reads as
   > substrate work and is the same boundary violation `SCOPE-2` already refused once: designing
   > the chooser inside the substrate because the substrate is the thing being written. **The
   > author proposed it a second time, in a different costume, and the PO caught it again.**
   
   So the real question is narrower and it is the substrate's: **what does a primitive's row look
   like, such that a feature can open its door without the substrate learning what the door
   means?** That is answerable now. Which doors open, and when, is the features' — and `M2.3`
   therefore waits on feature #3, not on more substrate.
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

| `M1.0` | **inventory what the legacy combat domain actually holds, and mark each: DELETE · re-declare · genuinely load-bearing.** The default is DELETE; anything claimed load-bearing needs a reason a reader can check | §6a below — 12 fields, each with a measured call-site count and a verdict | [x] |
| `M1.1` | declare the quantities the DESIGN needs — **derived from the design, never read off the old field list.** A quantity named because a struct field was named is the port this milestone refuses | `crates/ruleset-loader/artifacts/presets/proving-ground.toml` declares `vitality` · `swiftness` · `breath`, bound to `vital` · `initiative` · `action_budget`. **None is the name of the field it replaced**, deliberately: a rename would have satisfied every check, and different names make a surviving name-coincidence impossible | [x] |
| `M1.2` | `commit-service` depends on `actor-hub`; the domain resolves an actor through the hub's fold | `services/commit-service/Cargo.toml:40` + 12 `actor_hub::` sites. `A3.3` pasted: table size 3, stored fold 100, fold with a `+25` contribution 125 | [x] |
| `M1.3` | the legacy shape **deleted** — `Actor`'s field list, `CombatStats`, and whatever exists only to hold them. Deleted, not commented out | `grep -nE "^\s+(pub )?(hp\|max_hp\|av\|stats\|snapshot\|turn_slots)\s*:" domain/actor.rs` → **exit 1, no match**. `Actor` is now `{ hub, defending, stance, fled, side, status, knocked_out }` | [x] |
| `M1.4` | bite: delete a `QuantityDecl` and watch the consumer red | Bitten on **CONTENT**, which is stronger: the `action_budget` pool commented out of the preset → `RoleUnbound { role: "action_budget" }` at [`services/commit-service/src/domain/binding.rs:277`](../../services/commit-service/src/domain/binding.rs#L277), three suites red. Restored → 7/7 green | [x] |
| `M1.5` | **a vocabulary check with teeth**: no game noun re-enters the engine tier as an identifier. `hub-vocabulary-gate` already asserts the hub names no ordinal — extend it, or state why it cannot reach the consumer | **A NEW gate**, not an extension — different tree, different subject, opposite direction (see below). `scripts/engine-vocabulary-gate.py`, 89 files across 6 trees, self-test 13 cases, **6/6 harness mutations red**, and bitten on the real repo: a planted `name == "vitality"` in `law.rs` → 1 finding; removed → OK | [x] |
| `M2.1` | `CMD-10`'s owed bite, landed with its seal | `FORBIDDEN_VERB_KEYS` — three authority-bearing keys refused **by name, with the reason**, on the permissive parse before deserialization. Pasted: all three refusals name the verb, the key and why. `deny_unknown_fields` would have said *"unknown field"*, which is true and useless | [x] |
| `M2.2` | the verb row, `Delta`-only, as a declared table | `ruleset-core/src/verb/` — hashed, schema **6 → 7**, ordered by DECLARATION (`CMD-1`: an ordinal is the verb's identity). `EffectRow` has **no `kind` field**: one door is open, so there is nothing to discriminate, and the exhaustive destructure in `data_measure.rs` stops compiling when a second opens | [x] |
| `M2.3` | one `law.rs` arm replaced by a declared row | ⚠️ **NOT discharged, and the measurement is why** — see §6c. **No shipped arm is `Delta`-only.** What landed instead: the substrate has ONE arm for every verb that will ever exist, and the first declared verb is a new one | [~] |
| `M2.4` | refusal as a committed fact (`CMD-5`) + the cue channel (`CMD-4`) | Live, on real Postgres: `channel_event_id=7 {"actor":"1","reason":"requirement_unmet","type":"refused","verb":0}` · the cue reaches the client payload, parsed out of `TurnOutcome`'s narration | [x] |
| `A1.5` | **the acceptance test** — declaring a verb touches ZERO files in command core | `adding_a_verb_touches_zero_files.rs`, 7 tests. A verb declared in a TOML **string inside the test** resolves end to end; its cue reaches the fact; the tool manifest does **not** know it and it resolves anyway | [x] |
| `A2.*` | the live smoke | `scripts/declared-verb-live-smoke.sh` — **GREEN.** 7 rows read back out of Postgres, every one carrying its `ruleset_digest` pin; applied at `channel_event_id=5`, refused at `7`, wire payload pasted | [x] |
| `V.2` | the mechanical oracle | `scripts/declared-verb-oracle.py` — **AGREE.** Python · the preset parsed as TEXT · a running sum over rows read back from the log. Shares no method with the engine's fold-and-write | [x] |

## 6a. `M1.0` — the inventory, measured at `fa15b072f`

Counts are `grep -c '\.<field>\b'` across `services/commit-service/{src,tests}`. **The default
verdict is DELETE**; a row that survives says why in terms a reader can check.

| field | sites | verdict | the reason, checkable |
|---|---|---|---|
| `snapshot: StatSnapshot` | **0** | **DELETE outright** | Written twice, both `StatSnapshot::default()`; **read nowhere, not even in a test.** Its own doc-comment already passed this sentence on itself: *"written at construction and read nowhere outside tests today… if those land without consuming it, it must go."* They did not land. This is `orphan-model-gate`'s finding shape in a struct field. |
| `hp: i64` | 20 | **re-declare as a POOL** | `QTY-A4` (shipped, `resource/mod.rs:13`) already says a resource's `current` *"lives on the actor (`pools[ordinal]`)"*. **That slot has never existed.** `actor_hub::Actor::quantities` is it. |
| `max_hp: i64` | 2 | **DELETE — it is a CEILING, and the ceiling is already declared** | `CeilingBinding` exists and is hashed. A stored `max_hp` beside a declared ceiling is two SSOTs for one number. Both remaining sites are `llm_driver`'s display band. |
| `av: i64` | 9 | **re-declare as a QUANTITY** | A per-actor number that changes every turn and is **not** a stat slot — tempo state. It cannot be derived (the HSR advance subtracts it from everyone), so it must be stored, and the hub's array is where per-actor numbers live. |
| `stats: CombatStats` | 8 | **DELETE the FIELD; derive at use** | It is `CombatStats::archetype_melee(&rules.stats, max_hp)` — a pure function of the pinned ruleset and the ceiling, both available wherever it is read. A stored copy of a derivable value is the freeze the doc claims, implemented as duplication. **The TYPE survives** — see `M1-D3`. |
| `turn_slots: i64` | 6 | **re-declare as a POOL** | `state.rs` already calls it a *resource* (`CombatResource::TurnSlot`), and `ZeroBehaviour::BlockCosts` — *"refuse any action whose cost this pool cannot pay"* — is shipped, unused, and is exactly its semantics. Ceiling `Fixed(1)`. |
| `defending: bool` | 8 | **stays, recorded** | Non-numeric. It is the `StatusPropose` door, and §3 measures that door as **prose, 0 hits**. Porting it into a quantity would invent the door's shape from feature #1's chair. |
| `stance: Option<Stance>` | 2 | **stays, recorded** | Same. Also `TG-A4`, whose owner is `COMB_002`. |
| `fled: bool` | 3 | **stays, recorded** | Same, plus it is the island-handoff trigger (`externals`). |
| `knocked_out: Option<u8>` | 8 | **stays, recorded** | Same door, and it is a round counter, not a pool. |
| `status: AvStatus` | 4 | **stays, recorded** | Same door. |
| `side: Side` | 1 | **stays — genuinely load-bearing** | `COMB_001 Q5`: win/lose is evaluated per side, so an actor with no side can never be counted and the encounter can never end. Structural, not a number. |

⇒ **one outright deletion · four re-declarations · six recorded as the unbuilt `StatusPropose`
door · one structural.** `Actor` ends with **no `hp`, no `max_hp`, no `av`, no `stats`.**

### The three decisions this inventory forced

| # | |
|---|---|
| **`M1-D1`** | **The seam is SHIPPED and `M1` connects it — it does not invent one.** `QTY-A4` places a pool's `current` on *"the actor (`pools[ordinal]`)"* and the actor's array did not exist; the hub built it. So `M1` is not "add quantities to the actor", it is **wire QTY-A4's `current` to `actor_hub::Actor::quantities`.** That is why this milestone is derivable rather than designed. |
| **`M1-D2`** ⚠️ **SUPERSEDED by the build — see `M1-D2b` below.** | **Which ordinal is the vital is declared by CONTENT, through a binding that already ships and costs ZERO new hashed bytes.** `resource/mod.rs:103` states `Q2`'s exit criterion verbatim — *"a reality binds `Vital → qi` and the defeat law is **unchanged**"* — and `Vital` as a role has **exactly one occurrence in the repo: that comment.** It is unbuilt, which per the anti-laziness rule is *buildable*, not blocked. It is built as a **derivation, not a field**: the vital is *the pool whose `CeilingBinding` is `Slot(StatSlot::MaxHp)`*, which is the sentence `CeilingBinding::Slot`'s own doc already writes. Adding a `role:` field to `ResourceDecl` was rejected — `QTY-A10(c)` makes a hashed field permanent, and the module refuses `deps`/`tags` on that exact argument. **Zero, or two or more, is a boot REFUSAL naming the pools** — never a default. |
| **`M1-D2b`** ⚠️ **THE REVERSAL, recorded where the decision is, not only where the build is** | **`M1-D2` was overturned during `M1` and shipped the way it explicitly rejected: `ResourceDecl` gained `role: EngineRole`, schema 5 → 6.** The derive-from-`CeilingBinding` shortcut was dropped because it gives `ceiling` a second, hidden meaning (an author capping a second pool at `MaxHp` silently acquires a second vital) and because the two roles with no matching slot — `Initiative`, `ActionBudget` — have no honest key at all under it. **A cold-start reviewer found `M1-D2` still reading as sealed while the code said otherwise, which is exactly the stale-register defect this run has now recorded five times.** §6b row 1 carries the full argument; this row exists so a reader who re-reads the DECISION gets the right answer, per the run-state's own rule: *never re-litigate a sealed decision from memory; re-read it.* |
| **`M1-D3`** | **`M1` does NOT turn the ten `StatSlot`s into quantities, and that restraint is the decision.** `slots.rs` says the closed slot set is `DF7-A1`, and that doc 31 **`R02`** — *making the slot set ruleset-declared with digest-pinned ordinals* — is **PROPOSED, not applied**, adding: *"applying it here would be scope creep into a decision still open."* Storing the eight numbers as quantities would apply `R02` by the back door, under a milestone that is not about slots. So `CombatStats` survives **as `game-rules`' law-input view**, built where it is read; what dies is the actor's stored copy. **The finding this surfaced is recorded, not acted on:** `game_rules::stats::resolve_block` and `actor_hub::fold` are the same mechanism implemented twice, which is `D-3`'s *"same rot at three levels"* pointing at a fourth. Its trigger is `R02`. |

> ⚠️ **The trap this inventory was written to avoid, stated so it can be checked against the result.**
> Every re-declared row above names a quantity whose **name is authored in CONTENT and appears
> nowhere in engine source** — the engine holds ordinals and resolves the vital through a *binding*,
> not through a literal. That is the discriminator between this and `quantity[0] = "hp"`, which the
> PO named as the thing that would satisfy `M1` while changing nothing. It is not a matter of
> intent: `M1.5`'s gate is what makes it hold, and intent is not a mechanism.

## 6b. `M1` — what it cost, and the four things it forced that were not in the plan

`M1` is **DONE**. What it needed that §6's board did not anticipate is the part
worth recording, because each was a hole the plan could not see from outside.

| # | forced | |
|---|---|---|
| **1** | **`Vital` had to be BUILT — it existed as one prose sentence.** `Q2`'s exit criterion (*"a reality binds `Vital → qi` and the defeat law is unchanged"*) was written in `resource/mod.rs` and `Vital` appeared **nowhere else in the repository**. So `ResourceDecl` gained `role: EngineRole` — a new hashed field, schema **5 → 6**. It earns its permanence by the module's own test: `deps` and `tags` were refused for having **no consumer**, and this one has three engine laws reading it in the commit that adds it. The engine default's ENCODED size is unchanged (it declares no pools); the digest moved only because the schema version leads the stream, which is what that field is for. |
| **2** | **The hub had NO WRITE VERB, and its own doc said so.** `actor.rs` read *"no mutation verb for a quantity beyond attachment… every one of those features is unbuilt."* `M1` is the first one. `Actor::set_quantity` carries a value and refuses a writer that does not own the ordinal — the same shape as `set_existence`, and the door `M2`'s `Delta` walks through. **It made `attach`'s ownership guard observable for the first time**, exactly as that guard's comment predicted; the prediction held on the first try (bite pasted). |
| **3** | **`Actor.stats` was 64 bytes of duplicated ruleset, per combatant.** Every actor's block came from `archetype_melee(&rules.stats, max_hp)`, so the only per-actor difference was `CombatStats::max_hp` — and **no law reads that field**: `resolve_attack`, `action_value` and `evaluate_outcome` never touch it. One archetype per reality now. `Actor` went from ≤192 bytes to ≤160 **despite** gaining a 128-byte quantity array. |
| **4** | **A behaviour genuinely regressed, and it is tracked rather than glossed.** Per-actor stats no longer exist, so a per-actor `speed` cannot be expressed — the one test that used it (to make a hero act first) now sets the initiative pool directly, which is what it was reaching for. The advantage lasts until that actor's first reset instead of forever. `D-PER-ACTOR-STATS-UNEXPRESSIBLE`. |

**`M1.5` is a NEW gate rather than an extension of `hub-vocabulary-gate`, and the
distinction is the point.** That one guards `crates/actor-hub/src` and asks *does
the hub compare an ORDINAL to a literal* — the plugin's ordering vocabulary
leaking INTO the hub. This one guards the consumer and asks *does engine source
contain a quantity NAME* — the author's vocabulary leaking into the engine.
Different tree, different subject, **opposite direction**. Both were structurally
true and unguarded.

**Two ceilings were paid in SPLITS rather than absorbed into an allowlist**, which
is what a ceiling is for: `island/mod.rs`'s read surface → `island/view.rs` (its
row's fourth split in four slices), and the loader's shipped preset →
`ruleset-loader/src/preset.rs` (mechanism ↔ content, the only content file in
that crate). `actor.rs`'s unit tests became integration tests, which is an
improvement rather than a dodge: every item they touch is public surface, so a
unit test could pass against an API a plugin author cannot reach.

## 6c. `M2` — the measurement that changed the milestone, and what landed instead

**`M2.3` said *"one `law.rs` arm replaced by a declared row"*. It is NOT
discharged, and the reason is a measurement rather than an excuse.**

`CMD-3` closes the effect primitive set on *"a primitive exists iff the substrate
already built the door it goes through"*, and §3 measured **one door of seven
open** — `Delta`, a signed write to a declared quantity. Measured again at the
moment of building, against the four shipped arms:

| arm | what it changes | door |
|---|---|---|
| `strike` | a roll, then a vital delta, then a KO status | needs `ChanceSpec`, one of `O-CI-16`'s five undefined types |
| `defend` | a `bool` | `StatusPropose` — **prose, zero implementation** |
| `move` | an `enum` | `StatusPropose` |
| `flee` | a `bool` | `StatusPropose` |
| `EndTurn` | engine-only | never a declared verb, by construction (`IAS-D6`) |

⇒ **Not one of them is a pure `Delta`.** So `M2`'s first verb could not have
replaced an arm without opening a second door — which the closure rule forbids
until the door is built. The rule did its job; the plan's phrasing was written
before the measurement existed.

**What landed instead is the stronger half of what `M2.3` was for.** `law.rs`
has ONE arm for declared verbs, and it will never gain another: it routes to
`domain/substrate.rs`, which resolves every verb that will ever exist without
branching on a name. The four legacy arms are the combat vocabulary `D-14`
already slates for rewrite; they leave when their doors are built, and
`adding_a_verb_touches_zero_files.rs` is what makes the claim checkable now
rather than then.

### Three things `M2` forced that the plan did not anticipate

| # | |
|---|---|
| **1** | **A declared verb may not spend the ACTION BUDGET, and a test found it, not a design.** The engine spends that pool generically on every action (`IAS-D6`); the first authored verb declared the same cost, and it **refused itself with `RequirementUnmet` on its own first submission**. `BindingError::VerbSpendsEngineBudget` now says so at BOOT. The preset gained a role-free pool (`focus`) for verbs to spend — which is also the first demonstration that `EngineRole::None` is the common case. |
| **2** | **`EffectRow` has no `kind` field, and that is a decision.** A one-variant enum would put a discriminant byte in every reality's hashed bytes forever, encoding a choice that does not exist — and `QTY-A10(c)` forbids taking it back out. The kind arrives with the second door, as a schema bump, which is loud and is supposed to be. The count is kept by the COMPILER: an exhaustive destructure in `data_measure.rs` stops compiling when the field appears. |
| **3** | **`VerbTable` is ordered by DECLARATION, not sorted — the opposite call from `ResourceTable`.** A pool's identity is its quantity ordinal, assigned elsewhere, so that table can sort for a canonical encoding. A verb's identity IS its index (`CMD-1`, append-only, never reused) and committed history already names one; sorting would renumber every verb the moment an author added one whose name sorts earlier. |

### And a pre-existing RED, fixed in passing

`cargo build --all-targets` had been failing on this branch since migration
`0018` removed the `region`/`session`/`world_kv` projections as orphans and
deleted their fixtures: `services/world-service/benches/projection_hotpath.rs`
still named all three. **Nothing caught it because a bench is not built by
`cargo test`** — which is worth recording as its own small finding.

## 6d. `V.1` — the cold-start refuter found TEN, and six of them were real bugs

A reviewer that did not write the code, given the diff and told to **REFUTE** it,
working from a scratch crate outside the repo and editing nothing. **Every suite
was green when it started.** That is the whole argument for the clause.

| # | what it broke | fix |
|---|---|---|
| **1** | **A verb naming a quantity with no POOL committed a LIE.** `VerbTable::declare` validates against the QUANTITY table; an actor holds a number only for a declared POOL. So the verb passed every build check, wrote nothing, and committed `Acted { left: 5 }` for a quantity the actor does not have. *A silence would have been bad; a committed lie is worse* | `BindingError::VerbNamesUndeclaredPool` at boot, **plus** the substrate refusing rather than `unwrap_or(0)` — two layers, because a check whose only defence is another check's correctness is one edit from being wrong |
| **2** | **UNLIMITED FREE ACTIONS.** A verb whose `effect` targeted the action-budget pool: the engine deducted 1, the verb added it back. Four submissions, no turn boundary, budget never fell. `IAS-D6` defeated by content, boot-time-green | the refusal now covers **all three positions** |
| **3** | **The original bug still shipped.** The refusal's own docstring cited a `requires` incident while covering only `spend` — and the symptom it quoted (`RequirementUnmet` on the first submission) *cannot come from a spend at all*, which returns `CannotAfford`. **It was aimed at the wrong arm of the bug it was written for.** | same refusal |
| **4** | **Three SILENT paths**, under a header reading *"Every path commits a FACT"*. Out of budget, absent actor, resolved encounter → empty event vector → the spine committed `turn.resolved` with `events: []`, a turn that resolved into nothing. `RefusalReason::ActorAbsent` was **dead code**: the substrate had an arm nothing could reach | `refuse_declared`; `EncounterResolved` added (5 → 6 members, all three sides) |
| **5** | **`EffectRow::amount`'s "the engine clamps against the pool's own declared bounds" was FALSE.** It was `.max(0)` — a hardcoded floor ignoring `ResourceDecl::min`, and **no ceiling at all**. A pool of ceiling 100 driven to **15100** in three submissions | `RealityRules::pool_bounds`, and both the effect and the affordability test now read it |
| **6** | **Content could disable combat.** The verb table is consulted before the manifest and nothing refused a collision, so a preset declaring `strike` silently replaced the engine's attack with a self-targeted delta and dropped the target argument | `Reject::VerbShadowsTool` — refused, never resolved by precedence, because preferring either side makes the other silently lose |
| **7** | **`size_of::<Actor>() <= 160` did not fire on a new field.** 153 used in 160 allocated — **seven bytes of free growth** under a comment claiming otherwise. The hub's own `== 144` next door survived every attack | `== 160` |
| **8** | **The `QTY-A11` round-trip was true and UNTESTED at exactly the two versions this work added.** Every codec test uses `engine_default`, which declares zero pools and zero verbs — so the v6 role byte and every byte of the verb-row codec were never executed. `ROLE_SINCE` 6 → 5 reddened nothing | a round-trip over the shipped preset at every version, and the two length gates. **The mutation now reds** |
| **9** | **The live smoke reported `ok` when it did not run** — the skip's `eprintln!` is swallowed without `--nocapture`, so CI could not tell "smoked against Postgres" from "never touched a database". It also asserted `verb` and `cue` and **not** `delta`/`left`/`quantity`, so finding #1's fabricated `left` would have passed it | `REQUIRE_LIVE=1` (set by the script) turns a missing DSN into a failure; the three numbers are asserted, `left` against the declared bounds |
| **10** | **The oracle's stated check (4) was a TAUTOLOGY** — *"refusals carry no `delta` field"* is true by construction. In the one artifact whose whole premise is method-independence | the stream is walked and the vital is compared either side of each refusal |

**And the finding with no bug attached, which is the sharpest one.** The
acceptance test's *title* claims *"adding a verb touches zero files in command
core"*; what it asserted was *"one verb resolves end to end"*. Adding
`match verb { 0 => …, _ => … }` tomorrow would have left all seven green — and
`substrate.rs`'s header said *"if either appears, the acceptance test is false"*,
which **nothing checked.** `the_substrate_never_branches_on_a_verb` reads the
source at runtime and is bitten: a planted `verb == 0` reds it.

### What it tried and could NOT break — an absent finding is evidence

| attack | verdict |
|---|---|
| `engine-vocabulary-gate` | **SURVIVED the rule**, and its `[a-z][a-z0-9_]*` matches `QuantityName`'s charset exactly, so no legal quantity name evades it. Evasions found were contrived (`concat!`, `\u{79}`, byte arrays). **But it recorded two gaps in the gate's SCOPE, and both are now closed — see §6e.** |
| `QTY-A11` itself | **SURVIVED.** Holds at every version 1..=7, for `engine_default`, for the preset, and for a two-verb ruleset. Its COVERAGE was the defect, not the property |
| `actor_hub::Actor`'s `== 144` | **SURVIVED.** Exact; any field addition moves it |
| `FORBIDDEN_VERB_KEYS` | **SURVIVED**, and the refutation it tried is worth recording: *"`deny_unknown_fields` already rejects these, so the by-name refusal is decoration."* Measured false — that path never emits the VERB's name, which is what the test asserts. It also noted the `len() > 120` assertion alone would not bite (272 > 120); the name assertion is the load-bearing one |

## 6e. The gate's own scope was the defect it exists to refuse

`V.1` did not break `engine-vocabulary-gate`'s RULE. It broke its **scope**, in
two ways, and both are the shape the gate's own header condemns three paragraphs
above the code that had it.

**The scope was a hand-written list of directories.** The header says an
enumerated FILE list is *default-uncovered* — *"it says nothing about the file
created tomorrow"*. A directory list has the same defect one tier up: nothing
checked it against the dependency graph, so a crate created tomorrow that depends
on `ruleset-core` would be silently unguarded while the gate reported OK.

**It is DERIVED now** — every `src` tree whose `Cargo.toml` transitively reaches
`ruleset-core` or `actor-hub` through path dependencies. Those are exactly the
trees that can hold a quantity ordinal, so they are exactly the trees that could
name one instead; adding such a dependency extends the gate **in the same edit
that creates the risk.**

> **And the derivation caught the list being WRONG, not merely unchecked.** The
> hand-written version named `crates/sim-core/src`. `sim-core` does not depend on
> `ruleset-core` — `ruleset-core` depends on IT — so it can never hold a quantity
> ordinal. Six listed trees became **five derived** ones. A list I wrote by eye,
> defended in a header about lists written by eye.

**And the scope was `.rs` only** — while *the wire is exactly where `M2` worked
hardest to carry ordinals instead of names*. `contracts/game-wire/*.json` and the
TypeScript consumer that mirrors it were unguarded. Both are scanned now: 98
files became **108**.

**Bitten three ways, each pasted:** a quantity name planted in
`turnOutcome.ts` (a file the gate could not previously see) → 1 finding; a probe
crate depending on `ruleset-core` → 1 finding, where the hand-written list would
have been silent; and the harness, now **10/10 mutations red**, including *the
scope reverts to a hand-written list* and *the transitive closure stops*.

**Three of its own claims were also untested, and are now executed rather than
described:** `main()`'s empty-vocabulary refusal (`E1` stopped at `scan_source`
and *said in a comment* that main refuses — a claim about a branch nothing ran),
and both arms of the file walk, including the `--staged` path that pre-commit
actually uses.

## 6f. The features are NOT circularly dependent — and one artifact says why

The question, from the PO: *the missing pieces hook back into the actor hub, the
resource pool and an unfinished ownership design; the features depend on each
other; how do we untangle?*

**Tested rather than accepted, and it is not a cycle.** Tracing each missing
item to what it actually needs:

| tier | needs | items |
|---|---|---|
| **0** | **nobody** | the ordinal-space register · arity · a second relation (`at_most`) · the roll's verb term · `SEAM-1` |
| **1** | one external FIX, not a feature | roles + offer ← the subject source: `ChannelRoom.ts:375` returns `LW_CHANNEL_DEFAULT_ACTOR ?? '1'` for **any authenticated user absent from an env map**, so two users are bound to one actor. Re-measured at HEAD, not trusted from the register. It is a **tenancy defect** by `CLAUDE.md`'s own checklist before it is an offer problem |
| **2** | a feature to exist | status relations · a price that is not a quantity · `O-CI-4`'s reachable subject · six effect doors |

**It looks like a cycle because the coupling gets stated in NOUNS** — *the
substrate needs statuses; statuses need the substrate.* Stated in SHAPE it is
not:

> **A feature and the substrate are coupled only through an ORDINAL SPACE.** The
> substrate declares the space and the row shape; the feature declares what an
> ordinal MEANS; content assigns the name. **Neither needs the other to exist
> first.**

**This project has already done it twice and never stated it as a rule.**
`actor-hub` shipped with zero consumers and its first feature arrived two months
later; `M2`'s substrate resolves verbs whose meaning it never learns, and the
first verb arrived as a row in a TOML file. Both are held by shipped gates rather
than by intent — `hub-vocabulary-gate` and `engine-vocabulary-gate`.

⇒ **The rule is only MECHANICAL if the spaces are counted, and they were not.**
One design document says *"a sixth ordinal space"* and then corrects itself to
*"the honest count is TEN"* — in the same file, without listing either set. So
[`docs/specs/2026-08-06-ordinal-spaces.md`](../specs/2026-08-06-ordinal-spaces.md)
counts them, and it paid for itself on the first run:

| # | |
|---|---|
| **1** | **The word names two different things**, which is why six became ten: an AUTHOR-EXTENSIBLE space (content adds a member, one line of TOML) and a CLOSED ENGINE SET (a release, a codec arm, a mirror on every consumer). `§27.4`'s objection was about the first kind only |
| **2** | **`MAX_PLUGINS` derives its width from the wrong thing.** Two of the three aliases of the quantity space are *identity* — a pool IS a quantity, a progression kind IS a quantity. This one is aliased *"so the two ceilings move together"*, which is the exact shape `MAX_DECLARED_VERBS`' own doc refuses as *"a coincidence pretending to be an invariant"*. **The number is right and the derivation is wrong**: 32 is forced by `PluginSet` being a `u32`, and the correct pattern — deriving a width from the type's own integer — already ships eight files away on `FoldLayer::ORDINAL_SPACE`. Widening the quantity table silently widens the plugin ceiling today, and nothing would notice |
| **3** | **A THIRD kind exists that neither half describes** — plugin ordinals and fold layers are computed at BOOT and are **not in the hashed ruleset**. It cannot vary today (two constants, one plugin), so there is no live defect; the hazard is that it cannot vary *yet*. The day a reality's plugin set is content, two realities could share a digest and derive different plugin ordinals — `QTY-A14` arriving in a space the digest does not cover |
| **4** | **`cue` is unpriced.** `M2` shipped `cue: u16` with no width constant, no repin log and no argument, in a tier where every neighbour carries all three. `AF-8` had already found `RefKindMask` *"outside the six ordinal spaces"* — outside a set nobody had enumerated |

## 6g. Where the user→actor binding belongs — the answer, and the measurement behind it

**Asked by the PO**, who did not take it and asked which is optimal and most
standard, and why. It blocks the subject-source fix → roles + offer → any verb
that touches another actor. It blocks combat.

**Answer: `migrations/meta/012_player_character_index`, with the pc/npc vocabulary
removed. Not close.** Four reasons, heaviest first.

| | |
|---|---|
| **1 · The binding is inherently CROSS-REALITY; per-reality data is not** | A human exists across realities. In a per-reality DB, *"which actors do I drive?"* — the first question a character-select screen asks — becomes a fan-out over N databases |
| **2 · The meta DB is not infra-only, measured** | It already carries per-user rows on purpose, with the machinery this needs: `009_pii_registry` · `011_user_consent_ledger` · `018_user_cost_ledger` · `026_book_reality_subscription` · and `014_meta_read_audit` plus the `meta-sensitive-read-paths.yml` registry. It is the **cross-reality control plane** |
| **3 · `012`'s split is ALREADY the standard shape** | Its own header: `pc_id` is a *"per-reality PC identifier (**FK lives in per-reality DB**)"*. A control-plane pointer into a data-plane identity — exactly what `reality_ruleset_binding` is to a content-addressed artifact. `ruleset_boot.rs` states the same law: *"the meta DB holds the binding; the per-reality DB holds the channel log. Collapsing them would exercise a topology nothing runs"* |
| **4 · GDPR erasure** | This repo shipped a user-erasure orchestrator. Erasing a user must find EVERY binding; a fan-out over N reality DBs is the shape that leaves rows behind |

> **The general rule, since the PO asked for the standard:** the binding is
> **CONTROL, not SIMULATION.** Control questions are cross-instance by nature, so
> control data in a data-plane database is the anti-pattern. Meta = control
> plane (which reality, which ruleset, which human drives which actor);
> per-reality = data plane (the log, the state).

**And `012` already names the exact defect we have.** Its header:

> *"Risk: identity-manipulation attack (alter rows → impersonation, cross-user
> data leak). Defense: … sensitive-read audit on non-owner queries"*, with
> non-owner SELECTs registered as `player_index_cross_user`.

`actorForUser` returning `LW_CHANNEL_DEFAULT_ACTOR ?? '1'` for any unmapped
authenticated user **is** that identity-manipulation risk — and **the defence
written for it is sitting unused.** Building the binding anywhere else abandons a
defence that already exists and would have to be rebuilt.

**What is dead in `012`** is what the handoff already identified and nothing more:
`pc_name`, `status='npc_converted'`, `status='deceased'` — the two-kind vocabulary
and mortality in a lookup table. Keep the binding, drop those three.

> ⚠️ **The parking's own premise has EXPIRED.** It was parked because *"No
> producer, so nothing depends on it and deciding now would be guessing."* There
> is a producer now: the offer stage needs a subject it can trust. And
> `contracts/meta/player_index_parked_test.go` will go RED when a writer lands —
> **that is its trigger firing, not a regression.** It is the one deferral in
> this project whose mechanism is designed to announce its own discharge.

### And a register line that is WRONG — measured while answering this

The handoff says *"No producer, so nothing depends on it and deciding now would
be guessing."* **The first half is true; the second is false.**

```
services/meta-worker/pkg/user_erased_writer/pglive/pglive.go:58
   SELECT DISTINCT reality_id FROM player_character_index WHERE user_ref_id = $1
```

**The GDPR user-erasure path READS this table** — to find which realities a user
has an actor in — and a second leg scrubs `pc_name` through `MetaWrite`. Nothing
WRITES it, so it is empty and both legs run over nothing. That is currently
correct, because nothing records a user→actor binding anywhere; but it means
something stronger than "dormant":

> **The erasure path was built FOR this table and is waiting for it.** Landing
> the binding does not add work to GDPR — it **completes a path that already
> ships.** Same shape as `M1`: `QTY-A4` said a pool's `current` lives on *"the
> actor (`pools[ordinal]`)"* and that slot had never existed; the hub built it
> and `M1` connected it.

⇒ This strengthens the argument above rather than complicating it: the erasure
lookup already queries **this table, in the meta DB.** Putting the binding
anywhere else orphans a shipped GDPR path and requires rewriting it.

**One consequence worth naming:** removing `pc_name` does not only delete dead
vocabulary — it removes the **last PII in the table.** What remains is
`(uuid, uuid, uuid)`, and the meta scrub leg can retire with it.

### What is DEAD versus what INVERTED

The PO asked whether this is just old pc/npc confusion the new design no longer
needs. **Two thirds of it, yes — same call and same reason as `hp`.**
`npc_converted` is a transition between two kinds that no longer exist;
`deceased` is mortality in a lookup table, the same second-SSOT shape `0017`
removed.

**The third part inverts.** The new framing is *"a player is not a kind of actor
— it is a CONTROL INTERFACE: a human with a GUI driving an actor."* If "player"
is no longer a KIND, then `(user, reality, actor)` is the only thing that makes a
player a player. **Removing the PC/NPC distinction does not delete the binding;
it makes the binding the entire concept.** The dead half is the kind-vocabulary;
the live half became more load-bearing, not less.

**Still the PO's to take.** This section is the argument, not the decision.

## 7. Registers — append as it happens

### Decisions

| # | sealed | |
|---|---|---|
| **`SCOPE-1`** | 2026-08-06 | **The scope contract is SEALED** — [`2026-08-06-command-hub.md`](../specs/2026-08-06-command-hub.md). The DUMB DRIVER test decides in-or-out; the architecture line is the actor hub's one level up, and **if the two sentences stop being the same sentence, one of the two designs has drifted** |
| **`SCOPE-2`** | 2026-08-06 | **The chooser is a FEATURE, not a column.** `considerations`, `InputKind`, the effectiveness matrix and `attack_class` leave the substrate. The substrate owes the decision layer a **declared seam** and nothing else. `PO-5` is honoured, not overridden: it asked for the layer, and this says which side of the boundary it lives on |
| **`SCOPE-3`** | 2026-08-06 | **The substrate RESOLVES actions; it does not BUILD rulesets.** `CMD-13` and `O-CI-23`..`O-CI-25` are the **ruleset builder's**, not this layer's |
| **`SEALED-CMD`** | 2026-08-06 | 🔴 **PO: `CMD-10` is SEALED, and `CMD-1`..`CMD-6` with it.** The blocking condition was discharged three times over (prior art: 08-02 §3's six systems · the decision-layer round · the folded 08-05 round), and **`CMD-10`'s owed bite landed in `M2`** — `FORBIDDEN_VERB_KEYS` refuses three authority-bearing keys by name, with their reasons, and all three refusals are pasted. §4.1's forced order is discharged in the order it forced. |
| **`AUTHOR-1`** | 2026-08-06 | 🔴 **THE MANIFEST AUTHOR IS NOT A PROGRAMMER — PO, and this is a CONSTRAINT, not a preference.** *"The author is not a developer, and they usually use an LLM to produce the manifest, so if it gets too complex they cannot do it."* **Complexity in the AUTHORED SURFACE is a hard cost, priced against whatever it buys.** This is why `SEAM-1` resolves the way it does: striking `submitter_class` is not merely *"`CMD-10` came later"* — it **removes a field the author would have had to get right**, and a field whose wrong value is an authorisation defect. Consequences, stated so they are not re-derived: an extra `spend` row, a relation grammar, and a row that must name its own ordinal space each carry this cost and must earn it; `D-29` (*a declared THRESHOLD, never a predicate grammar*) is this axiom arriving from the other side; and where a space can be IMPLIED by the field's type it should be, because that is one thing fewer to write. |
| **`SEAM-1`** | 2026-08-06 | 🔴 **RESOLVED by the PO — strike `submitter_class` from the sealed contract's §4.** `CMD-10` is right and the build already followed it. See `AUTHOR-1` for the reason that decided it, which is stronger than seniority between two decisions. |
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
| `BDR-12` | **I shipped an ordinal with no width, in the week I spent auditing widths.** `M2`'s `cue: u16` has no named constant, no repin log and no argument, while `MAX_DECLARED_VERBS` — twelve lines away, written the same hour — carries all three and an essay about why it is not an alias. Nothing caught it: no gate counts ordinal spaces, which is precisely what `AF-8` reported about `RefKindMask` and what nobody acted on. **The register exists because the register did not exist**, and its first run found my own omission alongside the two it was looking for. |
| `BDR-11` | **I proposed opening a second effect door as the substrate's next task, and the PO refused it as a boundary violation.** `Delta`'s door was built by the ACTOR HUB — feature #1 — not by the substrate; `StatusPropose`'s belongs to a status feature that does not exist. The substrate never opens a door, it gains a primitive when a feature opens one. **This is `SCOPE-2` a second time in a different costume**: the chooser got designed inside the substrate because the substrate was the thing being written, and the same gravity pulled the doors in. §5's own wording carried it (*"build doors, or narrow the primitive set"*), so the plan had been saying it for two days and I read past it. ⇒ `M2.3` waits on **feature #3**, not on more substrate work. |
| `BDR-9` | **Six of the ten findings were bugs I had already written a CORRECT SENTENCE about.** `EffectRow::amount` said *"the engine clamps against the pool's own declared bounds"* while the code did `.max(0)`. `substrate.rs` said *"every path commits a FACT"* above three `return Vec::new()`. `actor.rs` said *"adding a field moves this number"* under a `<=`. `binding.rs`'s refusal cited an incident it did not cover. **The prose was not wrong — it was written first and never checked against the code beneath it**, which is the same defect as a stale register, one level down. A doc comment is a claim, and this run has now recorded that lesson at three scales: a register, a heading, and a doc comment. |
| `BDR-10` | **I nearly did not run `V.1` at all.** Every suite was green, both milestones were committed, the goal's other clauses were pasted, and the reviewer felt like ceremony on top of work already finished. It found six real bugs — including one that let content grant **unlimited free actions** — in code that had passed 2254 tests, 21 gate self-tests, a live smoke and an independent oracle. **Everything else I built measures whether the code does what I designed. Only this measured whether the design was right.** |
| `BDR-7` | **I wrote `M2.3` into the board as *"replace a `law.rs` arm"* and only measured whether that was possible when I came to do it.** It was not: no shipped arm is a pure `Delta`, and §3 had already priced the door count at one of seven — I had the number and did not apply it to the sentence beside it. The plan was internally inconsistent for two days. What saved it was refusing to open a second door to make a checkbox tick, which is the closure rule working; but the near-miss was *"just make `defend` a declared verb"*, which would have shipped `StatusPropose` as a `Delta` in disguise. |
| `BDR-8` | **The first authored verb refused itself, and I nearly patched the symptom.** `gather` declared a spend of the same pool the engine spends generically, so its own requirement failed on its first submission. The reachable-in-one-edit fix was to move the engine's generic spend after the verb's — which would have let a declared verb take an action for free. The right fix was a BOOT refusal saying the author may not re-declare the engine's turn cost, and it took longer. **A test failure whose quickest fix changes an invariant is the shape to slow down on.** |
| `BDR-4` | **I nearly shipped `M1` with the actor's numbers named `hp`, `av` and `turn_slots` in content** — the names were sitting in the field list I had just inventoried, and copying them would have read as faithful. The PO's correction (`BDR-3`) was about the *engine*, and I first satisfied it by moving the same words one file over. What stopped it was writing `M1.5`'s gate BEFORE choosing the names: a gate that greps for the declared vocabulary in engine source is trivially green when the vocabulary IS the engine's own words. **Different names are not decoration — they are what makes a surviving name-coincidence detectable.** |
| `BDR-5` | I wrote *"`scripts/engine-vocabulary-gate.py` is what keeps it one"* into `binding.rs`'s module doc **while the file did not exist.** It was true within the hour, which is exactly why it is the dangerous kind of claim: a citation to a mechanism that is *about to* exist is indistinguishable, to every future reader, from one that never will. This project has recorded four stale-register catches in a week and this would have been the fifth, authored deliberately. |
| `BDR-6` | **The bite harness caught a hole in my own gate's self-test.** Every one of my twelve cases reached `_exempt` through the comment-block branch; nothing reached the same-line branch, so `if PRAGMA in raw[line_no - 1]` could have been deleted with the suite green. I had written the header sentence *"a gate with no cry-wolf case is half-tested"* and then shipped a half-tested branch under it. **The mechanism found what the intent did not** — which is the standard's own thesis, demonstrated on its author. |
| `BDR-2` | `FATAL-2`'s door count was written when the actor round declared *"No code this round"*, and `actor-hub` has shipped since. I nearly carried the old *"seven of eight are design only"* forward unchanged. Re-measured: it improved by **exactly one door**, and that one is `Delta`. Carrying it forward would have been the fourth stale-register claim this week. |
